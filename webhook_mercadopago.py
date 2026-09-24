# webhook_mercadopago.py
import os
import logging
from datetime import datetime, timedelta, timezone
from database import supabase

try:
    import mercadopago
except ImportError:
    mercadopago = None

logger = logging.getLogger(__name__)

MERCADOPAGO_ACCESS_TOKEN = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN) if mercadopago else None

# Bot será injetado pelo main.py para poder notificar o usuário
_telegram_bot = None


def set_telegram_bot(bot):
    global _telegram_bot
    _telegram_bot = bot


def _calcular_dias_plano(tipo_plano: str) -> int:
    p = str(tipo_plano).lower()
    if "degustacao" in p or "free" in p:
        return 7
    if "trimestral" in p:
        return 90
    if "semestral" in p:
        return 180


async def processar_pagamento_aprovado(payment_id: str) -> bool:
    """Consulta o pagamento no MP e ativa a assinatura se aprovado."""
    if not sdk:
        logger.error("SDK do Mercado Pago não disponível.")
        return False

    try:
        result = sdk.payment().get(payment_id)
        if result.get("status") != 200:
            logger.error(f"Erro ao consultar pagamento {payment_id}: {result}")
            return False

        payment = result.get("response", {})
        status = payment.get("status")
        mp_payment_id = str(payment.get("id"))

        logger.info(f"🔔 Pagamento {mp_payment_id} - status: {status}")

        if status != "approved":
            logger.info(f"Pagamento {mp_payment_id} não aprovado (status={status}). Ignorando.")
            return False

        # 1. Busca registro em pagamentos_pix
        res = supabase.table("pagamentos_pix").select("*").eq("pix_id", mp_payment_id).execute()
        if not res.data:
            logger.warning(f"Pagamento {mp_payment_id} não encontrado em pagamentos_pix.")
            return False

        registro = res.data[0]
        chat_id = registro.get("chat_id")
        tipo_plano = registro.get("tipo_plano", "pro")

        # Já processado?
        if registro.get("status") == "approved":
            logger.info(f"Pagamento {mp_payment_id} já processado anteriormente.")
            return True

        # 2. Atualiza pagamentos_pix
        try:
            supabase.table("pagamentos_pix").update({
                "status": "approved",
            }).eq("pix_id", mp_payment_id).execute()
        except Exception as e:
            logger.warning(f"Erro ao atualizar pagamentos_pix: {e}")

                # 3. Calcula validade (SOMA se plano atual ainda ativo)
        dias = _calcular_dias_plano(tipo_plano)
        agora = datetime.now(timezone.utc)

        base = agora
        is_degustacao = "degustacao" in tipo_plano.lower()

        if not is_degustacao:
            try:
                res_venc = (
                    supabase.table("assinaturas")
                    .select("data_vencimento, status, tipo_plano")
                    .eq("chat_id", str(chat_id))
                    .order("created_at", desc=True)
                    .execute()
                )
                if res_venc.data:
                    info = res_venc.data[0]
                    status_atual = str(info.get("status", "")).lower()
                    tipo_atual = str(info.get("tipo_plano", "")).lower()
                    venc_str = info.get("data_vencimento")

                    if (
                        status_atual in ("ativo", "active", "ativa")
                        and tipo_atual != "degustacao"
                        and venc_str
                    ):
                        venc_dt = datetime.fromisoformat(
                            str(venc_str).replace("Z", "+00:00")
                        )
                        if venc_dt > agora:
                            base = venc_dt
                            logger.info(
                                f"📅 Webhook: soma aplicada, base = "
                                f"{base.strftime('%d/%m/%Y')}"
                            )
            except Exception as e:
                logger.warning(f"Erro ao checar vencimento (webhook): {e}")

        vencimento = base + timedelta(days=dias)

        # 4. Ativa assinatura
        supabase.table("assinaturas").upsert({
            "chat_id": str(chat_id),
            "tipo_plano": tipo_plano,
            "status": "ativo",
            "data_inicio": agora.isoformat(),
            "data_vencimento": vencimento.isoformat(),
        }, on_conflict="chat_id").execute()

        logger.info(
            f"✅ Assinatura ativada | chat_id={chat_id} | plano={tipo_plano} | "
            f"validade={dias} dias | vence={vencimento.strftime('%d/%m/%Y')}"
        )

        # 5. Notifica usuário
        if _telegram_bot:
            try:
                await _telegram_bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "🎉 <b>Pagamento confirmado!</b>\n\n"
                        f"Seu plano <b>{tipo_plano.upper()}</b> foi ativado com sucesso.\n"
                        f"• <b>Validade:</b> até {vencimento.strftime('%d/%m/%Y')}\n\n"
                        "Aproveite o VigiaSaúde! 🚀"
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Erro ao notificar usuário {chat_id}: {e}")

        return True

    except Exception as e:
        logger.error(f"Erro ao processar pagamento aprovado: {e}")
        return False