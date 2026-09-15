from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    force=True
)

# Silencia logs verbosos do httpx/httpcore (evita vazar token nos logs)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
import os
import json
import asyncio

from telegram import BotCommand, BotCommandScopeAllPrivateChats, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from admin_ia_controller import executar_acao_admin
from handler import (
    comando_planos,
    comando_privacidade,
    comando_verificar_todas,
    detalhar_plano,
    conv_cadastro,
    conv_consulta_especifica,
    conv_excluir,
    iniciar_cadastro_manual,
    iniciar_corrigir,
    iniciar_excluir,
    iniciar_verificar_especifico,
    mostrar_email_suporte,
    start,
    configurar_menu_comandos,
    callback_faq_suporte,
    callback_privacidade_voltar,
    callback_abrir_termo_privacidade,
    mostrar_email_suporte,
)

from handler_gestao import (
    selecionar_regulacao_callback,
    selecionar_campo_callback,
    salvar_novo_valor,
)
from handler_pagamento import gerar_pagamento_pix
from handler_tarefas import limpar_pagamentos_pendentes
from pagamento_polling import (
    verificar_pagamentos_pendentes,
    set_telegram_bot,
)
from utils import (
    SELECIONAR_REGULACAO,
    SELECIONAR_CAMPO,
    AGUARDAR_NOVO_VALOR,
)
from admin import (
    comando_estatisticas,
    comando_listar_ativos,
    comando_bloquear,
    comando_detalhes,
    comando_dar_plano,
    comando_cortesia,
    comando_remover_cortesia,
    comando_aviso,
    comando_menu_admin,
    comando_retirar_plano,
    comando_retirar_degustacao,
)
from suporte import (
    menu_suporte,
    exibir_resposta_faq,
    iniciar_atendimento_20,
    cancelar_suporte,
    conv_suporte,
    suporte_email,
)

logger = logging.getLogger(__name__)


async def erro_global_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exceção capturada pelo bot:", exc_info=context.error)


async def verificar_vencimentos(app):
    """Verifica assinaturas próximas do vencimento e envia alertas escalonados."""
    from datetime import datetime, timedelta, timezone
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from database import supabase

    agora = datetime.now(timezone.utc)

    # Faixas de aviso: (dias_restantes_max, dias_restantes_min, código, texto)
    FAIXAS = [
        (7.5, 6.5, "7d", "📅 <b>Faltam 7 dias</b> para seu plano vencer.\n\nRenove agora para não interromper o monitoramento das suas regulações."),
        (3.5, 2.5, "3d", "⏰ <b>Faltam apenas 3 dias!</b>\n\nGaranta a renovação do seu plano para continuar recebendo alertas das suas regulações."),
        (1.5, 0.5, "1d", "🚨 <b>Seu plano expira AMANHÃ!</b>\n\nRenove agora para não perder o acesso ao monitoramento."),
        (0.5, -0.5, "expirado", "❌ <b>Seu plano expirou hoje.</b>\n\nRenove para retomar o monitoramento das suas regulações."),
    ]

    try:
        res = supabase.table("assinaturas").select("*").eq("status", "ativo").execute()
        for assinatura in res.data:
            venc = assinatura.get("data_vencimento")
            tipo = str(assinatura.get("tipo_plano", "")).lower()
            if not venc or tipo == "cortesia":
                continue

            try:
                venc_dt = datetime.fromisoformat(str(venc).replace("Z", "+00:00"))
            except Exception:
                continue

            dias_restantes = (venc_dt - agora).total_seconds() / 86400

            for mx, mn, codigo, texto_base in FAIXAS:
                if mn <= dias_restantes < mx:
                    ultimo = assinatura.get("ultimo_aviso")

                    # Não repete o mesmo aviso
                    if ultimo == codigo:
                        break

                    chat_id = assinatura.get("chat_id")

                    msg = (
                        f"<b>Sua assinatura do VigiaSaúde</b>\n\n"
                        f"{texto_base}\n\n"
                        f"• <b>Plano atual:</b> {tipo.upper()}\n"
                        f"• <b>Vence em:</b> {venc_dt.strftime('%d/%m/%Y')}"
                    )

                    teclado = InlineKeyboardMarkup([
                        [InlineKeyboardButton("💳 Renovar Agora", callback_data="planos")]
                    ])

                    try:
                        await app.bot.send_message(
                            chat_id=chat_id,
                            text=msg,
                            reply_markup=teclado,
                            parse_mode="HTML",
                        )
                        logger.info(f"📢 Aviso {codigo} enviado para {chat_id}")

                        # Marca como enviado no banco
                        supabase.table("assinaturas").update({
                            "ultimo_aviso": codigo
                        }).eq("chat_id", str(chat_id)).execute()

                    except Exception as e:
                        logger.error(f"Erro ao enviar aviso para {chat_id}: {e}")

                    break  # só envia 1 aviso por assinatura por execução

    except Exception as e:
        logger.error(f"Erro na verificação de vencimentos: {e}")


async def post_init(app):
    """Executa tarefas após a inicialização do bot."""
    set_telegram_bot(app.bot)

    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(
            lambda _: asyncio.create_task(verificar_vencimentos(app)),
            interval=6 * 3600,
            first=60
        )
        job_queue.run_repeating(
            lambda _: asyncio.create_task(limpar_pagamentos_pendentes()),
            interval=6 * 3600,
            first=90
        )
        job_queue.run_repeating(
            lambda _: asyncio.create_task(verificar_pagamentos_pendentes()),
            interval=300,
            first=30
        )
        logger.info("✅ Tarefas agendadas: vencimentos (6h), limpeza (6h), polling MP (5min)")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    app = (
        ApplicationBuilder()
        .token(token)
        .post_init(post_init)
        .build()
    )
    app.add_error_handler(erro_global_handler)

    conv_corrigir = ConversationHandler(
        entry_points=[
            CommandHandler("corrigir", iniciar_corrigir),
            CallbackQueryHandler(selecionar_regulacao_callback, pattern="^corr_reg_")
        ],
        states={
            SELECIONAR_REGULACAO: [CallbackQueryHandler(selecionar_regulacao_callback, pattern="^corr_reg_")],
            SELECIONAR_CAMPO: [CallbackQueryHandler(selecionar_campo_callback, pattern="^corr_campo_")],
            AGUARDAR_NOVO_VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, salvar_novo_valor)],
        },
        fallbacks=[CallbackQueryHandler(selecionar_regulacao_callback, pattern="^cancelar_corr$")],
    )

    app.add_handler(conv_cadastro)
    app.add_handler(conv_consulta_especifica)
    app.add_handler(conv_corrigir)
    app.add_handler(conv_excluir)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("iniciar", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("cadastrar_nova", iniciar_cadastro_manual))
    app.add_handler(CommandHandler("verificar_todos", comando_verificar_todas))
    app.add_handler(CommandHandler("verificar_especifico", iniciar_verificar_especifico))
    app.add_handler(CommandHandler("corrigir", iniciar_corrigir))
    app.add_handler(CommandHandler("excluir", iniciar_excluir))
    app.add_handler(CommandHandler("planos", comando_planos))
    app.add_handler(CommandHandler("privacidade", comando_privacidade))
    app.add_handler(CommandHandler("suporte", menu_suporte))

    app.add_handler(CommandHandler("admin", comando_menu_admin))
    app.add_handler(CommandHandler("menu_admin", comando_menu_admin))
    app.add_handler(CommandHandler("estatisticas", comando_estatisticas))
    app.add_handler(CommandHandler("ativos", comando_listar_ativos))
    app.add_handler(CommandHandler("detalhes", comando_detalhes))
    app.add_handler(CommandHandler("dar_plano", comando_dar_plano))
    app.add_handler(CommandHandler("cortesia", comando_cortesia))
    app.add_handler(CommandHandler("remover_cortesia", comando_remover_cortesia))
    app.add_handler(CommandHandler("retirar_plano", comando_retirar_plano))
    app.add_handler(CommandHandler("retirar_degustacao", comando_retirar_degustacao))
    app.add_handler(CommandHandler("bloquear", comando_bloquear))
    app.add_handler(CommandHandler("aviso", comando_aviso))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, executar_acao_admin),
        group=1
    )

    app.add_handler(CallbackQueryHandler(detalhar_plano, pattern="^plano_"))
    app.add_handler(CallbackQueryHandler(gerar_pagamento_pix, pattern="^pix_"))
    app.add_handler(CallbackQueryHandler(comando_planos, pattern="^planos$"))
    app.add_handler(CallbackQueryHandler(start, pattern="^iniciar$"))
    app.add_handler(CallbackQueryHandler(exibir_resposta_faq, pattern="^faq_"))
    app.add_handler(CallbackQueryHandler(iniciar_atendimento_20, pattern="^iniciar_atendimento_20$"))
    app.add_handler(CallbackQueryHandler(cancelar_suporte, pattern="^fechar_menu$"))
    app.add_handler(CallbackQueryHandler(
    suporte_email,
    pattern="^suporte_email$"
))
    app.add_handler(CallbackQueryHandler(
    mostrar_email_suporte,
    pattern="^mostrar_email_suporte$"
))
    app.add_handler(conv_suporte)

    # --- Novos handlers de privacidade e FAQ ---
    app.add_handler(CallbackQueryHandler(
        callback_abrir_termo_privacidade,
        pattern="^abrir_termo_privacidade$"
    ))
    app.add_handler(CallbackQueryHandler(
        callback_privacidade_voltar,
        pattern="^privacidade_voltar$"
    ))
    app.add_handler(CallbackQueryHandler(
        callback_faq_suporte,
        pattern="^abrir_faq_suporte$"
    ))

    async def debug_todos_callbacks(update, context):
        print(f"🔵 CALLBACK RECEBIDO: '{update.callback_query.data}'", flush=True)

    app.add_handler(CallbackQueryHandler(debug_todos_callbacks), group=99)

    logger.info("Iniciando o bot VigiaSaude via polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()









