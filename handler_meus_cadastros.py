from telegram import Update
from telegram.ext import ContextTypes
from database import supabase
from utils import obter_teclado_menu
import logging

logger = logging.getLogger(__name__)


async def comando_meus_cadastros(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista as regulações ativas do usuário no VS Premium."""
    chat_id = update.effective_user.id

    try:
        # Busca na tabela do VS Premium
        res = (
            supabase.table("AlertaSUS_2.0")
            .select("numero_reg, nome_paciente, status_anterior, cbo, procedimento")
            .eq("chat_id", chat_id)
            .execute()
        )

        registros = res.data

        if not registros:
            await update.message.reply_text(
                "Você não possui nenhuma regulação cadastrada no momento.\nUse /cadastrar_nova para adicionar.",
                reply_markup=obter_teclado_menu(update.effective_user.id),
            )
            return

        msg = "<b>📋 Suas Regulações Cadastradas:</b>\n\n"
        for i, r in enumerate(registros, 1):
            # Pega os dados do banco
            especialidade = r.get("cbo") or "Não informada"
            procedimento = r.get("procedimento") or "Não informado"
            status = r.get("status_anterior") or "Aguardando verificação"

            msg += f"{i}. ID: <code>{r.get('numero_reg')}</code>\n"
            msg += f"👤 Paciente: {r.get('nome_paciente')}\n"
            msg += f"🩺 Especialidade: {especialidade}\n"
            msg += f"📋 Procedimento: {procedimento}\n"
            msg += f"📊 Status: {status}\n\n"

        msg += "<i>Para atualizar o status, use o botão '🔄 Verificar Todas'.</i>"

        await update.message.reply_text(
            msg, parse_mode="HTML", reply_markup=obter_teclado_menu(update.effective_user.id)
        )

    except Exception as e:
        logger.error(f"Erro ao listar cadastros: {e}")
        await update.message.reply_text(
            "❌ Erro ao buscar seus cadastros.", reply_markup=obter_teclado_menu(update.effective_user.id)
        )
