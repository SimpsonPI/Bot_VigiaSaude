import os
import logging
from datetime import datetime, timezone
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

from database import supabase

logger = logging.getLogger(__name__)

# Leitura dos IDs de administradores via variáveis de ambiente
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

def eh_admin(func):
    """Decorator unificado para validar se o usuário é administrador autorizado."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("⛔ Acesso negado: você não possui privilégios de administrador.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@eh_admin
async def comando_conceder_cortesia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Concede acesso de cortesia (VIP/Ilimitado) para um ID de usuário do Telegram."""
    admin_chat_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text("⚠️ <b>Uso correto:</b> <code>/cortesia &lt;TELEGRAM_ID&gt;</code>", parse_mode="HTML")
        return

    target_id = context.args[0].strip()

    try:
        int(target_id) # Valida se é numérico
    except ValueError:
        await update.message.reply_text("❌ O ID do Telegram informado é inválido.")
        return

    # Tenta buscar o nome do usuário no Telegram para mascarar
    nome_mascarado = "Desconhecido"
    try:
        chat_info = await context.bot.get_chat(target_id)
        nome_completo = chat_info.full_name or chat_info.first_name or "Usuário"
        
        # Lógica para mascarar o nome (mantém a 1ª e última letra de cada palavra)
        partes = nome_completo.split()
        partes_mascaradas = []
        for parte in partes:
            if len(parte) <= 2:
                partes_mascaradas.append(parte[0] + "*")
            else:
                partes_mascaradas.append(parte[0] + "*" * (len(parte) - 2) + parte[-1])
        nome_mascarado = " ".join(partes_mascaradas)
    except Exception as e:
        logger.warning(f"[ADMIN] ⚠️ Não foi possível obter o nome do usuário {target_id}: {e}")

    try:
        # Insere ou atualiza o status para cortesia no Supabase
        supabase.table("assinaturas").upsert({
            "chat_id": str(target_id),
            "tipo_plano": "cortesia",
            "limite_ids": 99,
            "status": "ativo",
            "data_inicio": datetime.now(timezone.utc).isoformat(),
            "data_vencimento": None
        }, on_conflict="chat_id").execute()

        await update.message.reply_text(
            f"✅ <b>CONFIRMAÇÃO DE CORTESIA</b>\n\n"
            f"• <b>Usuário:</b> {nome_mascarado} (<code>{target_id}</code>)\n"
            f"• <b>Plano:</b> Cortesia (Ilimitado)\n"
            f"• <b>Status no Banco:</b> Ativo",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao registrar cortesia no Supabase: {e}")
        await update.message.reply_text(f"❌ Erro ao registrar no banco de dados: {e}")
        return

    # Notificação para o usuário contemplado (se for diferente do admin)
    if str(target_id) != str(admin_chat_id):
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    "🎁 <b>Você recebeu um acesso Cortesia!</b>\n\n"
                    "Sua conta no <b>VigiaSaude</b> foi atualizada para acesso gratuito e ilimitado. "
                    "Aproveite todos os recursos da plataforma!"
                ),
                parse_mode="HTML"
            )
        except Exception as err:
            logger.warning(f"[ADMIN] ⚠️ Não foi possível notificar o usuário {target_id}: {err}")


@eh_admin
async def comando_remover_cortesia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Revoga o acesso de cortesia e retorna o usuário para o plano de degustação."""
    admin_chat_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Uso correto:</b> <code>/remover_cortesia &lt;TELEGRAM_ID&gt;</code>", 
            parse_mode="HTML"
        )
        return

    target_id = context.args[0].strip()
    try:
        int(target_id)
    except ValueError:
        await update.message.reply_text("❌ ID do Telegram inválido.")
        return

    try:
        # Atualiza o plano de volta para degustação e limpa dados residuais de cortesia/pagamento se necessário
        supabase.table("assinaturas").update({
            "status": "ativo",
            "tipo_plano": "degustacao",
            "mp_payment_id": None
        }).eq("chat_id", str(target_id)).execute()

        await context.bot.send_message(
            chat_id=admin_chat_id,
            text=f"🔴 <b>CONFIRMAÇÃO:</b> Cortesia removida e usuário retornado ao plano <b>Degustação</b> com sucesso para o ID <code>{target_id}</code>.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao remover cortesia no Supabase: {e}")
        await update.message.reply_text(f"❌ Erro ao atualizar o banco de dados: {e}")
        
        # Opcional: Tentar avisar o usuário que a cortesia expirou/foi revogada
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="⚠️ Seu acesso cortesia no <b>VigiaSaude</b> foi encerrado. Utilize o menu /planos para reativar sua conta.",
                parse_mode="HTML"
            )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao revogar cortesia: {e}")
        await update.message.reply_text(f"❌ Erro ao revogar cortesia no banco: {e}")