# handler_enquete_local.py
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
from admin import eh_admin
from enquetes_storage import (
    criar_enquete,
    obter_enquete,
    registrar_voto,
    listar_enquetes,
    encerrar_enquete,
    reabrir_enquete,
    apagar_enquete,
    apagar_todas,
    calcular_resultado,
)
from database import supabase

logger = logging.getLogger(__name__)

# Estados
AGUARDANDO_PERGUNTA = 1
AGUARDANDO_OPCOES = 2
AGUARDANDO_DESTINO = 3
AGUARDANDO_CONFIRMACAO = 4


# ═══════════════════════════════════════════════════════════
# CRIAÇÃO DA ENQUETE
# ═══════════════════════════════════════════════════════════

async def iniciar_criacao_enquete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return ConversationHandler.END

    for k in ("enq_pergunta", "enq_opcoes", "enq_destinos"):
        context.user_data.pop(k, None)

    await update.message.reply_text(
        "📊 <b>Criar Enquete</b>\n\n"
        "Digite a <b>pergunta</b>:\n\n"
        "<i>Ex: Qual sua principal dificuldade no VigiaSaúde?</i>\n\n"
        "Para cancelar, use /cancelar.",
        parse_mode="HTML"
    )
    return AGUARDANDO_PERGUNTA


async def receber_pergunta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pergunta = update.message.text.strip()
    if len(pergunta) < 5 or len(pergunta) > 300:
        await update.message.reply_text("❌ A pergunta deve ter entre 5 e 300 caracteres. Tente novamente:")
        return AGUARDANDO_PERGUNTA

    context.user_data["enq_pergunta"] = pergunta

    await update.message.reply_text(
        "✅ Pergunta salva.\n\n"
        "Agora envie as <b>opções</b>, uma por linha (mín. 2, máx. 10):\n\n"
        "<i>Exemplo:</i>\n<code>Cadastrar\nCorrigir\nExcluir\nInformações do bot</code>",
        parse_mode="HTML"
    )
    return AGUARDANDO_OPCOES


async def receber_opcoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    linhas = [l.strip() for l in update.message.text.split("\n") if l.strip()]
    if len(linhas) < 2 or len(linhas) > 10:
        await update.message.reply_text("❌ Envie entre 2 e 10 opções, uma por linha:")
        return AGUARDANDO_OPCOES
    for opt in linhas:
        if len(opt) > 100:
            await update.message.reply_text(f"❌ A opção \"{opt[:30]}...\" excede 100 caracteres:")
            return AGUARDANDO_OPCOES

    context.user_data["enq_opcoes"] = linhas

    await update.message.reply_text(
        f"✅ {len(linhas)} opções salvas.\n\n"
        "📨 Para quem deseja enviar?\n\n"
        "• Digite o <b>ID do chat</b>\n"
        "• Ou digite <b>todos</b> para enviar a todos os usuários.",
        parse_mode="HTML"
    )
    return AGUARDANDO_DESTINO


async def receber_destino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    destino = update.message.text.strip().lower()

    if destino == "todos":
        try:
            res = supabase.table("assinaturas").select("chat_id").execute()
            chat_ids = list(set(str(r["chat_id"]) for r in res.data if r.get("chat_id")))
        except Exception as e:
            logger.error(f"Erro ao buscar chat_ids: {e}")
            await update.message.reply_text("❌ Erro ao buscar lista de usuários.")
            return ConversationHandler.END
        if not chat_ids:
            await update.message.reply_text("⚠️ Nenhum usuário cadastrado.")
            return ConversationHandler.END
        context.user_data["enq_destinos"] = chat_ids
        alvo = f"<b>TODOS</b> ({len(chat_ids)} usuários)"
    else:
        try:
            chat_id_unico = str(int(destino))
        except ValueError:
            await update.message.reply_text("❌ ID inválido. Envie um número ou <b>todos</b>.", parse_mode="HTML")
            return AGUARDANDO_DESTINO
        context.user_data["enq_destinos"] = [chat_id_unico]
        alvo = f"ID <code>{chat_id_unico}</code>"

    pergunta = context.user_data.get("enq_pergunta")
    opcoes = context.user_data.get("enq_opcoes", [])
    preview = "\n".join(f"  {i+1}. {o}" for i, o in enumerate(opcoes))

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirmar", callback_data="enq_confirmar"),
            InlineKeyboardButton("❌ Cancelar", callback_data="enq_cancelar"),
        ]
    ])

    await update.message.reply_text(
        "📋 <b>Confirmação</b>\n\n"
        f"• <b>Pergunta:</b> {pergunta}\n"
        f"• <b>Opções:</b>\n{preview}\n"
        f"• <b>Destino:</b> {alvo}\n\n"
        "Confirma?",
        parse_mode="HTML",
        reply_markup=teclado
    )
    return AGUARDANDO_CONFIRMACAO


async def confirmar_criacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pergunta = context.user_data.get("enq_pergunta")
    opcoes = context.user_data.get("enq_opcoes")
    destinos = context.user_data.get("enq_destinos") or []

    if not pergunta or not opcoes or not destinos:
        await query.edit_message_text("❌ Dados incompletos.")
        return ConversationHandler.END

    enquete_id = criar_enquete(pergunta, opcoes, str(update.effective_user.id))

    admin_id_str = str(update.effective_user.id)
    if admin_id_str not in destinos:
        destinos.append(admin_id_str)

    await query.edit_message_text(f"📤 Enviando enquete #{enquete_id} para {len(destinos)} usuário(s)...")

    botoes = []
    for idx, opt in enumerate(opcoes):
        botoes.append([InlineKeyboardButton(opt, callback_data=f"voto_{enquete_id}_{idx}")])
    teclado = InlineKeyboardMarkup(botoes)

    enviados = 0
    falhas = 0
    for chat_id in destinos:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📊 <b>{pergunta}</b>\n\n<i>Toque em uma opção para votar:</i>",
                parse_mode="HTML",
                reply_markup=teclado
            )
            enviados += 1
        except Exception as e:
            falhas += 1
            logger.error(f"Erro ao enviar enquete para {chat_id}: {e}")

    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text=(
            f"✅ <b>Enquete #{enquete_id} enviada!</b>\n\n"
            f"• Enviadas: {enviados}\n"
            f"• Falhas: {falhas}\n\n"
            f"📊 Ver resultado: <code>/resultado {enquete_id}</code>\n"
            f"📋 Encerrar: <code>/encerrar {enquete_id}</code>\n"
            f"🗑️ Apagar: <code>/apagar_enquete {enquete_id}</code>"
        ),
        parse_mode="HTML"
    )

    for k in ("enq_pergunta", "enq_opcoes", "enq_destinos"):
        context.user_data.pop(k, None)

    return ConversationHandler.END


async def cancelar_criacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Criação cancelada.")
    elif update.message:
        await update.message.reply_text("❌ Criação cancelada.")
    for k in ("enq_pergunta", "enq_opcoes", "enq_destinos"):
        context.user_data.pop(k, None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════
# VOTAÇÃO
# ═══════════════════════════════════════════════════════════

async def receber_voto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    partes = query.data.split("_")
    enquete_id = int(partes[1])
    opcao_idx = int(partes[2])

    ok, msg = registrar_voto(enquete_id, str(user.id), user.first_name or "Usuário", opcao_idx)

    if not ok:
        await query.answer(msg, show_alert=True)
        return

    enquete = obter_enquete(enquete_id)
    opcoes = enquete.get("opcoes", [])
    opcao_escolhida = opcoes[opcao_idx] if opcao_idx < len(opcoes) else "?"

    await query.answer(f"✅ Voto registrado: {opcao_escolhida}", show_alert=False)

    # Desabilita os botões
    try:
        botoes = []
        for idx, opt in enumerate(opcoes):
            marcador = "✅ " if idx == opcao_idx else "▫️ "
            botoes.append([InlineKeyboardButton(marcador + opt, callback_data="voto_ja_registrado")])
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(botoes))
    except Exception as e:
        logger.error(f"Erro ao atualizar teclado: {e}")


async def voto_ja_registrado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("⚠️ Você já votou nesta enquete!", show_alert=True)


# ═══════════════════════════════════════════════════════════
# RESULTADO
# ═══════════════════════════════════════════════════════════

async def comando_resultado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Uso: <code>/resultado &lt;ID&gt;</code>", parse_mode="HTML")
        return

    try:
        enquete_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID inválido.")
        return

    enquete = obter_enquete(enquete_id)
    if not enquete:
        await update.message.reply_text(f"❌ Enquete #{enquete_id} não encontrada.")
        return

    r = calcular_resultado(enquete)
    total = r["total"]
    contagem = r["contagem"]
    opcoes = r["opcoes"]

    status = "🟢 Ativa" if enquete.get("ativa") else "🔒 Encerrada"

    texto = (
        f"📊 <b>Resultado — Enquete #{enquete_id}</b>\n"
        f"<i>{enquete.get('pergunta')}</i>\n\n"
        f"Status: {status}\n"
        f"Total de votos: <b>{total}</b>\n\n"
    )

    for i, opt in enumerate(opcoes):
        qtd = contagem.get(i, 0)
        pct = (qtd / total * 100) if total > 0 else 0
        barra = "█" * int(pct / 5)
        texto += f"<b>{opt}</b>\n{qtd} voto(s) — {pct:.1f}%\n{barra}\n\n"

    # Adiciona botões de ação
    botoes = []
    if enquete.get("ativa"):
        botoes.append([InlineKeyboardButton("🔒 Encerrar", callback_data=f"enq_encerrar_{enquete_id}")])
    else:
        botoes.append([InlineKeyboardButton("🔓 Reabrir", callback_data=f"enq_reabrir_{enquete_id}")])
    botoes.append([InlineKeyboardButton("🗑️ Apagar", callback_data=f"enq_apagar_{enquete_id}")])
    botoes.append([InlineKeyboardButton("🔄 Atualizar", callback_data=f"enq_atualizar_{enquete_id}")])

    await update.message.reply_text(
        texto,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(botoes)
    )


async def callback_resultado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botões dentro do resultado (encerrar, reabrir, apagar, atualizar)."""
    query = update.callback_query
    if not eh_admin(query.from_user.id):
        await query.answer("⛔ Acesso restrito.", show_alert=True)
        return

    data = query.data
    if data.startswith("enq_encerrar_"):
        eid = int(data.split("_")[-1])
        encerrar_enquete(eid)
        await query.answer("🔒 Enquete encerrada!")
    elif data.startswith("enq_reabrir_"):
        eid = int(data.split("_")[-1])
        reabrir_enquete(eid)
        await query.answer("🔓 Enquete reaberta!")
    elif data.startswith("enq_apagar_"):
        eid = int(data.split("_")[-1])
        apagar_enquete(eid)
        await query.answer("🗑️ Enquete apagada!")
        await query.edit_message_text(f"🗑️ Enquete #{eid} apagada com sucesso.")
        return
    elif data.startswith("enq_atualizar_"):
        eid = int(data.split("_")[-1])
        await query.answer("🔄 Atualizando...")

    # Recria a mensagem com dados atualizados
    enquete_id = int(data.split("_")[-1])
    enquete = obter_enquete(enquete_id)
    if not enquete:
        await query.edit_message_text("❌ Enquete não encontrada.")
        return

    r = calcular_resultado(enquete)
    total = r["total"]
    contagem = r["contagem"]
    opcoes = r["opcoes"]

    status = "🟢 Ativa" if enquete.get("ativa") else "🔒 Encerrada"

    texto = (
        f"📊 <b>Resultado — Enquete #{enquete_id}</b>\n"
        f"<i>{enquete.get('pergunta')}</i>\n\n"
        f"Status: {status}\n"
        f"Total de votos: <b>{total}</b>\n\n"
    )

    for i, opt in enumerate(opcoes):
        qtd = contagem.get(i, 0)
        pct = (qtd / total * 100) if total > 0 else 0
        barra = "█" * int(pct / 5)
        texto += f"<b>{opt}</b>\n{qtd} voto(s) — {pct:.1f}%\n{barra}\n\n"

    botoes = []
    if enquete.get("ativa"):
        botoes.append([InlineKeyboardButton("🔒 Encerrar", callback_data=f"enq_encerrar_{enquete_id}")])
    else:
        botoes.append([InlineKeyboardButton("🔓 Reabrir", callback_data=f"enq_reabrir_{enquete_id}")])
    botoes.append([InlineKeyboardButton("🗑️ Apagar", callback_data=f"enq_apagar_{enquete_id}")])
    botoes.append([InlineKeyboardButton("🔄 Atualizar", callback_data=f"enq_atualizar_{enquete_id}")])

    try:
        await query.edit_message_text(texto, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(botoes))
    except Exception:
        pass  # Se não mudou nada, ignora


async def comando_resultado_detalhado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Uso: <code>/resultado_detalhado &lt;ID&gt;</code>", parse_mode="HTML")
        return

    try:
        enquete_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID inválido.")
        return

    enquete = obter_enquete(enquete_id)
    if not enquete:
        await update.message.reply_text(f"❌ Enquete #{enquete_id} não encontrada.")
        return

    votos = enquete.get("votos", {})
    if not votos:
        await update.message.reply_text("ℹ️ Nenhum voto ainda.")
        return

    opcoes = enquete.get("opcoes", [])
    texto = f"📋 <b>Votos detalhados — Enquete #{enquete_id}</b>\n\n"
    for chat_id, v in votos.items():
        idx = v.get("opcao_idx", -1)
        opt = opcoes[idx] if 0 <= idx < len(opcoes) else "?"
        nome = v.get("nome", "?")
        texto += f"• <b>{nome}</b> (<code>{chat_id}</code>) → {opt}\n"

    if len(texto) > 4000:
        texto = texto[:3990] + "\n\n<i>[...]</i>"

    await update.message.reply_text(texto, parse_mode="HTML")


async def comando_listar_enquetes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return

    enquetes = listar_enquetes()
    if not enquetes:
        await update.message.reply_text("ℹ️ Nenhuma enquete criada ainda.")
        return

    texto = "📋 <b>Enquetes criadas:</b>\n\n"
    for e in enquetes[:20]:
        status = "🟢" if e.get("ativa") else "🔒"
        total = len(e.get("votos", {}))
        texto += f"{status} <b>#{e['id']}</b> — {e['pergunta'][:50]}\n   {total} voto(s)\n"

    texto += "\n<i>Use /resultado &lt;id&gt; para ver os votos.</i>"
    await update.message.reply_text(texto, parse_mode="HTML")


async def comando_encerrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Uso: <code>/encerrar &lt;ID&gt;</code>", parse_mode="HTML")
        return

    try:
        eid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID inválido.")
        return

    if encerrar_enquete(eid):
        await update.message.reply_text(f"🔒 Enquete #{eid} encerrada.")
    else:
        await update.message.reply_text("❌ Enquete não encontrada.")


async def comando_apagar_enquete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Uso: <code>/apagar_enquete &lt;ID&gt;</code>\n"
            "Ou <code>/apagar_enquete todas</code> para apagar todas.",
            parse_mode="HTML"
        )
        return

    arg = context.args[0].lower()
    if arg == "todas":
        qtd = apagar_todas()
        await update.message.reply_text(f"🗑️ {qtd} enquete(s) apagada(s).")
        return

    try:
        eid = int(arg)
    except ValueError:
        await update.message.reply_text("❌ ID inválido.")
        return

    if apagar_enquete(eid):
        await update.message.reply_text(f"🗑️ Enquete #{eid} apagada.")
    else:
        await update.message.reply_text("❌ Enquete não encontrada.")


# ═══════════════════════════════════════════════════════════
# ConversationHandler
# ═══════════════════════════════════════════════════════════

conv_criar_enquete = ConversationHandler(
    entry_points=[
        CommandHandler("criar_enquete", iniciar_criacao_enquete),
        CommandHandler("enviar_enquete", iniciar_criacao_enquete),
    ],
    states={
        AGUARDANDO_PERGUNTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_pergunta)],
        AGUARDANDO_OPCOES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_opcoes)],
        AGUARDANDO_DESTINO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_destino)],
        AGUARDANDO_CONFIRMACAO: [
            CallbackQueryHandler(confirmar_criacao, pattern="^enq_confirmar$"),
            CallbackQueryHandler(cancelar_criacao, pattern="^enq_cancelar$"),
        ],
    },
    fallbacks=[CommandHandler("cancelar", cancelar_criacao)],
    per_message=False,
)