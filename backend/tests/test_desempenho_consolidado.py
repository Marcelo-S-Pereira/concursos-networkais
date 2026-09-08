"""Desempenho consolidado (B5/B6/B7 + gamificação) — agrega dados persistidos.

Cria usuário+prova+simulado no banco de teste, confere as agregações e limpa
pelos ids.
"""

from datetime import UTC, datetime, timedelta

from app.db.models import Exam, Question, SimulationAnswer, SimulationRun, User
from app.db.session import SessionLocal
from app.modules.desempenho.consolidado import (
    dificuldade_por_enfase,
    eficacia_macete,
    gamificacao,
    mastery_consolidado,
)


def test_consolidado_agrega_mastery_dificuldade_e_xp():
    db = SessionLocal()
    u = User(nome="T", email="t_desemp@teste_test.local", cpf_cifrado="x",
             cpf_indice="idx_desemp_test", telefone="x", role="aluno")
    db.add(u)
    db.commit()
    db.refresh(u)

    ex = Exam(banca="x", orgao="x", cargo="__desemp_test__")
    db.add(ex)
    db.commit()
    db.refresh(ex)
    qm = Question(exam_id=ex.id, numero=1, disciplina="Matemática", enunciado="q", gabarito="A")
    qp = Question(exam_id=ex.id, numero=2, disciplina="Português", enunciado="q", gabarito="B")
    db.add_all([qm, qp])
    db.commit()
    db.refresh(qm)
    db.refresh(qp)

    agora = datetime.now(UTC)
    run = SimulationRun(exam_id=ex.id, user_id=u.id, deadline_at=agora + timedelta(minutes=60),
                        duration_seconds=3600, question_count=2, status="finished", finished_at=agora, acertos=1)
    db.add(run)
    db.commit()
    db.refresh(run)
    db.add_all([
        SimulationAnswer(run_id=run.id, question_id=qm.id, letra="A", correta=True),
        SimulationAnswer(run_id=run.id, question_id=qp.id, letra="C", correta=False),
    ])
    db.commit()

    try:
        mastery = {m["enfase"]: m for m in mastery_consolidado(db, u.id)}
        assert mastery["Matemática"]["acertos"] == 1 and mastery["Matemática"]["total"] == 1
        assert mastery["Português"]["acertos"] == 0 and mastery["Português"]["total"] == 1

        dif = {x["enfase"]: x for x in dificuldade_por_enfase(db, u.id)}
        assert dif["Português"]["erro_pct"] == 100.0 and dif["Português"]["dificuldade"] == "difícil"
        assert dif["Matemática"]["erro_pct"] == 0.0 and dif["Matemática"]["dificuldade"] == "fácil"

        g = gamificacao(db, u.id)
        assert g["acertos"] == 1 and g["simulados"] == 1
        assert g["xp"] == 1 * 10 + 1 * 20 + 0 * 5  # 30
        assert g["streak_dias"] == 1  # simulado entregue hoje

        assert eficacia_macete(db, u.id)["com_macete"] == 0
    finally:
        db.delete(run)
        db.delete(ex)   # cascata apaga as questões
        db.delete(u)
        db.commit()
        db.close()
