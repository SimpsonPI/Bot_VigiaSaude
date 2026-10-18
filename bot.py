from dotenv import load_dotenv

load_dotenv()
# ... o restante dos imports
import os
import logging
import asyncio
from admin_ia_controller import executar_acao_admin
import planos_config as pc
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import TELEGRAM_BOT_TOKEN
from handler import (
    comando_planos,
    comando_privacidade,
    comando_verificar_todas,
    detalhar_plano,
    conv_cadastro,
    conv_consulta_especifica,
    conv_excluir,
    iniciar_corrigir,
    iniciar_excluir,
    iniciar_verificar_especifico,
    start,  # <-- Importando a funÃ§Ã£o
)
from handler_gestao import (
    selecionar_regulacao_callback,
    selecionar_campo_callback,
    salvar_novo_valor,
)
from handler_pagamento import gerar_pagamento_pix
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

# IMPORTS DO SUPORTE
from suporte import (
    menu_suporte,
    exibir_resposta_faq,
    iniciar_atendimento_20,
    cancelar_suporte,
    conv_suporte,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def erro_global_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="ExceÃ§Ã£o capturada pelo bot:", exc_info=context.error)


async def verificar_vencimentos(app):
    """Verifica assinaturas que vencem em 1 dia e envia alerta."""
    from datetime import datetime, timedelta, timezone
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from database import supabase

    agora = datetime.now(timezone.utc)
    alvo = agora + timedelta(days=1)

    try:
        res = supabase.table("assinaturas").select("*").eq("status", "active").execute()
        for assinatura in res.data:
            venc = assinatura.get("data_vencimento")
            if not venc:
                continue
            venc_dt = datetime.fromisoformat(venc)
            if venc_dt <= alvo and venc_dt > agora:
                chat_id = assinatura["chat_id"]
                tipo = assinatura.get("tipo_plano", "").lower()

                if tipo == "degustacao":
                    msg = (
                        "âš ï¸ <b>Seu plano degustaÃ§Ã£o expira amanhÃ£!</b>\n\n"
                        "Para continuar monitorando suas regulaÃ§Ãµes sem interrupÃ§Ã£o, "
                        "assine um dos nossos planos Pro:\n"
                        f"{pc.texto_lista_planos()}\n\n"
                        "Clique no botÃ£o abaixo para ver os planos."
                    )
                else:
                    msg = (
                        "âš ï¸ <b>Seu plano Pro expira amanhÃ£!</b>\n\n"
                        "Renove agora para nÃ£o perder o acesso ao monitoramento.\n\n"
                        "Clique no botÃ£o abaixo para renovar."
                    )

                teclado = InlineKeyboardMarkup([[InlineKeyboardButton("ðŸ’³ Ver Planos", callback_data="planos")]])

                try:
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        reply_markup=teclado,
                        parse_mode="HTML",
                    )
                    logger.info(f"Alerta de vencimento enviado para {chat_id}")
                except Exception as e:
                    logger.error(f"Erro ao enviar alerta para {chat_id}: {e}")

    except Exception as e:
        logger.error(f"Erro na verificaÃ§Ã£o de vencimentos: {e}")


async def post_init(app):
    """Executa tarefas apÃ³s a inicializaÃ§Ã£o do bot."""
    # await configurar_menu_comandos(app)  # <-- COMENTADO PARA NÃƒO SOBRESCREVER O MENU

    # Agendar verificaÃ§Ã£o de vencimentos (a cada 6 horas)
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(
            lambda _: asyncio.create_task(verificar_vencimentos(app)),
            interval=6 * 3600,
            first=60,
        )
        logger.info("VerificaÃ§Ã£o de vencimentos agendada (a cada 6 horas)")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    app = ApplicationBuilder().token(token).post_init(post_init).build()
    app.add_error_handler(erro_global_handler)

    conv_corrigir = ConversationHandler(
        entry_points=[
            CommandHandler("corrigir", iniciar_corrigir),
            CallbackQueryHandler(selecionar_regulacao_callback, pattern="^corr_reg_"),
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
    # Redundante: já tratado no conv_cadastro
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

    # ==========================================
    # â¬‡ï¸ HANDLER DO ADMIN (linguagem natural) - AQUI
    # ==========================================
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, executar_acao_admin), group=1)

    app.add_handler(CallbackQueryHandler(detalhar_plano, pattern="^plano_"))
    app.add_handler(CallbackQueryHandler(gerar_pagamento_pix, pattern="^pix_"))
    app.add_handler(CallbackQueryHandler(comando_planos, pattern="^planos$"))
    app.add_handler(CallbackQueryHandler(start, pattern="^iniciar$"))
    app.add_handler(CallbackQueryHandler(exibir_resposta_faq, pattern="^faq_"))
    app.add_handler(CallbackQueryHandler(iniciar_atendimento_20, pattern="^iniciar_atendimento_20$"))
    app.add_handler(CallbackQueryHandler(cancelar_suporte, pattern="^fechar_menu$"))
    app.add_handler(CallbackQueryHandler(menu_suporte, pattern="^suporte$"))

    app.add_handler(conv_suporte)

    # Servidor HTTP auxiliar
    PORT = int(os.environ.get("PORT", "8080"))

    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot VigiaSaude 2.5 is running!")

    def run_http_server(port):
        server = HTTPServer(("0.0.0.0", port), SimpleHandler)
        server.serve_forever()

    threading.Thread(target=run_http_server, args=(PORT,), daemon=True).start()
    logger.info(f"Servidor HTTP auxiliar rodando na porta {PORT}")

    logger.info("Iniciando o bot VigiaSaude via polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
