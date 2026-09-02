"""Custo em dinheiro DERIVADO na leitura: tokens do log × preço da conexão.

Preço muda com o tempo; gravar o custo congelaria o histórico. Por isso o custo
é sempre recalculado ao exibir. Conexão sem preço cadastrado → custo None
('preço não cadastrado'), nunca zero (que seria enganoso)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AiCallLog, AiConnection


def resumo_custo(db: Session) -> dict:
    conns = {c.id: c for c in db.execute(select(AiConnection)).scalars()}
    total = 0.0
    tem_preco = False
    linhas = []
    for c_id, conn in conns.items():
        logs = list(db.execute(select(AiCallLog).where(AiCallLog.connection_id == c_id)).scalars())
        pt = sum(x.prompt_tokens or 0 for x in logs)
        ct = sum(x.completion_tokens or 0 for x in logs)
        if conn.preco_entrada_por_milhao is not None and conn.preco_saida_por_milhao is not None:
            custo = pt / 1e6 * conn.preco_entrada_por_milhao + ct / 1e6 * conn.preco_saida_por_milhao
            total += custo
            tem_preco = True
        else:
            custo = None
        linhas.append({"conexao": conn.nome, "prompt_tokens": pt, "completion_tokens": ct,
                       "custo": custo, "moeda": conn.moeda})
    return {"total": total if tem_preco else None, "por_conexao": linhas,
            "observacao": "Piso conhecido: só conexões com preço cadastrado entram no total."}
