from dotenv import load_dotenv
load_dotenv()
# ... o restante dos imports
import os
import logging
import asyncio
from telegram import BotCommand, BotCommandScopeAllPrivateChats
from admin_ia_controller import executar_acao_admin
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
    iniciar_cadastro_manual,
    iniciar_corrigir,
    iniciar_excluir,
    iniciar_verificar_especifico,
    start,
    configurar_menu_comandos,  # <-- Importando a função
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
    logger.error(msg="Exceção capturada pelo bot:", exc_info=context.error)

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
            venc_dt = datetime.fromisoformat(venc.replace("Z", "+00:00"))
            if venc_dt <= alvo and venc_dt > agora:
                chat_id = assinatura["chat_id"]
                tipo = assinatura.get("tipo_plano", "").lower()

                if tipo == "degustacao":
                    msg = (
                        "⚠️ <b>Seu plano degustação expira amanhã!</b>\n\n"
                        "Para continuar monitorando suas regulações sem interrupção, "
                        "assine um dos nossos planos Pro:\n"
                        "• ⭐ Trimestral (R$ 9,99)\n"
                        "• 🚀 Semestral (R$ 14,99)\n\n"
                        "Clique no botão abaixo para ver os planos."
                    )
                else:
                    msg = (
                        "⚠️ <b>Seu plano Pro expira amanhã!</b>\n\n"
                        "Renove agora para não perder o acesso ao monitoramento.\n\n"
                        "Clique no botão abaixo para renovar."
                    )

                teclado = InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Ver Planos", callback_data="planos")]
                ])

                try:
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        reply_markup=teclado,
                        parse_mode="HTML"
                    )
                    logger.info(f"Alerta de vencimento enviado para {chat_id}")
                except Exception as e:
                    logger.error(f"Erro ao enviar alerta para {chat_id}: {e}")

    except Exception as e:
        logger.error(f"Erro na verificação de vencimentos: {e}")


async def post_init(app):
    """Executa tarefas após a inicialização do bot."""
    # await configurar_menu_comandos(app)  # <-- COMENTADO PARA NÃO SOBRESCREVER O MENU

    job_queue = app.job_queue
    if job_queue:
        # Agendar verificação de vencimentos (a cada 6 horas)
        job_queue.run_repeating(
            lambda _: asyncio.create_task(verificar_vencimentos(app)),
            interval=6 * 3600,
            first=60
        )
        # NOVO: Agendar limpeza de pagamentos pendentes (a cada 6 horas)
        job_queue.run_repeating(
            lambda _: asyncio.create_task(limpar_pagamentos_pendentes()),
            interval=6 * 3600,
            first=90  # Primeira execução após 90 segundos (dá um tempo a mais para o bot iniciar)
        )
        logger.info("Verificação de vencimentos e limpeza de pagamentos pendentes agendadas (a cada 6 horas)")

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    app = ApplicationBuilder().token(token).post_init(post_init).build()
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

    # ==========================================
    # ⬇️ HANDLER DO ADMIN (linguagem natural) - AQUI
    # ==========================================
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
