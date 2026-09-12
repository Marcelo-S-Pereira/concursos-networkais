"""[115]: Chat de estudo com múltiplos cadernos. O ponto mais sensível: dois
cadernos diferentes podem ter os dois uma "Q1" — sem cuidado, revelar o
gabarito da Q1 de um caderno vazaria (ou pior, mostraria errado) o gabarito
da Q1 do OUTRO caderno também, quebrando a REGRA DE OURO ([087]/[090]:
gabarito só aparece depois que o aluno responde aquela questão específica).
Roda pelas rotas HTTP reais, fixture própria de 2 Exams com número colidindo."""

from fastapi.testclient import TestClient

from app.api.deps import usuario_atual
from app.db.models import ChatMessage, Conversation, CreditTransaction, Exam, Question, RagDocument, User
from app.db.session import SessionLocal
from app.main import app
from app.modules.creditos.carteira import creditar


def _montar():
    db = SessionLocal()
    aluno = User(nome="Aluno 115", email="aluno_115@teste_test.local",
                cpf_cifrado="x", cpf_indice="idx_115", telefone="x", role="aluno")
    db.add(aluno)
    db.commit()
    db.refresh(aluno)
    creditar(db, aluno.id, 50, "ajuste", "teste")

    exam_a = Exam(banca="__t__", orgao="Caderno A", cargo="__115_test__")
    exam_b = Exam(banca="__t__", orgao="Caderno B", cargo="__115_test__")
    db.add_all([exam_a, exam_b])
    db.commit()
    db.refresh(exam_a)
    db.refresh(exam_b)

    # as DUAS Q1, gabaritos DIFERENTES de propósito — se colidir, um dos dois vai vazar errado
    q1a = Question(exam_id=exam_a.id, numero=1, disciplina="Teste", enunciado="Q1 do caderno A", gabarito="A")
    q1b = Question(exam_id=exam_b.id, numero=1, disciplina="Teste", enunciado="Q1 do caderno B", gabarito="E")
    db.add_all([q1a, q1b])
    db.commit()
    db.refresh(q1a)
    db.refresh(q1b)

    ids = {"user_id": aluno.id, "exam_a": exam_a.id, "exam_b": exam_b.id, "q1a": q1a.id, "q1b": q1b.id}
    db.close()
    return ids


def _limpar(ids: dict):
    db = SessionLocal()
    db.query(ChatMessage).filter(
        ChatMessage.conversation_id.in_(
            db.query(Conversation.id).filter(Conversation.user_id == ids["user_id"])
        )
    ).delete(synchronize_session=False)
    db.query(Conversation).filter(Conversation.user_id == ids["user_id"]).delete()
    db.query(Question).filter(Question.id.in_([ids["q1a"], ids["q1b"]])).delete(synchronize_session=False)
    db.query(Exam).filter(Exam.id.in_([ids["exam_a"], ids["exam_b"]])).delete(synchronize_session=False)
    db.query(CreditTransaction).filter(CreditTransaction.user_id == ids["user_id"]).delete()
    db.query(User).filter(User.id == ids["user_id"]).delete()
    db.commit()
    db.close()


def test_responder_q1_do_caderno_a_nao_revela_q1_do_caderno_b():
    ids = _montar()
    user = SessionLocal().get(User, ids["user_id"])
    app.dependency_overrides[usuario_atual] = lambda: user
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/chat/conversas", json={
                "exam_ids": [ids["exam_a"], ids["exam_b"]], "modo": "chat", "titulo": "teste 115",
            })
            assert r.status_code == 201, r.text
            cid = r.json()["id"]
            assert r.json()["exam_ids"] == [ids["exam_a"], ids["exam_b"]]

            from app.modules.chat.chat import _contexto_caderno, _exam_ids_efetivos, _respondidas

            db = SessionLocal()
            conversa = db.get(Conversation, cid)
            exam_ids = _exam_ids_efetivos(conversa)
            assert exam_ids == [ids["exam_a"], ids["exam_b"]]

            # sem nenhuma resposta ainda: nenhum dos dois Q1 revelado
            ctx = _contexto_caderno(db, exam_ids, _respondidas(db, cid, exam_ids))
            assert "Gabarito: A (" not in ctx
            assert "Gabarito: E (" not in ctx

            # aluno responde a Q1 do caderno A (com prefixo, já que são 2 cadernos)
            db.add(ChatMessage(conversation_id=cid, role="user",
                               conteudo=f"Minha resposta da Q{ids['exam_a']}.1: A"))
            db.commit()

            ctx2 = _contexto_caderno(db, exam_ids, _respondidas(db, cid, exam_ids))
            # revelou a do caderno A...
            assert "Gabarito: A (o aluno respondeu A)" in ctx2
            # ...e a do caderno B continua ESCONDIDA — não vazou pela colisão de número
            assert "Gabarito: (NÃO revelado" in ctx2
            assert "Gabarito: E (" not in ctx2
            db.close()
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar(ids)


def test_mensagem_sem_prefixo_com_dois_cadernos_e_ambigua_e_ignorada():
    """Sem prefixo, com 2+ cadernos ativos, não dá pra saber de qual caderno é
    a Q1 — o sistema tem que ERRAR PRO LADO SEGURO (não revelar nada), nunca
    adivinhar."""
    ids = _montar()
    db = SessionLocal()
    from app.modules.chat.chat import _respondidas

    conversa = Conversation(user_id=ids["user_id"], exam_ids=[ids["exam_a"], ids["exam_b"]], modo="chat")
    db.add(conversa)
    db.commit()
    db.refresh(conversa)
    db.add(ChatMessage(conversation_id=conversa.id, role="user", conteudo="Minha resposta da Q1: A"))
    db.commit()

    respondidas = _respondidas(db, conversa.id, [ids["exam_a"], ids["exam_b"]])
    assert respondidas == {}  # ambíguo — nada foi marcado como respondido
    db.query(ChatMessage).filter(ChatMessage.conversation_id == conversa.id).delete()
    db.query(Conversation).filter(Conversation.id == conversa.id).delete()
    db.commit()
    db.close()
    _limpar(ids)


def test_questao_aleatoria_sorteia_do_universo_dos_cadernos_escolhidos():
    ids = _montar()
    user = SessionLocal().get(User, ids["user_id"])
    app.dependency_overrides[usuario_atual] = lambda: user
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/chat/conversas", json={
                "exam_ids": [ids["exam_a"], ids["exam_b"]], "modo": "chat", "titulo": "teste 115 random",
                "modo_questao": "random",
            })
            cid = r.json()["id"]
            r2 = client.post(f"/api/v1/chat/conversas/{cid}/questao-aleatoria")
            assert r2.status_code == 200, r2.text
            assert r2.json()["question_id"] in (ids["q1a"], ids["q1b"])
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar(ids)


def test_random_sem_caderno_da_422_na_criacao():
    ids = _montar()
    user = SessionLocal().get(User, ids["user_id"])
    app.dependency_overrides[usuario_atual] = lambda: user
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/chat/conversas", json={"modo": "chat", "modo_questao": "random"})
            assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar(ids)


def test_rag_doc_ids_filtra_por_uso_chat_nao_uso_tutor():
    """[115]: no modo "chat", só documento uso_chat=true pode ser escolhido —
    um documento marcado só uso_tutor=true tem que ser recusado (silenciosamente
    filtrado, não vira erro — mesmo padrão de [110])."""
    ids = _montar()
    db = SessionLocal()
    doc_chat = RagDocument(titulo="doc chat 115", uso_chat=True, uso_tutor=False, colecao="teste_115")
    doc_tutor = RagDocument(titulo="doc tutor 115", uso_chat=False, uso_tutor=True, colecao="teste_115")
    db.add_all([doc_chat, doc_tutor])
    db.commit()
    db.refresh(doc_chat)
    db.refresh(doc_tutor)
    doc_chat_id, doc_tutor_id = doc_chat.id, doc_tutor.id
    db.close()

    user = SessionLocal().get(User, ids["user_id"])
    app.dependency_overrides[usuario_atual] = lambda: user
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/chat/conversas", json={
                "modo": "chat", "titulo": "teste rag 115", "rag_doc_ids": [doc_chat_id, doc_tutor_id],
            })
            assert r.status_code == 201, r.text
            assert r.json()["rag_doc_ids"] == [doc_chat_id]  # só o uso_chat entrou
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar(ids)
        db = SessionLocal()
        db.query(RagDocument).filter(RagDocument.id.in_([doc_chat_id, doc_tutor_id])).delete(synchronize_session=False)
        db.commit()
        db.close()
