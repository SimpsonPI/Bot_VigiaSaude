import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from database import supabase
from utils import (
    SELECIONAR_REGULACAO, SELECIONAR_CAMPO, AGUARDAR_NOVO_VALOR,
    SELECIONAR_REGULACAO_EXCLUIR, CONFIRMAR_EXCLUSAO, TECLADO_MENU
)

logger = logging.getLogger(__name__)

def _mascarar_nome_custom(nome: str) -> str:
    if not nome or str(nome).lower() in ["none", "não informado", ""]:
        return "Não informado"
    partes = nome.strip().split()
    if len(partes) <= 1:
        return partes[0].capitalize()
    primeiro = partes[0].capitalize()
    iniciais = [f"{p[0].upper()}." for p in partes[1:]]
    return f"{primeiro} {' '.join(iniciais)}"

# --- FLUXO DE CORREÇÃO ---
async def iniciar_corrigir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        user_id = update.effective_user.id
        res = supabase.table("AlertaSUS_2.0").select("*").eq("chat_id", user_id).execute()
        regulacoes_brutas = res.data if res.data else []

        if not regulacoes_brutas:
            msg = "⚠️ Nenhuma regulação cadastrada para corrigir."
            if update.message: await update.message.reply_text(msg)
            elif update.callback_query: await update.callback_query.message.reply_text(msg)
            return ConversationHandler.END

        # 🛡️ Remove duplicatas com base no 'numero_reg' para a exibição
        vistos = set()
        regulacoes = []
        for reg in regulacoes_brutas:
            num_reg = reg.get("numero_reg")
            if num_reg not in vistos:
                vistos.add(num_reg)
                regulacoes.append(reg)

        teclado = []
        for reg in regulacoes:
            num_reg = reg.get("numero_reg")
            nome = reg.get("nome_paciente", "")
            rotulo = f"✏️ Reg: {num_reg} - {_mascarar_nome_custom(nome)}"
            teclado.append([InlineKeyboardButton(rotulo, callback_data=f"corr_reg_{num_reg}")])

        teclado.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_corr")])
        
        msg = "🔧 <b>Selecione qual regulação deseja corrigir:</b>"
        if update.message:
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(teclado), parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(teclado), parse_mode="HTML")

        return SELECIONAR_REGULACAO
    except Exception as e:
        logger.error(f"Erro em iniciar_corrigir: {e}")
        return ConversationHandler.END

async def mostrar_resumo_regulacao(update_or_query, context, num_reg):
    """
    Busca os dados atuais da regulação no Supabase e exibe o resumo para confirmação.
    """
    try:
        response = supabase.table("AlertaSUS_2.0").select("*").eq("numero_reg", num_reg).execute()
        
        if response.data:
            reg = response.data[0]
            resumo = (
                f"📋 <b>Regulação:</b> <code>{num_reg}</code>\n"
                f"👤 <b>Paciente:</b> {reg.get('nome_paciente', 'Não informado')}\n"
                f"🩺 <b>CBO / Especialidade:</b> {reg.get('cbo', 'Não informado')}\n"
                f"📱 <b>Celular:</b> {reg.get('celular', 'Não informado')}\n"
                f"🏥 <b>Procedimento:</b> {reg.get('procedimento', 'Não informado')}\n\n"
                f"✅ <b>Alteração realizada com sucesso!</b>"
            )
            
            teclado = [
                [InlineKeyboardButton("✏️ Editar outro campo", callback_data=f"corr_reg_{num_reg}")],
                [InlineKeyboardButton("🏁 Finalizar", callback_data="cancelar_corr")]
            ]
            reply_markup = InlineKeyboardMarkup(teclado)

            if hasattr(update_or_query, "message") and update_or_query.message:
                await update_or_query.message.reply_text(resumo, reply_markup=reply_markup, parse_mode="HTML")
            elif hasattr(update_or_query, "edit_message_text"):
                await update_or_query.edit_message_text(resumo, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Erro ao buscar resumo da regulação: {e}")
        if hasattr(update_or_query, "message") and update_or_query.message:
            await update_or_query.message.reply_text("✅ Campo atualizado com sucesso!", reply_markup=TECLADO_MENU)

async def selecionar_regulacao_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancelar_corr":
        await query.edit_message_text("❌ Correção cancelada.")
        context.user_data.clear()
        return ConversationHandler.END

    if data.startswith("corr_reg_"):
        num_reg = data.replace("corr_reg_", "")
        context.user_data["edit_num_reg"] = num_reg

        teclado = [
            [InlineKeyboardButton("👤 Nome do Paciente", callback_data="corr_campo_nome_paciente")],
            [InlineKeyboardButton("🩺 CBO / Especialidade", callback_data="corr_campo_cbo")],
            [InlineKeyboardButton("📱 Celular", callback_data="corr_campo_celular")],
            [InlineKeyboardButton("🩺 Procedimento", callback_data="corr_campo_procedimento")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_corr")]
        ]

        await query.edit_message_text(
            f"📋 Regulação selecionada: <b>{num_reg}</b>\n\nEscolha qual campo deseja alterar:",
            reply_markup=InlineKeyboardMarkup(teclado),
            parse_mode="HTML"
        )
        return SELECIONAR_CAMPO

    return SELECIONAR_REGULACAO

async def selecionar_campo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancelar_corr":
        await query.edit_message_text("❌ Correção cancelada.")
        context.user_data.clear()
        return ConversationHandler.END

    if data.startswith("corr_campo_"):
        campo = data.replace("corr_campo_", "")
        context.user_data["edit_campo"] = campo

        await query.edit_message_text(
            f"✍️ Digite o novo valor para o campo <b>{campo}</b>:",
            parse_mode="HTML"
        )
        return AGUARDAR_NOVO_VALOR

    return SELECIONAR_CAMPO

async def salvar_novo_valor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    novo_valor = update.message.text.strip()
    num_reg = context.user_data.get("edit_num_reg")
    campo = context.user_data.get("edit_campo")

    try:
        supabase.table("AlertaSUS_2.0").update({campo: novo_valor}).eq("numero_reg", num_reg).execute()
        # Exibe o espelho/resumo atualizado para confirmação do usuário
        await mostrar_resumo_regulacao(update, context, num_reg)
    except Exception as e:
        logger.error(f"Erro ao salvar alteração no Supabase: {e}")
        await update.message.reply_text("❌ Erro ao atualizar o dado no banco de dados.", reply_markup=TECLADO_MENU)

    context.user_data.clear()
    return ConversationHandler.END


# --- FLUXO DE EXCLUSÃO ---
async def iniciar_excluir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        user_id = update.effective_user.id
        res = supabase.table("AlertaSUS_2.0").select("*").eq("chat_id", user_id).execute()
        regulacoes_brutas = res.data if res.data else []

        # Remove duplicatas com base no 'numero_reg' para a exibição
        vistos = set()
        regulacoes = []
        for reg in regulacoes_brutas:
            num_reg = reg.get("numero_reg")
            if num_reg not in vistos:
                vistos.add(num_reg)
                regulacoes.append(reg)

        teclado = []
        for reg in regulacoes:
            num_reg = reg.get("numero_reg")
            nome = reg.get("nome_paciente", "")
            rotulo = f"🗑️ Reg: {num_reg} - {_mascarar_nome_custom(nome)}"
            teclado.append([InlineKeyboardButton(rotulo, callback_data=f"excl_reg_{num_reg}")])

        teclado.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_excl")])
        
        msg = "⚠️ <b>Selecione qual regulação deseja excluir permanentemente:</b>"
        if update.message:
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(teclado), parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(teclado), parse_mode="HTML")

        return SELECIONAR_REGULACAO_EXCLUIR
    except Exception as e:
        logger.error(f"Erro em iniciar_excluir: {e}")
        return ConversationHandler.END

async def selecionar_regulacao_excluir_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancelar_excl":
        await query.edit_message_text("❌ Exclusão cancelada.")
        context.user_data.clear()
        return ConversationHandler.END

    if data.startswith("excl_reg_"):
        num_reg = data.replace("excl_reg_", "")
        context.user_data["del_num_reg"] = num_reg

        teclado = [
            [InlineKeyboardButton("✅ Sim, quero excluir", callback_data="conf_excl_sim")],
            [InlineKeyboardButton("❌ Não, cancelar", callback_data="cancelar_excl")]
        ]

        await query.edit_message_text(
            f"⚠️ Tem certeza que deseja excluir a regulação <b>{num_reg}</b>?",
            reply_markup=InlineKeyboardMarkup(teclado),
            parse_mode="HTML"
        )
        return CONFIRMAR_EXCLUSAO

    return SELECIONAR_REGULACAO_EXCLUIR

async def confirmar_exclusao_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancelar_excl":
        await query.edit_message_text("❌ Exclusão cancelada.")
        context.user_data.clear()
        return ConversationHandler.END

    if data == "conf_excl_sim":
        num_reg = context.user_data.get("del_num_reg")
        user_id = update.effective_user.id
        try:
            supabase.table("AlertaSUS_2.0").delete().eq("numero_reg", num_reg).eq("chat_id", user_id).execute()
            await query.edit_message_text(f"🗑️ Regulação <b>{num_reg}</b> excluída com sucesso.", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Erro ao excluir regulação no Supabase: {e}")
            await query.edit_message_text("❌ Erro ao excluir regulação do banco de dados.")

    context.user_data.clear()
    return ConversationHandler.END