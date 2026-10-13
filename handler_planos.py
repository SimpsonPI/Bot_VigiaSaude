import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from database import supabase
import planos_config as pc

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
                    or pc.normalizar(row.get("tipo_plano")) == "degustacao"
                ):
                    ja_usou_degustacao = True
                    break
    except Exception as e:
        logger.error(f"Erro ao verificar degustação no Supabase: {e}")
        ja_usou_degustacao = True

    keyboard = []

    # Botão de degustação só se ainda não usou
    if not ja_usou_degustacao:
        keyboard.append([
            InlineKeyboardButton(
                pc.nome_botao("degustacao"), callback_data="plano_degustacao"
            )
        ])

    # Planos pagos — sempre aparecem
    for p in pc.planos_pagos():
        keyboard.append([
            InlineKeyboardButton(p["nome_botao"], callback_data=f"plano_{p['chave']}")
        ])

    return InlineKeyboardMarkup(keyboard)


def usuario_tem_acesso(plano_info: dict, user_id: int = None) -> bool:
    """Valida se o usuário possui acesso liberado (Cortesia, Degustação ou Pago)."""
    # 👑 Admin tem acesso total, sempre
    if user_id is not None:
        try:
            from config import is_admin
            if is_admin(user_id):
                logger.info(f"👑 Bypass admin em usuario_tem_acesso (planos) (user={user_id})")
                return True
        except Exception:
            pass

    status_bruto = str(plano_info.get("status", "")).strip().lower()
    tipo_plano = pc.normalizar(plano_info.get("tipo_plano"))
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
    tipo_plano = pc.normalizar(plano_info.get("tipo_plano"))
    is_cortesia = tipo_plano == "cortesia"
    is_degustacao = tipo_plano == "degustacao"
    is_ativo = usuario_tem_acesso(plano_info, user_id)

    if is_ativo and not is_degustacao:
        nome_plano_atual = pc.nome(tipo_plano) if tipo_plano != "cortesia" else "Cortesia VIP 👑"
        limite = plano_info.get("limite_ids") or "Ilimitado"

        venc = plano_info.get("data_vencimento")
        if venc:
            try:
                from datetime import datetime
                data_v = datetime.fromisoformat(venc.replace("Z", "+00:00"))
                venc_txt = data_v.strftime("%d/%m/%Y")
            except Exception:
                venc_txt = "—"
        else:
            venc_txt = "Sem vencimento" if is_cortesia else "—"

        texto = (
            "✨ <b>Sua Assinatura está Ativa!</b>\n\n"
            f"• <b>Plano Atual:</b> {nome_plano_atual}\n"
            "• <b>Status:</b> Ativo 🟢\n"
            f"• <b>Limite de Monitoramentos:</b> {limite}\n"
            f"• <b>Válido até:</b> {venc_txt}\n\n"
            "Você já conta com acesso completo para acompanhar suas consultas e exames!"
        )
        teclado = None

    elif is_ativo and is_degustacao:
        texto = (
            "🎁 <b>Você está utilizando o Plano Degustação (Grátis)!</b>\n\n"
            "Seu período de teste está <b>ativo</b> no VigiaSaúde.\n"
            "• <b>Limite Atual:</b> Até 2 regulações cadastradas\n\n"
            "💡 <i>Se desejar ampliar seu limite de monitoramentos, consulte nossos planos Pro abaixo:</i>"
        )
        teclado = await obter_menu_planos(user_id)

    else:
        texto = (
            "💳 <b>Planos e Assinaturas — VigiaSaúde</b>\n\n"
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

    # ─── Degustação ───
    if data == "plano_degustacao":
        try:
            supabase.table("assinaturas").upsert(
                {
                    "chat_id": str(telegram_id),
                    "tipo_plano": "degustacao",
                    "status": "ativo",
                    "limite_ids": pc.limite("degustacao"),
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
            f"• <b>Status:</b> Ativo\n"
            f"• <b>Capacidade:</b> Até {pc.limite('degustacao')} regulações cadastradas\n"
            "• <b>Alertas:</b> Notificações diretas no Telegram\n\n"
            "Aproveite os recursos da plataforma!"
        )
        keyboard_botoes = [
            [InlineKeyboardButton("⚡ Ver Planos Pro", callback_data="planos")]
        ]

    # ─── Planos pagos ───
    elif data.startswith("plano_"):
        plano_chave = data.replace("plano_", "")
        plano = pc.get(plano_chave)

        if not plano:
            texto = "Opção inválida."
            keyboard_botoes = [[InlineKeyboardButton("⬅️ Voltar", callback_data="planos")]]
        else:
            periodo_txt = {
                30: "mês",
                90: "trimestre",
                180: "semestre",
            }.get(plano["dias"], f"{plano['dias']} dias")

            badge = f"\n{plano['badge']}" if plano.get("badge") else ""

            texto = (
                f"{plano['emoji']} <b>{plano['nome']} ({plano['dias']} dias)</b>{badge}\n\n"
                f"• <b>Monitoramento Contínuo:</b> Notificações automáticas via Telegram.\n"
                f"• <b>Capacidade:</b> Até {plano['limite_ids']} regulações cadastradas.\n"
                f"• <b>Perfil:</b> {plano['subtitulo']}\n\n"
                f"<b>Valor:</b> R$ {plano['preco']:.2f} / {periodo_txt}"
            )
            keyboard_botoes = [
                [InlineKeyboardButton("💳 Pagar via Pix", callback_data=f"pix_{plano_chave}")],
                [InlineKeyboardButton("⬅️ Voltar aos Planos", callback_data="planos")],
            ]

    else:
        texto = "Opção inválida."
        keyboard_botoes = [[InlineKeyboardButton("⬅️ Voltar", callback_data="planos")]]

    await query.edit_message_text(
        text=texto,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard_botoes),
    )