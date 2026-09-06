import os
import io
import base64
import logging
import mercadopago
from telegram import Update
from telegram.ext import ContextTypes

from database import supabase

logger = logging.getLogger(__name__)

sdk = mercadopago.SDK(os.getenv("MERCADOPAGO_ACCESS_TOKEN", ""))

PLANOS = {
    "pro_mensal": {"nome": "Pro Trimestral (3 meses)", "valor": 9.90},
    "pro_semestral": {"nome": "Pro Semestral", "valor": 14.99},   
}

async def gerar_pagamento_pix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query:
        await query.answer()
        user_id = query.from_user.id
        first_name = query.from_user.first_name or "Usuario"
        last_name = query.from_user.last_name or "VigiaSaude"
        plano_chave = query.data.replace("pix_", "").replace("pix_pro_", "pro_")
        # Garante mapeamento correto das chaves de planos
        if plano_chave in ["semestral", "pro_semestral"]:
            plano_chave = "pro_semestral"
        else:
            plano_chave = "pro_mensal"
            
        chat_id = query.message.chat_id
    else:
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name or "Usuario"
        last_name = update.effective_user.last_name or "VigiaSaude"
        plano_chave = context.args[0].lower() if context.args else "pro_mensal"
        chat_id = update.effective_chat.id

    detalhes_plano = PLANOS.get(plano_chave, PLANOS["pro_mensal"])
    nome_plano = detalhes_plano["nome"]
    valor = detalhes_plano["valor"]

    payment_data = {
        "transaction_amount": float(valor),
        "description": f"VigiaSaude - {nome_plano}",
        "payment_method_id": "pix",
        "payer": {
            "email": f"cliente_{user_id}@gmail.com",
            "first_name": first_name,
            "last_name": last_name
        },
        "external_reference": str(user_id)
    }

    try:
        result = sdk.payment().create(payment_data)
        
        if result.get("status") not in [200, 201]:
            erro_mp = result.get("response", {})
            logger.error(f"❌ Erro do Mercado Pago: {erro_mp.get('message')} - {erro_mp.get('cause')}")
            await context.bot.send_message(chat_id=chat_id, text="❌ Erro ao gerar o pagamento no Mercado Pago. Tente novamente em instantes.")
            return

        payment = result.get("response", {})
        point_of_interaction = payment.get("point_of_interaction", {})
        transaction_data = point_of_interaction.get("transaction_data", {})
        
        pix_copia_cola = transaction_data.get("qr_code")
        qr_code_base64 = transaction_data.get("qr_code_base64")
        mp_payment_id = payment.get("id")

        if not pix_copia_cola or not mp_payment_id:
            logger.error("❌ Resposta do Mercado Pago sem qr_code ou ID válido.")
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Não foi possível recuperar os dados do Pix. Por favor, tente novamente em instantes."
            )
            return

        try:
            supabase.table("pagamentos_pix").insert({
                "chat_id": str(user_id),
                "pix_id": str(mp_payment_id),
                "valor": float(valor),
                "tipo_plano": plano_chave,
                "status": "pending"
            }).execute()
        except Exception as e_db:
            logger.warning(f"⚠️ Aviso ao registrar pagamento na tabela pagamentos_pix: {e_db}")

        legenda_mensagem = (
            f"💳 <b>{nome_plano.upper()} — VigiaSaude</b>\n\n"
            f"• <b>Valor:</b> R$ {valor:.2f}\n"
            f"• <b>Liberação:</b> Instantânea após a confirmação\n\n"
            f"Aponte a câmera do seu aplicativo bancário para o QR Code acima ou utilize o código Copia e Cola abaixo:"
        )

        if qr_code_base64:
            img_bytes = base64.b64decode(qr_code_base64)
            img_io = io.BytesIO(img_bytes)
            img_io.name = "qrcode_pix.png"

            await context.bot.send_photo(
                chat_id=chat_id,
                photo=img_io,
                caption=legenda_mensagem,
                parse_mode="HTML"
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=legenda_mensagem,
                parse_mode="HTML"
            )

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"`{pix_copia_cola}`",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"❌ Exceção ao gerar Pix: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Ocorreu um erro inesperado ao gerar a cobrança Pix. Tente novamente em instantes."
        )