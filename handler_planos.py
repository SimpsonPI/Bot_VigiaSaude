import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from database import supabase

logger = logging.getLogger(__name__)

async def obter_menu_planos(user_id: int) -> InlineKeyboardMarkup:
    """Gera os botões de planos verificando se a degustação foi usada no Supabase."""
    ja_usou_degustacao = False

    try:
        res = (
            supabase.table("assinaturas")
            .select("usou_degustacao", "tipo_plano")
            .eq("chat_id", str(user_id))
            .execute()
        )
        if res.data:
            for row in res.data:
                if (
                    row.get("usou_degustacao") is True
                    or row.get("tipo_plano") == "degustacao"
                ):
                    ja_usou_degustacao = True
                    break
    except Exception as e:
        logger.error(f"Erro ao verificar degustação no Supabase: {e}")
        ja_usou_degustacao = True

    keyboard = []

    if not ja_usou_degustacao:
        keyboard.append([
            InlineKeyboardButton(
                "🎁 Plano Degustação (Grátis)", callback_data="plano_degustacao"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⭐ Plano Semestral (R$ 9,99)", callback_data="plano_semestral"
        )
    ])
    keyboard.append([
        InlineKeyboardButton(
            "🚀 Plano Anual (R$ 14,99)", callback_data="plano_anual"
        )
    ])
    keyboard.append([
        InlineKeyboardButton(
            "💬 Falar com Comercial", url="https://wa.me/5586994083113"
        )
    ])

    return InlineKeyboardMarkup(keyboard)

def usuario_tem_acesso(plano_info: dict) -> bool:
    """Valida se o usuário possui acesso liberado (Cortesia, Degustação ou Pago)."""
    status_bruto = str(plano_info.get("status", "")).strip().lower()
    tipo_plano = str(plano_info.get("tipo_plano", "")).strip().lower()
    usou_degustacao = plano_info.get("usou_degustacao", False)

    is_cortesia = tipo_plano == "cortesia"
    is_degustacao = tipo_plano == "degustacao"

    return (
        is_cortesia
        or (is_degustacao and (usou_degustacao or status_bruto == "ativo"))
        or (status_bruto == "ativo")
    )

async def comando_planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe o menu de planos adaptado para Degustação, Cortesia VIP, Pago ou Sem Plano."""
    user_id = update.effective_user.id
    chat_id_str = str(user_id)

    try:
        res = (
            supabase.table("assinaturas")
            .select("*")
            .eq("chat_id", chat_id_str)
            .order("created_at", desc=True)
            .execute()
        )
        dados = res.data if res and hasattr(res, "data") else []
    except Exception as e:
        logger.error(f"Erro ao consultar assinaturas para {chat_id_str}: {e}")
        dados = []

    plano_info = dados[0] if dados else {}
    
    tipo_plano = str(plano_info.get("tipo_plano", "")).strip().lower()
    is_cortesia = tipo_plano == "cortesia"
    is_degustacao = tipo_plano == "degustacao"
    is_ativo = usuario_tem_acesso(plano_info)

    if is_ativo and not is_degustacao:
        tipo_formatado = "Cortesia VIP 👑" if is_cortesia else f"Pro ({tipo_plano.capitalize()})"
        limite = plano_info.get("limite_ids", "Ilimitado")

        texto = (
            "✨ <b>Sua Assinatura está Ativa!</b>\n\n"
            f"• <b>Plano Atual:</b> {tipo_formatado}\n"
            "• <b>Status:</b> Ativo 🟢\n"
            f"• <b>Limite de Monitoramentos:</b> {limite}\n\n"
            "Você já conta com acesso completo para acompanhar suas consultas e exames!"
        )
        teclado = None

    elif is_ativo and is_degustacao:
        texto = (
            "🎁 <b>Você está utilizando o Plano Degustação (Grátis)!</b>\n\n"
            "Seu período de teste está <b>ativo</b> no VigiaSaude.\n"
            "• <b>Limite Atual:</b> Até 2 regulações cadastradas\n\n"
            "💡 <i>Se desejar ampliar seu limite de monitoramentos, consulte nossos planos Pro abaixo:</i>"
        )
        teclado = await obter_menu_planos(user_id)

    else:
        texto = (
            "💳 <b>Planos e Assinaturas — VigiaSaude</b>\n\n"
            "Acompanhe suas consultas e exames sem preocupações. Escolha o plano ideal "
            "para você e receba notificações instantâneas no seu Telegram assim que sua regulação andar!\n\n"
            "<i>Selecione uma das opções abaixo para ver mais detalhes:</i>"
        )
        teclado = await obter_menu_planos(user_id)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)
    else:
        await update.message.reply_text(texto, parse_mode="HTML", reply_markup=teclado)

async def detalhar_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ativa a degustação ou exibe opções de pagamento via Pix."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    data = query.data
    telegram_id = query.from_user.id

    if data == "plano_degustacao":
        try:
            supabase.table("assinaturas").upsert(
                {
                    "chat_id": str(telegram_id),
                    "tipo_plano": "degustacao",
                    "status": "ativo",
                    "limite_ids": 2,
                    "usou_degustacao": True,
                },
                on_conflict="chat_id",
            ).execute()
            logger.info(f"✅ Degustação ativada no Supabase para: {telegram_id}")
        except Exception as err:
            logger.error(f"❌ Erro ao gravar degustação no Supabase: {err}")

        texto = (
            "🎁 <b>Plano Degustação Ativado!</b>\n\n"
            "Seu período de teste gratuito já está funcionando.\n\n"
            "• <b>Status:</b> Ativo\n"
            "• <b>Capacidade:</b> Até 2 regulações cadastradas\n"
            "• <b>Alertas:</b> Notificações diretas no Telegram\n\n"
            "Aproveite os recursos da plataforma!"
        )

        keyboard_botoes = [
            [InlineKeyboardButton("⚡ Ver Planos Pro", callback_data="planos")]
        ]

    elif data == "plano_semestral":
        texto = (
            "⭐ <b>Plano Semestral</b>\n\n"
            "• <b>Monitoramento Contínuo:</b> Notificações automáticas via Telegram.\n"
            "• <b>Capacidade:</b> Até 5 regulações cadastradas.\n\n"
            "<b>Valor:</b> R$ 9,99 / semestre"
        )
        keyboard_botoes = [
            [InlineKeyboardButton("💳 Pagar via Pix", callback_data="pix_pro_semestral")],
            [InlineKeyboardButton("⬅️ Voltar aos Planos", callback_data="planos")],
        ]

    elif data == "plano_anual":
        texto = (
            "🚀 <b>Plano Anual</b>\n\n"
            "• <b>Monitoramento Contínuo:</b> Notificações automáticas por 12 meses.\n"
            "• <b>Capacidade Ampliada:</b> Até 9 regulações cadastradas.\n\n"
            "<b>Valor:</b> R$ 14,99 / ano"
        )
        keyboard_botoes = [
            [InlineKeyboardButton("💳 Pagar via Pix", callback_data="pix_pro_anual")],
            [InlineKeyboardButton("⬅️ Voltar aos Planos", callback_data="planos")],
        ]
    else:
        texto = "Opção inválida."
        keyboard_botoes = [
            [InlineKeyboardButton("⬅️ Voltar", callback_data="planos")]
        ]

    await query.edit_message_text(
        text=texto,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard_botoes),
    )

    async def verificar_vencimentos(app):
    """Verifica assinaturas que vencem em 1 dia e envia alerta."""
    from datetime import datetime, timedelta, timezone
    import asyncio
    
    agora = datetime.now(timezone.utc)
    alvo = agora + timedelta(days=1)  # vence em 1 dia
    
    try:
        # Busca assinaturas ativas que ainda não expiraram
        res = supabase.table("assinaturas").select("*").eq("status", "active").execute()
        for assinatura in res.data:
            venc = assinatura.get("data_vencimento")
            if not venc:
                continue
            venc_dt = datetime.fromisoformat(venc.replace("Z", "+00:00"))
            # Se faltar exatamente 1 dia (ou menos) para vencer
            if venc_dt <= alvo and venc_dt > agora:
                chat_id = assinatura["chat_id"]
                tipo = assinatura.get("tipo_plano", "")
                # Mensagem personalizada
                if tipo == "degustacao":
                    msg = "⚠️ Seu plano degustação expira amanhã! Aproveite e assine um plano Pro para continuar monitorando suas regulações."
                else:
                    msg = "⚠️ Seu plano Pro expira amanhã! Renove para não perder o acesso."
                
                teclado = InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Ver Planos", callback_data="planos")]
                ])
                try:
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        reply_markup=teclado,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Erro ao enviar alerta para {chat_id}: {e}")
    except Exception as e:
        logger.error(f"Erro na verificação de vencimentos: {e}")