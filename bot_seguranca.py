import logging
import functools
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

def safe_callback(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        query = update.callback_query
        if query:
            try:
                await query.answer()
            except Exception:
                pass
        
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

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Erro global capturado: {context.error}", exc_info=context.error)
    if isinstance(update, Update):
        if update.callback_query:
            try:
                await update.callback_query.answer("⚠️ Ocorreu um erro. Tente novamente.", show_alert=True)
            except Exception:
                pass
        if update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "⚠️ Ocorreu um erro interno. Por favor, digite /start."
                )
            except Exception:
                pass