"""[153]: resposta dada no Chat de estudos precisa virar `ChatAnswer`
estruturada e entrar em Mastery/Dificuldade/XP (via `_respostas()`) e na
fila de Revisão (`ReviewSchedule.origem="chat"`) — antes disso só
`SimulationAnswer` entrava nessas contas."""

from app.db.models import ChatAnswer, Conversation, Exam, Question, ReviewSchedule, User
from app.db.session import SessionLocal
from app.modules.chat.chat import _persistir_resposta_chat
from app.modules.desempenho.consolidado import dificuldade_por_enfase, mastery_consolidado


def test_resposta_do_chat_entra_em_mastery_dificuldade_e_agenda_revisao_como_chat():
    db = SessionLocal()
    u = User(nome="T", email="t_chatstats@teste_test.local", cpf_cifrado="x",
             cpf_indice="idx_chatstats_test", telefone="x", role="aluno")
    db.add(u)
    db.commit()
    db.refresh(u)

    ex = Exam(banca="x", orgao="x", cargo="__chatstats_test__")
    db.add(ex)
    db.commit()
    db.refresh(ex)
    q_certa = Question(exam_id=ex.id, numero=1, disciplina="Matemática", enunciado="q", gabarito="A")
    q_errada = Question(exam_id=ex.id, numero=2, disciplina="Português", enunciado="q", gabarito="B")
    db.add_all([q_certa, q_errada])
    db.commit()
    db.refresh(q_certa)
    db.refresh(q_errada)

    conv = Conversation(user_id=u.id, exam_ids=[ex.id], modo="chat")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    try:
        _persistir_resposta_chat(db, conv, ex.id, 1, "A")  # acerta
        _persistir_resposta_chat(db, conv, ex.id, 2, "C")  # erra

        respostas = db.query(ChatAnswer).filter(ChatAnswer.conversation_id == conv.id).all()
        assert len(respostas) == 2
        certa = next(r for r in respostas if r.question_id == q_certa.id)
        errada = next(r for r in respostas if r.question_id == q_errada.id)
        assert certa.correta is True
        assert errada.correta is False

        mastery = {m["enfase"]: m for m in mastery_consolidado(db, u.id)}
        assert mastery["Matemática"]["acertos"] == 1 and mastery["Matemática"]["total"] == 1
        assert mastery["Português"]["acertos"] == 0 and mastery["Português"]["total"] == 1

        dif = {x["enfase"]: x for x in dificuldade_por_enfase(db, u.id)}
        assert dif["Português"]["dificuldade"] == "difícil"

        # errar no chat agenda a revisão com origem="chat" — a certa não agenda nada
        rev = db.query(ReviewSchedule).filter(
            ReviewSchedule.user_id == u.id, ReviewSchedule.question_id == q_errada.id
        ).one_or_none()
        assert rev is not None and rev.origem == "chat"
        assert db.query(ReviewSchedule).filter(
            ReviewSchedule.user_id == u.id, ReviewSchedule.question_id == q_certa.id
        ).one_or_none() is None
    finally:
        db.query(ChatAnswer).filter(ChatAnswer.conversation_id == conv.id).delete()
        db.query(ReviewSchedule).filter(ReviewSchedule.user_id == u.id).delete()
        db.delete(conv)
        db.delete(ex)  # cascata apaga as questões
        db.delete(u)
        db.commit()
        db.close()
