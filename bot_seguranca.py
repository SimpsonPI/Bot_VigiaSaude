import logging
import functools
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


# CAMADA 1: Destrava o botão e protege a função
def safe_callback(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        query = update.callback_query
        # 1. Destrava o botão no Telegram imediatamente
        if query:
            try:
                await query.answer()
            except Exception:
                pass

        # 2. Tenta rodar a função do bot
        try:
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            logger.error(f"Erro na função {func.__name__}: {e}", exc_info=True)
            if update.effective_message:
                try:
                    await update.effective_message.reply_text(
                        "⚠️ Ocorreu um erro ao processar sua solicitação.\nPor favor, digite /start para recomeçar."
                    )
                except Exception:
                    pass
            return None

    return wrapper


# CAMADA 2: Rede de segurança global
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Erro global capturado: {context.error}", exc_info=context.error)

    if isinstance(update, Update):
        # Se for um botão, destrava ele
        if update.callback_query:
            try:
                await update.callback_query.answer("⚠️ Ocorreu um erro. Tente novamente.", show_alert=True)
            except Exception:
                pass

        # Avisa o usuário no chat
        if update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "⚠️ Ocorreu um erro interno. Nossa equipe já foi notificada.\nPor favor, digite /start."
                )
            except Exception:
                pass
