import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

def obter_menu_principal():
    """Remove qualquer teclado persistente da tela do usuário."""
    return ReplyKeyboardRemove()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal do /start ou /iniciar."""
    user = update.effective_user
    nome = user.first_name or "Usuário"

    mensagem = (
        f"👋 Olá, <b>{nome}</b>! Bem-vindo ao <b>VigiaSaude</b>.\n\n"
        f"🆔 <b>Seu ID do Telegram:</b> <code>{user.id}</code>\n\n"
        "Acesse todas as opções e comandos diretamente pelo menu nativo do Telegram "
        "(botão <b>[/]</b> ao lado da barra de digitação)."
    )

    await update.message.reply_text(
        mensagem,
        reply_markup=obter_menu_principal(),
        parse_mode="HTML"
    )

async def comando_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde ao comando de ajuda com o script da Central de Atendimento."""
    script_atendimento = (
        "🤖 <b>Central de Atendimento Automatizado — VigiaSaude</b>\n\n"
        "Seja bem-vindo(a) ao suporte do VigiaSaude! Nosso sistema automatizado está pronto "
        "para auxiliar você com rapidez e precisão.\n\n"
        "📌 <b>O que você pode fazer por aqui?</b>\n"
        "• Consultar o status das suas regulações ativas.\n"
        "• Tirar dúvidas sobre planos e renovação de assinatura.\n"
        "• Obter orientações sobre a consulta via Cartão SUS ou ID da Regulação.\n"
        "• Notificar divergências ou solicitar suporte técnico no sistema.\n\n"
        "💡 <b>Como iniciar?</b>\n"
        "Acesse nossa central dedicada abaixo para ser atendido pelo nosso assistente:"
    )

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🤖 Central de Atendimento ao Usuário VigiaSaude",
                url="https://t.me/AlertaSUS_Atendimento_ao_Usuario"
            )
        ]
    ])

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(script_atendimento, parse_mode="HTML", reply_markup=teclado)
    else:
        await update.message.reply_text(script_atendimento, parse_mode="HTML", reply_markup=teclado)

async def callback_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde ao clique no botão Ajuda com o script da Central de Atendimento."""
    query = update.callback_query
    await query.answer()

    script_atendimento = (
        "🤖 <b>Central de Atendimento Automatizado — VigiaSaude</b>\n\n"
        "Seja bem-vindo(a) ao suporte do VigiaSaude! Nosso sistema automatizado está pronto "
        "para auxiliar você com rapidez e precisão.\n\n"
        "📌 <b>O que você pode fazer por aqui?</b>\n"
        "• Consultar o status das suas regulações ativas.\n"
        "• Tirar dúvidas sobre planos e renovação de assinatura.\n"
        "• Obter orientações sobre a consulta via Cartão SUS ou ID da Regulação.\n"
        "• Notificar divergências ou solicitar suporte técnico no sistema.\n\n"
        "💡 <b>Como iniciar?</b>\n"
        "Acesse nossa central dedicada abaixo para ser atendido pelo nosso assistente:"
    )

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🤖 Central de Atendimento ao Usuário VigiaSaude",
                url="https://t.me/AlertaSUS_Atendimento_ao_Usuario"
            )
        ],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="voltar_inicio")]
    ])

    await query.edit_message_text(
        script_atendimento,
        parse_mode="HTML",
        reply_markup=teclado
    )

async def comando_privacidade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe os Termos de Uso e Política de Privacidade oficiais do VigiaSaude."""
    texto = (
        "🔒 <b>Política de Privacidade e Termos de Uso — VigiaSaude</b>\n\n"
        "O <b>VigiaSaude</b> é uma ferramenta independente desenvolvida para facilitar o "
        "acompanhamento e a notificação de status de solicitações de regulação (consultas, "
        "exames e procedimentos) junto aos sistemas públicos de saúde.\n\n"
        "<b>1. Proteção de Dados (LGPD)</b>\n"
        "• Dados como CPF e número do Cartão SUS são utilizados <b>exclusivamente</b> para "
        "consultar a situação do seu agendamento nos portais oficiais de regulação.\n"
        "• Suas informações sensíveis de saúde são criptografadas e mantidas em ambiente seguro.\n"
        "• Não comercializamos nem compartilhamos seus dados com terceiros.\n\n"
        "<b>2. Isenção de Responsabilidade</b>\n"
        "• O VigiaSaude <b>não possui vínculo oficial</b> com o Ministério da Saúde ou secretarias de saúde.\n"
        "• A responsabilidade pelo agendamento, marcação e atendimento é exclusivamente das centrais de regulação do SUS.\n"
        "• Notificamos você assim que houver alteração nos sistemas públicos, mas não alteramos posições ou filas de espera.\n\n"
        "<b>3. Seus Direitos</b>\n"
        "• Você tem total autonomia para excluir suas consultas e dados cadastrados a qualquer momento através do menu do bot.\n\n"
        "<i>Ao utilizar o VigiaSaude, você declara estar de acordo com estes termos.</i>"
    )

    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Dúvidas / Suporte", url="https://t.me/seu_suporte")]
    ])

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                texto, parse_mode="HTML", reply_markup=teclado
            )
        except Exception as e:
            logger.error(f"Erro ao editar mensagem de privacidade: {e}")
            await update.callback_query.message.reply_text(
                texto, parse_mode="HTML", reply_markup=teclado
            )
    else:
        await update.message.reply_text(
            texto, parse_mode="HTML", reply_markup=teclado
        )