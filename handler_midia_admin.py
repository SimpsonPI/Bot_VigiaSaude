# handler_midia_admin.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from database import supabase
from admin import eh_admin

logger = logging.getLogger(__name__)

# Estados do ConversationHandler
AGUARDANDO_MIDIA = 1
AGUARDANDO_DESTINO = 2
AGUARDANDO_CONFIRMACAO = 3


async def iniciar_envio_midia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o fluxo de envio de mídia (somente admin)."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return ConversationHandler.END

    for k in ("midia_file_id", "midia_tipo", "midia_caption", "destino_chat_ids"):
        context.user_data.pop(k, None)

    await update.message.reply_text(
        "📤 <b>Envio de Mídia</b>\n\n"
        "Envie a <b>imagem</b> ou o <b>documento</b> que deseja distribuir.\n"
        "Você pode adicionar uma <b>legenda</b> na própria mensagem.\n\n"
        "Para cancelar a qualquer momento, use /cancelar.",
        parse_mode="HTML"
    )
    return AGUARDANDO_MIDIA


async def receber_midia_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe a mídia do admin e pede o destino."""
    msg = update.message

    if msg.photo:
        file_id = msg.photo[-1].file_id
        tipo = "photo"
    elif msg.document:
        file_id = msg.document.file_id
        tipo = "document"
    elif msg.video:
        file_id = msg.video.file_id
        tipo = "video"
    else:
        await msg.reply_text("❌ Formato não suportado. Envie uma imagem, documento ou vídeo.")
        return AGUARDANDO_MIDIA

    context.user_data["midia_file_id"] = file_id
    context.user_data["midia_tipo"] = tipo
    context.user_data["midia_caption"] = msg.caption or ""

    await msg.reply_text(
        f"✅ Mídia recebida ({tipo}).\n\n"
        "📨 Para quem deseja enviar?\n\n"
        "• Digite o <b>ID do chat</b> (ex: <code>123456789</code>)\n"
        "• Ou digite <b>todos</b> para enviar a todos os usuários cadastrados.",
        parse_mode="HTML"
    )
    return AGUARDANDO_DESTINO


async def receber_destino_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o destino (ID ou 'todos') e pede confirmação."""
    destino = update.message.text.strip().lower()

    if destino == "todos":
        try:
            res = supabase.table("assinaturas").select("chat_id").execute()
            chat_ids = list(set(str(row["chat_id"]) for row in res.data if row.get("chat_id")))
        except Exception as e:
            logger.error(f"Erro ao buscar chat_ids: {e}")
            await update.message.reply_text("❌ Erro ao buscar lista de usuários.")
            return ConversationHandler.END

        if not chat_ids:
            await update.message.reply_text("⚠️ Nenhum usuário cadastrado encontrado.")
            return ConversationHandler.END

        context.user_data["destino_chat_ids"] = chat_ids
        alvo_texto = f"<b>TODOS os usuários</b> ({len(chat_ids)} destinatários)"
    else:
        try:
            chat_id_unico = str(int(destino))
        except ValueError:
            await update.message.reply_text(
                "❌ Destino inválido. Envie um ID numérico ou a palavra <b>todos</b>.",
                parse_mode="HTML"
            )
            return AGUARDANDO_DESTINO

        context.user_data["destino_chat_ids"] = [chat_id_unico]
        alvo_texto = f"Chat ID <code>{chat_id_unico}</code>"

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirmar envio", callback_data="confirmar_envio_midia"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_envio_midia"),
        ]
    ])

    caption = context.user_data.get("midia_caption") or "<i>(sem legenda)</i>"
    tipo = context.user_data.get("midia_tipo")

    await update.message.reply_text(
        "📋 <b>Confirmação de envio</b>\n\n"
        f"• Tipo: <b>{tipo}</b>\n"
        f"• Destino: {alvo_texto}\n"
        f"• Legenda: {caption}\n\n"
        "Confirma o envio?",
        parse_mode="HTML",
        reply_markup=teclado
    )
    return AGUARDANDO_CONFIRMACAO


async def confirmar_envio_midia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma e realiza o envio."""
    query = update.callback_query
    await query.answer()

    file_id = context.user_data.get("midia_file_id")
    tipo = context.user_data.get("midia_tipo")
    caption = context.user_data.get("midia_caption") or ""
    destinos = context.user_data.get("destino_chat_ids") or []

    if not file_id or not destinos:
        await query.edit_message_text("❌ Dados incompletos. Recomece com /enviar_midia.")
        return ConversationHandler.END

    await query.edit_message_text(f"📤 Enviando para {len(destinos)} destinatário(s)... Aguarde.")

    enviados = 0
    falhas = 0

    for chat_id in destinos:
        try:
            if tipo == "photo":
                await context.bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption or None)
            elif tipo == "document":
                await context.bot.send_document(chat_id=chat_id, document=file_id, caption=caption or None)
            elif tipo == "video":
                await context.bot.send_video(chat_id=chat_id, video=file_id, caption=caption or None)
            enviados += 1
        except Exception as e:
            falhas += 1
            logger.error(f"Erro ao enviar para {chat_id}: {e}")

    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text=(
            "✅ <b>Envio concluído</b>\n\n"
            f"• Enviados com sucesso: {enviados}\n"
            f"• Falhas: {falhas}"
        ),
        parse_mode="HTML"
    )

    for k in ("midia_file_id", "midia_tipo", "midia_caption", "destino_chat_ids"):
        context.user_data.pop(k, None)

    return ConversationHandler.END


async def cancelar_envio_midia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela o envio."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Envio cancelado.")
    elif update.message:
        await update.message.reply_text("❌ Envio cancelado.")

    for k in ("midia_file_id", "midia_tipo", "midia_caption", "destino_chat_ids"):
        context.user_data.pop(k, None)

    return ConversationHandler.END


# ConversationHandler
conv_envio_midia = ConversationHandler(
    entry_points=[
        CommandHandler("enviar_midia", iniciar_envio_midia),
        CommandHandler("enviar_imagem", iniciar_envio_midia),
        CommandHandler("enviar_documento", iniciar_envio_midia),
    ],
    states={
        AGUARDANDO_MIDIA: [
            MessageHandler(filters.PHOTO | filters.Document.ALL | filters.VIDEO, receber_midia_admin),
        ],
        AGUARDANDO_DESTINO: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receber_destino_admin),
        ],
        AGUARDANDO_CONFIRMACAO: [
            CallbackQueryHandler(confirmar_envio_midia, pattern="^confirmar_envio_midia$"),
            CallbackQueryHandler(cancelar_envio_midia, pattern="^cancelar_envio_midia$"),
        ],
    },
    fallbacks=[
        CommandHandler("cancelar", cancelar_envio_midia),
    ],
    per_message=False,
)