from app.modules.ingestion.gabarito_parser import parse_respostas
from app.modules.ingestion.prova_parser import parse_prova


def test_gabarito_coluna_alvo():
    # duas provas em colunas: q21 aparece 2x (col0=A, col1=E), q1 só uma vez
    texto = "1 - A 21 - A 21 - E 22 - B 22 - D"
    r0 = parse_respostas(texto, coluna_alvo=0)
    r1 = parse_respostas(texto, coluna_alvo=1)
    assert r0[1] == "A"  # comum
    assert r0[21] == "A" and r1[21] == "E"  # coluna escolhe a prova
    assert r0[22] == "B" and r1[22] == "D"


def test_prova_parser_basico():
    paginas = [
        "1\nQual a capital do Brasil?\n(A) Rio\n(B) Brasília\n(C) SP\n(D) BH\n(E) Salvador\n"
        "2\nQuanto é dois mais dois no conjunto dos naturais?\n(A) 3\n(B) 4\n(C) 5\n(D) 6\n(E) 7\n"
    ]
    qs = parse_prova(paginas, primeira=1, ultima=2)
    assert len(qs) == 2
    assert qs[0].numero == 1 and len(qs[0].alternativas) == 5
    assert qs[1].alternativas["B"] == "4"
    assert all(q.confianca == 1.0 for q in qs)


def test_dehifenizacao():
    paginas = ["1\nutiliza- ção de recur- sos\n(A) a\n(B) b\n(C) c\n(D) d\n(E) e\n"]
    qs = parse_prova(paginas, 1, 1)
    assert "utilização" in qs[0].enunciado and "recursos" in qs[0].enunciado
