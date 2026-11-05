from telegram import Update
from telegram.ext import ContextTypes


async def comando_recursos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe a lista de todos os recursos do VS Bot Premium."""

    texto = (
        "✨ <b>Conheça todos os recursos do VS Bot Premium:</b>\n\n"
        "📸 <b>Cadastro por Foto (OCR):</b> A IA lê o comprovante e preenche os dados por você.\n"
        "🔄 <b>Reuso de Dados:</b> O bot lembra seu Cartão SUS para agilizar novos cadastros.\n"
        "📋 <b>Verificar Tudo:</b> Consulte todas as suas regulações de uma só vez.\n"
        "🎯 <b>Verificar Específico:</b> Consulte uma regulação individualmente.\n"
        "✏️ <b>Corrigir Dados:</b> Altere nome, data ou procedimento sem recadastrar.\n"
        "🎨 <b>Status Colorido:</b> Identifique rapidamente o andamento do exame.\n"
        "   🟢 Agendada | 🟡 Em fila | 🔴 Cancelada | 🔵 Vencida\n"
        "⏰ <b>Lembretes de Consulta:</b> Avisos automáticos 7, 3 e 1 dia antes do procedimento.\n"
        "💳 <b>Planos:</b> Gerencie sua assinatura, veja vencimento e limite de exames.\n"
        "🔒 <b>Privacidade:</b> Seus dados protegidos e Termo de Uso acessível.\n"
        "🎧 <b>Suporte:</b> Atendimento humanizado via Central de Atendimento.\n\n"
        "🚀 <i>O bot monitora o SUS de 6 em 6 horas e te avisa na hora que algo mudar!</i>"
    )

    # Se o comando foi chamado por um clique de botão, dá o answer
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(texto, parse_mode="HTML")
    else:
        await update.message.reply_text(texto, parse_mode="HTML")
