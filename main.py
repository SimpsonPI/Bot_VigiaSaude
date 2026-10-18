from dotenv import load_dotenv
from handler_broadcast import conv_broadcast
from admin_panel import comando_painel, callback_painel

load_dotenv()

from handler_consultas import (
    comando_verificar_todas,
    iniciar_verificar_especifico,
)

import logging

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    force=True,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, NetworkError

from admin_ia_controller import executar_acao_admin

from handler import (
    admin_cb_ver_todas,
    admin_cb_minhas_regs,
    admin_cb_estatisticas,
    admin_cb_ativos,
    admin_cb_refresh,
    admin_cb_enquetes,
    admin_cb_usuarios,
    admin_cb_comandos,
    admin_cb_enq_resultado,
    admin_cb_enq_detalhado,
    admin_cb_enq_listar,
    admin_cb_enq_info,
    comando_planos,
    comando_privacidade,
    detalhar_plano,
    conv_cadastro,
    conv_consulta_especifica,
    conv_excluir,
    iniciar_corrigir,
    mostrar_email_suporte,
    start,
    callback_faq_suporte,
    callback_privacidade_voltar,
    callback_abrir_termo_privacidade,
    callback_optout_teaser,
    faq_cadastrar,
    faq_consultar,
    faq_id,
    faq_alterar,
    faq_planos,
    faq_governo,
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
    comando_retirar_plano,
    comando_retirar_degustacao,
)
from suporte import (
    menu_suporte,
    iniciar_atendimento_20,
    cancelar_suporte,
    conv_suporte,
    suporte_email,
)

from handler_midia_admin import conv_envio_midia
from handler_enquete_local import (
    conv_criar_enquete,
    receber_voto,
    voto_ja_registrado,
    comando_resultado,
    callback_resultado,
    comando_resultado_detalhado,
    comando_listar_enquetes,
    comando_encerrar,
    comando_apagar_enquete,
)

logger = logging.getLogger(__name__)


async def erro_global_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    erro = context.error
    if isinstance(erro, (TimedOut, NetworkError)):
        logger.warning(f"âš ï¸ Timeout de rede: {erro}. Aguardando 5s...")
        await asyncio.sleep(5)
        return
    logger.error(msg="ExceÃ§Ã£o capturada pelo bot:", exc_info=context.error)


async def verificar_vencimentos(app):
    """Verifica assinaturas prÃ³ximas do vencimento e envia alertas escalonados."""
    from datetime import datetime, timezone
    from database import supabase
    from handler import enviar_alerta_expiracao

    agora = datetime.now(timezone.utc)

    try:
        res = supabase.table("assinaturas").select("*").eq("status", "ativo").execute()
        if not res.data:
            return

        for assinatura in res.data:
            venc = assinatura.get("data_vencimento")
            tipo = str(assinatura.get("tipo_plano", "")).lower()
            chat_id = assinatura.get("chat_id")

            if not venc or not chat_id:
                continue

            # Cortesia nÃ£o expira
            if tipo == "cortesia":
                continue

            try:
                venc_dt = datetime.fromisoformat(str(venc))
            except Exception:
                continue

            dias_restantes = (venc_dt - agora).total_seconds() / 86400
            ultimo_aviso = str(assinatura.get("ultimo_aviso") or "")

            # Define o alvo de aviso conforme dias restantes
            alvo = None
            if 2.5 <= dias_restantes < 3.5 and ultimo_aviso != "3d":
                alvo = 3
            elif 0.5 <= dias_restantes < 1.5 and ultimo_aviso not in ("1d", "0d"):
                alvo = 1
            elif -0.5 <= dias_restantes < 0.5 and ultimo_aviso != "0d":
                alvo = 0

            if alvo is None:
                continue

            # Envia o alerta
            await enviar_alerta_expiracao(app, str(chat_id), tipo, alvo, venc)

            # Marca no banco para nÃ£o repetir
            try:
                supabase.table("assinaturas").update({"ultimo_aviso": f"{alvo}d"}).eq("chat_id", str(chat_id)).execute()
            except Exception as e:
                logger.warning(f"Erro ao marcar ultimo_aviso para {chat_id}: {e}")

    except Exception as e:
        logger.error(f"Erro na verificaÃ§Ã£o de vencimentos: {e}")


async def post_init(app):
    """Executa tarefas apÃ³s a inicializaÃ§Ã£o do bot."""
    set_telegram_bot(app.bot)

    job_queue = app.job_queue
    if job_queue:
        # Vencimentos de assinatura (6h)
        job_queue.run_repeating(
            lambda _: asyncio.create_task(verificar_vencimentos(app)),
            interval=6 * 3600,
            first=180,
        )

        # Limpeza de pagamentos pendentes (6h)
        job_queue.run_repeating(
            lambda _: asyncio.create_task(limpar_pagamentos_pendentes()),
            interval=6 * 3600,
            first=180,
        )

        # Polling do Mercado Pago (5 min)
        job_queue.run_repeating(
            lambda _: asyncio.create_task(verificar_pagamentos_pendentes()),
            interval=300,
            first=30,
        )

        # âœ… Varredura automÃ¡tica de regulaÃ§Ãµes (6h)
        from handler import executar_varredura_automatica

        job_queue.run_repeating(
            executar_varredura_automatica,
            interval=6 * 3600,  # â† 6 HORAS
            first=180,  # primeira execuÃ§Ã£o 3 min apÃ³s o boot
        )
        logger.info(
            "âœ… Tarefas agendadas: vencimentos (6h), limpeza (6h), polling MP (5min), varredura regulaÃ§Ãµes (6h)"
        )

        # Verifica enquetes expiradas a cada 1 minuto
        from handler_enquete_local import verificar_enquetes_expiradas

        job_queue.run_repeating(
            verificar_enquetes_expiradas,
            interval=60,
            first=30,
        )
        logger.info("âœ… Tarefas agendadas: ... enquetes expiradas (60s)")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("O TELEGRAM_BOT_TOKEN precisa estar configurado nas variÃ¡veis de ambiente.")

    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )

    app = (
        ApplicationBuilder()
        .token(token)
        # .concurrent_updates(False)
        .request(request)
        .get_updates_request(request)
        .post_init(post_init)
        .build()
    )
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

    # ConversationHandlers
    app.add_handler(conv_cadastro)
    app.add_handler(conv_consulta_especifica)
    app.add_handler(conv_corrigir)
    app.add_handler(conv_excluir)
    app.add_handler(conv_envio_midia)
    app.add_handler(conv_criar_enquete)
    app.add_handler(conv_broadcast)
    # Comandos pÃºblicos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("iniciar", start))
    app.add_handler(CommandHandler("menu", start))
    # Redundante: já tratado no conv_cadastro
    app.add_handler(CommandHandler("verificar_todos", comando_verificar_todas))
    app.add_handler(CommandHandler("verificar_especifico", iniciar_verificar_especifico))
    app.add_handler(CommandHandler("corrigir", iniciar_corrigir))
    app.add_handler(CommandHandler("planos", comando_planos))
    app.add_handler(CommandHandler("privacidade", comando_privacidade))
    app.add_handler(CommandHandler("suporte", menu_suporte))

    # Comandos admin
    # Painel admin interativo
    app.add_handler(CommandHandler("painel", comando_painel))
    app.add_handler(CommandHandler("admin", comando_painel))
    app.add_handler(CommandHandler("menu_admin", comando_painel))
    app.add_handler(CallbackQueryHandler(admin_cb_ver_todas, pattern="^admin_ver_todas$"))
    app.add_handler(CallbackQueryHandler(admin_cb_minhas_regs, pattern="^admin_minhas$"))
    app.add_handler(CallbackQueryHandler(admin_cb_estatisticas, pattern="^painel_estatisticas$"))
    app.add_handler(CallbackQueryHandler(admin_cb_ativos, pattern="^painel_ativos$"))
    app.add_handler(CallbackQueryHandler(admin_cb_refresh, pattern="^admin_refresh$"))
    app.add_handler(CallbackQueryHandler(admin_cb_enquetes, pattern="^admin_enquetes$"))
    app.add_handler(CallbackQueryHandler(admin_cb_usuarios, pattern="^admin_usuarios$"))
    app.add_handler(CallbackQueryHandler(admin_cb_comandos, pattern="^admin_comandos$"))
    app.add_handler(CallbackQueryHandler(admin_cb_enq_resultado, pattern="^admin_enq_resultado$"))
    app.add_handler(CallbackQueryHandler(admin_cb_enq_detalhado, pattern="^admin_enq_detalhado$"))
    app.add_handler(CallbackQueryHandler(admin_cb_enq_listar, pattern="^admin_enq_listar$"))
    app.add_handler(CallbackQueryHandler(admin_cb_enq_info, pattern="^admin_enq_info$"))
    app.add_handler(CallbackQueryHandler(callback_painel, pattern="^painel_"))  # â† por Ãºltimo
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

    # Enquetes
    app.add_handler(CommandHandler("resultado", comando_resultado))
    app.add_handler(CommandHandler("resultado_detalhado", comando_resultado_detalhado))
    app.add_handler(CommandHandler("listar_enquetes", comando_listar_enquetes))
    app.add_handler(CommandHandler("encerrar", comando_encerrar))
    app.add_handler(CommandHandler("apagar_enquete", comando_apagar_enquete))

    # Handler IA do admin
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, executar_acao_admin),
        group=1,
    )

    # Callbacks de planos/pagamento
    app.add_handler(CallbackQueryHandler(detalhar_plano, pattern="^plano_"))
    app.add_handler(CallbackQueryHandler(gerar_pagamento_pix, pattern="^pix_"))
    app.add_handler(CallbackQueryHandler(comando_planos, pattern="^planos$"))
    app.add_handler(CallbackQueryHandler(start, pattern="^iniciar$"))

    # FAQ - handlers especÃ­ficos (substitui o genÃ©rico ^faq_)
    app.add_handler(CallbackQueryHandler(faq_cadastrar, pattern="^faq_cadastrar$"))
    app.add_handler(CallbackQueryHandler(faq_consultar, pattern="^faq_consultar$"))
    app.add_handler(CallbackQueryHandler(faq_id, pattern="^faq_id$"))
    app.add_handler(CallbackQueryHandler(faq_alterar, pattern="^faq_alterar$"))
    app.add_handler(CallbackQueryHandler(faq_planos, pattern="^faq_planos$"))
    app.add_handler(CallbackQueryHandler(faq_governo, pattern="^faq_governo$"))
    app.add_handler(CallbackQueryHandler(iniciar_atendimento_20, pattern="^iniciar_atendimento_20$"))
    app.add_handler(CallbackQueryHandler(cancelar_suporte, pattern="^fechar_menu$"))
    app.add_handler(CallbackQueryHandler(suporte_email, pattern="^suporte_email$"))
    app.add_handler(CallbackQueryHandler(mostrar_email_suporte, pattern="^mostrar_email_suporte$"))
    app.add_handler(conv_suporte)

    # Callbacks de privacidade
    app.add_handler(CallbackQueryHandler(callback_abrir_termo_privacidade, pattern="^abrir_termo_privacidade$"))
    app.add_handler(CallbackQueryHandler(callback_privacidade_voltar, pattern="^privacidade_voltar$"))
    app.add_handler(CallbackQueryHandler(callback_faq_suporte, pattern="^abrir_faq_suporte$"))
    app.add_handler(CallbackQueryHandler(callback_optout_teaser, pattern="^optout_teaser$"))

    # Callbacks de enquete (voto e admin)
    app.add_handler(CallbackQueryHandler(receber_voto, pattern="^voto_\\d+_\\d+$"))
    app.add_handler(CallbackQueryHandler(voto_ja_registrado, pattern="^voto_ja_registrado$"))
    app.add_handler(CallbackQueryHandler(callback_resultado, pattern="^enq_(encerrar|reabrir|apagar|atualizar)_\\d+$"))
    # app.add_handler(CallbackQueryHandler(
    # processar_verificar_especifico, pattern="^ver_esp_"
    # ))

    # â”€â”€â”€ Servidor HTTP auxiliar (Render / Railway) â”€â”€â”€
    PORT = int(os.environ.get("PORT", "8080"))

    class HealthHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # silencia logs

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"VigiaSaude is running!")

        def do_HEAD(self):
            self.send_response(200)
            self.end_headers()

    def run_http_server(port):
        try:
            server = HTTPServer(("0.0.0.0", port), HealthHandler)
            logger.info(f"âœ… Servidor HTTP auxiliar rodando na porta {port}")
            server.serve_forever()
        except Exception as e:
            logger.error(f"Erro no servidor HTTP: {e}")

    threading.Thread(target=run_http_server, args=(PORT,), daemon=True).start()

    logger.info("Iniciando o bot VigiaSaude via polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
