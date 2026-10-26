from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes


async def mostrar_termos_uso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    # COLE O SEU LINK DO TELEGRAPH AQUI EMBAIXO:
    link_termos = (
        "https://telegra.ph/TERMOS-DE-USO-E-CONDI%C3%87%C3%95ES-DO-SERVI%C3%87O--VIGIASA%C3%9ADE-PREMIUM-10-26"
    )

    texto = (
        "📜 <b>Termos de Uso e Privacidade</b>\n\n"
        "Para ler o nosso Termo de Uso completo, clique no link abaixo. "
        "O Telegram abrirá o documento instantaneamente para você:\n\n"
        f"👉 <a href='{link_termos}'>Abrir Termos de Uso</a>"
    )

    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar aos Planos", callback_data="planos")]])

    if query:
        # O disable_web_page_preview=False é o segredo para aparecer a caixinha do Instant View
        await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado, disable_web_page_preview=False)
    else:
        await update.message.reply_text(texto, parse_mode="HTML", reply_markup=teclado, disable_web_page_preview=False)
