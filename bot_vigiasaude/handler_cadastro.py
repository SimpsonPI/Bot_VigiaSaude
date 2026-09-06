# handler_cadastro.py
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from database import salvar_regulacao, registrar_consentimento_lgpd, supabase
from utils import (
    DISCLAIMER_TEXTO, TECLADO_MENU, TECLADO_CANCELAR,
    ETAPA_SUS, ETAPA_NOME, ETAPA_CELULAR, ETAPA_NASCIMENTO,
    ETAPA_REGULACAO, ETAPA_CBO, ETAPA_PROCEDIMENTO, ETAPA_LGPD,
    formatar_data, formatar_celular, formatar_maiusculo, verificar_se_e_menu_e_executar
)

async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    context.user_data["nome"] = formatar_maiusculo(update.message.text)
    await update.message.reply_text("Digite o número de <b>celular/WhatsApp</b> (com DDD):", parse_mode="HTML")
    return ETAPA_CELULAR

async def receber_celular(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    context.user_data["celular"] = formatar_celular(update.message.text)[cite: 2]
    await update.message.reply_text("Digite a <b>data de nascimento</b> do paciente (DD/MM/AAAA):", parse_mode="HTML")
    return ETAPA_NASCIMENTO

async def receber_nascimento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    context.user_data["nascimento"] = formatar_data(update.message.text)[cite: 2]
    await update.message.reply_text("Agora, por favor, digite o <b>Número da Regulação</b>:", parse_mode="HTML")
    return ETAPA_REGULACAO

async def receber_cbo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    cbo = update.message.text.strip()
    context.user_data["cbo"] = formatar_maiusculo(cbo) if cbo != "0" else ""
    await update.message.reply_text("Qual a descrição do <b>Procedimento/Exame</b>?", parse_mode="HTML")
    return ETAPA_PROCEDIMENTO

async def receber_procedimento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    context.user_data["procedimento"] = formatar_maiusculo(update.message.text)
    # Restante do código do termo LGPD...

async def iniciar_cadastro_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "📝 <b>Iniciando cadastro de nova regulação.</b>\n\n"
        "Por favor, digite o <b>número do Cartão SUS</b> do paciente (15 dígitos):",
        parse_mode="HTML", reply_markup=TECLADO_CANCELAR
    )
    return ETAPA_SUS

async def receber_sus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    chat_id = update.effective_chat.id
    numero_sus = update.message.text.strip()
    
    context.user_data['sus'] = numero_sus

    try:
        print(f"DEBUG: Buscando SUS {numero_sus} no Supabase...")
        # Altere "numero_sus" abaixo se a sua coluna no Supabase tiver outro nome (ex: "cartao_sus")
        resposta = supabase.table("AlertaSUS_2.0").select("*").eq("numero_sus", numero_sus).execute()
        registros = resposta.data

        if registros and len(registros) > 0:
            dados_antigos = registros[0]
            context.user_data['nome'] = dados_antigos.get('nome_paciente')
            context.user_data['celular'] = dados_antigos.get('celular')
            context.user_data['nascimento'] = dados_antigos.get('data_nascimento')
            context.user_data['cbo'] = dados_antigos.get('cbo')
            context.user_data['procedimento'] = dados_antigos.get('procedimento')

            print("DEBUG: SUS encontrado! Indo direto para ETAPA_REGULACAO.")
            await update.message.reply_text(
                f"🔍 <b>Cartão do SUS já cadastrado!</b>\n"
                f"Autopreenchemos os dados de: <b>{dados_antigos.get('nome_paciente')}</b>.\n\n"
                f"Agora, por favor, digite apenas o <b>Número da Regulação</b>:",
                parse_mode="HTML"
            )
            return ETAPA_REGULACAO
            
    except Exception as e:
        print(f"ERRO no bloco do SUS: {e}")

    print("DEBUG: SUS não encontrado. Indo para ETAPA_NOME.")
    await update.message.reply_text("Qual o nome completo do paciente?")
    return ETAPA_NOME

async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    context.user_data["nome"] = update.message.text.strip()
    await update.message.reply_text("Digite o número de <b>celular/WhatsApp</b> (com DDD):", parse_mode="HTML")
    return ETAPA_CELULAR

async def receber_celular(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    celular = formatar_celular(update.message.text.strip())
    context.user_data["celular"] = celular
    await update.message.reply_text("Digite a <b>data de nascimento</b> do paciente (DD/MM/AAAA):", parse_mode="HTML")
    return ETAPA_NASCIMENTO

async def receber_nascimento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    nascimento = formatar_data(update.message.text.strip())
    context.user_data["nascimento"] = nascimento
    await update.message.reply_text("Agora, por favor, digite o <b>Número da Regulação</b>:", parse_mode="HTML")
    return ETAPA_REGULACAO

async def receber_regulacao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    num_reg = re.sub(r"\D", "", update.message.text)
    if not num_reg:
        await update.message.reply_text("⚠️ Digite um número de regulação válido:")
        return ETAPA_REGULACAO
    context.user_data["numero_regulacao"] = num_reg
    await update.message.reply_text("Informe o código <b>CBO</b> da especialidade (opcional - digite 0 para pular):", parse_mode="HTML")
    return ETAPA_CBO

async def receber_cbo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    cbo = update.message.text.strip()
    context.user_data["cbo"] = cbo if cbo != "0" else ""
    await update.message.reply_text("Qual a descrição do <b>Procedimento/Exame</b>?", parse_mode="HTML")
    return ETAPA_PROCEDIMENTO

async def receber_procedimento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    context.user_data["procedimento"] = update.message.text.strip()

    teclado_lgpd = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Aceitar e Finalizar", callback_data="aceitar_lgpd")],
        [InlineKeyboardButton("❌ Cancelar Cadastro", callback_data="cancelar_cadastro")]
    ])

    await update.message.reply_text(
        "🛡️ <b>TERMO DE CONSENTIMENTO LGPD</b>\n\n"
        "Para prosseguir com o monitoramento automático, autorizo o armazenamento dos dados fornecidos exclusivamente para finalidades de consulta pública no sistema FMS Piauí.\n\n"
        f"{DISCLAIMER_TEXTO}\n\nVocê aceita o termo?",
        parse_mode="HTML", reply_markup=teclado_lgpd
    )
    return ETAPA_LGPD

async def finalizar_cadastro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    dados = context.user_data

    if query.data == "cancelar_cadastro":
        try:
            await query.message.delete()
        except Exception:
            pass
        await context.bot.send_message(chat_id=chat_id, text="❌ Cadastro cancelado pelo usuário.", reply_markup=TECLADO_MENU)
        context.user_data.clear()
        return ConversationHandler.END

    dados_salvar = {
        "chat_id": user_id,
        "numero_sus": dados.get("sus"),
        "nome_paciente": dados.get("nome"),
        "celular": dados.get("celular"),
        "data_nascimento": dados.get("nascimento"),
        "numero_reg": dados.get("numero_regulacao"),
        "cbo": dados.get("cbo"),
        "procedimento": dados.get("procedimento")
    }

    print("DEBUG 1: Salvando no Supabase...")
    sucesso = await salvar_regulacao(dados_salvar)
    print(f"DEBUG 2: salvar_regulacao = {sucesso}")

    try:
        registrar_consentimento_lgpd(user_id)
        print("DEBUG 3: LGPD registrado com sucesso.")
    except Exception as e:
        print(f"DEBUG 3 AVISO LGPD: {e}")

    # 1. Apaga a mensagem do Termo LGPD para sumir com os botões travados
    print("DEBUG 4: Apagando mensagem com os botões...")
    try:
        await query.message.delete()
        print("DEBUG 5: Mensagem do termo apagada com sucesso.")
    except Exception as e:
        print(f"DEBUG 5 ERRO ao apagar mensagem: {e}")
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

    # 2. Envia a mensagem de confirmação no chat
    print("DEBUG 6: Enviando mensagem de sucesso no chat...")
    await context.bot.send_message(
        chat_id=chat_id,
        text="✅ <b>Regulação cadastrada com sucesso!</b>\nEla será monitorada automaticamente pelo sistema.",
        parse_mode="HTML"
    )

    # 3. Envia o Menu Principal
    print("DEBUG 7: Enviando menu principal...")
    await context.bot.send_message(
        chat_id=chat_id,
        text="O que deseja fazer agora?",
        reply_markup=TECLADO_MENU
    )

    context.user_data.clear()
    print("DEBUG 8: Fluxo finalizado com sucesso!")
    return ConversationHandler.END