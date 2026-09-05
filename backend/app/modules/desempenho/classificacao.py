"""Classificação e eliminação pelas regras do edital (spec §7.1, §15).

O backend é a autoridade. Recebe as regras e os itens (disciplina, acertou) e
devolve nota ponderada, motivos de eliminação e o status final. Sem regra
cadastrada, o chamador simplesmente não anexa classificação."""

from app.db.models import ExamRules


def classificar(regras: ExamRules, itens: list[tuple[str, bool]]) -> dict:
    pesos = regras.pesos or {}
    minimos = regras.minimos or {}

    # acertos e nota ponderada por disciplina
    acertos_disc: dict[str, int] = {}
    total_disc: dict[str, int] = {}
    nota_ponderada = 0.0
    for disciplina, acertou in itens:
        total_disc[disciplina] = total_disc.get(disciplina, 0) + 1
        if acertou:
            acertos_disc[disciplina] = acertos_disc.get(disciplina, 0) + 1
            nota_ponderada += float(pesos.get(disciplina, 1.0))

    motivos: list[str] = []
    for disciplina, minimo in minimos.items():
        got = acertos_disc.get(disciplina, 0)
        if got < int(minimo):
            motivos.append(f"{disciplina}: {got} acertos (mínimo {minimo})")

    if regras.nota_corte is not None and nota_ponderada < regras.nota_corte:
        motivos.append(f"nota {round(nota_ponderada, 2)} abaixo do corte {regras.nota_corte}")

    return {
        "nota_ponderada": round(nota_ponderada, 2),
        "nota_corte": regras.nota_corte,
        "vagas": regras.vagas,
        "eliminado": len(motivos) > 0,
        "motivos": motivos,
        "por_disciplina": {
            d: {"acertos": acertos_disc.get(d, 0), "total": total_disc.get(d, 0),
                "peso": float(pesos.get(d, 1.0)), "minimo": minimos.get(d)}
            for d in sorted(total_disc)
        },
    }
