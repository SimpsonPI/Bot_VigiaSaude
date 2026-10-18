"""
OCR de comprovante de regulacao via Google Gemini.
Extrai: numero_reg, numero_sus, nome_paciente, cbo, procedimento.
"""

import os
import asyncio
import base64
import json
import logging
import re
import httpx

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-flash-lite-latest",
]
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT = """Voce recebe a foto de um comprovante de solicitacao de regulacao do SUS (FMS Teresina).

Extraia os campos abaixo e responda SOMENTE com JSON valido, sem texto adicional, sem markdown:

{
  "numero_reg": "8 digitos do campo 'Solicitacao de Regulacao n.' (apenas digitos)",
  "numero_sus": "15 digitos do campo 'Cartao SUS n.' (apenas digitos)",
  "nome_paciente": "nome completo do paciente em MAIUSCULAS",
  "cbo": "especialidade do campo CBO em MAIUSCULAS (ex: MEDICO REUMATOLOGISTA)",
  "procedimento": "descricao do procedimento em MAIUSCULAS",
  "confianca": "alta | media | baixa"
}

Regras:
- Se um campo nao for legivel, use null.
- Nao invente dados.
- numero_reg tem exatamente 8 digitos.
- numero_sus tem exatamente 15 digitos.
- Retorne APENAS o JSON, sem texto antes ou depois.
"""


async def extrair_dados_comprovante(imagem_bytes: bytes, mimetype: str = "image/jpeg") -> dict:
    """Envia imagem pro Gemini e retorna dict com dados extraidos."""
    if not GEMINI_API_KEY:
        return {"erro": "GEMINI_API_KEY nao configurada"}

    try:
        b64 = base64.b64encode(imagem_bytes).decode("ascii")
    except Exception as e:
        return {"erro": f"Falha ao codificar imagem: {e}"}

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": PROMPT},
                    {
                        "inline_data": {
                            "mime_type": mimetype,
                            "data": b64,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "response_mime_type": "application/json",
        },
    }

    conteudo = None
    ultimo_erro = None

    async with httpx.AsyncClient(timeout=60.0) as client:
        for modelo in GEMINI_MODELS:
            url = f"{GEMINI_URL_TEMPLATE.format(model=modelo)}?key={GEMINI_API_KEY}"

            # 2 tentativas por modelo (503 e temporario)
            for tentativa in range(2):
                try:
                    r = await client.post(url, json=payload)
                    if r.status_code == 200:
                        data = r.json()
                        conteudo = data["candidates"][0]["content"]["parts"][0]["text"]
                        logger.info(f"Gemini OK: {modelo} (tentativa {tentativa + 1})")
                        break
                    elif r.status_code == 503:
                        logger.warning(f"Gemini {modelo} 503 (tentativa {tentativa + 1})")
                        ultimo_erro = "503 sobrecarregado"
                        if tentativa == 0:
                            await asyncio.sleep(3)
                            continue
                        else:
                            break
                    else:
                        logger.warning(f"Gemini {modelo} HTTP {r.status_code}: {r.text[:200]}")
                        ultimo_erro = f"HTTP {r.status_code}"
                        break
                except Exception as e:
                    logger.warning(f"Gemini {modelo} erro: {e}")
                    ultimo_erro = str(e)
                    break
            if conteudo:
                break

    if not conteudo:
        return {"erro": f"IA indisponivel agora ({ultimo_erro}). Tente em 1 minuto."}

    # Parse do JSON
    try:
        parsed = json.loads(conteudo)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", conteudo, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                return {"erro": "Resposta da IA nao e JSON valido"}
        else:
            return {"erro": "Resposta da IA sem JSON"}

    # Normaliza
    out = {}
    if parsed.get("numero_reg"):
        nr = re.sub(r"\D", "", str(parsed["numero_reg"]))
        out["numero_reg"] = nr if len(nr) == 8 else None
    else:
        out["numero_reg"] = None

    if parsed.get("numero_sus"):
        ns = re.sub(r"\D", "", str(parsed["numero_sus"]))
        out["numero_sus"] = ns if len(ns) == 15 else None
    else:
        out["numero_sus"] = None

    out["nome_paciente"] = (parsed.get("nome_paciente") or "").strip().upper() or None
    out["cbo"] = (parsed.get("cbo") or "").strip().upper() or None
    out["procedimento"] = (parsed.get("procedimento") or "").strip().upper() or None
    out["confianca"] = parsed.get("confianca") or "media"

    return out
