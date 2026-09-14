"""[114]: explicar_questao passa a consultar a Biblioteca classificada
"Simulado" (uso="simulado") — validado com chamada real na sessão, aqui trava
o comportamento rápido com tudo mockado (mesmo padrão de test_youtube.py)."""

import unittest.mock

from app.modules.tutor import tutor


class _QuestaoFake:
    id = 1
    disciplina = "Matemática"
    enunciado = "Quanto é 2+2?"
    gabarito = "A"
    alternativas = []


class _DbFake:
    """Só o suficiente pra `explicar_questao` persistir sem tocar banco de verdade."""
    def add(self, _obj): pass
    def commit(self): pass
    def rollback(self): pass


SISTEMA_FAKE = "SISTEMA-DE-TESTE-EXPLICAR"


def test_explicar_questao_injeta_contexto_da_biblioteca_no_prompt():
    resposta_llm = (
        '{"diagnosis": "ok", "mini_lesson": "ok", '
        '"memory_trick": {"memory_hook": "", "rapid_rule": "", "steps": [], '
        '"applies_when": "", "warning": ""}, "error_type": "NONE", "review_recommendation": ""}'
    )
    prompts_recebidos = []

    def fake_conversar(db, categoria, mensagens, **kw):
        prompts_recebidos.append(mensagens[0]["content"])  # system prompt
        return resposta_llm

    def fake_contexto(db, consulta, uso, **kw):
        assert uso == "simulado"
        return "Trechos de referência da biblioteca: CONTEUDO-MARCADOR-DE-TESTE"

    with unittest.mock.patch("app.modules.tutor.tutor.servico.conversar", fake_conversar), \
         unittest.mock.patch("app.modules.tutor.tutor.contexto_biblioteca", fake_contexto), \
         unittest.mock.patch("app.modules.tutor.tutor.prompts.buscar", return_value=SISTEMA_FAKE), \
         unittest.mock.patch("app.modules.tutor.tutor.resolver.cadeia_para_categoria", return_value=[]):
        tutor.explicar_questao(db=_DbFake(), questao=_QuestaoFake(), user_id=1, student_answer="A")

    assert "CONTEUDO-MARCADOR-DE-TESTE" in prompts_recebidos[0]


def test_explicar_questao_sem_biblioteca_nao_adiciona_nada():
    resposta_llm = (
        '{"diagnosis": "ok", "mini_lesson": "ok", '
        '"memory_trick": {"memory_hook": "", "rapid_rule": "", "steps": [], '
        '"applies_when": "", "warning": ""}, "error_type": "NONE", "review_recommendation": ""}'
    )
    prompts_recebidos = []

    def fake_conversar(db, categoria, mensagens, **kw):
        prompts_recebidos.append(mensagens[0]["content"])
        return resposta_llm

    def fake_contexto(db, consulta, uso, **kw):
        return ""  # nada classificado pra "simulado" — sem trechos

    with unittest.mock.patch("app.modules.tutor.tutor.servico.conversar", fake_conversar), \
         unittest.mock.patch("app.modules.tutor.tutor.contexto_biblioteca", fake_contexto), \
         unittest.mock.patch("app.modules.tutor.tutor.prompts.buscar", return_value=SISTEMA_FAKE), \
         unittest.mock.patch("app.modules.tutor.tutor.resolver.cadeia_para_categoria", return_value=[]):
        tutor.explicar_questao(db=_DbFake(), questao=_QuestaoFake(), user_id=1, student_answer="A")

    assert prompts_recebidos[0] == SISTEMA_FAKE  # sistema intocado, sem bloco extra
