# database_atendimento.py
import logging
from datetime import datetime, timezone
from database import supabase

logger = logging.getLogger(__name__)

# ==========================================
# FUNÇÕES PARA FAQ AUTOMATIZADO
# ==========================================

async def buscar_faq_por_palavras_chave(texto_usuario: str) -> dict | None:
    """Busca no banco de dados uma resposta do FAQ baseada nas palavras-chave."""
    try:
        # Normaliza o texto do usuário
        texto_normalizado = texto_usuario.lower().strip()
        
        # Busca todas as FAQs ativas
        res = supabase.table("faq_perguntas").select("*").eq("ativo", True).execute()
        
        if not res.data:
            return None
        
        # Verifica qual FAQ melhor corresponde ao texto do usuário
        melhor_match = None
        melhor_pontuacao = 0
        
        for faq in res.data:
            pontuacao = 0
            palavras_chave = faq.get("palavras_chave", [])
            
            for palavra in palavras_chave:
                if palavra.lower() in texto_normalizado:
                    pontuacao += 1
            
            # Verifica também se a pergunta está contida no texto
            if faq.get("pergunta", "").lower() in texto_normalizado:
                pontuacao += 3
            
            if pontuacao > melhor_pontuacao:
                melhor_pontuacao = pontuacao
                melhor_match = faq
        
        if melhor_match and melhor_pontuacao > 0:
            return melhor_match
        
        return None
        
    except Exception as e:
        logger.error(f"Erro ao buscar FAQ: {e}")
        return None


# ==========================================
# FUNÇÕES PARA ATENDIMENTO HUMANIZADO
# ==========================================

async def registrar_chamado_suporte(chat_id: str, nome_usuario: str, mensagem: str) -> int | None:
    """Registra um novo chamado de suporte humanizado."""
    try:
        res = supabase.table("chamados_suporte").insert({
            "chat_id": str(chat_id),
            "nome_usuario": nome_usuario,
            "mensagem": mensagem,
            "status": "aberto",
            "prioridade": "normal"
        }).execute()
        
        if res.data:
            chamado_id = res.data[0]["id"]
            logger.info(f"Chamado {chamado_id} registrado para o chat {chat_id}")
            return chamado_id
        return None
        
    except Exception as e:
        logger.error(f"Erro ao registrar chamado: {e}")
        return None


async def adicionar_mensagem_fila(chamado_id: int, chat_id: str, mensagem: str, enviado_por: str = "usuario") -> bool:
    """Adiciona uma mensagem à fila do chamado."""
    try:
        supabase.table("mensagens_fila").insert({
            "chamado_id": chamado_id,
            "chat_id": str(chat_id),
            "mensagem": mensagem,
            "enviado_por": enviado_por
        }).execute()
        
        return True
        
    except Exception as e:
        logger.error(f"Erro ao adicionar mensagem à fila: {e}")
        return False


async def listar_chamados_abertos() -> list:
    """Lista todos os chamados abertos para o administrador."""
    try:
        res = supabase.table("chamados_suporte").select("*").in_("status", ["aberto", "em_andamento"]).order("created_at", desc=True).execute()
        return res.data if res.data else []
        
    except Exception as e:
        logger.error(f"Erro ao listar chamados abertos: {e}")
        return []


async def responder_chamado(chamado_id: int, resposta_admin: str, atendente_id: str) -> bool:
    """Registra a resposta do administrador e atualiza o chamado."""
    try:
        agora = datetime.now(timezone.utc).isoformat()
        
        supabase.table("chamados_suporte").update({
            "status": "respondido",
            "resposta_admin": resposta_admin,
            "atendente_id": str(atendente_id),
            "respondido_em": agora
        }).eq("id", chamado_id).execute()
        
        return True
        
    except Exception as e:
        logger.error(f"Erro ao responder chamado: {e}")
        return False


async def registrar_historico(chat_id: str, tipo: str, mensagem: str, origem: str = "bot") -> bool:
    """Registra uma mensagem no histórico de atendimento."""
    try:
        supabase.table("historico_atendimento").insert({
            "chat_id": str(chat_id),
            "tipo": tipo,
            "mensagem": mensagem,
            "origem": origem
        }).execute()
        
        return True
        
    except Exception as e:
        logger.error(f"Erro ao registrar histórico: {e}")
        return False


# ==========================================
# FUNÇÕES DE CONFIGURAÇÃO
# ==========================================

async def obter_configuracao(chave: str) -> str | None:
    """Obtém uma configuração do sistema."""
    try:
        res = supabase.table("configuracoes_atendimento").select("valor").eq("chave", chave).execute()
        
        if res.data:
            return res.data[0]["valor"]
        return None
        
    except Exception as e:
        logger.error(f"Erro ao obter configuração {chave}: {e}")
        return None


async def obter_email_suporte() -> str:
    """Obtém o email de suporte configurado."""
    email = await obter_configuracao("email_suporte")
    return email or "suportealertasus@gmail.com"