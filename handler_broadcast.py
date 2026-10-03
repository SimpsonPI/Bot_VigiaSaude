# handler_broadcast.py
import asyncio
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from database import supabase
from utils import (
    BROADCAST_ESCOLHER_SEGMENTO,
    BROADCAST_ENVIAR_CONTEUDO,
    BROADCAST_CONFIRMAR_ENVIO,
    TECLADO_MENU,
)

logger = logging.getLogger(__name__)

# Guarda o ID do admin que iniciou o broadcast (para confirmar antes de enviar)
ADMIN_ID = 5242040324  # ← ajuste se necessário

# ═══════════════════════════════════════════════
# BRANDING — Assinatura padrão dos broadcasts
# ═══════════════════════════════════════════════
CABECALHO = "📢 <b>VIGIASAÚDE — COMUNICADO OFICIAL</b>\n\n"

RODAPE = (
    "\n\n━━━━━━━━━━━━━━━━━━━━━\n"
    "🏥 <i>Ferramenta independente de monitoramento</i>\n"
    "🤖 Saiba mais: <b>@vigiasaude_bot</b>"
)

# ==========================================
# SEGMENTOS DISPONÍVEIS
# ==========================================
SEGMENTOS = {
    "todos": {
        "nome": "🌐 Todos os usuários",
        "emoji": "🌐",
        "filtro": None,
    },
    "ativos": {
        "nome": "✅ Só ativos",
        "emoji": "✅",
        "filtro": {"status_in": ["ativo", "active", "ativa"]},
    },
    "degustacao": {
        "nome": "🎁 Só degustação",
        "emoji": "🎁",
        "filtro": {"tipo_plano": "degustacao", "status_in": ["ativo", "active"]},
    },
    "trimestral": {
        "nome": "⭐ Só trimestral",
        "emoji": "⭐",
        "filtro": {"tipo_plano": "trimestral", "status_in": ["ativo", "active"]},
    },
    "semestral": {
        "nome": "🚀 Só semestral",
        "emoji": "🚀",
        "filtro": {"tipo_plano": "semestral", "status_in": ["ativo", "active"]},
    },
    "cortesia": {
        "nome": "👑 Só cortesia",
        "emoji": "👑",
        "filtro": {"tipo_plano": "cortesia", "status_in": ["ativo", "active"]},
    },
    "vencidos": {
        "nome": "❌ Só vencidos/bloqueados",
        "emoji": "❌",
        "filtro": {"status_in": ["expirado", "bloqueado", "inativo"]},
    },
}


def _buscar_usuarios_segmento(segmento: str) -> list:
    """Retorna a lista de chat_ids do segmento escolhido."""
    info = SEGMENTOS.get(segmento)
    if not info:
        return []

    try:
        query = supabase.table("assinaturas").select("chat_id")
        filtro = info.get("filtro")

        if filtro:
            if "tipo_plano" in filtro:
                query = query.eq("tipo_plano", filtro["tipo_plano"])
            if "status_in" in filtro:
                query = query.in_("status", filtro["status_in"])

        res = query.execute()
        chat_ids = list(set(str(r.get("chat_id")) for r in (res.data or []) if r.get("chat_id")))
        return chat_ids
    except Exception as e:
        logger.error(f"Erro ao buscar segmento {segmento}: {e}")
        return []


# ==========================================
# MENU DE SEGMENTOS
# ==========================================
def _teclado_segmentos() -> InlineKeyboardMarkup:
    """Monta o teclado de escolha de segmento."""
    botoes = [
        [InlineKeyboardButton("🌐 Todos os usuários", callback_data="bc_seg_todos")],
        [
            InlineKeyboardButton("✅ Só ativos", callback_data="bc_seg_ativos"),
            InlineKeyboardButton("❌ Só vencidos/bloqueados", callback_data="bc_seg_vencidos"),
        ],
        [
            InlineKeyboardButton("🎁 Degustação", callback_data="bc_seg_degustacao"),
            InlineKeyboardButton("⭐ Trimestral", callback_data="bc_seg_trimestral"),
        ],
        [
            InlineKeyboardButton("🚀 Semestral", callback_data="bc_seg_semestral"),
            InlineKeyboardButton("👑 Cortesia", callback_data="bc_seg_cortesia"),
        ],
        [InlineKeyboardButton("❌ Cancelar", callback_data="bc_cancelar")],
    ]
    return InlineKeyboardMarkup(botoes)


# ==========================================
# COMANDO /broadcast
# ==========================================
async def comando_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo de broadcast."""
    if update.effective_user.id != ADMIN_ID:
        if update.message:
            await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return ConversationHandler.END

    # Limpa estado antigo
    context.user_data.pop("bc_segmento", None)
    context.user_data.pop("bc_conteudo", None)
    context.user_data.pop("bc_tipo", None)

    texto = (
        "📢 <b>BROADCAST — Envio em Massa</b>\n\n"
        "Escolha o segmento de destinatários:"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(texto, parse_mode="HTML", reply_markup=_teclado_segmentos())
    else:
        await update.message.reply_text(texto, parse_mode="HTML", reply_markup=_teclado_segmentos())

    return BROADCAST_ESCOLHER_SEGMENTO


# ==========================================
# ESCOLHA DO SEGMENTO
# ==========================================
async def broadcast_escolher_segmento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa a escolha do segmento."""
    query = update.callback_query
    await query.answer()

    data = query.data

    # Cancelar
    if data == "bc_cancelar":
        await query.edit_message_text("❌ Broadcast cancelado.")
        context.user_data.clear()
        return ConversationHandler.END

    # Extrai segmento
    if not data.startswith("bc_seg_"):
        return BROADCAST_ESCOLHER_SEGMENTO

    segmento = data.replace("bc_seg_", "")
    info = SEGMENTOS.get(segmento)

    if not info:
        await query.edit_message_text("❌ Segmento inválido.")
        return ConversationHandler.END

    # Conta quantos usuários
    chat_ids = _buscar_usuarios_segmento(segmento)

    context.user_data["bc_segmento"] = segmento
    context.user_data["bc_total"] = len(chat_ids)

    texto = (
        f"✅ <b>Segmento selecionado:</b> {info['nome']}\n"
        f"👥 <b>Destinatários:</b> {len(chat_ids)} usuário(s)\n\n"
        "Agora envie a <b>mensagem</b> que deseja transmitir.\n\n"
        "<i>Você pode enviar:</i>\n"
        "• 📝 Texto simples\n"
        "• 📷 Foto (com ou sem legenda)\n"
        "• 🎬 Vídeo (com ou sem legenda)\n\n"
        "Use /cancelar para desistir."
    )

    await query.edit_message_text(texto, parse_mode="HTML")
    return BROADCAST_ENVIAR_CONTEUDO


# ==========================================
# RECEBE O CONTEÚDO
# ==========================================
async def broadcast_receber_conteudo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o conteúdo (texto, foto ou vídeo) e mostra prévia."""
    if not update.message:
        return BROADCAST_ENVIAR_CONTEUDO

    msg = update.message
    conteudo = {}
    tipo_previa = "texto"
    preview_texto = ""

    if msg.photo:
        conteudo = {
            "tipo": "photo",
            "file_id": msg.photo[-1].file_id,
            "caption": msg.caption or "",
        }
        tipo_previa = "foto"
        preview_texto = msg.caption or "(sem legenda)"
    elif msg.video:
        conteudo = {
            "tipo": "video",
            "file_id": msg.video.file_id,
            "caption": msg.caption or "",
        }
        tipo_previa = "vídeo"
        preview_texto = msg.caption or "(sem legenda)"
    elif msg.text:
        conteudo = {
            "tipo": "text",
            "text": msg.text,
        }
        tipo_previa = "texto"
        preview_texto = msg.text
    else:
        await msg.reply_text(
            "⚠️ Tipo de conteúdo não suportado.\n\n"
            "Envie apenas <b>texto</b>, <b>foto</b> ou <b>vídeo</b>.",
            parse_mode="HTML"
        )
        return BROADCAST_ENVIAR_CONTEUDO

    # Salva no contexto
    context.user_data["bc_conteudo"] = conteudo
    context.user_data["bc_tipo"] = tipo_previa

    # Monta prévia
    segmento = context.user_data.get("bc_segmento", "?")
    info = SEGMENTOS.get(segmento, {})
    total = context.user_data.get("bc_total", 0)

    preview = preview_texto[:300] if len(preview_texto) > 300 else preview_texto

    texto = (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 <b>PRÉVIA DO BROADCAST</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 <b>Segmento:</b> {info.get('nome', '?')}\n"
        f"👥 <b>Destinatários:</b> {total} usuário(s)\n"
        f"📎 <b>Tipo:</b> {tipo_previa}\n\n"
        "💬 <b>Conteúdo:</b>\n"
        f"<code>{preview}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📝 <b>COMO O USUÁRIO VAI VER:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>{CABECALHO.strip()}</i>\n\n"
        f"<code>{preview[:200]}</code>\n\n"
        f"<i>{RODAPE.strip()}</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ENVIAR AGORA", callback_data="bc_conf_enviar")],
        [InlineKeyboardButton("✏️ Trocar conteúdo", callback_data="bc_conf_trocar")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="bc_cancelar")],
    ])

    await msg.reply_text(texto, parse_mode="HTML", reply_markup=teclado)
    return BROADCAST_CONFIRMAR_ENVIO


# ==========================================
# CONFIRMAÇÃO E ENVIO
# ==========================================
async def broadcast_confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa a confirmação e faz o envio."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "bc_cancelar":
        await query.edit_message_text("❌ Broadcast cancelado.")
        context.user_data.clear()
        return ConversationHandler.END

    if data == "bc_conf_trocar":
        await query.edit_message_text(
            "✏️ Envie o novo conteúdo (texto, foto ou vídeo):"
        )
        return BROADCAST_ENVIAR_CONTEUDO

    if data != "bc_conf_enviar":
        return BROADCAST_CONFIRMAR_ENVIO

    # --- INÍCIO DO ENVIO ---
    segmento = context.user_data.get("bc_segmento", "todos")
    conteudo = context.user_data.get("bc_conteudo") or {}
    tipo = conteudo.get("tipo")

    chat_ids = _buscar_usuarios_segmento(segmento)

    if not chat_ids:
        await query.edit_message_text("⚠️ Nenhum destinatário encontrado para este segmento.")
        context.user_data.clear()
        return ConversationHandler.END

    # Mensagem de progresso
    await query.edit_message_text(
        f"📤 <b>Enviando para {len(chat_ids)} usuário(s)...</b>\n\n"
        "<i>Aguarde — isso pode levar alguns segundos.</i>",
        parse_mode="HTML"
    )

    enviados = 0
    falhas = 0
    detalhes_falhas = []
    bloqueados = []

    for cid in chat_ids:
        try:
            if tipo == "text":
                # Texto puro → cabeçalho + conteúdo + rodapé
                texto_final = CABECALHO + conteudo.get("text", "") + RODAPE
                await context.bot.send_message(
                    chat_id=cid,
                    text=texto_final,
                    parse_mode="HTML",
                )
            elif tipo == "photo":
                # Foto → cabeçalho + legenda + rodapé
                caption_original = conteudo.get("caption") or ""
                caption_final = CABECALHO + caption_original + RODAPE

                # Telegram limita legendas a 1024 chars
                if len(caption_final) > 1000:
                    caption_final = caption_final[:990] + "\n[...]"

                await context.bot.send_photo(
                    chat_id=cid,
                    photo=conteudo.get("file_id"),
                    caption=caption_final,
                    parse_mode="HTML",
                )
            elif tipo == "video":
                # Vídeo → cabeçalho + legenda + rodapé
                caption_original = conteudo.get("caption") or ""
                caption_final = CABECALHO + caption_original + RODAPE

                if len(caption_final) > 1000:
                    caption_final = caption_final[:990] + "\n[...]"

                await context.bot.send_video(
                    chat_id=cid,
                    video=conteudo.get("file_id"),
                    caption=caption_final,
                    parse_mode="HTML",
                )

            enviados += 1
            await asyncio.sleep(0.3)

        except Exception as e:
            falhas += 1
            erro_str = str(e).lower()

            if "blocked" in erro_str:
                motivo = "🚫 Bloqueou o bot"
                bloqueados.append(cid)
            elif "chat not found" in erro_str or "user not found" in erro_str:
                motivo = "❓ Nunca iniciou o bot"
            elif "deactivated" in erro_str:
                motivo = "💀 Conta desativada"
            else:
                motivo = f"⚠️ {str(e)[:60]}"

            detalhes_falhas.append(f"• <code>{cid}</code> → {motivo}")
            logger.error(f"Falha broadcast para {cid}: {repr(e)}")

    # Relatório final
    texto_final = (
        "✅ <b>Broadcast finalizado!</b>\n\n"
        f"📤 <b>Enviadas:</b> {enviados}\n"
        f"❌ <b>Falhas:</b> {falhas}\n"
    )

    if detalhes_falhas:
        texto_final += "\n📋 <b>Detalhes das falhas:</b>\n" + "\n".join(detalhes_falhas[:10])
        if len(detalhes_falhas) > 10:
            texto_final += f"\n<i>...e mais {len(detalhes_falhas) - 10} falha(s)</i>"

    if bloqueados:
        texto_final += (
            f"\n\n💡 <i>{len(bloqueados)} usuário(s) bloquearam o bot. "
            "Considere removê-los com /bloquear.</i>"
        )

    try:
        await query.edit_message_text(texto_final, parse_mode="HTML")
    except Exception:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=texto_final,
            parse_mode="HTML"
        )

    context.user_data.clear()
    return ConversationHandler.END


# ==========================================
# CANCELAR
# ==========================================
async def cancelar_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela o broadcast em qualquer etapa."""
    if update.message:
        await update.message.reply_text("❌ Broadcast cancelado.", reply_markup=TECLADO_MENU)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Broadcast cancelado.")

    context.user_data.clear()
    return ConversationHandler.END


# ==========================================
# CONVERSATION HANDLER
# ==========================================
from telegram.ext import ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters

conv_broadcast = ConversationHandler(
    entry_points=[
        CommandHandler("broadcast", comando_broadcast),
        CommandHandler("comunicar", comando_broadcast),
    ],
    states={
        BROADCAST_ESCOLHER_SEGMENTO: [
            CallbackQueryHandler(broadcast_escolher_segmento, pattern="^(bc_seg_|bc_cancelar)")
        ],
        BROADCAST_ENVIAR_CONTEUDO: [
            MessageHandler(
                filters.TEXT | filters.PHOTO | filters.VIDEO,
                broadcast_receber_conteudo
            ),
            CallbackQueryHandler(broadcast_escolher_segmento, pattern="^bc_cancelar$"),
        ],
        BROADCAST_CONFIRMAR_ENVIO: [
            CallbackQueryHandler(broadcast_confirmar, pattern="^(bc_conf_|bc_cancelar)")
        ],
    },
    fallbacks=[
        CommandHandler("cancelar", cancelar_broadcast),
        CommandHandler("cancelar_broadcast", cancelar_broadcast),
    ],
    per_message=False,
)