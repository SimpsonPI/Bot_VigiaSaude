import logging
import re
from html import escape
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from database import supabase
from scraper import consultar_status_fms

logger = logging.getLogger(__name__)

CONSULTAR_ID = 1

DISCLAIMER_TEXTO = "Serviço independente de monitoramento. Não possuímos vínculo oficial com a FMS ou Prefeitura de Teresina."

def _mascarar_nome_custom(nome: str) -> str:
    """Retorna: Primeiro nome + iniciais. Ex: 'João Silva Santos' -> 'João S. S.'"""
    if not nome or str(nome).lower() in ["none", "não informado", ""]:
        return "Não informado"
    partes = nome.strip().split()
    if len(partes) <= 1:
        return partes[0].capitalize()
    
    primeiro = partes[0].capitalize()
    iniciais = [f"{p[0].upper()}." for p in partes[1:]]
    return f"{primeiro} {' '.join(iniciais)}"

def _mascarar_sus_custom(sus: str) -> str:
    """Retorna: 3 primeiros + 3 últimos. Ex: '12345678912' -> '123*****912'"""
    s = str(sus).strip()
    if len(s) < 6:
        return s
    return f"{s[:3]}{'*' * 5}{s[-3:]}"

def _montar_msg_html(num_reg: str, resultado: dict, reg_db=None) -> str:
    cartao_sus_raw = ""
    nome_paciente_raw = ""
    cbo = "Não informado"
    procedimento = "Não informado"

    if reg_db:
        if isinstance(reg_db, dict):
            cartao_sus_raw = reg_db.get("numero_sus") or reg_db.get("cartao_sus") or ""
            nome_paciente_raw = reg_db.get("nome_paciente") or ""
            cbo = reg_db.get("cbo") or cbo
            procedimento = reg_db.get("procedimento") or procedimento

    nome_exibicao = _mascarar_nome_custom(nome_paciente_raw)
    cartao_sus_exibicao = _mascarar_sus_custom(cartao_sus_raw) if cartao_sus_raw else "Não informado"

    if isinstance(resultado, dict) and resultado.get("sucesso"):
        situacao = resultado.get("situacao") or "Informada no portal"
        posicao = resultado.get("posicao_fila") or "Não informada"
        previsao = resultado.get("previsao_atendimento") or "Não informada"
        alerta = resultado.get("alerta_fms") or resultado.get("alerta")
        data_consulta = resultado.get("data_consulta")
        estabelecimento = resultado.get("estabelecimento")
        endereco = resultado.get("endereco")
        telefone = resultado.get("telefone")
    else:
        situacao = "Não encontrada / Indisponível"
        posicao = "Não informada"
        previsao = "Não informada"
        alerta = resultado.get("mensagem") if isinstance(resultado, dict) else None
        data_consulta = None
        estabelecimento = None
        endereco = None
        telefone = None

    linhas = [
        "📋 <b>STATUS DA REGULAÇÃO</b>",
        "",
        f"<b>ID Regulação:</b> <code>{escape(str(num_reg))}</code>",
        f"<b>Cartão SUS:</b> <code>{escape(str(cartao_sus_exibicao))}</code>",
        f"<b>Paciente:</b> {escape(str(nome_exibicao))}",
        f"<b>CBO:</b> {escape(str(cbo).upper())}",
        f"<b>Procedimento:</b> {escape(str(procedimento).upper())}",
        f"<b>Status:</b> {escape(str(situacao))}",
        f"<b>Posição:</b> {escape(str(posicao))}",
    ]

    if data_consulta or estabelecimento:
        linhas.append(f"<b>Previsão:</b> {escape(str(previsao))}")
        linhas.append("")
        linhas.append("📅 <b>DADOS DO AGENDAMENTO</b>")
        if data_consulta:
            linhas.append(f"• <b>Data/Hora:</b> {escape(str(data_consulta))}")
        if estabelecimento:
            linhas.append(f"• <b>Local:</b> {escape(str(estabelecimento))}")
        if endereco:
            linhas.append(f"• <b>Endereço:</b> {escape(str(endereco))}")
        if telefone:
            linhas.append(f"• <b>Telefone:</b> {escape(str(telefone))}")

        if alerta and str(alerta).strip():
            linhas.append("")
            linhas.append(f"⚠️ <b>AVISO DO PORTAL:</b>\n<i>{escape(str(alerta.strip()))}</i>")
    else:
        linhas.append(f"<b>Previsão:</b> {escape(str(previsao))}")
        if alerta and str(alerta).strip():
            linhas.append("")
            linhas.append(f"⚠️ <b>Mensagem do Portal:</b>\n<i>{escape(str(alerta.strip()))}</i>")

    if DISCLAIMER_TEXTO:
        linhas.append("")
        linhas.append(f"ℹ️ <i>{DISCLAIMER_TEXTO.strip()}</i>")

    return "\n".join(linhas)

async def enviar_resposta(update: Update, texto: str, parse_mode="HTML", reply_markup=None):
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(texto, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception:
            await update.callback_query.message.reply_text(texto, parse_mode=parse_mode, reply_markup=reply_markup)
    elif update.message:
        await update.message.reply_text(texto, parse_mode=parse_mode, reply_markup=reply_markup)

async def comando_verificar_todas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        res = supabase.table("AlertaSUS_2.0").select("*").eq("chat_id", user_id).execute()
        regulacoes = res.data if res.data else []
    except Exception as e:
        logger.error(f"Erro ao buscar regulações no Supabase: {e}")
        regulacoes = []

    if not regulacoes:
        await enviar_resposta(update, "ℹ️ <b>Você não possui nenhuma regulação cadastrada.</b>\nUtilize o menu para cadastrar.", parse_mode="HTML")
        return

    # Envia uma mensagem inicial de carregamento
    total_regs = len(regulacoes)
    msg_carregando = f"🔄 Consultando <b>{total_regs}</b> regulação(ões) na FMS... Por favor, aguarde."
    if update.callback_query:
        try:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(msg_carregando, parse_mode="HTML")
        except Exception:
            await update.message.reply_text(msg_carregando, parse_mode="HTML")
    elif update.message:
        await update.message.reply_text(msg_carregando, parse_mode="HTML")

    relatorios = []

    for reg in regulacoes:
        num_reg = reg.get("numero_reg")
        if not num_reg:
            continue
        try:
            resultado = await consultar_status_fms(num_reg)
        except Exception as e:
            logger.error(f"Erro FMS {num_reg}: {e}")
            resultado = {"sucesso": False}

        msg_html = _montar_msg_html(num_reg, resultado, reg)
        relatorios.append(msg_html)

    if relatorios:
        # Junta todas as regulações em uma única mensagem separada por divisores
        mensagem_final = "\n\n➖➖➖➖➖➖➖➖➖➖\n\n".join(relatorios)
        if len(mensagem_final) <= 4096:
            await enviar_resposta(update, mensagem_final, parse_mode="HTML")
        else:
            for relatorio in relatorios:
                await enviar_resposta(update, relatorio, parse_mode="HTML")
                
        await enviar_resposta(update, "✅ Consulta concluída!")
    else:
        await enviar_resposta(update, "⚠️ Não foi possível recuperar os dados no momento. Tente novamente mais tarde.")

async def iniciar_verificar_especifico(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        user_id = update.effective_user.id
        
        # 1. Envia a mensagem de carregamento imediatamente
        msg_carregando = None
        if update.message:
            msg_carregando = await update.message.reply_text("⏳ Consultando suas regulações, aguarde...")
        elif update.callback_query:
            await update.callback_query.answer("Carregando...")
            msg_carregando = await update.callback_query.message.reply_text("⏳ Consultando suas regulações, aguarde...")

        # 2. Faz a consulta no Supabase
        res = supabase.table("AlertaSUS_2.0").select("*").eq("chat_id", user_id).execute()
        regulacoes = res.data if res.data else []

        if not regulacoes:
            msg_sem_dados = "⚠️ Nenhuma regulação cadastrada encontrada para o seu usuário."
            if msg_carregando:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=msg_carregando.message_id,
                    text=msg_sem_dados
                )
            return ConversationHandler.END

        teclado_botoes = []
        for reg in regulacoes:
            num_reg = reg.get("numero_reg")
            nome_bruto = reg.get("nome_paciente", "")
            cbo = reg.get("cbo", "")
            
            cbo_str = f" ({cbo.strip().upper()})" if cbo and str(cbo).strip().upper() not in ["NONE", "N/A", ""] else ""
            rotulo_botao = f"📄 {num_reg} - {_mascarar_nome_custom(nome_bruto)}{cbo_str}"

            teclado_botoes.append([InlineKeyboardButton(rotulo_botao, callback_data=f"ver_esp_{num_reg}")])

        teclado_botoes.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_ver_esp")])
        reply_markup = InlineKeyboardMarkup(teclado_botoes)

        msg = "🔍 <b>Selecione qual regulação deseja verificar:</b>\n<i>Ou se preferir, digite o número do ID da regulação abaixo:</i>"
        
        # 3. Substitui a mensagem de carregamento pelo menu final com os botões
        if msg_carregando:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=msg_carregando.message_id,
                text=msg,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )

        return CONSULTAR_ID
    except Exception as e:
        logger.error(f"Erro em iniciar_verificar_especifico: {e}")
        return ConversationHandler.END


# Adicione também esta função para processar o clique/digitação da consulta específica com a mensagem de carregamento:
async def processar_verificar_especifico(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        # Extrai o número do callback_data (ex: "ver_esp_123456" -> "123456")
        num_reg = query.data.replace("ver_esp_", "")
        msg_alvo = query.message
    else:
        num_reg = update.message.text.strip()
        msg_alvo = update.message

    msg_carregando = f"🔄 Consultando a regulação <b>{num_reg}</b> na FMS... Por favor, aguarde."
    await msg_alvo.reply_text(msg_carregando, parse_mode="HTML")

    try:
        resultado = await consultar_status_fms(num_reg)
        
        # Busca os dados complementares salvos no Supabase para montar a mensagem completa
        res_db = supabase.table("AlertaSUS_2.0").select("*").eq("numero_reg", num_reg).execute()
        reg_data = res_db.data[0] if res_db.data else {}

        msg_html = _montar_msg_html(num_reg, resultado, reg_data)
        await msg_alvo.reply_text(msg_html, parse_mode="HTML")
        await msg_alvo.reply_text("✅ Consulta concluída!")
    except Exception as e:
        logger.error(f"Erro ao consultar regulação específica {num_reg}: {e}")
        await msg_alvo.reply_text("⚠️ Ocorreu um erro ao consultar esta regulação na FMS. Tente novamente mais tarde.")

    return ConversationHandler.END