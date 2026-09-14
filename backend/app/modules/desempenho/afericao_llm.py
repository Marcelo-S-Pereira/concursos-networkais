"""Aferição do LLM: mede se o LLM cadastrado reproduz a lógica de classificação
do backend. O backend calcula (autoridade); o LLM recebe as MESMAS regras e
resultados e calcula também; comparamos e devolvemos só o **% de semelhança**.
A resposta do LLM não é exibida."""

from sqlalchemy.orm import Session

from app.db.models import Exam, ExamRules
from app.modules.ai_registry import servico
from app.modules.desempenho.classificacao import classificar
from app.modules.ingestion.transcricao_ia import _parse_json_tolerante
from app.modules.prompts import prompts


def _itens(disc_counts: dict[str, int], acertos: dict[str, int]) -> list[tuple[str, bool]]:
    itens = []
    for disc, total in disc_counts.items():
        certos = acertos.get(disc, 0)
        itens += [(disc, True)] * certos + [(disc, False)] * (total - certos)
    return itens


def _cenarios(disc_counts: dict[str, int], fases: dict[str, str]) -> list[dict[str, int]]:
    """Alguns cenários que exercitam a regra (passar/reprovar por fase)."""
    todos = {d: t for d, t in disc_counts.items()}
    metade = {d: t // 2 for d, t in disc_counts.items()}
    # reprova a 1ª fase encontrada / a 2ª fase
    labels = sorted(set(fases.get(d, d) for d in disc_counts))
    reprova = []
    for alvo in labels[:2]:
        c = {d: t for d, t in disc_counts.items()}
        for d in disc_counts:
            if fases.get(d, d) == alvo:
                c[d] = 0
        reprova.append(c)
    return [todos, metade, *reprova]


def _prompt(db: Session, regras: ExamRules, disc_counts: dict[str, int], acertos: dict[str, int]) -> list[dict]:
    linhas = "\n".join(f"- {d}: {acertos.get(d,0)} de {t} acertos" for d, t in disc_counts.items())
    fases = "\n".join(f"- {d} pertence à fase '{f}'" for d, f in (regras.fases or {}).items())
    minf = "\n".join(f"- fase '{f}': mínimo {p}% dos pontos" for f, p in (regras.minimo_pct_fase or {}).items())
    sz = ", ".join(regras.materias_sem_zero or []) or "nenhuma"
    user = (
        f"Regras:\nFases:\n{fases}\nMínimos por fase:\n{minf}\nMatérias que não podem zerar: {sz}\n\n"
        f"Resultado do candidato:\n{linhas}\n\nCalcule."
    )
    return [{"role": "system", "content": prompts.buscar(db, "afericao_llm_sistema")},
            {"role": "user", "content": user}]


def aferir(db: Session, exam: Exam, regras: ExamRules) -> dict:
    disc_counts: dict[str, int] = {}
    for q in exam.questoes:
        if not q.descartada:
            disc_counts[q.disciplina] = disc_counts.get(q.disciplina, 0) + 1

    checagens = 0
    acertos_comp = 0
    cenarios = _cenarios(disc_counts, regras.fases or {})
    for acertos in cenarios:
        meu = classificar(regras, _itens(disc_counts, acertos))
        try:
            resposta = servico.conversar(db, "texto", _prompt(db, regras, disc_counts, acertos),
                                         origem="aferir_llm", max_tokens=600)
            llm = _parse_json_tolerante(resposta)
        except Exception:  # noqa: BLE001 - LLM falhou nesse cenário: conta como divergência
            checagens += 1 + len(meu["por_fase"])
            continue
        # compara: eliminado + percentual por fase (±1pp)
        checagens += 1
        if bool(llm.get("eliminado")) == meu["eliminado"]:
            acertos_comp += 1
        llm_fases = {str(k): v for k, v in (llm.get("por_fase") or {}).items()}
        for f in meu["por_fase"]:
            checagens += 1
            alvo = f["percentual"]
            got = llm_fases.get(f["fase"])
            try:
                if got is not None and abs(float(got) - alvo) <= 1.0:
                    acertos_comp += 1
            except (TypeError, ValueError):
                pass

    similaridade = round(acertos_comp / checagens * 100, 1) if checagens else 0.0
    return {
        "similaridade_pct": similaridade,
        "cenarios": len(cenarios),
        "checagens": checagens,
        "veredito": "o LLM reproduz bem a lógica" if similaridade >= 80
                    else "o LLM diverge da lógica — reveja o modelo/prompt" if similaridade < 50
                    else "o LLM reproduz parcialmente",
    }
