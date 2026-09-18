# handler_enquete_admin.py
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Poll
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
AGUARDANDO_PERGUNTA = 1
AGUARDANDO_OPCOES = 2
AGUARDANDO_ANONIMATO = 3
AGUARDANDO_DURACAO = 4
AGUARDANDO_DESTINO_ENQ = 5
AGUARDANDO_CONFIRMACAO_ENQ = 6


# Mapeamento de duração: callback -> (segundos, texto)
DURACOES = {
    "enq_dur_1min":  (60,   "1 minuto"),
    "enq_dur_5min":  (300,  "5 minutos"),
    "enq_dur_10min": (600,  "10 minutos"),
    "enq_dur_30min": (1800, "30 minutos (fechamento agendado)"),
    "enq_dur_1h":    (3600, "1 hora (fechamento agendado)"),
    "enq_dur_1d":    (86400,"24 horas (fechamento agendado)"),
    "enq_dur_none":  (None, "Sem tempo limite (fechar manualmente)"),
}


async def iniciar_envio_enquete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o fluxo de envio de enquete (somente admin)."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return ConversationHandler.END

    for k in ("enq_pergunta", "enq_opcoes", "enq_anonima", "enq_duracao", "enq_destinos"):
        context.user_data.pop(k, None)

    await update.message.reply_text(
        "📊 <b>Envio de Enquete</b>\n\n"
        "Digite a <b>pergunta</b> da enquete:\n\n"
        "<i>Ex: Qual sua opinião sobre o novo layout do VigiaSaúde?</i>\n\n"
        "Para cancelar, use /cancelar.",
        parse_mode="HTML"
    )
    return AGUARDANDO_PERGUNTA


async def receber_pergunta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pergunta = update.message.text.strip()
    if len(pergunta) < 5:
        await update.message.reply_text("❌ A pergunta é muito curta. Digite novamente:")
        return AGUARDANDO_PERGUNTA
    if len(pergunta) > 300:
        await update.message.reply_text("❌ A pergunta deve ter no máximo 300 caracteres. Digite novamente:")
        return AGUARDANDO_PERGUNTA

    context.user_data["enq_pergunta"] = pergunta

    await update.message.reply_text(
        "✅ Pergunta salva.\n\n"
        "Agora envie as <b>opções de resposta</b>, <b>uma por linha</b>.\n"
        "Mínimo 2, máximo 10 opções.\n\n"
        "<i>Exemplo:</i>\n"
        "<code>Excelente\nBom\nRegular\nRuim</code>",
        parse_mode="HTML"
    )
    return AGUARDANDO_OPCOES


async def receber_opcoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    linhas = [l.strip() for l in update.message.text.split("\n") if l.strip()]

    if len(linhas) < 2:
        await update.message.reply_text("❌ São necessárias pelo menos 2 opções. Envie novamente:")
        return AGUARDANDO_OPCOES
    if len(linhas) > 10:
        await update.message.reply_text("❌ Máximo de 10 opções. Envie novamente:")
        return AGUARDANDO_OPCOES

    for opt in linhas:
        if len(opt) > 100:
            await update.message.reply_text(f"❌ A opção \"{opt[:30]}...\" excede 100 caracteres. Envie novamente:")
            return AGUARDANDO_OPCOES

    context.user_data["enq_opcoes"] = linhas

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("👁️ Pública (você vê quem votou)", callback_data="enq_anon_nao")],
        [InlineKeyboardButton("🔒 Anônima (só vê os totais)", callback_data="enq_anon_sim")],
    ])

    await update.message.reply_text(
        f"✅ {len(linhas)} opções salvas.\n\n"
        "Agora escolha o <b>tipo de votação</b>:\n\n"
        "• <b>Pública</b>: você vê quem votou em cada opção.\n"
        "• <b>Anônima</b>: você só vê os totais gerais.",
        parse_mode="HTML",
        reply_markup=teclado
    )
    return AGUARDANDO_ANONIMATO


async def receber_anonimato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    context.user_data["enq_anonima"] = (data == "enq_anon_sim")

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 min", callback_data="enq_dur_1min"),
            InlineKeyboardButton("5 min", callback_data="enq_dur_5min"),
            InlineKeyboardButton("10 min", callback_data="enq_dur_10min"),
        ],
        [
            InlineKeyboardButton("30 min", callback_data="enq_dur_30min"),
            InlineKeyboardButton("1 hora", callback_data="enq_dur_1h"),
            InlineKeyboardButton("24 horas", callback_data="enq_dur_1d"),
        ],
        [InlineKeyboardButton("♾️ Sem tempo limite", callback_data="enq_dur_none")],
    ])

    await query.edit_message_text(
        "⏱️ Agora escolha a <b>duração</b> da enquete:\n\n"
        "<i>Obs: o Telegram limita o fechamento automático a 10 minutos. "
        "Durações maiores serão fechadas por agendamento interno do bot.</i>",
        parse_mode="HTML",
        reply_markup=teclado
    )
    return AGUARDANDO_DURACAO


async def receber_duracao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data not in DURACOES:
        await query.edit_message_text("❌ Duração inválida.")
        return ConversationHandler.END

    segundos, texto = DURACOES[data]
    context.user_data["enq_duracao"] = segundos
    context.user_data["enq_duracao_texto"] = texto

    await query.edit_message_text(
        f"✅ Duração: <b>{texto}</b>\n\n"
        "📨 Para quem deseja enviar?\n\n"
        "• Digite o <b>ID do chat</b>\n"
        "• Ou digite <b>todos</b> para enviar a todos os usuários.",
        parse_mode="HTML"
    )
    return AGUARDANDO_DESTINO_ENQ


async def receber_destino_enquete(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        context.user_data["enq_destinos"] = chat_ids
        alvo = f"<b>TODOS</b> ({len(chat_ids)} destinatários)"
    else:
        try:
            chat_id_unico = str(int(destino))
        except ValueError:
            await update.message.reply_text(
                "❌ Destino inválido. Envie um ID numérico ou a palavra <b>todos</b>.",
                parse_mode="HTML"
            )
            return AGUARDANDO_DESTINO_ENQ

        context.user_data["enq_destinos"] = [chat_id_unico]
        alvo = f"Chat ID <code>{chat_id_unico}</code>"

    pergunta = context.user_data.get("enq_pergunta")
    opcoes = context.user_data.get("enq_opcoes", [])
    anon = context.user_data.get("enq_anonima")
    duracao_txt = context.user_data.get("enq_duracao_texto")

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirmar envio", callback_data="confirmar_envio_enquete"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_envio_enquete"),
        ]
    ])

    preview_opcoes = "\n".join(f"  {i+1}. {o}" for i, o in enumerate(opcoes))

    await update.message.reply_text(
        "📋 <b>Confirmação de envio</b>\n\n"
        f"• <b>Pergunta:</b> {pergunta}\n"
        f"• <b>Opções:</b>\n{preview_opcoes}\n"
        f"• <b>Tipo:</b> {'Anônima' if anon else 'Pública'}\n"
        f"• <b>Voto único:</b> Sim\n"
        f"• <b>Duração:</b> {duracao_txt}\n"
        f"• <b>Destino:</b> {alvo}\n\n"
        "Confirma?",
        parse_mode="HTML",
        reply_markup=teclado
    )
    return AGUARDANDO_CONFIRMACAO_ENQ


async def fechar_enquete_agendada(context: ContextTypes.DEFAULT_TYPE):
    """Job que fecha enquetes após o tempo configurado (para durações > 10 min)."""
    job = context.job
    chat_id = job.data["chat_id"]
    message_id = job.data["message_id"]
    try:
        await context.bot.stop_poll(chat_id=chat_id, message_id=message_id)
        logger.info(f"⏰ Enquete fechada automaticamente em {chat_id} (msg {message_id})")
    except Exception as e:
        logger.error(f"Erro ao fechar enquete agendada: {e}")


async def confirmar_envio_enquete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    from config import ADMIN_CHAT_ID, ADMIN_IDS

    pergunta = context.user_data.get("enq_pergunta")
    opcoes = context.user_data.get("enq_opcoes")
    anon = context.user_data.get("enq_anonima", False)
    duracao_seg = context.user_data.get("enq_duracao")
    destinos = list(context.user_data.get("enq_destinos") or [])

    if not pergunta or not opcoes or not destinos:
        await query.edit_message_text("❌ Dados incompletos. Recomece com /enviar_enquete.")
        return ConversationHandler.END

    # ✅ GARANTE que o admin (autor do comando) também receba a enquete
    admin_id_str = str(update.effective_user.id)
    if admin_id_str not in destinos:
        destinos.append(admin_id_str)
        logger.info(f"📊 Admin {admin_id_str} adicionado à lista de destinatários da enquete")

    await query.edit_message_text(f"📤 Enviando enquete para {len(destinos)} destinatário(s)...")

    enviados = 0
    falhas = 0
    agendados = 0

    open_period = None
    if duracao_seg is not None and duracao_seg <= 600:
        open_period = duracao_seg

    for chat_id in destinos:
        try:
            poll_msg = await context.bot.send_poll(
                chat_id=chat_id,
                question=pergunta,
                options=opcoes,
                is_anonymous=anon,
                allows_multiple_answers=False,
                type=Poll.REGULAR,
                open_period=open_period,
            )
            enviados += 1

            if duracao_seg is not None and duracao_seg > 600:
                if context.job_queue:
                    context.job_queue.run_once(
                        fechar_enquete_agendada,
                        when=duracao_seg,
                        data={"chat_id": chat_id, "message_id": poll_msg.message_id},
                        name=f"fechar_enquete_{chat_id}_{poll_msg.message_id}",
                    )
                    agendados += 1

        except Exception as e:
            falhas += 1
            logger.error(f"Erro ao enviar enquete para {chat_id}: {e}")

    resumo = (
        "✅ <b>Enquete enviada</b>\n\n"
        f"• Enviadas com sucesso: {enviados}\n"
        f"• Falhas: {falhas}\n"
    )
    if agendados > 0:
        resumo += f"• Fechamentos agendados: {agendados}\n"
    resumo += (
        "\n💡 <i>Você recebeu uma cópia da enquete para acompanhar os resultados em tempo real.</i>\n"
        "💡 <i>Após votar, o resultado geral aparece automaticamente.</i>"
    )

    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text=resumo,
        parse_mode="HTML"
    )

    for k in ("enq_pergunta", "enq_opcoes", "enq_anonima", "enq_duracao",
              "enq_duracao_texto", "enq_destinos"):
        context.user_data.pop(k, None)

    return ConversationHandler.END


async def cancelar_envio_enquete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Envio de enquete cancelado.")
    elif update.message:
        await update.message.reply_text("❌ Envio de enquete cancelado.")

    for k in ("enq_pergunta", "enq_opcoes", "enq_anonima", "enq_duracao",
              "enq_duracao_texto", "enq_destinos"):
        context.user_data.pop(k, None)

    return ConversationHandler.END


# ConversationHandler
conv_envio_enquete = ConversationHandler(
    entry_points=[
        CommandHandler("enviar_enquete", iniciar_envio_enquete),
        CommandHandler("enquete", iniciar_envio_enquete),
    ],
    states={
        AGUARDANDO_PERGUNTA: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receber_pergunta),
        ],
        AGUARDANDO_OPCOES: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receber_opcoes),
        ],
        AGUARDANDO_ANONIMATO: [
            CallbackQueryHandler(receber_anonimato, pattern="^enq_anon_"),
        ],
        AGUARDANDO_DURACAO: [
            CallbackQueryHandler(receber_duracao, pattern="^enq_dur_"),
        ],
        AGUARDANDO_DESTINO_ENQ: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receber_destino_enquete),
        ],
        AGUARDANDO_CONFIRMACAO_ENQ: [
            CallbackQueryHandler(confirmar_envio_enquete, pattern="^confirmar_envio_enquete$"),
            CallbackQueryHandler(cancelar_envio_enquete, pattern="^cancelar_envio_enquete$"),
        ],
    },
    fallbacks=[
        CommandHandler("cancelar", cancelar_envio_enquete),
    ],
    per_message=False,
)