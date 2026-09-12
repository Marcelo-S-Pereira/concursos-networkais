"""Chat de estudo: tutor especialista do caderno. Llama (texto) de cérebro;
MiniMax (visão) lê a figura da questão quando há imagem em foco."""

import base64
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ChatMessage, Conversation, Exam, Question
from app.modules.ai_registry import servico
from app.modules.rag.rag import contexto_biblioteca

FIGURAS_DIR = Path(__file__).resolve().parents[3].parent / "uploads" / "figuras"

SISTEMA = (
    "Você é um TUTOR especialista deste caderno de concurso. Ensine com base no "
    "conteúdo do caderno (questões, alternativas, gabaritos e figuras). Trabalhe UMA "
    "questão de cada vez, sem atropelar.\n\n"
    "REGRA DE OURO: o gabarito de uma questão só aparece pra você DEPOIS que o aluno "
    "responde. Questão marcada como 'Gabarito: (NÃO revelado — aluno ainda não "
    "respondeu)' significa exatamente isso — você não sabe qual é a certa. NUNCA "
    "adivinhe, nunca afirme qual alternativa está certa nesse caso, mesmo que ache que "
    "sabe pelo seu conhecimento geral. Se o aluno pedir para explicar, dar mini-aula, "
    "macete ou gêmeas de uma questão ainda não revelada, peça a ele para responder "
    "primeiro (escolher a letra). Quando o aluno informar a resposta dele (mensagem no "
    "formato 'Minha resposta da Q{n}: {letra}'), a partir DAÍ o gabarito passa a "
    "aparecer pra você — diga se ele acertou ou errou e ofereça continuar.\n\n"
    "Seu repertório, conforme o que o aluno pedir (só depois de revelado o gabarito):\n"
    "- EXPLICAR: por que a alternativa correta é correta e por que cada uma das outras "
    "está errada.\n"
    "- MINI-AULA: o conceito por trás da questão, do começo, curto e com exemplo.\n"
    "- MACETE: um gancho de memória, a regra rápida, os passos, quando usar e quando "
    "NÃO usar.\n"
    "- QUESTÕES GÊMEAS: questões novas que cobram a mesma habilidade em outro contexto.\n"
    "- VÍDEOS: você NÃO navega na internet e NÃO conhece links. Nunca invente URL nem "
    "título de vídeo. Em vez disso, dê de 3 a 5 termos de busca, cada um em uma linha "
    "própria começando exatamente com 'BUSCAR: '. O aluno quer entender A QUESTÃO E A "
    "BANCA, não uma aula genérica do tema — cada termo deve combinar: a banca do caderno "
    "(se aparecer no 'Conteúdo do caderno' abaixo), a disciplina/conceito exato da "
    "questão, e uma palavra que aponte pra resolução de prova ('questão comentada', "
    "'resolução comentada', 'prova comentada', 'gabarito comentado') — nunca só o tema "
    "solto tipo 'aula de física'. O aplicativo transforma cada linha dessas em uma busca "
    "real. Antes deles, diga em uma frase o que o aluno deve procurar aprender.\n\n"
    "Quando houver IMAGEM, use-a para explicar o que está desenhado. Nunca invente "
    "gabarito — o backend é a autoridade; se não souber, diga que não sabe. Escreva em "
    "português do Brasil, claro e direto, sem enrolação."
)

# [109]: Tutor IA — especialista geral (não amarrado a um caderno de questões
# oficial), grounded na biblioteca que o aluno mesmo escolheu (uso="tutor").
SISTEMA_TUTOR = (
    "Você é um TUTOR especialista no assunto que o aluno escolheu estudar. Não está "
    "ligado a um caderno de questões oficial — está ligado ao conteúdo da biblioteca "
    "(trechos de referência, quando houver). Explique cada detalhe com profundidade: o "
    "conceito, a lógica por trás, exemplos práticos, e o que costuma confundir quem "
    "estuda o assunto. Use os trechos de referência quando ajudarem a responder; se não "
    "houver trecho relevante, responda com seu conhecimento geral e diga com clareza que "
    "não há material específico da biblioteca sobre aquele ponto — nunca finja que tem.\n\n"
    "VÍDEOS: você NÃO navega na internet e NÃO conhece links. Nunca invente URL nem "
    "título de vídeo. Em vez disso, dê de 3 a 5 termos de busca, cada um em uma linha "
    "própria começando exatamente com 'BUSCAR: ' — o aplicativo transforma cada linha "
    "dessas em uma busca real de vídeos relevantes. Antes deles, diga em uma frase o que "
    "o aluno deve procurar aprender.\n\n"
    "Quando houver IMAGEM, use-a para explicar o que está desenhado. Escreva em "
    "português do Brasil, claro e direto, sem enrolação."
)
PERSONA_TUTOR = {
    "professor": (
        "Trate o aluno com a didática de um professor — estruturado, preciso, "
        "técnico quando o assunto exigir, mas sempre claro."
    ),
    "amigo": (
        "Trate o aluno como um amigo que entende bem do assunto — tom leve e "
        "direto, sem formalidade excessiva, sem perder a precisão do conteúdo."
    ),
}

# Marcador que o front manda quando o aluno escolhe a resposta no seletor A-E da
# questão em foco. Vira a fonte de verdade de "já respondeu" — derivado do próprio
# histórico da conversa, sem coluna nova no banco.
# [115]: prefixo "Q{exam_id}.{numero}" é opcional — só o front usa quando a
# conversa tem MAIS de um caderno selecionado (número de questão pode colidir
# entre cadernos diferentes); com um caderno só, "Q{numero}" continua igual a
# sempre foi, sem quebrar histórico já persistido.
_RE_RESPOSTA = re.compile(r"^Minha resposta da Q(?:(\d+)\.)?(\d+):\s*([A-E])\s*$", re.I)


def _sem_html(t: str | None) -> str:
    return re.sub(r"<[^>]+>", " ", t or "").replace("&nbsp;", " ").strip()


def _resolver_exam_id(prefixo: str | None, exam_ids: list[int]) -> int | None:
    """Prefixo explícito manda; sem prefixo só é seguro resolver quando a
    conversa tem exatamente 1 caderno — com mais de 1, uma mensagem sem
    prefixo é ambígua e é ignorada (nunca revela gabarito por engano)."""
    if prefixo:
        return int(prefixo)
    return exam_ids[0] if len(exam_ids) == 1 else None


def _respondidas(db: Session, conversation_id: int, exam_ids: list[int]) -> dict[tuple[int, int], str]:
    """{(exam_id, número): letra que o aluno marcou} — só as que ele já
    respondeu NESTA conversa. É isso que decide o que pode aparecer de
    gabarito no contexto — chave por caderno pra não colidir número repetido
    entre cadernos diferentes selecionados juntos."""
    out: dict[tuple[int, int], str] = {}
    textos = db.execute(
        select(ChatMessage.conteudo).where(
            ChatMessage.conversation_id == conversation_id, ChatMessage.role == "user",
        )
    ).scalars()
    for texto in textos:
        m = _RE_RESPOSTA.match((texto or "").strip())
        if not m:
            continue
        eid = _resolver_exam_id(m.group(1), exam_ids)
        if eid is not None:
            out[(eid, int(m.group(2)))] = m.group(3).upper()
    return out


def _exam_ids_efetivos(conversa: Conversation) -> list[int]:
    """[115]: `exam_ids` é a fonte de verdade pra conversas novas; conversas
    antigas só têm `exam_id` (singular) — tratado aqui, não precisou de
    backfill no banco."""
    if conversa.exam_ids:
        return list(conversa.exam_ids)
    return [conversa.exam_id] if conversa.exam_id else []


def _contexto_caderno(
    db: Session, exam_ids: list[int], respondidas: dict[tuple[int, int], str], limite_total: int = 60,
) -> str:
    if not exam_ids:
        return "Sem caderno específico — ajude o aluno no que ele estudar."
    exams = [e for e in (db.get(Exam, eid) for eid in exam_ids) if e]
    if not exams:
        return ""
    limite_por_caderno = max(10, limite_total // len(exams))
    linhas: list[str] = []
    for exam in exams:
        linhas.append(f"Caderno: {exam.orgao} · {exam.cargo} ({exam.banca}{f', {exam.ano}' if exam.ano else ''}).")
        for q in [q for q in exam.questoes if not q.descartada][:limite_por_caderno]:
            enun = _sem_html(q.pergunta or q.enunciado)[:200]
            alts = " | ".join(f"{c.letra}) {_sem_html(c.texto)[:60]}" for c in q.alternativas)
            fig = " [tem figura]" if q.tem_figura else ""
            chave = (exam.id, q.numero)
            if chave in respondidas:
                gab = f"Gabarito: {q.gabarito or '?'} (o aluno respondeu {respondidas[chave]})"
            else:
                gab = "Gabarito: (NÃO revelado — aluno ainda não respondeu)"
            linhas.append(f"Q{q.numero} [{q.disciplina}]: {enun} — {alts} — {gab}{fig}")
    return "\n".join(linhas)


def _figura_b64(db: Session, question_id: int | None) -> str | None:
    if not question_id:
        return None
    q = db.get(Question, question_id)
    if not q or not q.tem_figura:
        return None
    caminho = FIGURAS_DIR / f"exam{q.exam_id}_q{q.numero}.png"
    if not caminho.exists():
        return None
    return base64.b64encode(caminho.read_bytes()).decode()


def responder(db: Session, conversa: Conversation, texto_usuario: str,
              question_id: int | None = None, imagem_b64: str | None = None) -> str:
    exam_ids = _exam_ids_efetivos(conversa)
    # a resposta DESTA mensagem ainda não está no histórico (só é persistida depois que
    # responder() retorna) — mescla aqui para o próprio turno em que o aluno responde já
    # revelar o gabarito, sem esperar a próxima mensagem.
    respondidas = _respondidas(db, conversa.id, exam_ids)
    m = _RE_RESPOSTA.match(texto_usuario.strip())
    if m:
        eid = _resolver_exam_id(m.group(1), exam_ids)
        if eid is not None:
            respondidas[(eid, int(m.group(2)))] = m.group(3).upper()

    # [109]: modo "tutor" (aba Tutor IA) é especialista geral, grounded na
    # biblioteca uso=tutor — sem caderno de questões oficial. Modo "chat"
    # (padrão) segue como sempre: tutor do caderno, biblioteca uso=chat.
    # [115]: modo "chat" agora respeita a escolha de fontes RAG da conversa
    # (antes ignorava `rag_doc_ids` nesse modo — usava sempre TODOS os
    # documentos uso_chat=true, sem filtro nenhum).
    if conversa.modo == "tutor":
        sistema = SISTEMA_TUTOR + "\n\n" + PERSONA_TUTOR.get(conversa.persona, PERSONA_TUTOR["professor"])
        biblioteca = contexto_biblioteca(db, texto_usuario, uso="tutor", doc_ids=conversa.rag_doc_ids or None)
    else:
        sistema = SISTEMA + "\n\nConteúdo do caderno:\n" + _contexto_caderno(db, exam_ids, respondidas)
        biblioteca = contexto_biblioteca(db, texto_usuario, uso="chat", doc_ids=conversa.rag_doc_ids or None)
    # [108]: motor de biblioteca — best-effort, "" quando não há nada relevante.
    if biblioteca:
        sistema += "\n\n" + biblioteca
    historico = [
        {"role": m.role, "content": m.conteudo}
        for m in db.execute(
            select(ChatMessage).where(ChatMessage.conversation_id == conversa.id).order_by(ChatMessage.id)
        ).scalars()
    ][-20:]

    # imagem anexada pelo aluno tem prioridade sobre a figura da questão em foco
    img = imagem_b64 or _figura_b64(db, question_id)
    if img:
        conteudo = [
            {"type": "text", "text": texto_usuario},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}},
        ]
        mensagens = [{"role": "system", "content": sistema}, *historico, {"role": "user", "content": conteudo}]
        return servico.conversar(db, "visao", mensagens, origem="chat_visao", max_tokens=1200,
                                 user_id=conversa.user_id, connection_id=conversa.modelo_visao_id)

    mensagens = [{"role": "system", "content": sistema}, *historico, {"role": "user", "content": texto_usuario}]
    return servico.conversar(db, "texto", mensagens, origem="chat_texto", max_tokens=1200,
                             user_id=conversa.user_id, connection_id=conversa.modelo_texto_id)


def transcrever_pergunta(db: Session, conversa: Conversation, audio_bytes: bytes, nome_arquivo: str) -> dict:
    """Só o STT — separado de responder_e_falar() para a rota poder checar o
    crédito (cobrado por TEMPO real de fala) ANTES de gastar com LLM+TTS, que
    são bem mais caros que a transcrição."""
    return servico.transcrever_audio(
        db, audio_bytes, nome_arquivo, origem="chat_stt", user_id=conversa.user_id,
        connection_id=conversa.modelo_transcricao_id,
    )


def responder_e_falar(db: Session, conversa: Conversation, texto_usuario: str,
                      question_id: int | None = None) -> dict:
    """Responde pelo MESMO pipeline de texto (mesmo gate de gabarito, mesmo
    ramo de visão quando a questão tem figura) e fala a resposta (TTS)."""
    resposta = responder(db, conversa, texto_usuario, question_id)
    audio_resposta = servico.falar_texto(
        db, resposta, origem="chat_tts", user_id=conversa.user_id, connection_id=conversa.modelo_voz_id,
    )
    return {"resposta": resposta, "audio_b64": base64.b64encode(audio_resposta).decode()}
