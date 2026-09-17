"""Chat de estudo: tutor especialista do caderno. Llama (texto) de cérebro;
MiniMax (visão) lê a figura da questão quando há imagem em foco."""

import base64
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ChatAnswer, ChatMessage, Conversation, Exam, Question, RagDocument
from app.modules.ai_registry import servico
from app.modules.desempenho.revisao import agendar_erro
from app.modules.prompts import prompts
from app.modules.rag.rag import contexto_biblioteca

FIGURAS_DIR = Path(__file__).resolve().parents[3].parent / "uploads" / "figuras"
# [133]: entrega por URL real (uploads/audio_chat/ + GET /chat/audio/{nome})
# foi REVERTIDA — achado real em produção: a Cloudflare (proxy laranja do
# domínio) cacheava a resposta por ter extensão .mp3 e `Cache-Control:
# max-age`, e o cache dela NÃO respeita cookie de sessão por padrão — uma
# requisição SEM cookie nenhum recebeu `cf-cache-status: HIT` e os MESMOS
# bytes de áudio de uma conversa privada. Ou seja, o `Depends(usuario_atual)`
# da rota nunca chegava a rodar pra quem pegasse a URL depois do 1º acesso —
# vazamento real de conteúdo de conversa. Voltou pra `audio_b64` (o que já
# funcionava no celular) até esse problema de cache ser resolvido de verdade
# (ex.: `Cache-Control: private, no-store` na resposta, e mesmo assim raciocinar
# se a CDN reconhece esse header pra rotas autenticadas).

# [125]: o texto dos prompts abaixo (chat_sistema/chat_sistema_tutor/
# chat_persona_professor/chat_persona_amigo) mora na tabela `prompts`, não
# mais aqui — `prompts.buscar(db, chave)` é a única forma de obtê-los.


def _material_selecionado(db: Session, conversa: Conversation) -> str:
    """[123]: injeta o QUE está carregado nesta conversa do Tutor de forma
    INCONDICIONAL — não depende de busca semântica pela mensagem do aluno
    (que falha pra saudação/pedido genérico). Usa a `descricao` já gerada na
    ingestão ([108]) como resumo do material. Best-effort: nunca lança."""
    if conversa.modo != "tutor" or not conversa.rag_doc_ids:
        return ""
    try:
        docs = db.execute(
            select(RagDocument).where(RagDocument.id.in_(conversa.rag_doc_ids))
        ).scalars().all()
    except Exception:  # noqa: BLE001 — apoio opcional, nunca derruba a resposta
        return ""
    if not docs:
        return ""
    linhas = [
        f"- \"{d.titulo}\": {d.descricao}" if d.descricao else f"- \"{d.titulo}\" (ainda sem resumo)"
        for d in docs
    ]
    return "MATERIAL DESTA CONVERSA (selecionado pelo aluno):\n" + "\n".join(linhas)

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


def _persistir_resposta_chat(db: Session, conversa: Conversation, exam_id: int, numero: int, letra: str) -> None:
    """[153]: resposta real dada no Chat vira `ChatAnswer` estruturada — até
    aqui só existia como texto solto em `ChatMessage`, e por isso nunca
    entrava em Mastery/Dificuldade/Revisão (só `SimulationAnswer` entrava).
    Errar aqui agenda a questão pra revisão, com origem="chat" — mesmo
    caminho que o simulado já usa ([045]), só com o rótulo certo. Best-effort
    de propósito: sem a questão cadastrada (caderno apagado etc.), não trava
    a resposta do chat por causa de estatística."""
    q = db.execute(
        select(Question).where(Question.exam_id == exam_id, Question.numero == numero)
    ).scalar_one_or_none()
    if not q:
        return
    correta = letra.upper() == (q.gabarito or "").upper()
    db.add(ChatAnswer(
        user_id=conversa.user_id, conversation_id=conversa.id, question_id=q.id,
        letra=letra.upper(), correta=correta,
    ))
    if not correta:
        agendar_erro(db, conversa.user_id, q.id, origem="chat")
    db.commit()


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
              question_id: int | None = None, imagem_b64: str | None = None, falado: bool = False) -> str:
    exam_ids = _exam_ids_efetivos(conversa)
    # a resposta DESTA mensagem ainda não está no histórico (só é persistida depois que
    # responder() retorna) — mescla aqui para o próprio turno em que o aluno responde já
    # revelar o gabarito, sem esperar a próxima mensagem.
    respondidas = _respondidas(db, conversa.id, exam_ids)
    m = _RE_RESPOSTA.match(texto_usuario.strip())
    if m:
        eid = _resolver_exam_id(m.group(1), exam_ids)
        if eid is not None:
            numero = int(m.group(2))
            letra = m.group(3).upper()
            respondidas[(eid, numero)] = letra
            # [153]: persiste como ChatAnswer só na 1ª vez que esta resposta é
            # processada — chega aqui exatamente 1 vez por turno real (nunca
            # via a varredura de histórico acima, que é só leitura).
            _persistir_resposta_chat(db, conversa, eid, numero, letra)

    # [109]: modo "tutor" (aba Tutor IA) é especialista geral, grounded na
    # biblioteca uso=tutor — sem caderno de questões oficial. Modo "chat"
    # (padrão) segue como sempre: tutor do caderno, biblioteca uso=chat.
    # [115]: modo "chat" agora respeita a escolha de fontes RAG da conversa
    # (antes ignorava `rag_doc_ids` nesse modo — usava sempre TODOS os
    # documentos uso_chat=true, sem filtro nenhum).
    if conversa.modo == "tutor":
        persona_chave = "chat_persona_amigo" if conversa.persona == "amigo" else "chat_persona_professor"
        sistema = prompts.buscar(db, "chat_sistema_tutor") + "\n\n" + prompts.buscar(db, persona_chave)
        material = _material_selecionado(db, conversa)
        if material:
            sistema += "\n\n" + material
        # k maior que o padrão (4): o pedido foi "saber tudo sobre o arquivo" —
        # com poucos documentos selecionados, uma busca mais generosa cobre
        # bem mais do conteúdo real por pergunta.
        biblioteca = contexto_biblioteca(db, texto_usuario, uso="tutor", k=8, doc_ids=conversa.rag_doc_ids or None)
    else:
        sistema = (prompts.buscar(db, "chat_sistema") + "\n\nConteúdo do caderno:\n"
                   + _contexto_caderno(db, exam_ids, respondidas))
        biblioteca = contexto_biblioteca(db, texto_usuario, uso="chat", doc_ids=conversa.rag_doc_ids or None)
    # [108]: motor de biblioteca — best-effort, "" quando não há nada relevante.
    if biblioteca:
        sistema += "\n\n" + biblioteca
    # [132]: quando a resposta vai ser falada (TTS), o LLM precisa saber disso
    # — sem isto ele nega ter "ouvido" a pergunta (que já chegou transcrita) e
    # nega poder "falar" a resposta, mesmo ambas as coisas acontecendo de
    # verdade fora do alcance dele.
    if falado:
        sistema += "\n\n" + prompts.buscar(db, "chat_modo_voz_addendum")
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
    ramo de visão quando a questão tem figura) e fala a resposta (TTS).

    `falado=True` avisa o LLM que esta resposta vai ser falada (ver
    `chat_modo_voz_addendum`, [133]). `audio_b64` — [133] tentou trocar por
    URL servida e revertou por achado de vazamento via cache da CDN."""
    resposta = responder(db, conversa, texto_usuario, question_id, falado=True)
    audio_resposta = servico.falar_texto(
        db, resposta, origem="chat_tts", user_id=conversa.user_id, connection_id=conversa.modelo_voz_id,
        voz=conversa.voz_escolhida,  # [151]: voz do Kokoro escolhida pelo aluno; None = padrão
    )
    return {"resposta": resposta, "audio_b64": base64.b64encode(audio_resposta).decode()}
