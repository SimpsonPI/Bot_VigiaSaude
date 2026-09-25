import asyncio
from html import escape
import logging
from time import timezone
import warnings

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.warnings import PTBUserWarning

# Silencia os avisos de rastreamento do ConversationHandler
warnings.filterwarnings("ignore", category=PTBUserWarning)

from config import TELEGRAM_BOT_TOKEN, BOT_SUPORTE_LINK
from handler_consultas import _montar_msg_html
from database import (
    ativar_ou_atualizar_assinatura,
    atualizar_campo_regulacao,
    buscar_todas_regulacoes_ativas,
    desativar_regulacoes_por_chat_id,
    supabase,
)
from handler_cadastro import (
    iniciar_cadastro_manual,
    receber_cbo,
    receber_celular,
    receber_nascimento,
    receber_nome,
    receber_procedimento,
    receber_regulacao,
    receber_sus,
    finalizar_cadastro,
)

from handler_consultas import (
    comando_verificar_todas,
    iniciar_verificar_especifico,
    processar_verificar_especifico,
)

from handler_gestao import (
    confirmar_exclusao_callback,
    iniciar_corrigir,
    iniciar_excluir,
    salvar_novo_valor,
    selecionar_campo_callback,
    selecionar_regulacao_callback,
    selecionar_regulacao_excluir_callback,
)
from utils import (
    AGUARDAR_NOVO_VALOR,
    CONFIRMAR_EXCLUSAO,
    CONSULTAR_ID,
    ETAPA_CBO,
    ETAPA_CELULAR,
    ETAPA_LGPD,
    ETAPA_NASCIMENTO,
    ETAPA_NOME,
    ETAPA_PROCEDIMENTO,
    ETAPA_REGULACAO,
    ETAPA_SUS,
    SELECIONAR_CAMPO,
    SELECIONAR_REGULACAO,
    SELECIONAR_REGULACAO_EXCLUIR,
)

try:
    from scraper import consultar_status_fms, montar_mensagem_regulacao
except ImportError:

    async def consultar_status_fms(num_reg):
        return None

    def montar_mensagem_regulacao(*args, **kwargs):
        return ""


URL_TERMO_LGPD = "https://telegra.ph/DECLARA%C3%87%C3%83O-DE-INDEPEND%C3%8ANCIA-08-13"
VARREDURA_INTERVALO_MINUTOS = 120

logger = logging.getLogger(__name__)


# --- REMOÇÃO DO MENU FLUTUANTE ---
def obter_menu_principal():
    """Remove qualquer teclado persistente da tela do usuário."""
    return ReplyKeyboardRemove()


async def cancelar_operacao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela a operação atual e limpa os dados do usuário."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Operação cancelada.")
    elif update.message:
        await update.message.reply_text(
            "❌ Operação cancelada.", reply_markup=obter_menu_principal()
        )

    context.user_data.clear()
    context.user_data.pop("_em_fluxo_admin", None)   # ← ADICIONE
    return ConversationHandler.END


async def callback_faq_suporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🔵🔵🔵 FAQ CALLBACK RECEBIDO!", flush=True)  # ← ADICIONE ESTA LINHA
    query = update.callback_query
    await query.answer()

    faq_texto = (
        "❓ <b>FAQ e Central de Ajuda — VigiaSaude 2.5</b>\n\n"
        "<b>1. O que é o VigiaSaude 2.5?</b>\n"
        "Serviço independente de monitoramento. Não possuímos vínculo oficial com a FMS ou Prefeitura de Teresina, fazemos o monitoramento do andamento de suas regulações de saúde (consultas, exames e cirurgias) de forma automatizada.\n\n"
        "<b>2. Como o bot rastreia minhas solicitações?</b>\n"
        "Utilizamos os dados informados por você (como o número da regulação) para verificar atualizações diretamente nos sistemas públicos.\n\n"
        "<b>3. Meus dados estão seguros?</b>\n"
        "Sim! Suas informações são tratadas com total privacidade, seguindo diretrizes rígidas de segurança e LGPD.\n\n"
        "<b>4. Como faço para corrigir um número ou procedimento?</b>\n"
        "Basta utilizar o comando /corrigir no menu principal para atualizar dados como Especialidade, celular ou nome do paciente.\n\n"
        "<b>5. O bot substitui a fila oficial do SUS?</b>\n"
        "Não. O VigiaSaude é um facilitador de avisos e consultas. A marcação, chamada e gestão de vagas continuam sob responsabilidade exclusiva da Secretaria de Saúde.\n\n"
        "<b>6. Como posso falar com o suporte humano?</b>\n"
        "Caso tenha problemas técnicos, envie uma mensagem diretamente para nossa equipe de atendimento."
    )

    teclado_volta = InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Voltar", callback_data="privacidade_voltar")]]
    )

    try:
        await query.edit_message_text(
            faq_texto, parse_mode="HTML", reply_markup=teclado_volta
        )
    except Exception as e:
        logger.error(f"Erro ao exibir FAQ: {e}")


async def callback_privacidade_voltar(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Retorna para a tela inicial de privacidade."""
    query = update.callback_query
    await query.answer()

    texto = "Clique no botão abaixo para ler a nossa Política de Privacidade e Termos de Uso:"
    teclado = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔒 Abrir Política de Privacidade e Termos",
                    callback_data="abrir_termo_privacidade",
                )
            ],
            [
                InlineKeyboardButton(
                    "💬 Dúvidas / Suporte (FAQ)", callback_data="abrir_faq_suporte"
                )
            ],
        ]
    )

    await query.edit_message_text(texto, reply_markup=teclado)


async def callback_abrir_termo_privacidade(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Envia o link da Política de Privacidade e Termos de Uso."""
    query = update.callback_query
    await query.answer()

    texto = (
        "🔒 <b>Política de Privacidade e Termos de Uso</b>\n\n"
        "Acesse o documento completo no link abaixo:\n\n"
        f'👉 <a href="{URL_TERMO_LGPD}">Abrir Política de Privacidade</a>'
    )

    await query.message.reply_text(
        texto, parse_mode="HTML", disable_web_page_preview=False
    )


# --- HANDLER DO COMANDO /START E /INICIAR ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal do /start ou /iniciar."""
    user = update.effective_user
    nome = user.first_name or "Usuário"

    mensagem = (
        f"👋 Olá, <b>{nome}</b>! Bem-vindo (a) ao <b>VigiaSaude</b>.\n\n"
        f"🆔 <b>Seu ID do Telegram:</b> <code>{user.id}</code>\n\n"
        "Acesse todas as opções e comandos diretamente pelo menu nativo do Telegram "
        "(botão <b>[/]</b> ao lado da barra de digitação)."
    )

    await update.message.reply_text(
        mensagem, reply_markup=obter_menu_principal(), parse_mode="HTML"
    )


# --- TECLADO E LÓGICA COMERCIAL DE PLANOS ---
async def obter_menu_planos(user_id: int) -> InlineKeyboardMarkup:
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
        logger.error(f"Erro ao verificar degustação: {e}")
        ja_usou_degustacao = True

    keyboard = []
    if not ja_usou_degustacao:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🎁 Ativar Degustação (7 dias grátis)",
                    callback_data="plano_degustacao",
                )
            ]
        )
    keyboard.append(
        [
            InlineKeyboardButton(
                "⭐ Plano Trimestral (R$ 9,99)", callback_data="plano_trimestral"
            )
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                "🚀 Plano Semestral (R$ 14,99)", callback_data="plano_semestral"
            )
        ]
    )
    keyboard.append(
        [InlineKeyboardButton("📧 Email de Suporte", callback_data="atendimento_email")]
    )
    return InlineKeyboardMarkup(keyboard)


def usuario_tem_acesso(plano_info: dict) -> bool:
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
    """Tela unificada: mostra status atual + planos disponíveis para assinatura."""
    user_id = update.effective_user.id
    chat_id_str = str(user_id)

    # ─── Busca dados do usuário no Supabase ───
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
        logger.error(f"Erro ao consultar assinaturas: {e}")
        dados = []

    plano_info = dados[0] if dados else {}
    tipo_plano = str(plano_info.get("tipo_plano", "")).strip().lower()
    is_cortesia = tipo_plano == "cortesia"
    is_degustacao = tipo_plano == "degustacao"
    is_ativo = usuario_tem_acesso(plano_info)

    # ─── Calcula dias restantes ───
    from datetime import datetime, timezone

    venc = plano_info.get("data_vencimento")
    dias_restantes = None
    venc_txt = None

    if venc:
        try:
            venc_dt = datetime.fromisoformat(str(venc).replace("Z", "+00:00"))
            dias_restantes = max(0, (venc_dt - datetime.now(timezone.utc)).days)
            venc_txt = venc_dt.strftime("%d/%m/%Y")
        except Exception:
            pass

    # ─── Monta o cabeçalho com o status atual ───
    if is_cortesia:
        cabecalho = (
            "👑 <b>Você é Cortesia VIP!</b>\n\n"
            "• <b>Plano:</b> Cortesia (Ilimitado)\n"
            "• <b>Status:</b> Ativo 🟢\n"
            "• <b>Vencimento:</b> Sem vencimento\n"
        )
    elif is_degustacao and is_ativo:
        dias_txt = f"{dias_restantes} dia(s)" if dias_restantes is not None else "?"
        cabecalho = (
            "🎁 <b>Você está na Degustação (Grátis)</b>\n\n"
            "• <b>Plano:</b> Degustação\n"
            "• <b>Status:</b> Ativo 🟢\n"
            f"• <b>Vence em:</b> {venc_txt or '—'}\n"
            f"• <b>Dias restantes:</b> {dias_txt}\n"
        )
    elif is_ativo:
        nomes_planos = {
            "pro": "Pro",
            "pro_trimestral": "Pro Trimestral",
            "trimestral": "Pro Trimestral",
            "pro_semestral": "Pro Semestral",
            "semestral": "Pro Semestral",
        }
        tipo_formatado = nomes_planos.get(tipo_plano, "Pro")
        dias_txt = f"{dias_restantes} dia(s)" if dias_restantes is not None else "—"

        # Alerta se estiver perto de vencer
        alerta_venc = ""
        if dias_restantes is not None and dias_restantes <= 3:
            alerta_venc = "\n⚠️ <b>Atenção: seu plano está prestes a vencer!</b>\n"

        cabecalho = (
            f"✨ <b>Sua Assinatura está Ativa!</b>\n\n"
            f"• <b>Plano:</b> {tipo_formatado}\n"
            f"• <b>Status:</b> Ativo 🟢\n"
            f"• <b>Vence em:</b> {venc_txt or '—'}\n"
            f"• <b>Dias restantes:</b> {dias_txt}\n"
            f"{alerta_venc}"
        )
    else:
        cabecalho = (
            "💳 <b>Você ainda não possui um plano ativo</b>\n\n"
            "Ative uma degustação gratuita ou assine um dos nossos planos.\n"
        )

    # ─── Monta o bloco de planos disponíveis ───
    planos_txt = (
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💎 <b>Planos Disponíveis</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "• ⭐ <b>Trimestral</b> — R$ 9,99 (3 meses)\n"
        "  <i>Até 5 regulações monitoradas</i>\n\n"
        "• 🚀 <b>Semestral</b> — R$ 14,99 (6 meses)\n"
        "  <i>Até 9 regulações monitoradas</i>\n\n"
        "💠 <b>Pagamento:</b> Pix (QR Code ou Copia e Cola)\n"
        "⚡ <b>Liberação:</b> Instantânea após a confirmação\n"
    )

    # ─── Junta tudo ───
    texto_final = cabecalho + planos_txt

    # ─── Cria os botões ───
    teclado = await obter_menu_planos(user_id)

    # ─── Envia ───
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                texto_final, parse_mode="HTML", reply_markup=teclado
            )
        except Exception:
            await update.callback_query.message.reply_text(
                texto_final, parse_mode="HTML", reply_markup=teclado
            )
    else:
        await update.message.reply_text(
            texto_final, parse_mode="HTML", reply_markup=teclado
        )


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
        from datetime import datetime, timezone, timedelta

        agora = datetime.now(timezone.utc)
        vencimento = agora + timedelta(days=7)

        try:
            supabase.table("assinaturas").upsert(
                {
                    "chat_id": str(telegram_id),
                    "tipo_plano": "degustacao",
                    "status": "ativo",
                    "data_vencimento": vencimento.isoformat(),
                    "limite_ids": 999,
                    "usou_degustacao": True,
                    "ultimo_aviso": None,
                },
                on_conflict="chat_id",
            ).execute()
        except Exception as err:
            logger.error(f"Erro ao gravar degustação: {err}")

        texto = (
            "🎁 <b>Degustação Ativada — 7 dias grátis!</b>\n\n"
            f"Você tem acesso completo ao VigiaSaúde até <b>{vencimento.strftime('%d/%m/%Y')}</b>.\n\n"
            "<b>O que você ganha assinando:</b>\n"
            "✅ Monitoramento ilimitado das regulações\n"
            "✅ Avisos automáticos de mudança de status\n"
            "✅ Suporte prioritário\n\n"
            "Aproveite os 7 dias — e assine antes do fim para não perder o acesso:"
        )
        keyboard_botoes = [
            [
                InlineKeyboardButton(
                    "⭐ Trimestral (R$ 9,99)", callback_data="plano_trimestral"
                )
            ],
            [
                InlineKeyboardButton(
                    "🚀 Semestral (R$ 14,99)", callback_data="plano_semestral"
                )
            ],
            [InlineKeyboardButton("💳 Ver todos os planos", callback_data="planos")],
        ]

    elif data == "plano_trimestral":
        texto = "⭐ <b>Plano Trimestral</b>\n\n• Até 5 regulações.\n<b>Valor:</b> R$ 9,99 / trimestre"
        keyboard_botoes = [
            [InlineKeyboardButton("💳 Pagar via Pix", callback_data="pix_trimestral")],
            [InlineKeyboardButton("⬅️ Voltar aos Planos", callback_data="planos")],
        ]

    elif data == "plano_semestral":
        texto = "🚀 <b>Plano Semestral</b>\n\n• Até 9 regulações.\n<b>Valor:</b> R$ 14,99 / semestre"
        keyboard_botoes = [
            [InlineKeyboardButton("💳 Pagar via Pix", callback_data="pix_semestral")],
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

def verificar_plano_ativo(user_id: int) -> tuple[bool, dict]:
    """
    Verifica se o usuário tem plano ativo.
    Retorna (ativo: bool, info: dict)
    """
    from datetime import datetime, timezone
    from database import supabase

    try:
        res = (
            supabase.table("assinaturas")
            .select("*")
            .eq("chat_id", str(user_id))
            .order("created_at", desc=True)
            .execute()
        )
        dados = res.data if res and hasattr(res, "data") else []
    except Exception as e:
        logger.error(f"Erro ao verificar plano: {e}")
        return False, {}

    if not dados:
        return False, {}

    info = dados[0]
    status = str(info.get("status", "")).strip().lower()
    tipo = str(info.get("tipo_plano", "")).strip().lower()

    # Cortesia sempre ativa
    if tipo == "cortesia":
        return True, info

    # Status precisa ser ativo
    if status not in ("ativo", "active", "ativa"):
        return False, info

    # Verifica vencimento
    venc = info.get("data_vencimento")
    if not venc:
        return False, info

    try:
        venc_dt = datetime.fromisoformat(str(venc).replace("Z", "+00:00"))
        from datetime import timedelta
        if datetime.now(timezone.utc) >= (venc_dt - timedelta(hours=12)):
            return False, info
    except Exception as e:
        logger.error(f"Erro ao parsear vencimento: {e}")
        return False, info

    return True, info


async def enviar_alerta_plano_expirado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia mensagem acolhedora informando que o plano expirou."""
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Ver Planos e Renovar", callback_data="planos")],
        [InlineKeyboardButton("❓ Tirar dúvidas", callback_data="atendimento_faq")],
        [InlineKeyboardButton("👤 Falar com Atendente", callback_data="atendimento_humanizado")],
    ])

    texto = (
        "🕊️ <b>Olá! Sentimos sua falta por aqui...</b>\n\n"
        "Percebemos que seu plano do <b>VigiaSaúde</b> chegou ao fim, "
        "mas não se preocupe — é rapidinho para reativar! 💙\n\n"

        "🌟 <b>O que você perde quando o plano expira:</b>\n"
        "• 🔕 <b>Sem alertas automáticos</b> — você não será mais avisado quando sua regulação mudar de status\n"
        "• 📊 <b>Sem consultas rápidas</b> — o status das suas regulações fica indisponível\n"
        "• 🏥 <b>Sem monitoramento contínuo</b> — você pode perder prazos importantes\n\n"

        "💚 <b>Reative agora e continue no controle:</b>\n"
        "• ⭐ <b>Trimestral</b> — R$ 9,99 (3 meses)\n"
        "• 🚀 <b>Semestral</b> — R$ 14,99 (6 meses)\n\n"

        "🎁 <i>Renovação em menos de 1 minuto, direto pelo Pix.</i>\n\n"

        "Toque em <b>\"Ver Planos e Renovar\"</b> abaixo para continuar cuidando da sua saúde. 💙"
    )

    if update.callback_query:
        try:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(texto, parse_mode="HTML", reply_markup=teclado)
        except Exception:
            await update.callback_query.message.reply_text(texto, parse_mode="HTML", reply_markup=teclado)
    elif update.message:
        await update.message.reply_text(texto, parse_mode="HTML", reply_markup=teclado)

async def comando_privacidade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teclado = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔒 Abrir Política de Privacidade e Termos",
                    callback_data="abrir_termo_privacidade",
                )
            ],
            [
                InlineKeyboardButton(
                    "💬 Dúvidas / Suporte (FAQ)", callback_data="abrir_faq_suporte"
                )
            ],
        ]
    )
    texto = "Clique no botão abaixo para ler a nossa Política de Privacidade e Termos de Uso:"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(texto, reply_markup=teclado)
    else:
        await update.message.reply_text(texto, reply_markup=teclado)


# --- FUNÇÕES DE AJUDA E SUPORTE ---
async def comando_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia o menu de ajuda e FAQs para o usuário."""
    texto = (
        "🤖 *Central de Ajuda e FAQ - VigiaSaude*\n\n"
        "Selecione uma das opções abaixo para tirar suas dúvidas ou obter suporte:"
    )

    teclado = [
        [InlineKeyboardButton("❓ O que é o VigiaSaude?", callback_data="faq_o_que_e")],
        [InlineKeyboardButton("🔍 Como rastrear?", callback_data="faq_rastrear")],
        [InlineKeyboardButton("🔒 Segurança de Dados", callback_data="faq_seguranca")],
        [InlineKeyboardButton("✏️ Como corrigir dados", callback_data="faq_corrigir")],
        [
            InlineKeyboardButton(
                "💬 Falar com Suporte", callback_data="abrir_faq_suporte"
            )
        ],
    ]
    reply_markup = InlineKeyboardMarkup(teclado)

    if update.message:
        await update.message.reply_text(
            texto, reply_markup=reply_markup, parse_mode="Markdown"
        )
    elif update.callback_query:
        await update.callback_query.message.edit_text(
            texto, reply_markup=reply_markup, parse_mode="Markdown"
        )


async def comando_suporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Central de Atendimento - Links, FAQs e Email"""
    texto = (
        "🤖 <b>Central de Atendimento VigiaSaude</b>\n\n"
        "Como podemos ajudar você hoje?\n\n"
        "<b>📌 Canais de Atendimento:</b>\n"
        "• 🤖 <b>Bot de Atendimento:</b> @central_vigiasaude_bot\n"
        "• 📧 <b>Email:</b> suportevigiasaude@gmail.com\n\n"
        "<b>❓ Perguntas Frequentes (FAQs):</b>\n"
        "1️⃣ Como cadastrar uma nova regulação?\n"
        "2️⃣ Como verificar o status das regulações?\n"
        "3️⃣ Onde encontrar o Cartão SUS ou ID?\n"
        "4️⃣ Como corrigir dados?\n"
        "5️⃣ Planos e Assinaturas\n"
        "6️⃣ O VigiaSaude tem vínculo com o governo?\n\n"
        "Selecione uma opção abaixo:"
    )

    teclado = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🤖 Bot de Atendimento", url=BOT_SUPORTE_LINK),
                InlineKeyboardButton("📧 Email", callback_data="mostrar_email_suporte"),
            ],
            [
                InlineKeyboardButton("1️⃣ Cadastrar", callback_data="faq_cadastrar"),
                InlineKeyboardButton("2️⃣ Consultar", callback_data="faq_consultar"),
            ],
            [
                InlineKeyboardButton("3️⃣ Cartão SUS/ID", callback_data="faq_id"),
                InlineKeyboardButton("4️⃣ Alterar Dados", callback_data="faq_alterar"),
            ],
            [
                InlineKeyboardButton("5️⃣ Planos", callback_data="faq_planos"),
                InlineKeyboardButton(
                    "6️⃣ Vínculo Governo", callback_data="faq_governo"
                ),
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Voltar ao Menu Principal", callback_data="iniciar"
                )
            ],
        ]
    )

    if update.message:
        await update.message.reply_text(texto, reply_markup=teclado, parse_mode="HTML")
    elif update.callback_query:
        await update.callback_query.message.edit_text(
            texto, reply_markup=teclado, parse_mode="HTML"
        )


async def voltar_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retorna para o menu principal de ajuda."""
    await callback_ajuda(update, context)


async def faq_o_que_e(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    texto = "💡 <b>O que é o VigiaSaude?</b>\n\nÉ uma ferramenta independente desenvolvida para facilitar o acompanhamento de status de solicitações de regulação junto aos sistemas públicos de saúde."
    teclado = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Voltar", callback_data="ajuda")]]
    )
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def faq_rastrear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    texto = (
        "🔍 <b>Como rastrear minha regulação?</b>\n\n"
        "Cadastre o número da sua solicitação (regulação) pelo menu. "
        "Depois, você pode usar a opção <b>'Verificar Específico'</b> para selecionar uma regulação cadastrada e checar o status, "
        "ou <b>'Verificar Todas'</b> para checar todas as suas regulações de uma só vez de forma automática."
    )
    teclado = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Voltar", callback_data="ajuda")]]
    )
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def faq_seguranca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    texto = "🔒 <b>Meus dados estão seguros?</b>\n\nSim! Informações sensíveis são tratadas com privacidade estrita seguindo a LGPD."
    teclado = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Voltar", callback_data="ajuda")]]
    )
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def faq_corrigir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    texto = "✏️ <b>Como corrigir dados?</b>\n\nUtilize o comando de correção no menu principal para atualizar informações cadastrais ou Especialidade (Especialidade)."
    teclado = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Voltar", callback_data="ajuda")]]
    )
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


def _deve_notificar(resultado_fms: dict, status_ant: str, posicao_ant: str) -> tuple[bool, str]:
    """
    Retorna (True, motivo) se deve notificar, ou (False, motivo) se não.
    """
    status_novo = str(resultado_fms.get("situacao") or "").strip()
    posicao_nova = str(resultado_fms.get("posicao_fila") or "").strip()
    status_ant = (status_ant or "").strip()
    posicao_ant = (posicao_ant or "").strip()

    status_lower = status_novo.lower()
    posicao_lower = posicao_nova.lower()

    # 1. VENCIDA — só notifica UMA vez
    if "vencid" in status_lower or "expirad" in status_lower:
        if "vencid" in status_ant.lower() or "expirad" in status_ant.lower():
            return False, "vencida_ja_avisada"
        return True, "vencida_1x"

    # 2. REATIVAÇÃO — notifica se o status mudou
    if "reativa" in status_lower:
        if status_lower != status_ant.lower():
            return True, "reativacao"
        return False, "sem_mudanca"

    # 3. MUDANÇA DE STATUS
    if status_lower != status_ant.lower():
        return True, "status_mudou"

    # 4. MUDANÇA DE POSIÇÃO NA FILA
    if (
        posicao_nova
        and posicao_lower not in ("não informada", "n/i", "nao informada", "")
        and posicao_nova != posicao_ant
    ):
        return True, "posicao_mudou"

    return False, "sem_mudanca"


async def executar_varredura_automatica(context: ContextTypes.DEFAULT_TYPE):
    """Varredura automática: diferencia status (completo) de fila (simples).
    Só roda se passou pelo menos 6h desde a última execução (proteção contra restart)."""
    from teaser_storage import pode_enviar_teaser, registrar_envio_teaser
    from datetime import datetime, timezone

    # ═══════════════════════════════════════════════════════════
    # 🚩 PROTEÇÃO: só roda se passou 6h desde a última varredura
    # ═══════════════════════════════════════════════════════════
    try:
        from database import supabase as sb_check
        res_check = sb_check.table("config_sistema").select("valor").eq("chave", "ultima_varredura").execute()
        if res_check.data:
            ultima_str = res_check.data[0]["valor"]
            ultima = datetime.fromisoformat(str(ultima_str).replace("Z", "+00:00"))
            diff_seg = (datetime.now(timezone.utc) - ultima).total_seconds()
            if diff_seg < 6 * 3600 - 60:  # margem de 60s
                logger.info(
                    f"⏭️ Varredura ignorada: última rodou há {diff_seg/60:.0f} min "
                    f"(<6h). Reinício não vai duplicar notificações."
                )
                return
    except Exception as e:
        logger.warning(f"Erro ao checar última varredura: {e}")

    # Registra que a varredura vai rodar AGORA
    try:
        from database import supabase as sb_save
        sb_save.table("config_sistema").upsert({
            "chave": "ultima_varredura",
            "valor": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        logger.warning(f"Erro ao salvar timestamp da varredura: {e}")

    # ═══════════════════════════════════════════════════════════
    # VARREDURA (código original)
    # ═══════════════════════════════════════════════════════════
    logger.info("🔍 Varredura automática iniciada...")

    try:
        regulacoes = buscar_todas_regulacoes_ativas()
        if not regulacoes:
            logger.info("Nenhuma regulação ativa para verificar.")
            return

        # Deduplicação por (numero_reg + chat_id)
        unicos = {}
        for reg in regulacoes:
            num = str(reg.get("numero_reg") or "").strip()
            cid = str(reg.get("chat_id") or "").strip()
            if num and cid:
                unicos[f"{num}::{cid}"] = reg
        regulacoes = list(unicos.values())

        total = len(regulacoes)
        verificadas = 0
        notif_status = 0
        notif_fila = 0
        teasers = 0
        ignoradas = 0

        cache_fms: dict[str, dict] = {}
        mudancas_por_usuario: dict[str, list] = {}

        for reg in regulacoes:
            num_reg = reg.get("numero_reg")
            chat_id = reg.get("chat_id")
            status_ant = (reg.get("status_anterior") or "").strip()
            posicao_ant = (reg.get("posicao_anterior") or "").strip()

            if not num_reg or not chat_id:
                continue

            num_key = str(num_reg).strip()

            if num_key in cache_fms:
                resultado_fms = cache_fms[num_key]
            else:
                try:
                    resultado_fms = await consultar_status_fms(num_key)
                    cache_fms[num_key] = resultado_fms
                except Exception as e:
                    logger.error(f"Erro ao consultar {num_reg}: {e}")
                    continue

            if not (isinstance(resultado_fms, dict) and resultado_fms.get("sucesso")):
                continue

            verificadas += 1

            deve, motivo = _deve_notificar(resultado_fms, status_ant, posicao_ant)

            if not deve:
                logger.info(f"⏭️ {num_reg} (chat {chat_id}): ignorado ({motivo})")
                ignoradas += 1
                continue

            # Atualiza status no banco (para os dois casos)
            try:
                from database import supabase as sb
                status_novo = (resultado_fms.get("situacao") or "").strip()
                posicao_nova = (resultado_fms.get("posicao_fila") or "").strip()
                sb.table("AlertaSUS_2.0").update({
                    "status_anterior": status_novo,
                    "posicao_anterior": posicao_nova,
                }).eq("numero_reg", str(num_reg)).eq(
                    "chat_id", str(chat_id)
                ).execute()
            except Exception as e:
                logger.error(f"Erro ao salvar no banco: {e}")

            # Verifica se o usuário tem plano ativo
            ativo, info = verificar_plano_ativo(chat_id)

            if ativo:
                # 📩 Usuário ativo
                if motivo == "posicao_mudou":
                    # Apenas alerta simples de mudança de fila
                    logger.info(f"📊 {num_reg} (chat {chat_id}): notificando fila")
                    try:
                        msg = _montar_msg_fila_simples(str(num_reg), resultado_fms, reg)
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=msg,
                            parse_mode="HTML",
                        )
                        notif_fila += 1
                    except Exception as e:
                        logger.error(f"Erro ao notificar fila {chat_id}: {e}")
                else:
                    # Mudança de status → mensagem completa
                    logger.info(f"🔔 {num_reg} (chat {chat_id}): notificando status ({motivo})")
                    try:
                        msg = _montar_msg_html(
                            num_reg=str(num_reg),
                            resultado=resultado_fms,
                            reg_db=reg,
                            titulo="🔔 <b>ATUALIZAÇÃO DE REGULAÇÃO</b>",
                        )
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=msg,
                            parse_mode="HTML",
                        )
                        notif_status += 1
                    except Exception as e:
                        logger.error(f"Erro ao notificar status {chat_id}: {e}")
            else:
                # 🔒 Usuário expirado → acumula teaser
                logger.info(f"🎁 {num_reg} (chat {chat_id}): acumulando para teaser")
                mudancas_por_usuario.setdefault(str(chat_id), []).append({
                    "num_reg": num_reg,
                    "resultado": resultado_fms,
                    "reg_db": reg,
                    "motivo": motivo,
                })

            await asyncio.sleep(0.5)

        # ─── Envia teasers (1 por usuário) ───
        for chat_id, mudancas in mudancas_por_usuario.items():
            if not pode_enviar_teaser(chat_id):
                logger.info(f"⏭️ Teaser para {chat_id}: bloqueado (opt-out ou <24h)")
                continue

            try:
                msg = _montar_msg_teaser(mudancas)
                teclado = InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Ver Planos e Renovar", callback_data="planos")],
                    [InlineKeyboardButton("🔕 Não quero receber mais", callback_data="optout_teaser")],
                ])
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode="HTML",
                    reply_markup=teclado,
                )
                registrar_envio_teaser(chat_id)
                teasers += 1
                logger.info(f"🎁 Teaser enviado para {chat_id} ({len(mudancas)} mudanças)")
            except Exception as e:
                logger.error(f"Erro ao enviar teaser para {chat_id}: {e}")

            await asyncio.sleep(0.5)

        logger.info(
            f"✅ Varredura: {verificadas}/{total} verificadas | "
            f"{notif_status} status | {notif_fila} fila | {teasers} teasers | {ignoradas} ignoradas"
        )

    except Exception as e:
        logger.error(f"Erro na varredura automática: {e}")

def _montar_msg_fila_simples(num_reg: str, resultado: dict, reg_db: dict) -> str:
    """Mensagem simples apenas avisando que a posição na fila mudou."""
    num_esc = escape(str(num_reg))
    cbo = escape((reg_db.get("cbo") or "Não informado").upper())
    procedimento = escape((reg_db.get("procedimento") or "Não informado").upper())
    posicao = escape(str(resultado.get("posicao_fila") or "Não informada"))
    status = escape(str(resultado.get("situacao") or "—"))

    return (
        "📊 <b>ATUALIZAÇÃO NA FILA DE ESPERA</b>\n\n"
        f"🆔 <b>Regulação:</b> <code>{num_esc}</code>\n"
        f"🩺 <b>Especialidade:</b> {cbo}\n"
        f"🏥 <b>Procedimento:</b> {procedimento}\n\n"
        f"🔔 Sua posição na fila foi atualizada!\n"
        f"• <b>Posição atual:</b> {posicao}\n"
        f"• <b>Status:</b> {status}\n\n"
        f"<i>Você continua na fila. Assim que houver uma mudança de status, "
        f"avisaremos com mais detalhes.</i>"
    )

def _montar_msg_teaser(mudancas: list) -> str:
    """
    Monta mensagem teaser para usuários com plano expirado.
    mudancas: lista de dicts com num_reg, resultado, reg_db, motivo
    """
    total = len(mudancas)

    if total == 1:
        cabecalho = "🔔 <b>Olá! Uma novidade apareceu...</b>\n\n"
    else:
        cabecalho = f"🔔 <b>Olá! {total} novidades apareceram enquanto você esteve fora!</b>\n\n"

    # Lista de regulações que mudaram (sem detalhes)
    linhas_regs = ""
    for m in mudancas[:5]:  # máximo 5
        num = m["num_reg"]
        procedimento = (m["reg_db"].get("procedimento") or "Não informado").upper()
        linhas_regs += f"• <code>{num}</code> — {procedimento}\n"

    if total > 5:
        linhas_regs += f"• <i>...e mais {total - 5} regulação(ões)</i>\n"

    texto = (
        f"{cabecalho}"
        f"<b>Suas regulações com atualização:</b>\n"
        f"{linhas_regs}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 <b>Detalhes disponíveis apenas para assinantes</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚠️ Houve <b>mudança real</b> no status das suas regulações. "
        f"Para ver <b>o que mudou</b> (status, posição na fila, datas), "
        f"reative seu plano agora:\n\n"
        f"• ⭐ <b>Trimestral</b> — R$ 9,99 (3 meses)\n"
        f"• 🚀 <b>Semestral</b> — R$ 14,99 (6 meses)\n\n"
        f"⏱️ <i>Reativação em menos de 1 minuto via Pix.</i>"
    )

    return texto


# --- ALIASES ---
cancelar_corrigir = cancelar_operacao
cancelar_excluir = cancelar_operacao
cancelar_cadastro = cancelar_operacao

verificar_todos = comando_verificar_todas
verificar_especifico = iniciar_verificar_especifico
cadastrar_nova = iniciar_cadastro_manual
corrigir = iniciar_corrigir
planos = comando_planos
excluir = iniciar_excluir
privacidade = comando_privacidade


# --- MENU FLUTUANTE DE COMANDOS DO TELEGRAM ---
async def configurar_menu_comandos(app):
    comandos = [
        BotCommand("iniciar", "🚀 Menu principal e boas-vindas"),
        BotCommand("verificar_todos", "🔍 Verificar todas as regulações"),
        BotCommand("verificar_especifico", "🎯 Verificar regulação específica"),
        BotCommand("cadastrar_nova", "➕ Cadastrar nova regulação"),
        BotCommand("corrigir", "✏️ Corrigir dados de regulação"),
        BotCommand("planos", "💳 Ver planos e assinaturas"),
        BotCommand("excluir", "🗑️ Excluir uma regulação"),
        BotCommand("privacidade", "🔒 Política de privacidade e LGPD"),
        BotCommand("suporte", "🤖 Central de Atendimento"),
    ]
    await app.bot.set_my_commands(comandos)


# --- CONVERSATION HANDLERS ---
conv_consulta_especifica = ConversationHandler(
    entry_points=[
        CommandHandler("consultar", iniciar_verificar_especifico),
        CommandHandler("verificar_especifico", iniciar_verificar_especifico),
        CallbackQueryHandler(
            iniciar_verificar_especifico, pattern="^verificar_especifico$"
        ),
        # ✅ NOVO: reentra no estado se o usuário clicar no botão depois de reiniciar o bot
        CallbackQueryHandler(
            processar_verificar_especifico, pattern="^ver_esp_"
        ),
    ],
    states={
        CONSULTAR_ID: [
            CallbackQueryHandler(processar_verificar_especifico),
            MessageHandler(
                filters.TEXT & ~filters.COMMAND, processar_verificar_especifico
            ),
        ]
    },
    fallbacks=[CommandHandler("cancelar", cancelar_operacao)],
    per_message=False,
)

conv_cadastro = ConversationHandler(
    entry_points=[
        CommandHandler("cadastrar", iniciar_cadastro_manual),
        CommandHandler("cadastrar_nova", iniciar_cadastro_manual),
        CallbackQueryHandler(iniciar_cadastro_manual, pattern="^cadastrar_nova$"),
    ],
    states={
        ETAPA_SUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_sus)],
        ETAPA_NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)],
        ETAPA_CELULAR: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receber_celular)
        ],
        ETAPA_NASCIMENTO: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nascimento)
        ],
        ETAPA_REGULACAO: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receber_regulacao)
        ],
        ETAPA_CBO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_cbo)],
        ETAPA_PROCEDIMENTO: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receber_procedimento)
        ],
        ETAPA_LGPD: [
            CallbackQueryHandler(
                finalizar_cadastro, pattern="^(aceitar_lgpd|cancelar_cadastro)$"
            )
        ],
    },
    fallbacks=[CommandHandler("cancelar", cancelar_operacao)],
    per_message=False,
)

conv_corrigir = ConversationHandler(
    entry_points=[
        CommandHandler("corrigir", iniciar_corrigir),
        CallbackQueryHandler(iniciar_corrigir, pattern="^corrigir$"),
    ],
    states={
        SELECIONAR_REGULACAO: [
            CallbackQueryHandler(
                selecionar_regulacao_callback, pattern="^(corr_reg_|cancelar_corr)"
            )
        ],
        SELECIONAR_CAMPO: [
            CallbackQueryHandler(
                selecionar_campo_callback,
                pattern="^(form_edit_|form_salvar_|corr_campo_|cancelar_corr)",
            )
        ],
        AGUARDAR_NOVO_VALOR: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, salvar_novo_valor)
        ],
    },
    fallbacks=[CommandHandler("cancelar", cancelar_operacao)],
    per_message=False,
)

conv_excluir = ConversationHandler(
    entry_points=[
        CommandHandler("excluir", iniciar_excluir),
        CallbackQueryHandler(iniciar_excluir, pattern="^excluir$"),
    ],
    states={
        SELECIONAR_REGULACAO_EXCLUIR: [
            CallbackQueryHandler(
                selecionar_regulacao_excluir_callback,
                pattern="^(excl_reg_|cancelar_excl)",
            )
        ],
        CONFIRMAR_EXCLUSAO: [
            CallbackQueryHandler(
                confirmar_exclusao_callback, pattern="^(conf_excl_sim|cancelar_excl)"
            )
        ],
    },
    fallbacks=[CommandHandler("cancelar", cancelar_operacao)],
    per_message=False,
)


# ═══════════════════════════════════════════════════════════════
# NOVAS FUNÇÕES DE ATENDIMENTO AO CLIENTE (ADICIONADAS ABAIXO)
# SEM ALTERAR NENHUMA FUNÇÃO EXISTENTE ACIMA
# ═══════════════════════════════════════════════════════════════

# --- IMPORTS DAS FUNÇÕES DE ATENDIMENTO ---
# --- IMPORTS DAS FUNÇÕES DE ATENDIMENTO ---
# --- IMPORTS DAS FUNÇÕES DE ATENDIMENTO ---
try:
    from handler_atendimento import (
        menu_atendimento,
        iniciar_faq,
        processar_pergunta_faq,
        iniciar_atendimento_humanizado,
        processar_mensagem_humanizado,
        ver_meus_chamados,
        comando_ver_chamados,
        comando_responder_chamado,
        cancelar_atendimento,
    )
    from database_atendimento import (
        buscar_faq_por_palavras_chave,
        registrar_chamado_suporte,
        adicionar_mensagem_fila,
        registrar_historico,
        obter_email_suporte,
    )

    ATENDIMENTO_IMPORTADO = True
except ImportError as e:
    logger.warning(f"Erro ao importar funções de atendimento: {e}")
    ATENDIMENTO_IMPORTADO = False

# --- FALLBACK: Se a importação falhar, define funções dummy ---
if not ATENDIMENTO_IMPORTADO:

    async def menu_atendimento(update, context):
        if update.message:
            await update.message.reply_text(
                "🤖 Central de Atendimento em manutenção. Tente novamente mais tarde."
            )

    async def iniciar_faq(update, context):
        if update.message:
            await update.message.reply_text(
                "❓ FAQ em manutenção. Tente novamente mais tarde."
            )

    async def processar_pergunta_faq(update, context):
        return

    async def iniciar_atendimento_humanizado(update, context):
        if update.message:
            await update.message.reply_text(
                "👤 Atendimento humanizado em manutenção. Tente novamente mais tarde."
            )
        return 1

    async def processar_mensagem_humanizado(update, context):
        return

    async def ver_meus_chamados(update, context):
        return

    async def comando_ver_chamados(update, context):
        return

    async def comando_responder_chamado(update, context):
        return

    async def cancelar_atendimento(update, context):
        return


# --- CONSTANTE DE ESTADO DO ATENDIMENTO HUMANIZADO ---
AGUARDANDO_MENSAGEM_CHAMADO = 1

# --- NOVO CONVERSATION HANDLER PARA ATENDIMENTO HUMANIZADO ---
conv_atendimento_humanizado = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(
            iniciar_atendimento_humanizado, pattern="^atendimento_humanizado$"
        ),
        CommandHandler("atendimento_humanizado", iniciar_atendimento_humanizado),
    ],
    states={
        AGUARDANDO_MENSAGEM_CHAMADO: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND, processar_mensagem_humanizado
            )
        ],
    },
    fallbacks=[
        CommandHandler("cancelar", cancelar_atendimento),
        CallbackQueryHandler(cancelar_atendimento, pattern="^cancelar_atendimento$"),
    ],
    per_message=False,
)

# ==========================================
# RESPOSTAS DO FAQ - NOVAS FUNÇÕES
# ==========================================


async def faq_cadastrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resposta para Como cadastrar uma regulação."""
    query = update.callback_query
    await query.answer()
    texto = (
        "📌 <b>Como cadastrar uma nova regulação?</b>\n\n"
        "• Utilize o comando <b>/cadastrar_nova</b> no menu do bot.\n"
        "• Digite o número do seu <b>Cartão SUS</b> (15 dígitos) ou o <b>ID da Regulação</b>.\n"
        "• Siga as instruções na tela até a confirmação do cadastro."
    )
    teclado = InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Voltar", callback_data="suporte")]]
    )
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def faq_consultar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resposta para Como consultar minhas regulações."""
    query = update.callback_query
    await query.answer()
    texto = (
        "🔍 <b>Como consultar minhas regulações?</b>\n\n"
        "• Para ver todas as suas regulações: digite <b>/verificar_todos</b>.\n"
        "• Para consultar uma regulação específica: digite <b>/verificar_especifico</b>."
    )
    teclado = InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Voltar", callback_data="suporte")]]
    )
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def faq_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resposta para Onde encontrar o Cartão SUS ou ID."""
    query = update.callback_query
    await query.answer()
    texto = (
        "🆔 <b>Onde encontrar o Cartão SUS ou ID da Regulação?</b>\n\n"
        "• <b>Cartão SUS:</b> O número possui 15 dígitos e pode ser encontrado no seu cartão impresso ou no aplicativo 'Meu SUS Digital'.\n"
        "• <b>ID da Regulação:</b> É o código fornecido pelo posto de saúde ou hospital no momento da solicitação."
    )
    teclado = InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Voltar", callback_data="suporte")]]
    )
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def faq_alterar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resposta para Como alterar meus dados."""
    query = update.callback_query
    await query.answer()
    texto = (
        "✏️ <b>Como alterar ou corrigir dados?</b>\n\n"
        "• Para alterar informações de uma regulação já cadastrada, utilize o comando <b>/corrigir</b> no menu principal."
    )
    teclado = InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Voltar", callback_data="suporte")]]
    )
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def faq_planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resposta para Planos e Assinaturas."""
    query = update.callback_query
    await query.answer()
    texto = (
        "💳 <b>Planos e Assinaturas</b>\n\n"
        "• Para verificar seus planos ativos, renovar ou fazer upgrade, acesse o comando <b>/planos</b> no menu principal."
    )
    teclado = InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Voltar", callback_data="suporte")]]
    )
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def mostrar_email_suporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe o email de suporte como texto copiável."""
    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        "📧 <b>Email de Suporte</b>\n\n"
        "<code>suportevigiasaude@gmail.com</code>\n\n"
        "Toque no email acima para copiar.",
        parse_mode="HTML",
    )


async def faq_governo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resposta para O VigiaSaude tem vínculo com o governo."""
    query = update.callback_query
    await query.answer()
    texto = (
        "⚠️ <b>O VigiaSaude tem vínculo com o governo?</b>\n\n"
        "Não. O VigiaSaude é uma ferramenta <b>independente</b> e não possui vínculo oficial com a Prefeitura de Teresina, FMS ou SUS.\n"
        "As informações são baseadas nos dados públicos dos portais de regulação."
    )
    teclado = InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Voltar", callback_data="suporte")]]
    )
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)

async def callback_optout_teaser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usuário clicou em 'Não quero receber mais'."""
    from teaser_storage import ativar_optout, desativar_optout, esta_em_optout

    query = update.callback_query
    await query.answer()

    chat_id = str(query.from_user.id)

    if esta_em_optout(chat_id):
        # Já está em opt-out — reativar
        desativar_optout(chat_id)
        texto = (
            "✅ <b>Pronto! Você voltará a receber os alertas de atualização.</b>\n\n"
            "Se mudar de ideia novamente, é só tocar no botão abaixo."
        )
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔕 Não quero receber mais", callback_data="optout_teaser")]
        ])
    else:
        # Ativa opt-out
        ativar_optout(chat_id)
        texto = (
            "🔕 <b>Entendido! Não enviaremos mais alertas de atualização.</b>\n\n"
            "Você continuará recebendo apenas:\n"
            "• Confirmações de pagamento\n"
            "• Respostas do suporte\n\n"
            "Se quiser reativar os alertas, toque no botão abaixo."
        )
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔔 Quero receber novamente", callback_data="optout_teaser")]
        ])

    try:
        await query.edit_message_reply_markup(reply_markup=teclado)
    except Exception:
        pass

    await query.message.reply_text(texto, parse_mode="HTML", reply_markup=teclado)


# --- EXPORTAÇÃO DE SÍMBOLOS DO HANDLER ATUALIZADA ---
__all__ = [
    "CONSULTAR_ID",
    "SELECIONAR_REGULACAO",
    "SELECIONAR_CAMPO",
    "AGUARDAR_NOVO_VALOR",
    "SELECIONAR_REGULACAO_EXCLUIR",
    "CONFIRMAR_EXCLUSAO",
    "ETAPA_SUS",
    "ETAPA_NOME",
    "ETAPA_CELULAR",
    "ETAPA_NASCIMENTO",
    "ETAPA_REGULACAO",
    "ETAPA_CBO",
    "ETAPA_PROCEDIMENTO",
    "ETAPA_LGPD",
    "start",
    "comando_ajuda",
    "comando_suporte",
    "callback_ajuda",
    "voltar_ajuda",
    "faq_o_que_e",
    "faq_rastrear",
    "faq_seguranca",
    "faq_corrigir",
    "comando_privacidade",
    "callback_faq_suporte",
    "callback_privacidade_voltar",
    "callback_optout_teaser",
    "comando_planos",
    "cancelar_operacao",
    "configurar_menu_comandos",
    "executar_varredura_automatica",
    "comando_verificar_todas",
    "iniciar_verificar_especifico",
    "processar_verificar_especifico",
    "iniciar_cadastro_manual",
    "receber_sus",
    "receber_nome",
    "receber_celular",
    "receber_nascimento",
    "receber_regulacao",
    "receber_cbo",
    "receber_procedimento",
    "finalizar_cadastro",
    "iniciar_corrigir",
    "selecionar_regulacao_callback",
    "selecionar_campo_callback",
    "salvar_novo_valor",
    "cancelar_corrigir",
    "iniciar_excluir",
    "selecionar_regulacao_excluir_callback",
    "confirmar_exclusao_callback",
    "cancelar_excluir",
    "conv_consulta_especifica",
    "conv_cadastro",
    "conv_corrigir",
    "conv_excluir",
    "obter_menu_principal",
    "obter_menu_planos",
    "detalhar_plano",
    "comando_atendimento",
    "comando_faq",
    "voltar_menu_atendimento",
    "callback_email_suporte",
    "conv_atendimento_humanizado",
    "AGUARDANDO_MENSAGEM_CHAMADO",
    "comando_suporte",
    "faq_cadastrar",
    "faq_consultar",
    "faq_id",
    "faq_alterar",
    "faq_planos",
    "faq_governo",
    "mostrar_email_suporte",
]
