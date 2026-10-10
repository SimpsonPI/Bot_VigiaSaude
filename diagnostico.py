"""
Diagnóstico rápido de problemas no banco.
Uso: python diagnostico.py
"""
from dotenv import load_dotenv
load_dotenv()

from database import supabase

def testar_operacoes(tabela: str, filtro_campo: str, filtro_valor):
    print(f"\n{'='*60}")
    print(f"Testando tabela: {tabela}")
    print(f"{'='*60}\n")

    # 1) SELECT
    try:
        r = supabase.table(tabela).select("*").eq(filtro_campo, filtro_valor).execute()
        n_select = len(r.data)
        print(f"✅ SELECT: {n_select} linha(s)")
        if n_select == 0:
            print("   ⚠️  Nenhuma linha encontrada — verifique o filtro")
            return
        registro = r.data[0]
        print(f"   Campos: {list(registro.keys())}")
    except Exception as e:
        print(f"❌ SELECT falhou: {e}")
        return

    # 2) UPDATE (testa permissão sem alterar nada)
    try:
        campo_update = "status_anterior"
        valor_atual = registro.get(campo_update)
        r = supabase.table(tabela).update({campo_update: valor_atual}).eq(filtro_campo, filtro_valor).execute()
        if len(r.data) > 0:
            print(f"✅ UPDATE: permitido")
        else:
            print(f"❌ UPDATE: bloqueado por RLS (0 linhas afetadas)")
    except Exception as e:
        print(f"❌ UPDATE falhou: {e}")

    # 3) DELETE (testa em uma cópia — NÃO executa de verdade)
    try:
        # Usa um filtro impossível pra não deletar nada real
        r = supabase.table(tabela).delete().eq(filtro_campo, -1).execute()
        print(f"✅ DELETE: query aceita (teste com filtro inexistente)")
        print(f"   ⚠️  Para testar de verdade, use: python diagnostico.py --delete <id>")
    except Exception as e:
        print(f"❌ DELETE falhou: {e}")


if __name__ == "__main__":
    import sys

    print("🔍 DIAGNÓSTICO DE PERMISSÕES SUPABASE")
    print("Testando RLS nas tabelas do bot...\n")

    # Testa as tabelas críticas com dados reais (só SELECT)
    testar_operacoes("AlertaSUS_2.0", "chat_id", 5242040324)

    # Se quiser testar DELETE de verdade:
    if len(sys.argv) > 1 and sys.argv[1] == "--delete":
        if len(sys.argv) < 3:
            print("\nUso: python diagnostico.py --delete <id>")
            sys.exit(1)
        id_alvo = int(sys.argv[2])
        print(f"\n🗑️  Deletando ID {id_alvo}...")
        r = supabase.table("AlertaSUS_2.0").delete().eq("id", id_alvo).execute()
        print(f"Deletou: {len(r.data)} linha(s)")
        if len(r.data) == 0:
            print("❌ RLS bloqueando DELETE — habilite policy no Supabase")