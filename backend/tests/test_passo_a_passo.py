"""[117]: Tutor por voz guiado — gera os passos narrados e fala cada um.
Mockado (sem custo de API a cada pytest); a geração real (7-8 passos
coerentes) e a síntese de voz real já foram validadas manualmente na sessão."""

import unittest.mock

from fastapi.testclient import TestClient

from app.api.deps import usuario_atual
from app.db.models import CreditTransaction, Exam, Question, User
from app.db.session import SessionLocal
from app.main import app
from app.modules.creditos.carteira import creditar
from app.modules.tutor import tutor


def _usuario_com_credito(sufixo: str) -> User:
    db = SessionLocal()
    u = User(nome="Teste 117", email=f"t_117_{sufixo}@teste_test.local", cpf_cifrado="x",
             cpf_indice=f"idx_117_{sufixo}", telefone="x", role="aluno")
    db.add(u)
    db.commit()
    db.refresh(u)
    creditar(db, u.id, 50, "ajuste", "teste")
    db.close()
    return u


def _limpar(uid: int, exam_id: int | None = None) -> None:
    db = SessionLocal()
    if exam_id:
        db.query(Question).filter(Question.exam_id == exam_id).delete()
        db.query(Exam).filter(Exam.id == exam_id).delete()
    db.query(CreditTransaction).filter(CreditTransaction.user_id == uid).delete()
    db.query(User).filter(User.id == uid).delete()
    db.commit()
    db.close()


def test_gerar_passo_a_passo_parseia_lista_e_limita_a_10():
    resposta_llm = '{"passos": ' + str([f"passo {i}" for i in range(15)]).replace("'", '"') + "}"

    class _QFake:
        id = 1
        disciplina = "Matemática"
        enunciado = "Quanto é 2+2?"
        gabarito = "A"
        alternativas = []

    with unittest.mock.patch.object(tutor.servico, "conversar", return_value=resposta_llm):
        passos = tutor.gerar_passo_a_passo(db=None, questao=_QFake(), user_id=1)
    assert len(passos) == 10  # teto de segurança
    assert passos[0] == "passo 0"


def test_gerar_passo_a_passo_resposta_vazia_da_fallback_honesto():
    class _QFake:
        id = 1
        disciplina = "Matemática"
        enunciado = "x"
        gabarito = "A"
        alternativas = []

    with unittest.mock.patch.object(tutor.servico, "conversar", return_value='{"passos": []}'):
        passos = tutor.gerar_passo_a_passo(db=None, questao=_QFake(), user_id=1)
    assert len(passos) == 1
    assert "não consegui" in passos[0].lower()


def test_rota_passo_a_passo_sem_credito_da_402():
    u = _usuario_com_credito("sem_credito")
    db = SessionLocal()
    db.query(CreditTransaction).filter(CreditTransaction.user_id == u.id).delete()  # zera o crédito de propósito
    db.commit()
    db.close()
    app.dependency_overrides[usuario_atual] = lambda: u
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/exames/questoes/1/passo-a-passo", json={})
        assert r.status_code == 402
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar(u.id)


def test_rota_passo_a_passo_ponta_a_ponta_mockada():
    u = _usuario_com_credito("ok")
    db = SessionLocal()
    ex = Exam(banca="__t__", orgao="__117_test__", cargo="__117_test__")
    db.add(ex)
    db.commit()
    db.refresh(ex)
    q = Question(exam_id=ex.id, numero=1, disciplina="Teste", enunciado="Quanto é 2+2?", gabarito="A")
    db.add(q)
    db.commit()
    db.refresh(q)
    exam_id, qid = ex.id, q.id
    db.close()

    app.dependency_overrides[usuario_atual] = lambda: SessionLocal().get(User, u.id)
    try:
        with unittest.mock.patch.object(tutor.servico, "conversar",
                                        return_value='{"passos": ["Primeiro passo.", "Segundo passo."]}'), \
             TestClient(app) as client:
            r = client.post(f"/api/v1/exames/questoes/{qid}/passo-a-passo", json={"student_answer": "A"})
        assert r.status_code == 200, r.text
        assert r.json()["passos"] == ["Primeiro passo.", "Segundo passo."]
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar(u.id, exam_id)


def test_rota_falar_passo_devolve_audio_e_recusa_texto_vazio():
    u = _usuario_com_credito("falar")
    app.dependency_overrides[usuario_atual] = lambda: SessionLocal().get(User, u.id)
    try:
        with unittest.mock.patch("app.modules.ai_registry.servico.falar_texto", return_value=b"audio-fake-bytes"), \
             TestClient(app) as client:
            r = client.post("/api/v1/exames/questoes/1/passo-a-passo/falar", json={"texto": "Primeiro passo."})
            assert r.status_code == 200, r.text
            import base64
            assert base64.b64decode(r.json()["audio_b64"]) == b"audio-fake-bytes"

            r2 = client.post("/api/v1/exames/questoes/1/passo-a-passo/falar", json={"texto": "   "})
            assert r2.status_code == 422
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar(u.id)
