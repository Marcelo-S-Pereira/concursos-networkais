"""Estados de Mastery e desempenho por ênfase (spec §7.3, §8).

O backend calcula tudo — a IA não entra aqui. Mastery inicial precisa de no
mínimo 3 itens válidos; abaixo disso é NOT_TESTED."""

MIN_ITENS = 3


def estado_mastery(acertos: int, total: int) -> str:
    if total < MIN_ITENS:
        return "NOT_TESTED"
    pct = acertos / total * 100
    if pct < 50:
        return "WEAK"
    if pct < 70:
        return "UNSTABLE"
    if pct < 85:
        return "CONSISTENT"
    return "STRONG"


def por_enfase(itens: list[tuple[str, bool]]) -> list[dict]:
    """itens: (disciplina/ênfase, acertou). Devolve por ênfase: acertos, total,
    %, estado, tamanho da amostra."""
    agrupado: dict[str, list[bool]] = {}
    for enfase, acertou in itens:
        agrupado.setdefault(enfase or "Sem classificação", []).append(acertou)

    saida = []
    for enfase, acertos_lista in sorted(agrupado.items()):
        total = len(acertos_lista)
        acertos = sum(1 for a in acertos_lista if a)
        saida.append({
            "enfase": enfase,
            "acertos": acertos,
            "total": total,
            "percentual": round(acertos / total * 100, 1) if total else 0.0,
            "mastery": estado_mastery(acertos, total),
            "amostra": total,
        })
    return saida


def rotulo_delta(delta: float) -> str:
    if delta >= 15:
        return "muito acima"
    if delta >= 5:
        return "acima"
    if delta > -5:
        return "próximo"
    if delta > -15:
        return "abaixo"
    return "muito abaixo"
