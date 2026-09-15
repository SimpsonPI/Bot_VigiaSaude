# corrigir.py
import io

ARQUIVO = "handler.py"

with io.open(ARQUIVO, "r", encoding="utf-8") as f:
    linhas = f.readlines()

# Índices são 0-based, então linha 308 = índice 307
def fix_indent(idx, espacos=8):
    linha = linhas[idx]
    linha_limpa = linha.lstrip()
    linhas[idx] = (" " * espacos) + linha_limpa

# Fix 1: linha 308 — keyboard_botoes deve ter 8 espaços
fix_indent(307, 8)

# Fix 2: linha 309 — trocar pix_semestral por pix_trimestral
linhas[308] = linhas[308].replace("pix_semestral", "pix_trimestral")

# Fix 3: linha 314 — texto do plano semestral com 8 espaços
fix_indent(313, 8)

# Fix 4: linha 315 — keyboard_botoes do semestral com 8 espaços
fix_indent(314, 8)

with io.open(ARQUIVO, "w", encoding="utf-8") as f:
    f.writelines(linhas)

print("✅ handler.py corrigido com sucesso.")