"""[103]/[104]: a porta diária ([099]) tem que cobrir TODA rota de simulado/
chat/tutor, não só as ações "caras". Achado real do usuário: uma conta com 0
crédito conseguia corrigir simulado (modo treino), pedir explicação/gêmeas do
tutor, EXPANDIR um caderno pra ler as questões, e CRIAR conversa no chat, tudo
sem nunca passar pela porta. Ver quais cadernos existem (`GET /exames`) e ver
que o Chat existe continuam livres — é só navegação. Roda pelas rotas HTTP
reais.
"""

from fastapi.testclient import TestClient

from app.api.deps import usuario_atual
from app.db.models import Conversation, CreditTransaction, Exam, Question, User
from app.db.session import SessionLocal
from app.main import app


def test_sem_credito_nao_corrige_nem_pede_tutor_com_credito_funciona():
    db = SessionLocal()
    aluno = User(
        nome="Aluno Teste 103", email="aluno_porta_103@teste_test.local",
        cpf_cifrado="x", cpf_indice="idx_porta_103", telefone="x", role="aluno",
    )
    db.add(aluno)
    db.commit()
    db.refresh(aluno)
    uid = aluno.id

    ex = Exam(banca="__t__", orgao="__t__", cargo="__porta_103_test__")
    db.add(ex)
    db.commit()
    db.refresh(ex)
    q = Question(exam_id=ex.id, numero=1, disciplina="Teste", enunciado="x", gabarito="A")
    db.add(q)
    db.commit()
    db.refresh(q)
    exam_id, qid = ex.id, q.id
    db.close()

    app.dependency_overrides[usuario_atual] = lambda: SessionLocal().get(User, uid)

    try:
        with TestClient(app) as client:
            # ver quais cadernos existem continua livre (é só navegação)
            r0 = client.get("/api/v1/exames")
            assert r0.status_code == 200, r0.text

            # sem crédito: as 5 rotas recusam com 402 — nenhuma faz o trabalho
            r1 = client.post(f"/api/v1/exames/{exam_id}/corrigir", json={"respostas": {}})
            assert r1.status_code == 402, r1.text

            r2 = client.post(f"/api/v1/exames/questoes/{qid}/explicar", json={})
            assert r2.status_code == 402, r2.text

            r3 = client.post(f"/api/v1/exames/questoes/{qid}/gemeas")
            assert r3.status_code == 402, r3.text

            r5 = client.get(f"/api/v1/exames/{exam_id}/questoes")
            assert r5.status_code == 402, r5.text

            r6 = client.post("/api/v1/chat/conversas", json={"exam_id": None, "titulo": "t"})
            assert r6.status_code == 402, r6.text

            # credita o suficiente para abrir a porta hoje
            db2 = SessionLocal()
            db2.add(CreditTransaction(user_id=uid, delta=50, tipo="bonus", descricao="teste"))
            db2.commit()
            db2.close()

            # agora tudo funciona (a porta abriu e não cobra de novo)
            r7 = client.post(f"/api/v1/exames/{exam_id}/corrigir", json={"respostas": {}})
            assert r7.status_code == 200, r7.text
            r8 = client.get(f"/api/v1/exames/{exam_id}/questoes")
            assert r8.status_code == 200, r8.text
            r9 = client.post("/api/v1/chat/conversas", json={"exam_id": None, "titulo": "t"})
            assert r9.status_code == 201, r9.text
    finally:
        app.dependency_overrides.clear()
        db = SessionLocal()
        db.query(Conversation).filter(Conversation.user_id == uid).delete()
        db.query(CreditTransaction).filter(CreditTransaction.user_id == uid).delete()
        db.query(Question).filter(Question.exam_id == exam_id).delete()
        db.query(Exam).filter(Exam.id == exam_id).delete()
        db.query(User).filter(User.id == uid).delete()
        db.commit()
        db.close()
