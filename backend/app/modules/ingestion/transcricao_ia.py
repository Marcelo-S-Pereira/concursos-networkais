"""Transcrição de UMA questão por IA cadastrada.

LLM (categoria 'texto') recebe o texto da página (em colunas) e extrai a questão.
VLM (categoria 'visao') recebe a imagem da página e faz o mesmo. Devolve
{enunciado, alternativas{A..E}} — NUNCA o gabarito (o backend é dono dele).
Não salva: é sugestão para o usuário revisar.
"""

import base64
import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Question
from app.modules.ai_registry import servico

FIGURAS_DIR = Path(__file__).resolve().parents[3].parent / "uploads" / "figuras"

SISTEMA = (
    "Você extrai UMA questão de prova de concurso e devolve SOMENTE um JSON válido, "
    "sem texto antes ou depois. Não invente conteúdo, não inclua o gabarito, não "
    "resolva a questão. Formato exigido: "
    '{"enunciado": "...", "alternativas": {"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}}'
)


def _parse_json_tolerante(texto: str) -> dict:
    """Extrai o primeiro objeto JSON da resposta, tolerando lixo em volta."""
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio >= 0 and fim > inicio:
        bruto = texto[inicio : fim + 1]
        try:
            return json.loads(bruto)
        except json.JSONDecodeError:
            # remove vírgulas finais antes de } ou ]
            limpo = re.sub(r",\s*([}\]])", r"\1", bruto)
            return json.loads(limpo)
    raise ValueError("A IA não devolveu JSON reconhecível.")


def _normalizar(dados: dict) -> dict:
    alts = dados.get("alternativas") or {}
    return {
        "enunciado": str(dados.get("enunciado", "")).strip(),
        "alternativas": {L: str(alts.get(L, "")).strip() for L in "ABCDE"},
    }


def transcrever_questao(db: Session, questao: Question) -> dict:
    numero = questao.numero
    if questao.tem_figura:
        # VLM: manda a imagem da página + instrução
        img = FIGURAS_DIR / f"exam{questao.exam_id}_pagina{questao.pagina}.png"
        if not img.exists():
            raise ValueError("Imagem da página não encontrada para a leitura por visão.")
        b64 = base64.b64encode(img.read_bytes()).decode()
        mensagens = [
            {"role": "system", "content": SISTEMA},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Transcreva a questão nº {numero} desta página. "
                                "Se houver figura/gráfico essencial, descreva-o dentro do enunciado.",
                    },
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            },
        ]
        resposta = servico.conversar(db, "visao", mensagens, origem="transcricao_vlm", max_tokens=2000)
    else:
        txt = (FIGURAS_DIR / f"exam{questao.exam_id}_pagina{questao.pagina}.txt")
        pagina_texto = txt.read_text(encoding="utf-8") if txt.exists() else questao.enunciado
        mensagens = [
            {"role": "system", "content": SISTEMA},
            {"role": "user", "content": f"Texto da página (em colunas):\n\n{pagina_texto}\n\n"
                                        f"Extraia a questão de número {numero}."},
        ]
        resposta = servico.conversar(db, "texto", mensagens, origem="transcricao_llm", max_tokens=2000)

    return _normalizar(_parse_json_tolerante(resposta))
