import shutil

# ─── Backup ───
for a in ["database.py", "handler.py", "handler_planos.py"]:
    shutil.copy2(a, a + ".bak_bypass")
print("Backup OK\n")


def aplicar_patch(arquivo, antigo, novo, descricao):
    with open(arquivo, encoding="utf-8") as f:
        content = f.read()
    if antigo not in content:
        print(f"  FALTOU: {descricao} ({arquivo})")
        return False
    content = content.replace(antigo, novo, 1)
    with open(arquivo, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  OK: {descricao}")
    return True


# ═══════════════════════════════════════════════════════════
# 1) database.py — verificar_assinatura_ativa
# ═══════════════════════════════════════════════════════════
antigo_db = '''def verificar_assinatura_ativa(user_id: int) -> bool:
    """Verifica se o usuário possui uma assinatura ativa no Supabase."""
    try:'''

novo_db = '''def verificar_assinatura_ativa(user_id: int) -> bool:
    """Verifica se o usuário possui uma assinatura ativa no Supabase."""
    # 👑 Admin tem acesso total, sempre
    try:
        from config import is_admin
        if is_admin(user_id):
            logger.info(f"👑 Bypass admin em verificar_assinatura_ativa (user={user_id})")
            return True
    except Exception:
        pass

    try:'''

aplicar_patch("database.py", antigo_db, novo_db,
              "database.py: bypass em verificar_assinatura_ativa")


# ═══════════════════════════════════════════════════════════
# 2) handler.py — usuario_tem_acesso
# ═══════════════════════════════════════════════════════════
antigo_h = '''def usuario_tem_acesso(plano_info: dict) -> bool:
    status_bruto = str(plano_info.get("status", "")).strip().lower()'''

novo_h = '''def usuario_tem_acesso(plano_info: dict, user_id: int = None) -> bool:
    # 👑 Admin tem acesso total, sempre
    if user_id is not None:
        try:
            from config import is_admin
            if is_admin(user_id):
                logger.info(f"👑 Bypass admin em usuario_tem_acesso (user={user_id})")
                return True
        except Exception:
            pass

    status_bruto = str(plano_info.get("status", "")).strip().lower()'''

aplicar_patch("handler.py", antigo_h, novo_h,
              "handler.py: bypass em usuario_tem_acesso")


# ═══════════════════════════════════════════════════════════
# 3) handler_planos.py — usuario_tem_acesso
# ═══════════════════════════════════════════════════════════
antigo_hp = '''def usuario_tem_acesso(plano_info: dict) -> bool:
    """Valida se o usuário possui acesso liberado (Cortesia, Degustação ou Pago)."""
    status_bruto = str(plano_info.get("status", "")).strip().lower()'''

novo_hp = '''def usuario_tem_acesso(plano_info: dict, user_id: int = None) -> bool:
    """Valida se o usuário possui acesso liberado (Cortesia, Degustação ou Pago)."""
    # 👑 Admin tem acesso total, sempre
    if user_id is not None:
        try:
            from config import is_admin
            if is_admin(user_id):
                logger.info(f"👑 Bypass admin em usuario_tem_acesso (planos) (user={user_id})")
                return True
        except Exception:
            pass

    status_bruto = str(plano_info.get("status", "")).strip().lower()'''

aplicar_patch("handler_planos.py", antigo_hp, novo_hp,
              "handler_planos.py: bypass em usuario_tem_acesso")


print("\nEtapa B concluida")
