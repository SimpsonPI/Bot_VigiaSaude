# admin_panel.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from config import ADMIN_CHAT_ID

logger = logging.getLogger(__name__)

ADMIN_ID = ADMIN_CHAT_ID or 5242040324


def _eh_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ═══════════════════════════════════════════════
# TECLADOS
# ═══════════════════════════════════════════════

def _teclado_principal() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Relatórios", callback_data="painel_relatorios"),
            InlineKeyboardButton("👑 Planos", callback_data="painel_planos"),
        ],
        [
            InlineKeyboardButton("🛡️ Segurança", callback_data="painel_seguranca"),
            InlineKeyboardButton("📢 Comunicação", callback_data="painel_comunicacao"),
        ],
        [
            InlineKeyboardButton("📋 Enquetes", callback_data="painel_enquetes"),
            InlineKeyboardButton("🔧 Sistema", callback_data="painel_sistema"),
        ],
        [InlineKeyboardButton("❌ Fechar Painel", callback_data="painel_fechar")],
    ])


def _teclado_voltar() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data="painel_inicio")],
    ])


# ═══════════════════════════════════════════════
# TEXTOS DAS CATEGORIAS
# ═══════════════════════════════════════════════

def _texto_relatorios() -> str:
    return (
        "📊 <b>RELATÓRIOS E DADOS</b>\n\n"
        "• <code>/estatisticas</code> — Visão geral do sistema\n"
        "• <code>/ativos</code> — Últimas assinaturas ativas\n"
        "• <code>/detalhes 123456789</code> — Dados de um usuário\n\n"
        "<i>Digite o comando na barra de mensagens.</i>"
    )


def _texto_planos() -> str:
    return (
        "👑 <b>GESTÃO DE PLANOS E ACESSOS</b>\n\n"
        "• <code>/cortesia 123456789</code> — Concede VIP ilimitado\n"
        "• <code>/remover_cortesia 123456789</code> — Remove cortesia\n"
        "• <code>/dar_plano 123456789 trimestral 90</code> — Concede plano\n"
        "• <code>/retirar_plano 123456789</code> — Remove plano pago\n"
        "• <code>/retirar_degustacao 123456789</code> — Remove degustação\n\n"
        "<i>💡 Use o ID sem os símbolos &lt; &gt;.</i>"
    )


def _texto_seguranca() -> str:
    return (
        "🛡️ <b>SEGURANÇA</b>\n\n"
        "• <code>/bloquear 123456789</code> — Bloqueia um usuário\n\n"
        "<i>💡 Use o ID sem os símbolos &lt; &gt;.</i>"
    )


def _texto_comunicacao() -> str:
    return (
        "📢 <b>COMUNICAÇÃO</b>\n\n"
        "<b>⭐ Recomendado:</b>\n"
        "• <code>/broadcast</code> — Envio segmentado com prévia\n\n"
        "<b>Envio rápido:</b>\n"
        "• <code>/aviso Sua mensagem aqui</code> — Broadcast simples\n\n"
        "<i>💡 O /broadcast permite escolher segmento e ver prévia antes.</i>"
    )


def _texto_enquetes() -> str:
    return (
        "📋 <b>ENQUETES</b>\n\n"
        "• <code>/listar_enquetes</code> — Lista todas\n"
        "• <code>/resultado 5</code> — Resultado resumido\n"
        "• <code>/resultado_detalhado 5</code> — Resultado completo\n"
        "• <code>/encerrar 5</code> — Encerra uma enquete\n"
        "• <code>/apagar_enquete 5</code> — Apaga uma enquete"
    )


def _texto_sistema() -> str:
    return (
        "🔧 <b>SISTEMA</b>\n\n"
        "• <code>/painel</code> — Este painel\n"
        "• <code>/start</code> — Volta ao menu principal do usuário\n"
        "• <code>/suporte</code> — Central de Atendimento\n\n"
        "<b>📌 Informações:</b>\n"
        f"• Seu ID: <code>{ADMIN_ID}</code>\n"
        "• Bot: @vigiasaude_bot"
    )


# ═══════════════════════════════════════════════
# COMANDO /painel
# ═══════════════════════════════════════════════

async def comando_painel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abre o painel de controle interativo."""
    if not _eh_admin(update.effective_user.id):
        if update.message:
            await update.message.reply_text("⛔ Acesso restrito a administradores.")
        return

    texto = (
        "🎛️ <b>PAINEL DE CONTROLE ADMINISTRATIVO</b>\n"
        "VigiaSaúde — Central de Operações\n\n"
        "Selecione uma categoria:"
    )
    teclado = _teclado_principal()

    if update.message:
        await update.message.reply_text(texto, parse_mode="HTML", reply_markup=teclado)
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)
        except Exception:
            await update.callback_query.message.reply_text(texto, parse_mode="HTML", reply_markup=teclado)


# ═══════════════════════════════════════════════
# CALLBACK DO PAINEL
# ═══════════════════════════════════════════════

async def callback_painel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa os cliques no painel."""
    query = update.callback_query
    await query.answer()

    if not _eh_admin(query.from_user.id):
        await query.edit_message_text("⛔ Acesso negado.")
        return

    data = query.data

    if data == "painel_fechar":
        await query.edit_message_text(
            "🎛️ Painel fechado.\n\nUse <code>/painel</code> para reabrir.",
            parse_mode="HTML"
        )
        return

    if data == "painel_inicio":
        texto = (
            "🎛️ <b>PAINEL DE CONTROLE ADMINISTRATIVO</b>\n"
            "VigiaSaúde — Central de Operações\n\n"
            "Selecione uma categoria:"
        )
        await query.edit_message_text(texto, parse_mode="HTML", reply_markup=_teclado_principal())
        return

    mapeamento = {
        "painel_relatorios": _texto_relatorios,
        "painel_planos": _texto_planos,
        "painel_seguranca": _texto_seguranca,
        "painel_comunicacao": _texto_comunicacao,
        "painel_enquetes": _texto_enquetes,
        "painel_sistema": _texto_sistema,
    }

    if data in mapeamento:
        texto = mapeamento[data]()
        await query.edit_message_text(texto, parse_mode="HTML", reply_markup=_teclado_voltar())
        return