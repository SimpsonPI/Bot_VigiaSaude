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

# ==========================================
# BENEFÍCIOS DOS PLANOS
# ==========================================
BENEFICIOS_PLANO = {
    "degustacao": {
        "nome": "Degustação",
        "emoji": "🎁",
        "beneficios": [
            "Até 2 regulações monitoradas",
            "Notificações em tempo real no Telegram",
            "Acesso a todas as funcionalidades",
        ],
    },
    "trimestral": {
        "nome": "Pro Trimestral",
        "emoji": "⭐",
        "beneficios": [
            "Até 5 regulações monitoradas",
            "Notificações em tempo real no Telegram",
            "Acompanhamento automático de status",
            "Suporte via bot de atendimento",
        ],
    },
    "semestral": {
        "nome": "Pro Semestral",
        "emoji": "🚀",
        "beneficios": [
            "Até 9 regulações monitoradas",
            "Notificações em tempo real no Telegram",
            "Acompanhamento automático de status",
            "Suporte via bot de atendimento",
        ],
    },
    "cortesia": {
        "nome": "Cortesia VIP",
        "emoji": "👑",
        "beneficios": [
            "Regulações ilimitadas",
            "Notificações em tempo real no Telegram",
            "Acompanhamento automático de status",
            "Suporte prioritário",
        ],
    },
}


def _get_beneficios_plano(tipo_plano: str) -> dict:
    p = str(tipo_plano).lower()
    if "degustacao" in p:
        return BENEFICIOS_PLANO["degustacao"]
    if "semestral" in p:
        return BENEFICIOS_PLANO["semestral"]
    if "cortesia" in p:
        return BENEFICIOS_PLANO["cortesia"]
    return BENEFICIOS_PLANO["trimestral"]


def _montar_mensagem_boas_vindas(tipo_plano, limite_ids, vencimento, is_renovacao: bool) -> str:
    info = _get_beneficios_plano(tipo_plano)
    emoji = info["emoji"]
    nome = info["nome"]
    benef_list = "\n".join(f"  ✅ {b}" for b in info["beneficios"])

    if is_renovacao:
        titulo = "🎉 <b>Renovação confirmada!</b>"
        subtitulo = f"Que bom ter você de volta! Seu plano {emoji} <b>{nome}</b> foi renovado com sucesso."
    else:
        titulo = f"{emoji} <b>Bem-vindo ao VigiaSaúde!</b>"
        subtitulo = f"Seu plano <b>{nome}</b> foi ativado com sucesso e você já pode aproveitar tudo!"

    return (
        f"{titulo}\n\n"
        f"{subtitulo}\n\n"
        f"<b>📦 O que seu plano inclui:</b>\n"
        f"{benef_list}\n\n"
        f"<b>📅 Detalhes da assinatura:</b>\n"
        f"  • <b>Limite de regulações:</b> {limite_ids}\n"
        f"  • <b>Válido até:</b> {vencimento.strftime('%d/%m/%Y')}\n\n"
        f"<b>💡 Próximos passos:</b>\n"
        f"  1. Cadastre suas regulações com /cadastrar_nova\n"
        f"  2. Acompanhe o status com /verificar_todos\n"
        f"  3. Gerencie seu plano com /planos\n\n"
        f"Qualquer dúvida, acesse /suporte. Boas consultas! 🩺"
    )

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
    """Ativa/atualiza a assinatura do usuário e notifica com mensagem de boas-vindas."""
    try:
        # 1. Detecta se é renovação (já tinha plano ativo antes)
        is_renovacao = False
        try:
            res_ant = supabase.table("assinaturas").select(
                "tipo_plano, status, data_vencimento"
            ).eq("chat_id", str(chat_id)).execute()
            if res_ant.data:
                ant = res_ant.data[0]
                tipo_ant = str(ant.get("tipo_plano", "")).lower()
                status_ant = str(ant.get("status", "")).lower()
                # Considera renovação se já tinha um plano pago/ativo antes
                if tipo_ant and tipo_ant not in ("", "none") and status_ant in ("ativo", "active", "ativa"):
                    is_renovacao = True
                    logger.info(f"🔄 Renovação detectada para {chat_id} (plano anterior: {tipo_ant})")
        except Exception as e:
            logger.warning(f"Erro ao detectar renovação: {e}")

        # 2. Ativa/atualiza assinatura
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
            "ultimo_aviso": None,   # reseta avisos de vencimento
        }, on_conflict="chat_id").execute()

        logger.info(
            f"✅ Assinatura {'renovada' if is_renovacao else 'ativada'} | "
            f"chat_id={chat_id} | plano={tipo_plano} | limite={limite_ids} | "
            f"dias={dias} | vence={vencimento.strftime('%d/%m/%Y')}"
        )

        # 3. Notifica com mensagem de boas-vindas
        if _telegram_bot:
            try:
                texto = _montar_mensagem_boas_vindas(
                    tipo_plano, limite_ids, vencimento, is_renovacao
                )
                await _telegram_bot.send_message(
                    chat_id=chat_id,
                    text=texto,
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