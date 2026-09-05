"""Estimativa de classificação/ranking (spec §15).

A partir do desempenho do candidato por ênfase, da estatística pública de acerto
por ênfase e do total de inscritos, estima percentil, posição e situação. É
ESTIMATIVA — nunca falsa precisão: sem dado público, devolve
PUBLIC_DATA_NOT_FOUND; sempre traz um nível de confiança.
"""

import math
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EmphasisPublicStat, Exam, ExamRules

# suavidade da curva delta→percentil (pontos percentuais para ~73% de percentil).
K = 8.0


def estimar_ranking(db: Session, exam: Exam, itens: list[tuple[str, bool]], regras: ExamRules) -> dict:
    total = len(itens)
    acertos = sum(1 for _, a in itens if a)
    cand_pct = acertos / total * 100 if total else 0.0

    por_enfase = Counter(d for d, _ in itens)
    num = den = 0.0
    faltando: list[str] = []
    fontes = []
    for enfase, n in por_enfase.items():
        stat = db.execute(
            select(EmphasisPublicStat).where(
                EmphasisPublicStat.enfase == enfase,
                EmphasisPublicStat.banca == exam.banca, EmphasisPublicStat.cargo == exam.cargo,
            )
        ).scalars().first() or db.execute(
            select(EmphasisPublicStat).where(EmphasisPublicStat.enfase == enfase)
        ).scalars().first()
        if stat and stat.acerto_pct is not None and stat.status == "OK":
            num += stat.acerto_pct * n
            den += n
            if stat.fonte:
                fontes.append(stat.fonte)
        else:
            faltando.append(enfase)

    if den == 0:
        return {"status": "PUBLIC_DATA_NOT_FOUND",
                "observacao": "Sem estatística pública por ênfase — cadastre em Estatísticas para estimar o ranking."}

    publico_pct = num / den
    delta = cand_pct - publico_pct
    percentil = 1 / (1 + math.exp(-delta / K))  # 0..1 (fração que o candidato supera)

    total_inscritos = regras.total_inscritos
    vagas = regras.vagas
    posicao = round((1 - percentil) * total_inscritos) if total_inscritos else None

    situacao = None
    if posicao is not None and vagas:
        if posicao <= vagas:
            situacao = "dentro das vagas"
        elif posicao <= 2 * vagas:
            situacao = "cadastro de reserva provável"
        else:
            situacao = "fora das vagas"

    # confiança: alta se todas as ênfases têm dado; cai com o que falta e com amostra do simulado
    if not faltando and total >= 30:
        confianca = "alta"
    elif len(faltando) <= 1 and total >= 15:
        confianca = "moderada"
    else:
        confianca = "baixa"

    return {
        "status": "OK",
        "candidato_pct": round(cand_pct, 1),
        "publico_pct": round(publico_pct, 1),
        "delta_pp": round(delta, 1),
        "percentil_estimado": round(percentil * 100, 1),
        "posicao_estimada": posicao,
        "total_inscritos": total_inscritos,
        "vagas": vagas,
        "situacao": situacao,
        "confianca": confianca,
        "enfases_sem_dado": faltando,
        "fontes": sorted(set(fontes)),
    }
