"""Classificação e eliminação pelas regras do edital (spec §7.1, §15; edital
Cesgranrio item 7.1.4.3). Regra por FASE: mínimo percentual de pontos por fase,
matérias que não podem zerar, e nota de corte. O backend é a autoridade."""

from app.db.models import ExamRules


def classificar(regras: ExamRules, itens: list[tuple[str, bool]]) -> dict:
    pesos = regras.pesos or {}
    fases = regras.fases or {}
    minimo_pct_fase = regras.minimo_pct_fase or {}
    sem_zero = set(regras.materias_sem_zero or [])

    acertos_disc: dict[str, int] = {}
    total_disc: dict[str, int] = {}
    pontos_disc: dict[str, float] = {}
    for disciplina, acertou in itens:
        total_disc[disciplina] = total_disc.get(disciplina, 0) + 1
        peso = float(pesos.get(disciplina, 1.0))
        if acertou:
            acertos_disc[disciplina] = acertos_disc.get(disciplina, 0) + 1
            pontos_disc[disciplina] = pontos_disc.get(disciplina, 0.0) + peso

    nota_ponderada = sum(pontos_disc.values())
    motivos: list[str] = []

    # --- por fase (mínimo percentual) ---
    pontos_fase: dict[str, float] = {}
    total_pontos_fase: dict[str, float] = {}
    for disciplina in total_disc:
        fase = fases.get(disciplina, disciplina)
        peso = float(pesos.get(disciplina, 1.0))
        pontos_fase[fase] = pontos_fase.get(fase, 0.0) + pontos_disc.get(disciplina, 0.0)
        total_pontos_fase[fase] = total_pontos_fase.get(fase, 0.0) + total_disc[disciplina] * peso

    resumo_fase = []
    for fase, tot in sorted(total_pontos_fase.items()):
        obtido = pontos_fase.get(fase, 0.0)
        pct = round(obtido / tot * 100, 1) if tot else 0.0
        minimo = minimo_pct_fase.get(fase)
        resumo_fase.append({"fase": fase, "pontos": round(obtido, 2), "total": round(tot, 2),
                            "percentual": pct, "minimo_pct": minimo})
        if minimo is not None and pct < float(minimo):
            motivos.append(f"{fase}: {pct}% (mínimo {minimo}%)")

    # --- mínimos por disciplina (opcional, além das fases) ---
    for disciplina, minimo in (regras.minimos or {}).items():
        if acertos_disc.get(disciplina, 0) < int(minimo):
            motivos.append(f"{disciplina}: {acertos_disc.get(disciplina, 0)} acertos (mínimo {minimo})")

    # --- matérias que não podem zerar ---
    for disciplina in sem_zero:
        if total_disc.get(disciplina, 0) > 0 and acertos_disc.get(disciplina, 0) == 0:
            motivos.append(f"{disciplina}: zerou (não pode ter grau zero)")

    # --- nota de corte ---
    if regras.nota_corte is not None and nota_ponderada < regras.nota_corte:
        motivos.append(f"nota {round(nota_ponderada, 2)} abaixo do corte {regras.nota_corte}")

    return {
        "nota_ponderada": round(nota_ponderada, 2),
        "nota_corte": regras.nota_corte,
        "vagas": regras.vagas,
        "eliminado": len(motivos) > 0,
        "motivos": motivos,
        "por_fase": resumo_fase,
        "por_disciplina": {
            d: {"acertos": acertos_disc.get(d, 0), "total": total_disc.get(d, 0),
                "peso": float(pesos.get(d, 1.0))}
            for d in sorted(total_disc)
        },
    }
