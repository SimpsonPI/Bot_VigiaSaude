import os
import json
import logging
import httpx
from telegram import Update
from telegram.ext import ContextTypes
from database import supabase
from datetime import datetime, timedelta

ADMIN_ID = int(os.getenv("ADMIN_ID") or os.getenv("ADMIN_CHAT_ID") or "0")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
NOME_ADMIN = os.getenv("NOME_ADMIN", "Sr. Lincoln")

logger = logging.getLogger(__name__)

GITHUB_BASE_URL = "https://raw.githubusercontent.com/SimpsonPI/central_alertasus_2.5/main/"

TABELAS_PERMITIDAS = ["assinaturas", "AlertaSUS_2.0", "pagamentos_pix", "lgpd_consentimentos"]

SAUDACOES = [
    "olá", "oi", "bom dia", "boa tarde", "boa noite", "tudo bem",
    "hello", "hey", "e aí", "como vai", "opa", "salve"
]

PALAVRAS_CHAVE = [
    "resumo", "estatísticas", "quantos", "dados da tabela", "ler arquivo",
    "verificar regulação", "minha regulação", "total", "listar", "relatório",
    "vencimento", "pagamentos", "usuários ativos", "inativos", "status",
    "consulta", "plano", "assinatura", "bloqueado", "pendente", "pix", "custa"
]

PALAVRAS_NOVIDADES = [
    "novidades", "mudanças recentes", "o que mudou", "últimas", "recentes",
    "novos cadastros", "novas regulações", "atualizações hoje"
]

async def obter_conhecimento() -> str:
    """Busca o conteúdo dos arquivos de conhecimento no GitHub."""
    conhecimento = ""
    try:
        url = f"{GITHUB_BASE_URL}conhecimento.md"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                conhecimento = response.text[:3000]
    except Exception as e:
        logger.error(f"Erro ao ler arquivo de conhecimento: {e}")
    return conhecimento

async def chamar_groq(system_prompt: str, user_message: str) -> str:
    """Chama a API do Groq e retorna a resposta em texto."""
    if not GROQ_API_KEY:
        return "❌ GROQ_API_KEY não configurada."
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.2
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Erro ao chamar Groq: {e}")
        return f"❌ Erro na chamada à IA: {str(e)}"

async def executar_acao_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para mensagens do administrador (linguagem natural)."""
    if update.effective_user.id != ADMIN_ID:
        return
    if not update.message or not update.message.text:
        return

    user_message = update.message.text
    user_text_lower = user_message.lower()

    # 1. Se for saudação, conversa normal (sem consultar dados)
    if any(saudacao in user_text_lower for saudacao in SAUDACOES):
        prompt_conversa = (
            f"Você é o VS, assistente do {NOME_ADMIN}. "
            f"O usuário é {NOME_ADMIN}. "
            "Responda de forma amigável e curta. NUNCA invente informações."
        )
        resposta = await chamar_groq(prompt_conversa, user_message)
        try:
            await update.message.reply_text(resposta, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(resposta, parse_mode=None)
        return

    # 2. Se for pergunta sobre "novidades", consulta banco de dados
    if any(palavra in user_text_lower for palavra in PALAVRAS_NOVIDADES):
        try:
            agora = datetime.utcnow()
            inicio = agora - timedelta(days=1)
            novas_regulacoes = supabase.table("AlertaSUS_2.0").select("*", count="exact").gte("created_at", inicio.isoformat()).execute().count
            novas_assinaturas = supabase.table("assinaturas").select("*", count="exact").gte("created_at", inicio.isoformat()).execute().count
            novos_pagamentos = supabase.table("pagamentos_pix").select("*", count="exact").gte("created_at", inicio.isoformat()).execute().count
            dados = (f"Nas últimas 24 horas: {novas_regulacoes} novas regulações, {novas_assinaturas} novas assinaturas, {novos_pagamentos} novos pagamentos.")

            prompt = (
                f"Você é o VS, assistente do {NOME_ADMIN}. "
                f"O administrador pediu: '{user_message}'. "
                f"Dados reais do banco: {dados}. "
                "Responda de forma EXTREMAMENTE OBJETIVA. Apenas traga os números. "
                "Não explique nada. Não use frases longas. Apenas os dados solicitados."
            )
            resposta_final = await chamar_groq(prompt, "Formate a resposta.")
        except Exception as e:
            logger.error(f"Erro ao buscar novidades: {e}")
            resposta_final = "❌ Não consegui buscar as novidades."

        try:
            await update.message.reply_text(resposta_final, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(resposta_final, parse_mode=None)
        return

    # 3. Se for pedido administrativo, consulta tudo
    if not any(palavra in user_text_lower for palavra in PALAVRAS_CHAVE):
        prompt_conversa = (
            f"Você é o VS, assistente do {NOME_ADMIN}. "
            f"O usuário é {NOME_ADMIN}. "
            "Responda de forma amigável e curta. NUNCA invente informações."
        )
        resposta = await chamar_groq(prompt_conversa, user_message)
        try:
            await update.message.reply_text(resposta, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(resposta, parse_mode=None)
        return

    # 4. Carrega conhecimento (com FALLBACK)
    conhecimento = ""
    try:
        conhecimento = await obter_conhecimento()
    except Exception as e:
        logger.error(f"Erro ao obter conhecimento: {e}")
        conhecimento = ""

    # 🔄 FALLBACK: Se o conhecimento do GitHub falhar, usa esta descrição básica
    if not conhecimento:
        conhecimento = (
            "O VigiaSaúde é um serviço independente que monitora regulações de saúde (consultas e exames) "
            "no SUS de Teresina-PI. Ele avisa o usuário quando há mudança no status da regulação. "
            "Planos: Degustação (7 dias grátis), Trimestral (R$ 9,99) e Semestral (R$ 14,99). "
            "Cadastro: Número do SUS, Nome, Celular, Data de nascimento, ID da Regulação, CBO e Procedimento."
        )

    prompt_deteccao = (
        f"Você é o VS, assistente do {NOME_ADMIN}. Identifique a ação que o administrador deseja executar. "
        "Responda APENAS com um JSON válido: "
        "{\"acao\": \"consultar\" | \"ler_arquivo\" | \"resumo\", "
        "\"tabela\": \"nome_da_tabela\", "
        "\"filtros\": {\"campo\": \"valor\"}, "
        "\"arquivo\": \"nome_do_arquivo\"} "
        "Tabelas disponíveis: assinaturas, AlertaSUS_2.0, pagamentos_pix, lgpd_consentimentos. "
        "Para perguntas sobre preços de planos, use a ação 'resumo' (a informação está no conhecimento). "
        "Se não souber, retorne {\"acao\": \"resumo\"}."
    )

    resposta_ia = await chamar_groq(prompt_deteccao, user_message)

    try:
        data = json.loads(resposta_ia)
        acao = data.get("acao", "resumo")
        tabela = data.get("tabela", "")
        filtros = data.get("filtros", {})
        arquivo = data.get("arquivo", "")

        if tabela and tabela not in TABELAS_PERMITIDAS:
            tabela = "assinaturas"

        dados_brutos = ""

        if acao == "consultar":
            try:
                query = supabase.table(tabela).select("*")
                if filtros:
                    for campo, valor in filtros.items():
                        query = query.eq(campo, valor)
                res = query.limit(20).execute()
                dados_brutos = json.dumps(res.data, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Erro ao consultar tabela {tabela}: {e}")
                dados_brutos = f"Erro: {str(e)}"

        elif acao == "ler_arquivo":
            try:
                url = f"{GITHUB_BASE_URL}{arquivo}"
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        dados_brutos = response.text[:3000]
                    else:
                        dados_brutos = f"Arquivo não encontrado (status {response.status_code})."
            except Exception as e:
                logger.error(f"Erro ao ler arquivo: {e}")
                dados_brutos = f"Erro: {str(e)}"

        elif acao == "resumo":
            try:
                total_assinaturas = supabase.table("assinaturas").select("*", count="exact").execute().count
                total_regulacoes = supabase.table("AlertaSUS_2.0").select("*", count="exact").execute().count
                total_pix_pendentes = supabase.table("pagamentos_pix").select("*", count="exact").eq("status", "pending").execute().count
                dados_brutos = f"Total assinaturas: {total_assinaturas}. Total regulações: {total_regulacoes}. Pagamentos pendentes: {total_pix_pendentes}."
            except Exception as e:
                logger.error(f"Erro ao gerar resumo: {e}")
                dados_brutos = f"Erro: {str(e)}"

        prompt_formatacao = (
            f"Você é o VS, assistente do {NOME_ADMIN}. "
            f"O administrador pediu: '{user_message}'. "
            f"Dados do banco: {dados_brutos}. "
            f"Conhecimento do sistema: {conhecimento}. "
            "Responda de forma EXTREMAMENTE OBJETIVA. Apenas traga os dados solicitados. "
            "Não explique o que é o sistema. Não adicione textos extras. "
            "Se for uma lista, formate como lista curta. Se forem números, apenas mostre os números."
        )
        resposta_final = await chamar_groq(prompt_formatacao, "Formate a resposta acima.")

    except json.JSONDecodeError:
        prompt_formatacao = (
            f"Você é o VS, assistente do {NOME_ADMIN}. "
            f"O administrador pediu: '{user_message}'. "
            f"Conhecimento do sistema: {conhecimento}. "
            "Responda de forma amigável e curta. NUNCA invente informações."
        )
        resposta_final = await chamar_groq(prompt_formatacao, "Responda a pergunta.")

    try:
        await update.message.reply_text(resposta_final, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Erro ao enviar resposta com Markdown: {e}")
        await update.message.reply_text(resposta_final, parse_mode=None)