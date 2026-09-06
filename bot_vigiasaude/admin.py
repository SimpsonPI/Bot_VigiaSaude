import os
import logging
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Configuração do Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Lista de IDs de administradores autorizados
ADMIN_IDS = [5242040324]  # Seu ID de admin


def eh_admin(user_id: int) -> bool:
    """Verifica se o usuário é administrador."""
    return user_id in ADMIN_IDS


async def comando_estatisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Visão geral de usuários, planos e cadastros de regulações."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    try:
        res_assinaturas = supabase.table("assinaturas").select("*", count="exact").execute()
        total_assinaturas = res_assinaturas.count if hasattr(res_assinaturas, 'count') else len(res_assinaturas.data)

        res_ativos = supabase.table("assinaturas").select("tipo_plano", count="exact").eq("status", "active").execute()
        total_ativos = res_ativos.count if hasattr(res_ativos, 'count') else len(res_ativos.data)

        res_regulacoes = supabase.table("AlertaSUS_2.0").select("*", count="exact").execute()
        total_regulacoes = res_regulacoes.count if hasattr(res_regulacoes, 'count') else len(res_regulacoes.data)

        texto = (
            "📊 <b>ESTATÍSTICAS GERAIS</b>\n\n"
            f"👥 <b>Total de Usuários (assinaturas):</b> {total_assinaturas}\n"
            f"✅ <b>Assinaturas Ativas:</b> {total_ativos}\n"
            f"📋 <b>Total de Cadastros de Regulação:</b> {total_regulacoes}\n"
        )
        await update.message.reply_text(texto, parse_mode="HTML")
    except Exception as e:
        logger.error(f"[ADMIN] Erro ao executar estatísticas: {e}")
        await update.message.reply_text("❌ Erro ao calcular estatísticas.")


async def comando_listar_ativos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista as últimas assinaturas ativas ou cortesias cadastradas."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    try:
        response = supabase.table("assinaturas").select("chat_id, tipo_plano, status, data_inicio").eq("status", "ativo").limit(15).execute()
        registros = response.data

        if not registros:
            await update.message.reply_text("ℹ️ Nenhuma assinatura ativa encontrada no momento.")
            return

        texto_lista = "📋 <b>Últimas Assinaturas Ativas (Máx. 15):</b>\n\n"
        for reg in registros:
            texto_lista += (
                f"• ID: <code>{reg.get('chat_id')}</code>\n"
                f"  Plano: <b>{reg.get('tipo_plano')}</b> | Status: {reg.get('status')}\n\n"
            )
        await update.message.reply_text(texto_lista, parse_mode="HTML")
    except Exception as e:
        logger.error(f"[ADMIN] Erro ao listar ativos: {e}")
        await update.message.reply_text("❌ Erro ao buscar lista de ativos.")


async def comando_bloquear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Altera o status de um usuário para banido/bloqueado no banco."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ <b>Uso correto:</b> <code>/bloquear &lt;TELEGRAM_ID&gt;</code>", parse_mode="HTML")
        return

    target_id = context.args[0].strip()

    try:
        supabase.table("assinaturas").update({
            "status": "bloqueado",
            "tipo_plano": "bloqueado"
        }).eq("chat_id", str(target_id)).execute()

        await update.message.reply_text(
            f"🚫 <b>CONFIRMAÇÃO:</b> O usuário <code>{target_id}</code> foi bloqueado com sucesso.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"[ADMIN] Erro ao bloquear usuário: {e}")
        await update.message.reply_text(f"❌ Erro ao bloquear no banco de dados: {e}")


async def comando_detalhes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Busca e exibe todas as informações de um usuário específico pelo ID."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ <b>Uso correto:</b> <code>/detalhes &lt;TELEGRAM_ID&gt;</code>", parse_mode="HTML")
        return

    target_id = context.args[0].strip()

    try:
        response = supabase.table("assinaturas").select("*").eq("chat_id", str(target_id)).execute()
        dados = response.data

        if not dados:
            await update.message.reply_text(f"ℹ️ Nenhum registro encontrado para o ID <code>{target_id}</code>.", parse_mode="HTML")
            return

        user_data = dados[0]
        texto = (
            f"🔍 <b>Detalhes do Usuário</b> (<code>{target_id}</code>)\n\n"
            f"• <b>Plano:</b> {user_data.get('tipo_plano')}\n"
            f"• <b>Status:</b> {user_data.get('status')}\n"
            f"• <b>Início:</b> {user_data.get('data_inicio')}\n"
            f"• <b>Vencimento:</b> {user_data.get('data_vencimento') or 'Não aplicável'}\n"
            f"• <b>ID Pagamento MP:</b> {user_data.get('mp_payment_id') or 'Nenhum'}\n"
            f"• <b>Limite IDs:</b> {user_data.get('limite_ids')}\n"
        )
        await update.message.reply_text(texto, parse_mode="HTML")
    except Exception as e:
        logger.error(f"[ADMIN] Erro ao buscar detalhes do usuário {target_id}: {e}")
        await update.message.reply_text("❌ Erro ao consultar dados do usuário.")


async def comando_dar_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Concede um plano específico com validade em dias para um usuário."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ <b>Uso correto:</b> <code>/dar_plano &lt;ID&gt; &lt;plano&gt; &lt;dias&gt;</code>\n"
            "<i>Exemplo:</i> <code>/dar_plano 123456789 pro 30</code>",
            parse_mode="HTML"
        )
        return

    target_id = context.args[0].strip()
    nome_plano = context.args[1].strip().lower()

    try:
        dias = int(context.args[2])
    except ValueError:
        await update.message.reply_text("❌ O número de dias precisa ser um valor inteiro.")
        return

    data_inicio = datetime.now(timezone.utc)
    data_vencimento = data_inicio + timedelta(days=dias)

    try:
        supabase.table("assinaturas").upsert({
            "chat_id": str(target_id),
            "tipo_plano": nome_plano,
            "status": "ativo",
            "data_inicio": data_inicio.isoformat(),
            "data_vencimento": data_vencimento.isoformat()
        }, on_conflict="chat_id").execute()

        await update.message.reply_text(
            f"✅ <b>Plano Concedido com Sucesso!</b>\n\n"
            f"• <b>Usuário ID:</b> <code>{target_id}</code>\n"
            f"• <b>Novo Plano:</b> {nome_plano}\n"
            f"• <b>Validade:</b> {dias} dias (Até {data_vencimento.strftime('%d/%m/%Y')})",
            parse_mode="HTML"
        )

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎁 <b>Seu plano foi atualizado!</b>\n\n"
                     f"Você agora possui acesso ao plano <b>{nome_plano.upper()}</b> válido por {dias} dias. Aproveite!",
                parse_mode="HTML"
            )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"[ADMIN] Erro ao atribuir plano personalizado: {e}")
        await update.message.reply_text(f"❌ Erro ao atualizar plano no banco: {e}")


async def comando_cortesia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Concede acesso VIP/Cortesia ilimitada para um usuário."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ <b>Uso correto:</b> <code>/cortesia &lt;TELEGRAM_ID&gt;</code>", parse_mode="HTML")
        return

    target_id = context.args[0].strip()
    try:
        supabase.table("assinaturas").upsert({
            "chat_id": str(target_id),
            "tipo_plano": "cortesia",
            "status": "ativo",
            "data_inicio": datetime.now(timezone.utc).isoformat(),
            "data_vencimento": None
        }, on_conflict="chat_id").execute()

        await update.message.reply_text(f"🎁 Cortesia aplicada com sucesso para o ID <code>{target_id}</code>.", parse_mode="HTML")
    except Exception as e:
        logger.error(f"[ADMIN] Erro ao dar cortesia: {e}")
        await update.message.reply_text(f"❌ Erro ao conceder cortesia: {e}")


async def comando_remover_cortesia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a cortesia de um usuário, deixando-o neutro (sem plano, sem degustação)."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Uso correto: <code>/remover_cortesia &lt;TELEGRAM_ID&gt;</code>", parse_mode="HTML")
        return

    target_id = context.args[0].strip()

    try:
        # Verifica se o usuário existe
        res = supabase.table("assinaturas").select("*").eq("chat_id", str(target_id)).execute()
        if not res.data:
            # Se não existe, cria um registro neutro com trava de degustação
            supabase.table("assinaturas").insert({
                "chat_id": str(target_id),
                "tipo_plano": None,
                "status": None,
                "usou_degustacao": True
            }).execute()
        else:
            # Atualiza para estado neutro, mantendo a trava de degustação
            supabase.table("assinaturas").update({
                "tipo_plano": None,
                "status": None,
                "data_inicio": None,
                "data_vencimento": None,
                "limite_ids": None,
                "usou_degustacao": True
            }).eq("chat_id", str(target_id)).execute()

        await update.message.reply_text(f"✅ Cortesia removida do ID <code>{target_id}</code>. Usuário agora está neutro.", parse_mode="HTML")
    except Exception as e:
        logger.error(f"[ADMIN] Erro ao remover cortesia: {e}")
        await update.message.reply_text(f"❌ Erro ao remover cortesia: {e}")


async def comando_retirar_plano(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retira o plano de um usuário, deixando-o neutro (sem plano, com trava de degustação)."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Uso correto: /retirar_plano <ID>")
        return

    target_id = context.args[0].strip()

    try:
        # Verifica se existe registro
        res = supabase.table("assinaturas").select("*").eq("chat_id", str(target_id)).execute()
        if not res.data:
            # Se não existe, cria um registro neutro com trava de degustação
            supabase.table("assinaturas").insert({
                "chat_id": str(target_id),
                "tipo_plano": None,
                "status": None,
                "usou_degustacao": True
            }).execute()
        else:
            # Atualiza para estado neutro, mantendo a trava de degustação
            supabase.table("assinaturas").update({
                "tipo_plano": None,
                "status": None,
                "data_inicio": None,
                "data_vencimento": None,
                "limite_ids": None,
                "usou_degustacao": True
            }).eq("chat_id", str(target_id)).execute()

        await update.message.reply_text(f"✅ Plano retirado do usuário {target_id}. Usuário agora está neutro.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao retirar plano: {e}")


async def comando_retirar_degustacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retira o acesso à degustação de um usuário (impede de usar novamente)."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Uso correto: /retirar_degustacao <ID>")
        return

    target_id = context.args[0].strip()

    try:
        # Verifica se existe registro
        res = supabase.table("assinaturas").select("*").eq("chat_id", str(target_id)).execute()
        if not res.data:
            # Cria registro neutro com trava de degustação
            supabase.table("assinaturas").insert({
                "chat_id": str(target_id),
                "tipo_plano": None,
                "status": None,
                "usou_degustacao": True
            }).execute()
        else:
            # Atualiza para neutro e trava degustação
            supabase.table("assinaturas").update({
                "usou_degustacao": True,
                "tipo_plano": None,
                "status": None,
                "data_inicio": None,
                "data_vencimento": None,
                "limite_ids": None
            }).eq("chat_id", str(target_id)).execute()

        await update.message.reply_text(f"✅ Degustação retirada do usuário {target_id}. Usuário agora está neutro.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao retirar degustação: {e}")


async def comando_aviso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia uma mensagem de broadcast (aviso em massa) para todos os usuários cadastrados."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ <b>Uso correto:</b> <code>/aviso &lt;Sua mensagem aqui&gt;</code>", parse_mode="HTML")
        return

    mensagem_broadcast = " ".join(context.args)

    try:
        response = supabase.table("assinaturas").select("chat_id").execute()
        registros = response.data

        if not registros:
            await update.message.reply_text("ℹ️ Nenhum usuário encontrado para enviar o aviso.")
            return

        await update.message.reply_text(f"🚀 Iniciando envio de aviso para {len(registros)} usuários...")

        enviados = 0
        falhas = 0

        for reg in registros:
            chat_id = reg.get("chat_id")
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"📢 <b>AVISO IMPORTANTE - VigiaSaude</b>\n\n{mensagem_broadcast}",
                    parse_mode="HTML"
                )
                enviados += 1
            except Exception:
                falhas += 1

        await update.message.reply_text(
            f"✅ <b>Broadcast Finalizado!</b>\n\n"
            f"• Enviados com sucesso: <code>{enviados}</code>\n"
            f"• Falhas (usuários que bloquearam o bot): <code>{falhas}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"[ADMIN] Erro no broadcast: {e}")
        await update.message.reply_text(f"❌ Erro ao executar o envio em massa: {e}")


async def comando_menu_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe o painel de controle administrativo."""
    if not eh_admin(update.effective_user.id):
        await update.message.reply_text("❌ Você não tem permissão para usar este comando.")
        return

    texto = (
        "🎛️ <b>PAINEL DE CONTROLE ADMINISTRATIVO</b>\n"
        "VigiaSaude - Central de Operações\n\n"
        "Selecione ou utilize um dos comandos abaixo para gerenciar o bot:\n\n"
        "📊 <b>Relatórios e Dados:</b>\n"
        "• /estatisticas - Visão geral de usuários, planos e cadastros\n"
        "• /ativos - Lista as últimas assinaturas ativas\n"
        "• /detalhes &lt;ID&gt; - Mostra dados completos de um usuário\n\n"
        "👑 <b>Gestão de Planos e Acessos:</b>\n"
        "• /cortesia &lt;ID&gt; - Concede acesso ilimitado/VIP\n"
        "• /remover_cortesia &lt;ID&gt; - Retira cortesia e deixa neutro\n"
        "• /dar_plano &lt;ID&gt; &lt;plano&gt; &lt;dias&gt; - Concede plano com validade\n"
        "• /retirar_plano &lt;ID&gt; - Retira plano pago e deixa neutro\n"
        "• /retirar_degustacao &lt;ID&gt; - Retira acesso à degustação\n\n"
        "🛡️ <b>Segurança e Comunicação:</b>\n"
        "• /bloquear &lt;ID&gt; - Bloqueia o acesso de um usuário\n"
        "• /aviso &lt;mensagem&gt; - Dispara broadcast para toda a base\n\n"
        "💡 <i>Dica: Pode digitar o comando diretamente na barra de mensagens.</i>"
    )
    await update.message.reply_text(texto, parse_mode="HTML")
