"""
planos_config.py — Fonte única de verdade dos planos do VigiaSaúde.

Para ajustar valores, limites, textos ou benefícios: edite APENAS este arquivo.
Todos os handlers importam daqui.

Última atualização: 2026-10-12
"""

# ═══════════════════════════════════════════════════════════
# DEFINIÇÃO DOS PLANOS
# ═══════════════════════════════════════════════════════════
# A chave é o identificador do plano (usado em tipo_plano no banco).
# NUNCA mude a chave sem migrar o banco antes.

PLANOS = {
    "degustacao": {
        "chave": "degustacao",
        "nome": "Degustação",
        "nome_botao": "🎁 Plano Degustação (Grátis)",
        "emoji": "🎁",
        "preco": 0.0,
        "dias": 7,
        "limite_ids": 2,
        "subtitulo": "Teste grátis por 7 dias",
        "badge": None,
        "beneficios": [
            "Até 2 regulações monitoradas",
            "Notificações em tempo real no Telegram",
            "Sem necessidade de cartão de crédito",
        ],
    },
    "mensal": {
        "chave": "mensal",
        "nome": "Pro Mensal",
        "nome_botao": "🟢 Plano Mensal (R$ 9,99)",
        "emoji": "🟢",
        "preco": 9.99,
        "dias": 30,
        "limite_ids": 6,
        "subtitulo": "Flexibilidade mês a mês",
        "badge": None,
        "beneficios": [
            "Até 6 regulações monitoradas",
            "Notificações em tempo real no Telegram",
            "Renovação mensal",
        ],
    },
    "pro_trimestral": {
        "chave": "pro_trimestral",
        "nome": "Pro Trimestral",
        "nome_botao": "🟡 Plano Trimestral (R$ 19,99)",
        "emoji": "🟡",
        "preco": 19.99,
        "dias": 90,
        "limite_ids": 8,
        "subtitulo": "Economia de 33% — equivale a R$ 6,66/mês",
        "badge": "⭐ 33% OFF",
        "beneficios": [
            "Até 8 regulações monitoradas",
            "Notificações em tempo real no Telegram",
            "90 dias de tranquilidade",
        ],
    },
    "pro_semestral": {
        "chave": "pro_semestral",
        "nome": "Pro Semestral",
        "nome_botao": "🔴 Plano Semestral (R$ 29,99)",
        "emoji": "🔴",
        "preco": 29.99,
        "dias": 180,
        "limite_ids": 12,
        "subtitulo": "Máxima proteção — equivale a R$ 4,99/mês",
        "badge": "🔥 MAIS VENDIDO — 50% OFF",
        "beneficios": [
            "Até 12 regulações monitoradas (família)",
            "Notificações em tempo real no Telegram",
            "180 dias de tranquilidade",
        ],
    },
}


# ═══════════════════════════════════════════════════════════
# ALIASES (compatibilidade com dados antigos do banco)
# ═══════════════════════════════════════════════════════════

ALIASES = {
    "trimestral": "pro_trimestral",
    "semestral": "pro_semestral",
    "pro": "pro_trimestral",
    "free": "degustacao",
    "cortesia": "cortesia",   # cortesia não é plano pago, mas precisa existir
}


# ═══════════════════════════════════════════════════════════
# ORDEM DE EXIBIÇÃO NOS MENUS
# ═══════════════════════════════════════════════════════════

ORDEM_PAGOS = ["mensal", "pro_trimestral", "pro_semestral"]


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def normalizar(tipo: str) -> str:
    """Normaliza variações antigas para o id canônico."""
    t = str(tipo or "").strip().lower()
    return ALIASES.get(t, t)


def get(tipo: str) -> dict | None:
    """Retorna o dict completo do plano, ou None."""
    return PLANOS.get(normalizar(tipo))


def planos_pagos() -> list[dict]:
    """Lista de planos pagos na ordem de exibição."""
    return [PLANOS[k] for k in ORDEM_PAGOS if k in PLANOS]


def dias(tipo: str) -> int:
    p = get(tipo)
    return p["dias"] if p else 30


def limite(tipo: str) -> int:
    p = get(tipo)
    return p["limite_ids"] if p else 2


def nome(tipo: str) -> str:
    p = get(tipo)
    return p["nome"] if p else "Desconhecido"


def preco(tipo: str) -> float:
    p = get(tipo)
    return p["preco"] if p else 0.0


def nome_botao(tipo: str) -> str:
    p = get(tipo)
    return p["nome_botao"] if p else tipo


def emoji(tipo: str) -> str:
    p = get(tipo)
    return p["emoji"] if p else "⚪"


def beneficios(tipo: str) -> list[str]:
    p = get(tipo)
    return p.get("beneficios", []) if p else []


def texto_lista_planos() -> str:
    """Texto formatado com todos os planos pagos (para mensagens)."""
    linhas = []
    for p in planos_pagos():
        badge = f" {p['badge']}" if p.get("badge") else ""
        linhas.append(
            f"{p['emoji']} <b>{p['nome']}</b> — R$ {p['preco']:.2f}{badge}\n"
            f"   {p['subtitulo']} · até {p['limite_ids']} regulações"
        )
    return "\n\n".join(linhas)