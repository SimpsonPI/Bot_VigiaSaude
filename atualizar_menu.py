import os
import asyncio
from dotenv import load_dotenv
from telegram import Bot, BotCommand

# Carrega as variáveis do arquivo .env
load_dotenv()

# Obtém o token do ambiente (não precisa colar o token no código)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN não configurado no arquivo .env")

async def atualizar():
    bot = Bot(token=TOKEN)
    comandos = [
        BotCommand("iniciar", "🚀 Menu principal e boas-vindas"),
        BotCommand("verificar_todos", "🔍 Verificar todas as regulações"),
        BotCommand("verificar_especifico", "🎯 Verificar regulação específica"),
        BotCommand("cadastrar_nova", "➕ Cadastrar nova regulação"),
        BotCommand("corrigir", "✏️ Corrigir dados de regulação"),
        BotCommand("planos", "💳 Ver planos e assinaturas"),
        BotCommand("excluir", "🗑️ Excluir uma regulação"),
        BotCommand("privacidade", "🔒 Política de privacidade e LGPD"),
        BotCommand("suporte", "🤖 Central de Atendimento"),
    ]
    await bot.set_my_commands(comandos)
    print("✅ Menu atualizado com sucesso!")

asyncio.run(atualizar())