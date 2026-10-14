import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

LIMITE_CADASTROS_DIA = 5


def _hoje_brasilia():
    agora = datetime.now(timezone.utc) - timedelta(hours=3)
    return agora.strftime("%Y-%m-%d")


def pode_cadastrar(chat_id):
    from database import supabase
    hoje = _hoje_brasilia()
    try:
        res = supabase.table("cadastros_usuarios").select("total").eq(
            "chat_id", str(chat_id)
        ).eq("data", hoje).execute()
        usados = res.data[0].get("total", 0) if res.data else 0
        restantes = max(0, LIMITE_CADASTROS_DIA - usados)
        if restantes <= 0:
            return (False, "limite_diario", 0)
        return (True, "", restantes)
    except Exception as e:
        logger.error(f"Erro ao verificar rate limit: {e}")
        return (True, "", LIMITE_CADASTROS_DIA)


def registrar_cadastro(chat_id):
    from database import supabase
    hoje = _hoje_brasilia()
    try:
        res = supabase.table("cadastros_usuarios").select("id, total").eq(
            "chat_id", str(chat_id)
        ).eq("data", hoje).execute()
        if res.data:
            atual = res.data[0].get("total", 0)
            supabase.table("cadastros_usuarios").update({
                "total": atual + 1,
            }).eq("id", res.data[0]["id"]).execute()
        else:
            supabase.table("cadastros_usuarios").insert({
                "chat_id": str(chat_id),
                "data": hoje,
                "total": 1,
            }).execute()
    except Exception as e:
        logger.error(f"Erro ao registrar cadastro: {e}")
