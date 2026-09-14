# pagamento_polling.py
import logging
import os
from datetime import datetime, timedelta, timezone
from database import supabase

try:
    import mercadopago
except ImportError:
    mercadopago = None

logger = logging.getLogger(__name__)

MERCADOPAGO_ACCESS_TOKEN = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN) if mercadopago else None

# Bot injetado pelo main.py
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
    if "anual" in p:
        return 365
    return 30


def _limite_por_plano(tipo_plano: str) -> int:
    p = str(tipo_plano).lower()
    if "degustacao" in p:
        return 2
    if "trimestral" in p:
        return 5
    if "semestral" in p:
        return 9
    if "anual" in p:
        return 9
    return 5


async def _consultar_pagamento_mp(payment_id: str) -> dict | None:
    """Consulta o pagamento no Mercado Pago. Retorna dict ou None."""
    if not sdk:
        logger.error("SDK Mercado Pago não disponível.")
        return None
    try:
        result = sdk.payment().get(payment_id)
        if result.get("status") == 200:
            return result.get("response", {})
        logger.error(f"Erro ao consultar MP ({payment_id}): {result}")
        return None
    except Exception as e:
        logger.error(f"Exceção ao consultar MP ({payment_id}): {e}")
        return None


async def _ativar_assinatura(chat_id: str, tipo_plano: str, mp_payment_id: str) -> bool:
    """Ativa/atualiza a assinatura do usuário e notifica."""
    try:
        dias = _calcular_dias_plano(tipo_plano)
        limite_ids = _limite_por_plano(tipo_plano)
        agora = datetime.now(timezone.utc)
        vencimento = agora + timedelta(days=dias)

        supabase.table("assinaturas").upsert({
            "chat_id": str(chat_id),
            "tipo_plano": tipo_plano,
            "status": "ativo",
            "data_inicio": agora.isoformat(),
            "data_vencimento": vencimento.isoformat(),
            "limite_ids": limite_ids,
        }, on_conflict="chat_id").execute()

        logger.info(
            f"✅ Assinatura ativada | chat_id={chat_id} | plano={tipo_plano} | "
            f"limite={limite_ids} | dias={dias} | vence={vencimento.strftime('%d/%m/%Y')}"
        )

        # Notifica o usuário
        if _telegram_bot:
            try:
                await _telegram_bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "🎉 <b>Pagamento confirmado!</b>\n\n"
                        f"Seu plano <b>{tipo_plano.upper()}</b> foi ativado com sucesso.\n"
                        f"• <b>Limite de regulações:</b> {limite_ids}\n"
                        f"• <b>Validade:</b> até {vencimento.strftime('%d/%m/%Y')}\n\n"
                        "Aproveite o VigiaSaúde! 🚀"
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Erro ao notificar usuário {chat_id}: {e}")

        return True
    except Exception as e:
        logger.error(f"Erro ao ativar assinatura de {chat_id}: {e}")
        return False


async def verificar_pagamentos_pendentes():
    """Roda periodicamente: verifica pagamentos pendentes e ativa assinaturas aprovadas."""
    if not sdk:
        return

    try:
        res = supabase.table("pagamentos_pix").select("*").eq("status", "pending").execute()
        pendentes = res.data if res.data else []
    except Exception as e:
        logger.error(f"Erro ao buscar pagamentos pendentes: {e}")
        return

    if not pendentes:
        logger.debug("Nenhum pagamento pendente para verificar.")
        return

    logger.info(f"🔍 Verificando {len(pendentes)} pagamento(s) pendente(s)...")

    for pag in pendentes:
        pix_id = pag.get("pix_id")
        chat_id = pag.get("chat_id")
        tipo_plano = pag.get("tipo_plano", "trimestral")

        if not pix_id:
            continue

        payment = await _consultar_pagamento_mp(str(pix_id))
        if not payment:
            continue

        status_mp = payment.get("status")
        logger.info(f"💳 Pagamento {pix_id} → status MP: {status_mp}")

        if status_mp == "approved":
            try:
                supabase.table("pagamentos_pix").update({
                    "status": "approved"
                }).eq("pix_id", str(pix_id)).execute()
            except Exception as e:
                logger.warning(f"Erro ao atualizar pagamentos_pix ({pix_id}): {e}")

            await _ativar_assinatura(chat_id, tipo_plano, str(pix_id))

        elif status_mp in ("cancelled", "rejected", "refunded"):
            try:
                supabase.table("pagamentos_pix").update({
                    "status": status_mp
                }).eq("pix_id", str(pix_id)).execute()
                logger.info(f"Pagamento {pix_id} marcado como {status_mp}")
            except Exception as e:
                logger.warning(f"Erro ao atualizar status de {pix_id}: {e}")