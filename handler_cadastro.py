# handler_cadastro.py
import re
from database import supabase
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from database import salvar_regulacao, registrar_consentimento_lgpd, supabase
from utils import (
    DISCLAIMER_TEXTO, TECLADO_MENU, TECLADO_CANCELAR,
    ETAPA_SUS, ETAPA_NOME, ETAPA_CELULAR, ETAPA_NASCIMENTO,
    ETAPA_REGULACAO, ETAPA_CBO, ETAPA_PROCEDIMENTO, ETAPA_LGPD,
    ETAPA_CONFIRMAR_REUSO,
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
    from handler import (
        verificar_plano_ativo,
        enviar_alerta_plano_expirado,
        enviar_oferta_limite_atingido,
        _obter_limite_plano,
    )
    from database import supabase, iniciar_degustacao
    import logging
    logger = logging.getLogger(__name__)

    user_id = update.effective_user.id

    # 1. Verifica se tem registro de assinatura
    try:
        res = supabase.table("assinaturas").select(
            "tipo_plano, status, usou_degustacao, limite_ids"
        ).eq("chat_id", str(user_id)).execute()
        tem_registro = bool(res.data)
        info = res.data[0] if res.data else {}
        usou_degustacao = info.get("usou_degustacao", False)
    except Exception as e:
        logger.error(f"Erro ao consultar assinatura: {e}")
        tem_registro = False
        info = {}
        usou_degustacao = False

    # 2. Usuário NOVO → ativa degustação automaticamente
    if not tem_registro:
        try:
            await iniciar_degustacao(user_id)
            logger.info(f"🎁 Degustação ativada automaticamente para novo usuário {user_id}")
            # Recarrega o info
            res = supabase.table("assinaturas").select(
                "tipo_plano, status, limite_ids"
            ).eq("chat_id", str(user_id)).execute()
            info = res.data[0] if res.data else {}
        except Exception as e:
            logger.error(f"Erro ao ativar degustação: {e}")
    else:
        # 3. Verifica se o plano está ativo
        ativo, info_ativo = verificar_plano_ativo(user_id)
        if not ativo:
            # 3.1. Nunca usou degustação? Pode usar
            if not usou_degustacao:
                try:
                    await iniciar_degustacao(user_id)
                    logger.info(f"🎁 Degustação ativada para {user_id}")
                except Exception as e:
                    logger.error(f"Erro ao ativar degustação: {e}")
            # 3.2. Já usou degustação e não tem plano → win-back
            else:
                await enviar_alerta_plano_expirado(update, context)
                return ConversationHandler.END
        else:
            info = info_ativo

    # 4. Verifica LIMITE de regulações
    try:
        res_count = supabase.table("AlertaSUS_2.0").select("id", count="exact").eq("chat_id", user_id).execute()
        total_regs = res_count.count if hasattr(res_count, "count") and res_count.count is not None else len(res_count.data or [])
    except Exception as e:
        logger.error(f"Erro ao contar regulações: {e}")
        total_regs = 0

        # Cortesia = acesso ilimitado, nunca bloqueia
    tipo_atual = str(info.get("tipo_plano") or "").lower()
    if "cortesia" in tipo_atual:
        limite = 999
    else:
        limite = _obter_limite_plano(info)

    if total_regs >= limite:
        logger.info(f"⏸️ Limite atingido: {total_regs}/{limite} para {user_id}")
        await enviar_oferta_limite_atingido(update, context, total_regs, limite)
        return ConversationHandler.END

    # 5. Continua o fluxo
    context.user_data.clear()
    await update.message.reply_text(
        "📝 <b>Iniciando cadastro de nova regulação.</b>\n\n"
        f"Você tem <b>{total_regs}/{limite}</b> regulações monitoradas.\n\n"
        "Por favor, digite o <b>número do Cartão SUS</b> do paciente (15 dígitos):",
        parse_mode="HTML", reply_markup=TECLADO_CANCELAR
    )
    print(f"🔵 DEBUG CADASTRO: setando _em_fluxo_admin=cadastro", flush=True)
    context.user_data["_em_fluxo_admin"] = "cadastro"
    return ETAPA_SUS

async def receber_sus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    import re as _re

    chat_id = update.effective_chat.id
    texto_bruto = update.message.text.strip()

    # Normaliza: mantém só dígitos (remove espaços, pontos, traços)
    numero_sus = _re.sub(r"\D", "", texto_bruto)

    if not numero_sus:
        await update.message.reply_text(
            "⚠️ Não consegui identificar nenhum dígito.\n\n"
            "Digite o número do Cartão SUS (apenas números):"
        )
        return ETAPA_SUS

    context.user_data['sus'] = numero_sus

    try:
        print(f"DEBUG: Buscando SUS {numero_sus} no Supabase...")

        resposta = supabase.table("AlertaSUS_2.0").select("*").eq(
            "numero_sus", numero_sus
        ).execute()
        registros = resposta.data

        if registros and len(registros) > 0:
            dados_antigos = registros[0]
            context.user_data['_dados_reuso_pendente'] = {
                'nome': dados_antigos.get('nome_paciente'),
                'celular': dados_antigos.get('celular'),
                'nascimento': dados_antigos.get('data_nascimento'),
                'cbo': dados_antigos.get('cbo'),
                'procedimento': dados_antigos.get('procedimento'),
            }

            nome = dados_antigos.get('nome_paciente') or "Não informado"
            celular = dados_antigos.get('celular') or "Não informado"
            nasc = dados_antigos.get('data_nascimento') or "Não informado"

            print("DEBUG: SUS encontrado! Aguardando confirmação.")

            teclado = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Usar esses dados", callback_data="reuso_sim")],
                [InlineKeyboardButton("🔄 Digitar do zero", callback_data="reuso_nao")],
            ])

            await update.message.reply_text(
                f"🔍 <b>Cartão do SUS já cadastrado!</b>\n\n"
                f"Encontramos os seguintes dados:\n"
                f"👤 <b>Nome:</b> {nome}\n"
                f"📱 <b>Celular:</b> {celular}\n"
                f"📅 <b>Nascimento:</b> {nasc}\n\n"
                f"Deseja usar esses dados?",
                parse_mode="HTML",
                reply_markup=teclado,
            )
            return ETAPA_CONFIRMAR_REUSO

    except Exception as e:
        print(f"ERRO no bloco do SUS: {e}")

    print("DEBUG: SUS não encontrado. Indo para ETAPA_NOME.")
    await update.message.reply_text("Qual o nome completo do paciente?")
    return ETAPA_NOME

async def callback_reuso_dados(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa a escolha do usuário: reusar dados ou digitar do zero."""
    query = update.callback_query
    await query.answer()

    dados = context.user_data.get('_dados_reuso_pendente') or {}

    if query.data == "reuso_sim":
        context.user_data['nome'] = dados.get('nome')
        context.user_data['celular'] = dados.get('celular')
        context.user_data['nascimento'] = dados.get('nascimento')
        context.user_data['cbo'] = dados.get('cbo')
        context.user_data['procedimento'] = dados.get('procedimento')

        await query.edit_message_text(
            "✅ <b>Dados carregados com sucesso!</b>\n\n"
            "Agora digite apenas o <b>Número da Regulação</b>:",
            parse_mode="HTML",
        )
        return ETAPA_REGULACAO

    else:
        for campo in ('nome', 'celular', 'nascimento', 'cbo', 'procedimento'):
            context.user_data[campo] = None
        context.user_data.pop('_dados_reuso_pendente', None)

        await query.edit_message_text(
            "Ok! Vamos começar do zero.\n\n"
            "👤 Qual o <b>nome completo do paciente</b>?",
            parse_mode="HTML",
        )
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

    aviso = (
        "✅ <b>Data de nascimento registrada.</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚠️ <b>PRÓXIMO PASSO: ID da Regulação</b>\n\n"
        "Antes de digitar, tenha em mãos o seu <b>comprovante de agendamento</b> e confira:\n\n"
        "✅ O ID correto no papel\n"
        "✅ Se os <b>8 dígitos</b> conferem <b>exatamente</b>\n"
        "✅ Se o ID é da <b>sua</b> regulação\n\n"
        "❌ <b>Se você digitar o ID errado, o bot pode mostrar "
        "dados de outro paciente do SUS.</b>\n\n"
        "📌 <i>Exemplo:</i>\n"
        "Cadastrar <code>12345678</code> em vez de <code>87654321</code> "
        "pode trazer um agendamento <b>completamente diferente</b>.\n\n"
        "💡 O ID tem <b>8 dígitos</b>.\n\n"
        "<b>Digite o ID da Regulação:</b>"
    )

    await update.message.reply_text(aviso, parse_mode="HTML")
    return ETAPA_REGULACAO

async def receber_regulacao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    num_reg = re.sub(r"\D", "", update.message.text)

    if not num_reg:
        await update.message.reply_text(
            "⚠️ Digite um número de regulação válido (apenas dígitos):"
        )
        return ETAPA_REGULACAO

    # ✅ Validação: ID da regulação tem 8 dígitos
    if len(num_reg) != 8:
        await update.message.reply_text(
            f"⚠️ <b>O ID da regulação deve ter 8 dígitos.</b>\n\n"
            f"Você digitou <b>{len(num_reg)}</b> dígito(s).\n\n"
            "📌 <i>Confira no comprovante de agendamento ou na "
            "unidade básica de saúde.</i>\n\n"
            "Digite novamente:",
            parse_mode="HTML",
        )
        return ETAPA_REGULACAO

    # ✅ Verifica duplicata na conta do usuário
    try:
        chat_id = str(update.effective_user.id)
        res_dup = supabase.table("AlertaSUS_2.0").select("id").eq(
            "numero_reg", num_reg
        ).eq("chat_id", int(chat_id) if chat_id.isdigit() else chat_id).execute()

        if res_dup.data:
            await update.message.reply_text(
                f"⚠️ <b>Você já cadastrou a regulação {num_reg}!</b>\n\n"
                "• Para ver o status: use /verificar_especifico\n"
                "• Para corrigir dados: use /corrigir\n\n"
                "O cadastro foi cancelado.",
                parse_mode="HTML",
            )
            context.user_data.clear()
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Erro ao verificar duplicata no cadastro: {e}")

    # ✅ Salva o número da regulação
    context.user_data["numero_regulacao"] = num_reg

    # ✅ FORA DO TRY/EXCEPT — sempre pede a especialidade no fluxo normal
    await update.message.reply_text(
        "Agora informe a <b>Especialidade</b> da consulta/exame\n"
        "<i>(ex: ULTRASSONOGRAFIA, CARDIOLOGIA, OFTALMOLOGIA)</i>\n\n"
        "Se não souber, digite <code>0</code> para pular.",
        parse_mode="HTML",
    )
    return ETAPA_CBO

async def receber_cbo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context): return ConversationHandler.END
    
    valor = update.message.text.strip()
    
    if valor == "0":
        context.user_data["cbo"] = ""
        await update.message.reply_text(
            "⏭️ <b>Especialidade pulada.</b>\n\n"
            "Agora informe a <b>descrição do Procedimento/Exame</b>:\n"
            "<i>(ex: ULTRASSONOGRAFIA, CONSULTA CARDIOLOGIA)</i>",
            parse_mode="HTML",
        )
        return ETAPA_PROCEDIMENTO
    
    context.user_data["cbo"] = formatar_maiusculo(valor)
    
    await update.message.reply_text(
        f"✅ <b>Especialidade registrada:</b> {formatar_maiusculo(valor)}\n\n"
        "Agora informe a <b>descrição do Procedimento/Exame</b>:\n"
        "<i>(ex: ULTRASSONOGRAFIA, CONSULTA CARDIOLOGIA)</i>",
        parse_mode="HTML",
    )
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
        context.user_data.pop("_em_fluxo_admin", None)
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

    # 4. Marketing: oferta pós-1ª regulação
    try:
        from handler import enviar_oferta_primeira_regulacao
        await enviar_oferta_primeira_regulacao(update, context, str(user_id))
    except Exception as e:
        print(f"DEBUG MARKETING: {e}")

    context.user_data.clear()
    print("DEBUG 8: Fluxo finalizado com sucesso!")
    return ConversationHandler.END