"""Cartões de questão/gêmea impressos no chat, sem chamar IA nenhuma.

Regra de segurança: o TEXTO é sempre montado aqui, no servidor, a partir da
`Question`/`TwinQuestion` real — nunca aceita texto livre do cliente. Isso
fecha a brecha de alguém poluir o histórico da própria conversa com uma
mensagem "assistant" falsa (que entraria no contexto enviado ao LLM depois).
"""

from app.db.models import Question, TwinQuestion
from app.modules.chat.chat import _sem_html


def texto_questao(q: Question) -> str:
    """Mesma regra do Caderno no simulado: imagem se `modo_exibicao=="imagem"`
    E tem figura, senão texto (enunciado + col2 + pergunta)."""
    linhas = [f"📖 Q{q.numero} · {q.disciplina}", ""]
    if q.modo_exibicao == "imagem" and q.tem_figura:
        linhas.append(f"FIGURA:{q.id}")
        legenda = _sem_html(q.pergunta) or _sem_html(q.enunciado)
        if legenda:
            linhas.append(legenda)
    else:
        for campo in (q.enunciado, q.enunciado_col2, q.pergunta):
            texto = _sem_html(campo)
            if texto:
                linhas.append(texto)
    linhas.append("")
    for c in q.alternativas:
        linhas.append(f"{c.letra}) {_sem_html(c.texto)}")
    linhas.append("")
    linhas.append("Toque numa letra abaixo para responder.")
    return "\n".join(linhas)


def texto_gemea(tw: TwinQuestion, ordem: str) -> str:
    """Gêmea é sempre texto — a IA que a criou não desenha figura."""
    linhas = [f"👯 Questão gêmea {ordem} — mesma habilidade, contexto novo", "", tw.enunciado.strip(), ""]
    for letra, texto in sorted(tw.alternativas.items()):
        linhas.append(f"{letra}) {texto}")
    linhas.append("")
    linhas.append("Toque numa letra abaixo para responder.")
    return "\n".join(linhas)


def texto_correcao_gemea(tw: TwinQuestion, letra_aluno: str, acertou: bool) -> str:
    if acertou:
        return f"✅ Acertou — {letra_aluno} está correta."
    return f"❌ Errou — você marcou {letra_aluno}, a correta é {tw.gabarito}."


_MASTERY_PT = {
    "STRONG": "forte", "CONSISTENT": "consistente", "UNSTABLE": "instável",
    "WEAK": "fraco", "NOT_TESTED": "sem dados",
}


def texto_fechamento(disciplina: str, principal_ok: bool, gemea_a_ok: bool, gemea_b_ok: bool,
                     mastery: dict | None) -> str:
    """Resumo do ciclo (principal + 2 gêmeas). Mastery vem de
    `mastery_consolidado` — só soma respostas de SIMULADO real, nunca deste
    chat; sem amostra suficiente, diz isso, nunca inventa percentual (spec §19)."""
    acertos_gemeas = int(gemea_a_ok) + int(gemea_b_ok)
    linhas = [
        "🏁 Fechamento", "",
        f"Principal: {'✅ acertou' if principal_ok else '❌ errou'}",
        f"Gêmeas: {acertos_gemeas}/2",
        "",
    ]
    if mastery and mastery.get("amostra", 0) >= 3:
        rotulo = _MASTERY_PT.get(mastery["mastery"], mastery["mastery"])
        linhas.append(
            f"Mastery em {disciplina} (histórico de simulados): "
            f"{mastery['acertos']}/{mastery['total']} ({mastery['percentual']:.0f}%) — {rotulo}."
        )
    else:
        linhas.append(f"Mastery em {disciplina}: ainda sem simulados suficientes pra calcular (mínimo 3).")
    linhas.append("")
    if not principal_ok or acertos_gemeas < 2:
        # A revisão espaçada real (spec §17) só é agendada a partir do SIMULADO
        # ([045], simulado.py) — o chat não agenda nada, então não afirmo isso aqui.
        linhas.append("Vale revisar este tema — ele ainda não está consistente.")
    return "\n".join(linhas)
