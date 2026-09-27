from dotenv import load_dotenv
load_dotenv()

from handler_consultas import (
    comando_verificar_todas,
    iniciar_verificar_especifico,
    processar_verificar_especifico,
)

import logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    force=True
)

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
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, NetworkError

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
    _ativar_assinatura,
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
        logger.warning(f"⚠️ Timeout de rede: {erro}. Aguardando 5s...")
        await asyncio.sleep(5)
        return
    logger.error(msg="Exceção capturada pelo bot:", exc_info=context.error)


async def verificar_vencimentos(app):
    """Verifica assinaturas próximas do vencimento e envia alertas escalonados."""
    from datetime import datetime, timezone
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
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

            # Cortesia não expira
            if tipo == "cortesia":
                continue

            try:
                venc_dt = datetime.fromisoformat(str(venc).replace("Z", "+00:00"))
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

            # Marca no banco para não repetir
            try:
                supabase.table("assinaturas").update({
                    "ultimo_aviso": f"{alvo}d"
                }).eq("chat_id", str(chat_id)).execute()
            except Exception as e:
                logger.warning(f"Erro ao marcar ultimo_aviso para {chat_id}: {e}")

    except Exception as e:
        logger.error(f"Erro na verificação de vencimentos: {e}")


async def post_init(app):
    """Executa tarefas após a inicialização do bot."""
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

        # ✅ Varredura automática de regulações (6h)
        from handler import executar_varredura_automatica
        job_queue.run_repeating(
            executar_varredura_automatica,
            interval=6 * 3600,   # ← 6 HORAS
            first=180,           # primeira execução 3 min após o boot
        )
        logger.info(
            "✅ Tarefas agendadas: vencimentos (6h), limpeza (6h), polling MP (5min), varredura regulações (6h)"
        )

        # Verifica enquetes expiradas a cada 1 minuto
        from handler_enquete_local import verificar_enquetes_expiradas
        job_queue.run_repeating(
            verificar_enquetes_expiradas,
            interval=60, first=30,
        )
        logger.info("✅ Tarefas agendadas: ... enquetes expiradas (60s)")
    
def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("O TELEGRAM_BOT_TOKEN precisa estar configurado nas variáveis de ambiente.")

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

    # Comandos públicos
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

    # Comandos admin
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

    # FAQ - handlers específicos (substitui o genérico ^faq_)
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
    app.add_handler(CallbackQueryHandler(
        callback_resultado,
        pattern="^enq_(encerrar|reabrir|apagar|atualizar)_\\d+$"
    ))
    app.add_handler(CallbackQueryHandler(
        processar_verificar_especifico, pattern="^ver_esp_"
    ))

    logger.info("Iniciando o bot VigiaSaude via polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()