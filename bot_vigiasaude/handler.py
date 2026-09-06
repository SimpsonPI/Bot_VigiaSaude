import asyncio
from html import escape
import logging
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

from config import TELEGRAM_BOT_TOKEN
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


URL_TERMO_LGPD = (
    "https://telegra.ph/DECLARA%C3%87%C3%83O-DE-INDEPEND%C3%8ANCIA-08-13"
)
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
        await update.message.reply_text("❌ Operação cancelada.", reply_markup=obter_menu_principal())
    
    context.user_data.clear()
    return ConversationHandler.END


async def callback_faq_suporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe a FAQ completa do VigiaSaude 2.5 diretamente no chat."""
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
        "Basta utilizar o comando /corrigir no menu principal para atualizar dados como CBO, celular ou nome do paciente.\n\n"
        "<b>5. O bot substitui a fila oficial do SUS?</b>\n"
        "Não. O VigiaSaude é um facilitador de avisos e consultas. A marcação, chamada e gestão de vagas continuam sob responsabilidade exclusiva da Secretaria de Saúde.\n\n"
        "<b>6. Como posso falar com o suporte humano?</b>\n"
        "Caso tenha problemas técnicos, envie uma mensagem diretamente para nossa equipe de atendimento."
    )
    
    teclado_volta = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Voltar", callback_data="privacidade_voltar")]
    ])
    
    try:
        await query.edit_message_text(faq_texto, parse_mode="HTML", reply_markup=teclado_volta)
    except Exception as e:
        logger.error(f"Erro ao exibir FAQ: {e}")


async def callback_privacidade_voltar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retorna para a tela inicial de privacidade."""
    query = update.callback_query
    await query.answer()
    
    texto = "Clique no botão abaixo para ler a nossa Política de Privacidade e Termos de Uso:"
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔒 Abrir Política de Privacidade e Termos", callback_data="https://seu-site-ou-link-de-privacidade.com")],
        [InlineKeyboardButton("💬 Dúvidas / Suporte (FAQ)", callback_data="abrir_faq_suporte")]
    ])
    
    await query.edit_message_text(texto, reply_markup=teclado)


# --- HANDLER DO COMANDO /START E /INICIAR ---
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
                if row.get("usou_degustacao") is True or row.get("tipo_plano") == "degustacao":
                    ja_usou_degustacao = True
                    break
    except Exception as e:
        logger.error(f"Erro ao verificar degustação: {e}")
        ja_usou_degustacao = True

    keyboard = []
    if not ja_usou_degustacao:
        keyboard.append([InlineKeyboardButton("🎁 Plano Degustação (Grátis)", callback_data="plano_degustacao")])
    keyboard.append([InlineKeyboardButton("⭐ Plano Trimestral (R$ 9,99)", callback_data="plano_trimestral")])
    keyboard.append([InlineKeyboardButton("🚀 Plano Semestral (R$ 14,99)", callback_data="plano_semestral")])
    keyboard.append([InlineKeyboardButton("📧 Email de Suporte", callback_data="atendimento_email")])
    return InlineKeyboardMarkup(keyboard)


def usuario_tem_acesso(plano_info: dict) -> bool:
    status_bruto = str(plano_info.get("status", "")).strip().lower()
    tipo_plano = str(plano_info.get("tipo_plano", "")).strip().lower()
    usou_degustacao = plano_info.get("usou_degustacao", False)
    is_cortesia = tipo_plano == "cortesia"
    is_degustacao = tipo_plano == "degustacao"
    return is_cortesia or (is_degustacao and (usou_degustacao or status_bruto == "ativo")) or (status_bruto == "ativo")


async def comando_planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id_str = str(user_id)
    try:
        res = supabase.table("assinaturas").select("*").eq("chat_id", chat_id_str).order("created_at", desc=True).execute()
        dados = res.data if res and hasattr(res, "data") else []
    except Exception as e:
        logger.error(f"Erro ao consultar assinaturas: {e}")
        dados = []

    plano_info = dados[0] if dados else {}
    tipo_plano = str(plano_info.get("tipo_plano", "")).strip().lower()
    is_cortesia = tipo_plano == "cortesia"
    is_degustacao = tipo_plano == "degustacao"
    is_ativo = usuario_tem_acesso(plano_info)

    if is_ativo and not is_degustacao:
        tipo_formatado = "Cortesia VIP 👑" if is_cortesia else f"Pro ({tipo_plano.capitalize()})"
        limite = plano_info.get("limite_ids", "Ilimitado")
        texto = f"✨ <b>Sua Assinatura está Ativa!</b>\n\n• <b>Plano:</b> {tipo_formatado}\n• <b>Status:</b> Ativo 🟢\n• <b>Limite:</b> {limite}"
        teclado = None
    elif is_ativo and is_degustacao:
        texto = "🎁 <b>Plano Degustação Ativo!</b>\n• <b>Limite:</b> Até 2 regulações"
        teclado = await obter_menu_planos(user_id)
    else:
        texto = "💳 <b>Planos e Assinaturas — VigiaSaude</b>\nEscolha um plano abaixo:"
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
        except Exception as err:
            logger.error(f"Erro ao gravar degustação: {err}")

        texto = "🎁 <b>Plano Degustação Ativado!</b>\n\nSeu período de teste gratuito já está funcionando (até 2 regulações)."
        keyboard_botoes = [[InlineKeyboardButton("⚡ Ver Planos Pro", callback_data="planos")]]

    elif data == "plano_trimestral":
        texto = "⭐ <b>Plano Trimestral</b>\n\n• Até 5 regulações.\n<b>Valor:</b> R$ 9,99 / trimestre"
        keyboard_botoes = [
            [InlineKeyboardButton("💳 Pagar via Pix", callback_data="pix_pro_trimestral")],
            [InlineKeyboardButton("⬅️ Voltar aos Planos", callback_data="planos")],
        ]

    elif data == "plano_semestral":
        texto = "🚀 <b>Plano Semestral</b>\n\n• Até 9 regulações.\n<b>Valor:</b> R$ 14,99 / semestre"
        keyboard_botoes = [
            [InlineKeyboardButton("💳 Pagar via Pix", callback_data="pix_pro_semestral")],
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


async def comando_privacidade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔒 Abrir Política de Privacidade e Termos", callback_data="https://seu-site-ou-link-de-privacidade.com")],
        [InlineKeyboardButton("💬 Dúvidas / Suporte (FAQ)", callback_data="abrir_faq_suporte")]
    ])
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
        [InlineKeyboardButton("💬 Falar com Suporte", callback_data="abrir_faq_suporte")]
    ]
    reply_markup = InlineKeyboardMarkup(teclado)
    
    if update.message:
        await update.message.reply_text(texto, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.edit_text(texto, reply_markup=reply_markup, parse_mode="Markdown")

async def comando_suporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Central de Atendimento - Links, FAQs e Email"""
    texto = (
        "🤖 <b>Central de Atendimento VigiaSaude</b>\n\n"
        "Como podemos ajudar você hoje?\n\n"
        "<b>📌 Canais de Atendimento:</b>\n"
        "• 🤖 <b>Bot de Atendimento:</b> @central_vigiasaude_bot\n"
        "• 📧 <b>Email:</b> suportealertasus@gmail.com\n\n"
        "<b>❓ Perguntas Frequentes (FAQs):</b>\n"
        "1️⃣ Como cadastrar uma nova regulação?\n"
        "2️⃣ Como verificar o status das regulações?\n"
        "3️⃣ Onde encontrar o Cartão SUS ou ID?\n"
        "4️⃣ Como corrigir dados?\n"
        "5️⃣ Planos e Assinaturas\n"
        "6️⃣ O VigiaSaude tem vínculo com o governo?\n\n"
        "Selecione uma opção abaixo:"
    )
    
    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 Bot de Atendimento", url="https://t.me/meu_atendimento_123_bot"),
            InlineKeyboardButton("📧 Email", url="mailto:suportealertasus@gmail.com")
        ],
        [
            InlineKeyboardButton("1️⃣ Cadastrar", callback_data="faq_cadastrar"),
            InlineKeyboardButton("2️⃣ Consultar", callback_data="faq_consultar")
        ],
        [
            InlineKeyboardButton("3️⃣ Cartão SUS/ID", callback_data="faq_id"),
            InlineKeyboardButton("4️⃣ Alterar Dados", callback_data="faq_alterar")
        ],
        [
            InlineKeyboardButton("5️⃣ Planos", callback_data="faq_planos"),
            InlineKeyboardButton("6️⃣ Vínculo Governo", callback_data="faq_governo")
        ],
        [InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="iniciar")]
    ])
    
    if update.message:
        await update.message.reply_text(texto, reply_markup=teclado, parse_mode="HTML")
    elif update.callback_query:
        await update.callback_query.message.edit_text(texto, reply_markup=teclado, parse_mode="HTML")

async def voltar_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retorna para o menu principal de ajuda."""
    await callback_ajuda(update, context)


async def faq_o_que_e(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    texto = "💡 <b>O que é o VigiaSaude?</b>\n\nÉ uma ferramenta independente desenvolvida para facilitar o acompanhamento de status de solicitações de regulação junto aos sistemas públicos de saúde."
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="ajuda")]])
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
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="ajuda")]])
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def faq_seguranca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    texto = "🔒 <b>Meus dados estão seguros?</b>\n\nSim! Informações sensíveis são tratadas com privacidade estrita seguindo a LGPD."
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="ajuda")]])
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def faq_corrigir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    texto = "✏️ <b>Como corrigir dados?</b>\n\nUtilize o comando de correção no menu principal para atualizar informações cadastrais ou CBO (Especialidade)."
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data="ajuda")]])
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def executar_varredura_automatica(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Varredura automática iniciada...")
    try:
        regulacoes = buscar_todas_regulacoes_ativas()
        if not regulacoes:
            return
        for reg in regulacoes:
            num_reg = reg.get("numero_reg") or reg.get("numero_regulacao") or reg.get("id_regulacao")
            chat_id = reg.get("chat_id") or reg.get("id_do_chat") or reg.get("telegram_id")
            if not num_reg or not chat_id:
                continue
            resultado_fms = await consultar_status_fms(str(num_reg))
            if isinstance(resultado_fms, dict) and resultado_fms.get("sucesso"):
                status_novo = resultado_fms.get("situacao") or "Informada no portal"
            await asyncio.sleep(0.1)
    except Exception as e:
        logger.error(f"Erro na varredura: {e}")


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
        CallbackQueryHandler(iniciar_verificar_especifico, pattern="^verificar_especifico$"),
    ],
    states={
        CONSULTAR_ID: [
            CallbackQueryHandler(processar_verificar_especifico),
            MessageHandler(filters.TEXT & ~filters.COMMAND, processar_verificar_especifico),
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
        ETAPA_CELULAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_celular)],
        ETAPA_NASCIMENTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nascimento)],
        ETAPA_REGULACAO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_regulacao)],
        ETAPA_CBO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_cbo)],
        ETAPA_PROCEDIMENTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_procedimento)],
        ETAPA_LGPD: [CallbackQueryHandler(finalizar_cadastro, pattern="^(aceitar_lgpd|cancelar_cadastro)$")],
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
        SELECIONAR_REGULACAO: [CallbackQueryHandler(selecionar_regulacao_callback, pattern="^(corr_reg_|cancelar_corr)")],
        SELECIONAR_CAMPO: [CallbackQueryHandler(selecionar_campo_callback, pattern="^(form_edit_|form_salvar_|corr_campo_|cancelar_corr)")],
        AGUARDAR_NOVO_VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, salvar_novo_valor)],
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
        SELECIONAR_REGULACAO_EXCLUIR: [CallbackQueryHandler(selecionar_regulacao_excluir_callback, pattern="^(excl_reg_|cancelar_excl)")],
        CONFIRMAR_EXCLUSAO: [CallbackQueryHandler(confirmar_exclusao_callback, pattern="^(conf_excl_sim|cancelar_excl)")],
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
            await update.message.reply_text("🤖 Central de Atendimento em manutenção. Tente novamente mais tarde.")
    
    async def iniciar_faq(update, context):
        if update.message:
            await update.message.reply_text("❓ FAQ em manutenção. Tente novamente mais tarde.")
    
    async def processar_pergunta_faq(update, context):
        return
    
    async def iniciar_atendimento_humanizado(update, context):
        if update.message:
            await update.message.reply_text("👤 Atendimento humanizado em manutenção. Tente novamente mais tarde.")
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
        CallbackQueryHandler(iniciar_atendimento_humanizado, pattern="^atendimento_humanizado$"),
        CommandHandler("atendimento_humanizado", iniciar_atendimento_humanizado),
    ],
    states={
        AGUARDANDO_MENSAGEM_CHAMADO: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, processar_mensagem_humanizado)
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
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="suporte")]])
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
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="suporte")]])
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
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="suporte")]])
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def faq_alterar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resposta para Como alterar meus dados."""
    query = update.callback_query
    await query.answer()
    texto = (
        "✏️ <b>Como alterar ou corrigir dados?</b>\n\n"
        "• Para alterar informações de uma regulação já cadastrada, utilize o comando <b>/corrigir</b> no menu principal."
    )
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="suporte")]])
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def faq_planos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resposta para Planos e Assinaturas."""
    query = update.callback_query
    await query.answer()
    texto = (
        "💳 <b>Planos e Assinaturas</b>\n\n"
        "• Para verificar seus planos ativos, renovar ou fazer upgrade, acesse o comando <b>/planos</b> no menu principal."
    )
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="suporte")]])
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)


async def faq_governo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resposta para O VigiaSaude tem vínculo com o governo."""
    query = update.callback_query
    await query.answer()
    texto = (
        "⚠️ <b>O VigiaSaude tem vínculo com o governo?</b>\n\n"
        "Não. O VigiaSaude é uma ferramenta <b>independente</b> e não possui vínculo oficial com a Prefeitura de Teresina, FMS ou SUS.\n"
        "As informações são baseadas nos dados públicos dos portais de regulação."
    )
    teclado = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="suporte")]])
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)

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
]
