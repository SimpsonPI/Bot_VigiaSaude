import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import supabase

logger = logging.getLogger(__name__)

# Chave de acesso do Mercado Pago
MP_TOKEN = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")

async def gerar_pagamento_pix(update: Update, context: ContextTypes.DEFAULT_TYPE, plano_chave: str, preco: float):
    """Gera o Pix direto pela API do Mercado Pago, sem SDK."""
    query = update.callback_query
    if query:
        await query.answer()
        
    user_id = update.effective_user.id
    nome = update.effective_user.first_name or "Cliente"
    
    url = "https://api.mercadopago.com/v1/payments"
    headers = {
        "Authorization": f"Bearer {MP_TOKEN}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": f"pix_{user_id}_{plano_chave}"
    }
    
    payload = {
        "transaction_amount": float(preco),
        "description": f"VigiaSaude - Plano {plano_chave}",
        "payment_method_id": "pix",
        "payer": {
            "email": f"user_{user_id}@vigiasaude.com.br",
            "first_name": nome,
            "identification": {"type": "CPF", "number": "00000000000"} # CPF fictício para testes
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        dados = response.json()
        
        if response.status_code in [200, 201]:
            qr_code = dados["point_of_interaction"]["transaction_data"]["qr_code"]
            qr_code_base64 = dados["point_of_interaction"]["transaction_data"]["qr_code_base64"]
            payment_id = dados["id"]
            
            # Salva no Supabase (ajuste o nome da tabela se necessário)
            supabase.table("pagamentos_pix").upsert({
                "chat_id": str(user_id),
                "payment_id": str(payment_id),
                "status": "pending",
                "plano": plano_chave,
                "valor": preco
            }).execute()
            
            import base64
            foto = base64.b64decode(qr_code_base64)
            
            await context.bot.send_photo(
                chat_id=user_id,
                photo=foto,
                caption=f"💳 <b>Pagamento via Pix</b>\n\nPlano: {plano_chave}\nValor: R$ {preco:.2f}\n\n<i>Escaneie o QR Code ou use o código copia e cola.</i>\n\n<code>{qr_code}</code>",
                parse_mode="HTML"
            )
        else:
            logger.error(f"Erro MP: {dados}")
            await context.bot.send_message(chat_id=user_id, text="❌ Erro ao gerar o Pix. Tente novamente mais tarde.")
            
    except Exception as e:
        logger.error(f"Erro no pagamento: {e}")
        await context.bot.send_message(chat_id=user_id, text="❌ Erro de conexão com o Mercado Pago.")
