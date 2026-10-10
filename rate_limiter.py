import time
from collections import defaultdict
from telegram import Update
from telegram.ext import ContextTypes


# Dicionário em memória para rastrear as requisições: {user_id: [timestamps]}
_controle_acessos = defaultdict(list)

def rate_limit(max_mensagens: int = 5, janela_segundos: int = 60):
    """
    Decorator de Rate Limiting (Antispam).
    Limita o usuário a um número máximo de interações por janela de tempo.
    """
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not update.effective_user:
                return await func(update, context, *args, **kwargs)
            
            user_id = update.effective_user.id
            agora = time.time()
            
            # Filtra apenas os timestamps dentro da janela de tempo atual (últimos 60 segundos)
            timestamps = _controle_acessos[user_id]
            _controle_acessos[user_id] = [t for t in timestamps if agora - t < janela_segundos]
            
            # Verifica se o usuário excedeu o limite
            if len(_controle_acessos[user_id]) >= max_mensagens:
                if update.message:
                    await update.message.reply_text(
                        "⚠️ Você está enviando mensagens muito rápido. Aguarde alguns instantes."
                    )
                return
            
            # Registra o acesso atual e prossegue com a função original
            _controle_acessos[user_id].append(agora)
            return await func(update, context, *args, **kwargs)
            
        return wrapper
    return decorator

# ═══════════════════════════════════════════════
# CAMADA 3 — SEMÁFORO GLOBAL + RATE LIMIT GLOBAL
# ═══════════════════════════════════════════════
import asyncio
import logging
from collections import deque

logger = logging.getLogger(__name__)

MAX_CONSULTAS_PARALELAS = 3
LIMITE_GLOBAL_MAX = 30
LIMITE_GLOBAL_JANELA_SEG = 60

_semaforo_fms = asyncio.Semaphore(MAX_CONSULTAS_PARALELAS)
_rate_global: deque = deque()


async def _aguardar_rate_global():
    agora = time.time()
    while _rate_global and agora - _rate_global[0] > LIMITE_GLOBAL_JANELA_SEG:
        _rate_global.popleft()

    if len(_rate_global) >= LIMITE_GLOBAL_MAX:
        espera = LIMITE_GLOBAL_JANELA_SEG - (agora - _rate_global[0]) + 1
        logger.warning(f"⏳ Rate global FMS atingido. Aguardando {espera:.1f}s...")
        await asyncio.sleep(espera)
        agora = time.time()
        while _rate_global and agora - _rate_global[0] > LIMITE_GLOBAL_JANELA_SEG:
            _rate_global.popleft()

    _rate_global.append(time.time())


async def consultar_com_limite(num_reg: str) -> dict:
    from scraper import consultar_status_fms

    await _aguardar_rate_global()
    async with _semaforo_fms:
        return await consultar_status_fms(num_reg)