# handler_cadastro.py
import os
import logging
from bot_seguranca import safe_callback

logger = logging.getLogger(__name__)
import re
import logging
from database import supabase

# ... (resto dos imports)
logger = logging.getLogger(__name__)
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from database import salvar_regulacao, registrar_consentimento_lgpd
from utils import (
    DISCLAIMER_TEXTO,
    TECLADO_MENU,
    ETAPA_SUS,
    ETAPA_NOME,
    ETAPA_CELULAR,
    ETAPA_NASCIMENTO,
    ETAPA_REGULACAO,
    ETAPA_CBO,
    ETAPA_PROCEDIMENTO,
    ETAPA_LGPD,
    ETAPA_CONFIRMAR_REUSO,
    ETAPA_ESCOLHER_SUS,
    ETAPA_AGUARDANDO_FOTO,
    ETAPA_CONFIRMAR_OCR,
    ETAPA_ESCOLHER_METODO,
    formatar_data,
    formatar_celular,
    formatar_maiusculo,
    verificar_se_e_menu_e_executar,
)


async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END
    nome = update.message.text.strip()
    # 🔒 Sanitização: remove tags HTML e limita tamanho
    nome = nome.replace("<", "").replace(">", "").replace("&", "&amp;")[:80]
    context.user_data["nome"] = nome
    await update.message.reply_text("Digite a <b>Data de Nascimento</b> (ex: DD/MM/AAAA):", parse_mode="HTML")
    return ETAPA_NASCIMENTO


async def receber_celular(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END
    context.user_data["celular"] = formatar_celular(update.message.text)
    await update.message.reply_text(
        "Digite a <b>data de nascimento</b> do paciente (DD/MM/AAAA):",
        parse_mode="HTML",
    )
    return ETAPA_NASCIMENTO


async def receber_nascimento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END
    context.user_data["nascimento"] = formatar_data(update.message.text)
    await update.message.reply_text("Agora, por favor, digite o <b>Número da Regulação</b>:", parse_mode="HTML")
    return ETAPA_REGULACAO


async def receber_cbo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END
    cbo = update.message.text.strip()
    # 🔒 Sanitização
    cbo = cbo.replace("<", "").replace(">", "").replace("&", "&amp;")[:80]
    context.user_data["cbo"] = cbo
    context.user_data["cbo"] = formatar_maiusculo(cbo) if cbo != "0" else ""
    await update.message.reply_text("Qual a descrição do <b>Procedimento/Exame</b>?", parse_mode="HTML")
    return ETAPA_PROCEDIMENTO


async def receber_procedimento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END
    procedimento = update.message.text.strip()
    # 🔒 Sanitização
    procedimento = procedimento.replace("<", "").replace(">", "").replace("&", "&amp;")[:80]
    context.user_data["procedimento"] = procedimento


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
        res = (
            supabase.table("assinaturas")
            .select("tipo_plano, status, usou_degustacao, limite_ids")
            .eq("chat_id", str(user_id))
            .execute()
        )
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
            res = (
                supabase.table("assinaturas")
                .select("tipo_plano, status, limite_ids")
                .eq("chat_id", str(user_id))
                .execute()
            )
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
        total_regs = (
            res_count.count
            if hasattr(res_count, "count") and res_count.count is not None
            else len(res_count.data or [])
        )
    except Exception as e:
        logger.error(f"Erro ao contar regulações: {e}")
        total_regs = 0

        # Cortesia = acesso ilimitado, nunca bloqueia
    # Cortesia e admin = acesso ilimitado
    from config import is_admin

    tipo_atual = str(info.get("tipo_plano") or "").lower()
    if is_admin(user_id) or "cortesia" in tipo_atual or "admin" in tipo_atual:
        limite = 999
    else:
        limite = _obter_limite_plano(info)

    if total_regs >= limite:
        logger.info(f"⏸️ Limite atingido: {total_regs}/{limite} para {user_id}")
        await enviar_oferta_limite_atingido(update, context, total_regs, limite)
        return ConversationHandler.END

    # 5. Menu: foto ou manual
    context.user_data.clear()
    context.user_data["_em_fluxo_admin"] = "cadastro"
    context.user_data["_total_regs"] = total_regs
    context.user_data["_limite"] = limite
    context.user_data["_user_id"] = user_id

    teclado = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("\U0001f4f7 Enviar foto do comprovante", callback_data="cad_foto")],
            [InlineKeyboardButton("\u2328\ufe0f Digitar manualmente", callback_data="cad_manual")],
            [InlineKeyboardButton("\u274c Cancelar", callback_data="iniciar")],
        ]
    )
    await update.message.reply_text(
        "\U0001f4dd <b>Iniciando cadastro de nova regula\u00e7\u00e3o.</b>\n\n"
        f"Voc\u00ea tem <b>{total_regs}/{limite}</b> regula\u00e7\u00f5es monitoradas.\n\n"
        "Como deseja preencher os dados?\n\n"
        "\U0001f4f7 <b>Enviar foto</b> - a IA extrai os dados automaticamente\n"
        "\u2328\ufe0f <b>Digitar manualmente</b> - voc\u00ea informa os dados",
        parse_mode="HTML",
        reply_markup=teclado,
    )
    return ETAPA_ESCOLHER_METODO


async def receber_sus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END
    import re as _re

    chat_id = update.effective_chat.id
    texto_bruto = update.message.text.strip()

    # Normaliza: mantém só dígitos (remove espaços, pontos, traços)
    numero_sus = _re.sub(r"\D", "", texto_bruto)

    if not numero_sus:
        await update.message.reply_text(
            "⚠️ Não consegui identificar nenhum dígito.\n\n" "Digite o número do Cartão SUS (apenas números):"
        )
        return ETAPA_SUS

    context.user_data["sus"] = numero_sus

    try:
        resposta = (
            supabase.table("AlertaSUS_2.0")
            .select("*")
            .eq("numero_sus", numero_sus)
            .eq("chat_id", str(chat_id))
            .execute()
        )
        registros = resposta.data

        if registros and len(registros) > 0:
            dados_antigos = registros[0]
            context.user_data["_dados_reuso_pendente"] = {
                "nome": dados_antigos.get("nome_paciente"),
                "nascimento": dados_antigos.get("data_nascimento"),
                "cbo": dados_antigos.get("cbo"),
                "procedimento": dados_antigos.get("procedimento"),
            }

            nome = dados_antigos.get("nome_paciente") or "Não informado"
            nasc = dados_antigos.get("data_nascimento") or "Não informado"

            teclado = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("✅ Usar esses dados", callback_data="reuso_sim")],
                    [InlineKeyboardButton("🔄 Digitar do zero", callback_data="reuso_nao")],
                ]
            )

            await update.message.reply_text(
                f"🔍 <b>Cartão do SUS já cadastrado!</b>\n\n"
                f"Encontramos os seguintes dados:\n"
                f"👤 <b>Nome:</b> {nome}\n"
                f"📅 <b>Nascimento:</b> {nasc}\n\n"
                f"Deseja usar esses dados?",
                parse_mode="HTML",
                reply_markup=teclado,
            )
            return ETAPA_CONFIRMAR_REUSO

    except Exception as e:
        print(f"ERRO no bloco do SUS: {e}")

    await update.message.reply_text("Qual o nome completo do paciente?")
    return ETAPA_NOME


async def callback_reuso_dados(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa a escolha do usuário: reusar dados ou digitar do zero."""
    query = update.callback_query
    await query.answer()

    dados = context.user_data.get("_dados_reuso_pendente") or {}

    if query.data == "reuso_sim":
        context.user_data["nome"] = dados.get("nome")
        context.user_data["celular"] = dados.get("celular")
        context.user_data["nascimento"] = dados.get("nascimento")
        context.user_data["cbo"] = dados.get("cbo")
        context.user_data["procedimento"] = dados.get("procedimento")

        await query.edit_message_text(
            "✅ <b>Dados carregados com sucesso!</b>\n\n" "Agora digite apenas o <b>Número da Regulação</b>:",
            parse_mode="HTML",
        )
        return ETAPA_REGULACAO

    else:
        for campo in ("nome", "celular", "nascimento", "cbo", "procedimento"):
            context.user_data[campo] = None
        context.user_data.pop("_dados_reuso_pendente", None)

        await query.edit_message_text(
            "Ok! Vamos começar do zero.\n\n👤 Qual o <b>nome completo do paciente</b>?",
            parse_mode="HTML",
        )
        return ETAPA_NOME


async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END
    context.user_data["nome"] = update.message.text.strip()
    await update.message.reply_text("Digite a <b>Data de Nascimento</b> (ex: DD/MM/AAAA):", parse_mode="HTML")
    return ETAPA_NASCIMENTO


async def receber_celular(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END
    celular = formatar_celular(update.message.text.strip())
    context.user_data["celular"] = celular
    await update.message.reply_text(
        "Digite a <b>data de nascimento</b> do paciente (DD/MM/AAAA):",
        parse_mode="HTML",
    )
    return ETAPA_NASCIMENTO


async def receber_nascimento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END
    nascimento = formatar_data(update.message.text.strip())

    if not nascimento:
        await update.message.reply_text(
            "Data invalida. Digite no formato DD/MM/AAAA:",
            parse_mode="HTML",
        )
        return ETAPA_NASCIMENTO

    context.user_data["nascimento"] = nascimento

    # Se veio do OCR, ja tem tudo -> pula pro LGPD
    if context.user_data.get("_origem_ocr"):
        return await _enviar_termo_lgpd(update, context)

        # Fluxo normal
        texto_id = (
            "✅ <b>Dados registrados.</b>\n\n"
            "⚠️ <b>PRÓXIMO PASSO: ID da Regulação</b>\n\n"
            "Antes de digitar, tenha em mãos o seu <b>comprovante de agendamento</b> e confira:\n"
            "✅ O ID correto no papel\n"
            "✅ Se os <b>8 dígitos</b> conferem\n\n"
            "🆔 <b>Digite o ID da Regulação:</b>"
        )

    caminho_imagem = os.path.join(os.path.dirname(__file__), "comprovante_sus.jpg")
    try:
        with open(caminho_imagem, "rb") as foto:
            await update.message.reply_photo(photo=foto, caption=texto_id, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Erro ao enviar imagem: {e}")
        await update.message.reply_text(
            texto_id + "\n\n(Imagem ilustrativa indisponível no momento)", parse_mode="HTML"
        )

    return ETAPA_REGULACAO


async def receber_regulacao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END
    num_reg = re.sub(r"\D", "", update.message.text)

    if not num_reg:
        await update.message.reply_text("⚠️ Digite um número de regulação válido (apenas dígitos):")
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

    # ✅ Rate limit de cadastros (5/dia)
    from mitigacao_cadastro import pode_cadastrar, registrar_cadastro

    chat_id = str(update.effective_user.id)
    pode, _motivo, _restantes = pode_cadastrar(chat_id)
    if not pode:
        await update.message.reply_text(
            "⏳ <b>Limite diário de cadastros atingido!</b>\n\n"
            "Você já cadastrou <b>5 regulações</b> hoje.\n\n"
            "💡 <i>Você pode cadastrar mais amanhã ou usar /corrigir para editar regulações existentes.</i>",
            parse_mode="HTML",
        )
        context.user_data.clear()
        return ConversationHandler.END

    # ✅ Verifica duplicata global (mesmo usuário ou outro)
    try:
        chat_id_int = int(chat_id) if chat_id.isdigit() else chat_id
        res_dup = supabase.table("AlertaSUS_2.0").select("id, chat_id").eq("numero_reg", num_reg).execute()

        if res_dup.data:
            mesmo_usuario = any(str(r.get("chat_id")) == str(chat_id_int) for r in res_dup.data)
            if mesmo_usuario:
                await update.message.reply_text(
                    f"⚠️ <b>Você já cadastrou a regulação {num_reg}!</b>\n\n"
                    "• Para ver o status: use /verificar_especifico\n"
                    "• Para corrigir dados: use /corrigir\n\n"
                    "O cadastro foi cancelado.",
                    parse_mode="HTML",
                )
                context.user_data.clear()
                return ConversationHandler.END
            else:
                await update.message.reply_text(
                    "⚠️ <b>Este ID já está sendo monitorado por outro usuário.</b>\n\n"
                    "Se você acredita que este ID é seu, entre em contato:\n"
                    "📧 suportevigiasaude@gmail.com\n\n"
                    "O cadastro foi cancelado.",
                    parse_mode="HTML",
                )

                try:
                    dono_chat_id = str(res_dup.data[0].get("chat_id"))
                    await context.bot.send_message(
                        chat_id=int(dono_chat_id),
                        text=(
                            "🔔 <b>Tentativa de cadastro detectada</b>\n\n"
                            f"Alguém tentou cadastrar a regulação <code>{num_reg}</code> "
                            "em outra conta.\n\n"
                            "Se não foi você, sua regulação está segura."
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"Nao notificou dono original: {e}")

                context.user_data.clear()
                return ConversationHandler.END
    except Exception as e:
        logger.error(f"Erro ao verificar duplicata no cadastro: {e}")

    registrar_cadastro(chat_id)

    # ✅ Salva o número da regulação
    context.user_data["numero_regulacao"] = num_reg

    # ✅ FORA DO TRY/EXCEPT — sempre pede a especialidade no fluxo normal
    await update.message.reply_text(
        "Agora informe a <b>Especialidade</b> da consulta/exame\n"
        "<i>(Ex: Consulta / Exame)</i>\n\n"
        "Se não souber, digite <code>0</code> para pular.",
        parse_mode="HTML",
    )
    return ETAPA_CBO


async def receber_cbo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END

    valor = update.message.text.strip()

    if valor == "0":
        context.user_data["cbo"] = ""
        await update.message.reply_text(
            "⏭️ <b>Especialidade pulada.</b>\n\n"
            "Agora informe a <b>descrição do Procedimento/Exame</b>:\n"
            "<i>(Ex: Consulta / Exame)</i>",
            parse_mode="HTML",
        )
        return ETAPA_PROCEDIMENTO

    context.user_data["cbo"] = formatar_maiusculo(valor)

    await update.message.reply_text(
        f"✅ <b>Especialidade registrada:</b> {formatar_maiusculo(valor)}\n\n"
        "Agora informe a <b>descrição do Procedimento/Exame</b>:\n"
        "<i>(Ex: Consulta / Exame)</i>",
        parse_mode="HTML",
    )
    return ETAPA_PROCEDIMENTO


async def receber_procedimento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await verificar_se_e_menu_e_executar(update, context):
        return ConversationHandler.END
    context.user_data["procedimento"] = update.message.text.strip()

    teclado_lgpd = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Aceitar e Finalizar", callback_data="aceitar_lgpd")],
            [InlineKeyboardButton("❌ Cancelar Cadastro", callback_data="cancelar_cadastro")],
        ]
    )

    await update.message.reply_text(
        "🛡️ <b>TERMO DE CONSENTIMENTO LGPD</b>\n\n"
        "Para prosseguir com o monitoramento automático, autorizo o armazenamento dos dados fornecidos exclusivamente para finalidades de consulta pública no sistema FMS Piauí.\n\n"
        f"{DISCLAIMER_TEXTO}\n\nVocê aceita o termo?",
        parse_mode="HTML",
        reply_markup=teclado_lgpd,
    )
    return ETAPA_LGPD


@safe_callback
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
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Cadastro cancelado pelo usuário.",
            reply_markup=TECLADO_MENU,
        )
        context.user_data.clear()
        context.user_data.pop("_em_fluxo_admin", None)
        return ConversationHandler.END

    dados_salvar = {
        "chat_id": user_id,
        "numero_sus": dados.get("sus"),
        "nome_paciente": dados.get("nome"),
        
        "data_nascimento": dados.get("nascimento"),
        "numero_reg": dados.get("numero_regulacao"),
        "cbo": dados.get("cbo"),
        "procedimento": dados.get("procedimento"),
    }
    # 🛡️ Prevenção de duplicata: mesmo chat_id + numero_reg
    numero_reg_novo = dados_salvar.get("numero_reg")
    if numero_reg_novo:
        try:
            checagem = (
                supabase.table("AlertaSUS_2.0")
                .select("id")
                .eq("chat_id", user_id)
                .eq("numero_reg", numero_reg_novo)
                .execute()
            )
            if checagem.data:
                try:
                    await query.message.delete()
                except Exception:
                    try:
                        await query.edit_message_reply_markup(reply_markup=None)
                    except Exception:
                        pass

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⚠️ <b>Você já tem a regulação <code>{numero_reg_novo}</code> cadastrada.</b>\n\n"
                        "Não é possível cadastrar a mesma regulação duas vezes.\n\n"
                        "💡 Se precisar alterar algo, use /corrigir.\n"
                        "💡 Se quiser remover, use /excluir."
                    ),
                    parse_mode="HTML",
                    reply_markup=TECLADO_MENU,
                )
                context.user_data.clear()
                context.user_data.pop("_em_fluxo_admin", None)
                return ConversationHandler.END
        except Exception as e:
            print(f"DEBUG duplicata: erro na checagem ({e}) — seguindo com insert")

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
        parse_mode="HTML",
    )

    # 3. Envia o Menu Principal
    print("DEBUG 7: Enviando menu principal...")
    await context.bot.send_message(chat_id=chat_id, text="O que deseja fazer agora?", reply_markup=TECLADO_MENU)

    # 4. Marketing: oferta pós-1ª regulação
    try:
        from handler import enviar_oferta_primeira_regulacao

        await enviar_oferta_primeira_regulacao(update, context, str(user_id))
    except Exception as e:
        print(f"DEBUG MARKETING: {e}")

    context.user_data.clear()
    print("DEBUG 8: Fluxo finalizado com sucesso!")
    return ConversationHandler.END


# ═══════════════════════════════════════════════
# FUNÇÕES DE OCR E LGPD (adicionadas 2026-10-15)
# ═══════════════════════════════════════════════


async def _enviar_termo_lgpd(update, context):
    """Envia o Termo de Consentimento LGPD com botões."""
    teclado_lgpd = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Aceitar e Finalizar", callback_data="aceitar_lgpd")],
            [InlineKeyboardButton("❌ Cancelar Cadastro", callback_data="cancelar_cadastro")],
        ]
    )
    await update.message.reply_text(
        "🛡️ <b>TERMO DE CONSENTIMENTO LGPD</b>\n\n"
        "Para prosseguir com o monitoramento automático, autorizo o armazenamento "
        "dos dados fornecidos exclusivamente para finalidades de consulta pública "
        "no sistema FMS Piauí.\n\n"
        f"{DISCLAIMER_TEXTO}\n\nVocê aceita o termo?",
        parse_mode="HTML",
        reply_markup=teclado_lgpd,
    )
    return ETAPA_LGPD


from bot_seguranca import safe_callback


@safe_callback
async def callback_escolher_sus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa a escolha do SUS no início do cadastro."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancelar":
        await query.edit_message_text("❌ Cadastro cancelado.")
        context.user_data.clear()
        return ConversationHandler.END

    if data == "novo_sus":
        for k in ("sus", "nome", "nascimento"):
            context.user_data.pop(k, None)
        await query.edit_message_text(
            "Ok! Digite o <b>número do Cartão SUS</b> do paciente (15 dígitos):",
            parse_mode="HTML",
        )
        return ETAPA_SUS

    if data.startswith("usar_sus_"):
        num_sus = data.replace("usar_sus_", "")
        try:
            res = (
                supabase.table("AlertaSUS_2.0")
                .select("nome_paciente, data_nascimento")
                .eq("chat_id", update.effective_user.id)
                .eq("numero_sus", num_sus)
                .order("id", desc=True)
                .limit(1)
                .execute()
            )
            dados = res.data[0] if res.data else {}
        except Exception as e:
            logger.error(f"Erro ao buscar dados do SUS: {e}")
            dados = {}

        context.user_data["sus"] = num_sus
        context.user_data["nome"] = dados.get("nome_paciente") or ""
        context.user_data["nascimento"] = dados.get("data_nascimento") or ""

        texto_id = (
            f"✅ <b>SUS carregado:</b> <code>{num_sus}</code>\n\n"
            f"👤 <b>Paciente:</b> {dados.get('nome_paciente') or '—'}\n"
            f"📅 <b>Nascimento:</b> {dados.get('data_nascimento') or '—'}\n\n"
            "🆔 <b>Agora digite o ID da Regulação (8 dígitos):</b>"
        )

        try:
            await query.message.delete()
        except Exception:
            pass

        caminho_imagem = os.path.join(os.path.dirname(__file__), "comprovante_sus.jpg")
        try:
            with open(caminho_imagem, "rb") as foto:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id, photo=foto, caption=texto_id, parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Erro ao enviar imagem: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=texto_id + "\n\n(Imagem ilustrativa indisponível no momento)",
                parse_mode="HTML",
            )

        return ETAPA_REGULACAO

    return ConversationHandler.END


@safe_callback
async def callback_escolher_metodo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa a escolha: foto ou manual."""
    print("🔴 CLIQUE RECEBIDO NO BOTÃO MANUAL!", flush=True)
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if query.data == "cad_foto":
        await query.edit_message_text(
            "📸 <b>Envie a foto do comprovante de regulação.</b>\n\n"
            "<i>Certifique-se de que o número da regulação e o cartão SUS estejam legíveis.</i>",
            parse_mode="HTML",
        )
        return ETAPA_AGUARDANDO_FOTO

    # fluxo manual
    try:
        # CORRIGIDO: Removido o 'celular' da busca para não dar erro no Supabase
        res_sus = (
            supabase.table("AlertaSUS_2.0")
            .select("numero_sus, nome_paciente, data_nascimento")
            .eq("chat_id", user_id)
            .order("id", desc=True)
            .execute()
        )
        registros = res_sus.data or []
    except Exception as e:
        logger.error(f"Erro ao buscar SUS: {e}")
        registros = []

    # CORRIGIDO: Adicionado o loop 'for' que estava faltando
    sus_unicos = {}
    for r in registros:
        num = r.get("numero_sus")
        if num and num not in sus_unicos:
            sus_unicos[num] = r

    sus_lista = list(sus_unicos.items())

    if not sus_lista:
        await query.edit_message_text(
            "📝 <b>Cadastro manual</b>\n\nDigite o <b>número do Cartão SUS</b> do paciente (15 dígitos):",
            parse_mode="HTML",
        )
        return ETAPA_SUS

    # Monta a tela com os botões (igual à imagem)
    botoes = []
    for num, dados in sus_lista:
        nome = dados.get("nome_paciente") or "Sem nome"
        # Corta o nome se for muito grande para o botão não quebrar
        nome_curto = nome[:20] + "..." if len(nome) > 20 else nome
        botoes.append([InlineKeyboardButton(f"💳 {num} · {nome_curto}", callback_data=f"usar_sus_{num}")])

    botoes.append([InlineKeyboardButton("➕ Cadastrar novo SUS", callback_data="novo_sus")])
    botoes.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")])

    teclado = InlineKeyboardMarkup(botoes)

    await query.edit_message_text(
        "📝 <b>Iniciando cadastro de nova regulação.</b>\n\n" "Selecione qual Cartão do SUS deseja usar:",
        parse_mode="HTML",
        reply_markup=teclado,
    )
    return ETAPA_ESCOLHER_SUS

    # cad_manual — fluxo antigo
    try:
        res_sus = (
            supabase.table("AlertaSUS_2.0")
            .select("numero_sus, nome_paciente, data_nascimento")
            .eq("chat_id", user_id)
            .order("id", desc=True)
            .execute()
        )
        registros = res_sus.data or []
    except Exception as e:
        logger.error(f"Erro ao buscar SUS: {e}")
        registros = []

    sus_unicos = {}
    for r in registros:
        num = r.get("numero_sus")
        if num and num not in sus_unicos:
            sus_unicos[num] = r
    sus_lista = list(sus_unicos.items())

    if not sus_lista:
        await query.edit_message_text(
            "📝 <b>Cadastro manual</b>\n\nDigite o <b>número do Cartão SUS</b> do paciente (15 dígitos):",
            parse_mode="HTML",
        )
        return ETAPA_SUS

    if len(sus_lista) == 1:
        num, dados = sus_lista[0]
        nome = dados.get("nome_paciente") or "—"
        teclado = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Usar mesmo Cartão do SUS", callback_data=f"usar_sus_{num}")],
                [InlineKeyboardButton("🔄 Cadastrar novo SUS", callback_data="novo_sus")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="iniciar")],
            ]
        )
        await query.edit_message_text(
            f"💳 Detectei um Cartão do SUS cadastrado:\n<code>{num}</code> · {nome}\n\nDeseja usar o mesmo?",
            parse_mode="HTML",
            reply_markup=teclado,
        )
    else:
        botoes = []
        for num, dados in sus_lista:
            nome = (dados.get("nome_paciente") or "—")[:22]
            botoes.append([InlineKeyboardButton(f"💳 {num} · {nome}", callback_data=f"usar_sus_{num}")])
        botoes.append([InlineKeyboardButton("➕ Cadastrar novo SUS", callback_data="novo_sus")])
        botoes.append([InlineKeyboardButton("❌ Cancelar", callback_data="iniciar")])
        await query.edit_message_text(
            "💳 <b>Selecione qual Cartão do SUS deseja usar:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(botoes),
        )

    return ETAPA_ESCOLHER_SUS


async def receber_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe foto do comprovante e extrai dados via IA (Gemini)."""
    if not update.message or not update.message.photo:
        await update.message.reply_text(
            "⚠️ Envie uma <b>foto</b> do comprovante (não um arquivo).",
            parse_mode="HTML",
        )
        return ETAPA_AGUARDANDO_FOTO

    msg = await update.message.reply_text("🔍 <b>Analisando o comprovante...</b>", parse_mode="HTML")

    try:
        from ocr_vision import extrair_dados_comprovante

        foto = update.message.photo[-1]
        arquivo = await foto.get_file()
        imagem_bytes = bytes(await arquivo.download_as_bytearray())

        dados = await extrair_dados_comprovante(imagem_bytes)

        if dados.get("erro"):
            await msg.edit_text(
                f"❌ <b>Não consegui ler o comprovante.</b>\n\n<i>{dados['erro']}</i>\n\nTente outra foto ou digite manualmente.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("📷 Tentar outra foto", callback_data="cad_foto")],
                        [InlineKeyboardButton("⌨️ Digitar manualmente", callback_data="cad_manual")],
                    ]
                ),
            )
            return ETAPA_AGUARDANDO_FOTO

        context.user_data["_ocr_dados"] = dados

        linhas = ["📄 <b>Dados extraídos do comprovante:</b>\n"]
        if dados.get("numero_reg"):
            linhas.append(f"🔢 <b>Regulação:</b> <code>{dados['numero_reg']}</code>")
        if dados.get("numero_sus"):
            linhas.append(f"💳 <b>Cartão SUS:</b> <code>{dados['numero_sus']}</code>")
        if dados.get("nome_paciente"):
            linhas.append(f"👤 <b>Paciente:</b> {dados['nome_paciente']}")
        if dados.get("cbo"):
            linhas.append(f"🩺 <b>Especialidade:</b> {dados['cbo']}")
        if dados.get("procedimento"):
            linhas.append(f"🏥 <b>Procedimento:</b> {dados['procedimento']}")
        linhas.append(f"\n<i>Confiança: {dados.get('confianca', 'média')}</i>")

        # Bloqueio de duplicata
        num_reg = dados.get("numero_reg")
        if num_reg:
            try:
                res_dup = supabase.table("AlertaSUS_2.0").select("chat_id").eq("numero_reg", num_reg).execute()
                if res_dup.data:
                    mesmo = any(str(r.get("chat_id")) == str(update.effective_user.id) for r in res_dup.data)
                    if mesmo:
                        await msg.edit_text(
                            f"⚠️ <b>Você já cadastrou a regulação {num_reg}!</b>",
                            parse_mode="HTML",
                        )
                        return ConversationHandler.END
                    else:
                        await msg.edit_text(
                            "⚠️ <b>Este ID já está sendo monitorado por outro usuário.</b>",
                            parse_mode="HTML",
                        )
                        return ConversationHandler.END
            except Exception as e:
                logger.error(f"Erro dup OCR: {e}")

        teclado = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Está correto", callback_data="ocr_ok")],
                [InlineKeyboardButton("✏️ Corrigir manualmente", callback_data="ocr_manual")],
                [InlineKeyboardButton("📷 Enviar outra foto", callback_data="cad_foto")],
            ]
        )
        await msg.edit_text("\n".join(linhas), parse_mode="HTML", reply_markup=teclado)
        return ETAPA_CONFIRMAR_OCR

    except Exception as e:
        logger.error(f"Erro em receber_foto: {e}")
        await msg.edit_text(
            "❌ <b>Erro ao processar a foto.</b>\n\nTente novamente ou digite manualmente.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("📷 Tentar outra foto", callback_data="cad_foto")],
                    [InlineKeyboardButton("⌨️ Digitar manualmente", callback_data="cad_manual")],
                ]
            ),
        )
        return ETAPA_AGUARDANDO_FOTO


async def callback_confirmar_ocr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa confirmação dos dados OCR."""
    query = update.callback_query
    await query.answer()
    dados = context.user_data.get("_ocr_dados") or {}

    if query.data == "ocr_ok":
        context.user_data["sus"] = dados.get("numero_sus")
        context.user_data["nome"] = dados.get("nome_paciente")
        context.user_data["cbo"] = dados.get("cbo")
        context.user_data["procedimento"] = dados.get("procedimento")
        context.user_data["numero_regulacao"] = dados.get("numero_reg")
        context.user_data["_origem_ocr"] = True

        await query.edit_message_text(
            "✅ <b>Dados confirmados!</b>\n\nFalta apenas 1 informação.\n\n📅 Digite a <b>Data de Nascimento</b> (ex: DD/MM/AAAA):",
            parse_mode="HTML",
        )
        return ETAPA_NASCIMENTO

    elif query.data == "ocr_manual":
        context.user_data["sus"] = dados.get("numero_sus")
        context.user_data["nome"] = dados.get("nome_paciente")
        context.user_data["cbo"] = dados.get("cbo")
        context.user_data["procedimento"] = dados.get("procedimento")
        context.user_data["numero_regulacao"] = dados.get("numero_reg")
        context.user_data["_origem_ocr"] = True

        await query.edit_message_text(
            "✏️ <b>Correção manual</b>\n\nDigite o <b>número do Cartão SUS</b> (15 dígitos):",
            parse_mode="HTML",
        )
        return ETAPA_SUS

    return ETAPA_CONFIRMAR_OCR
