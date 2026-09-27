"""[171]: embeddings locais + indexador em segundo plano + busca por modelo.

O que pode dar errado de verdade: prefixo do modelo errado (piora a busca sem dar
erro), vetores de modelos diferentes misturados na mesma busca, e indexação que
regrava trecho idêntico ou deixa o documento "em análise" para sempre."""

import numpy as np
from fastapi.testclient import TestClient

from app.api.deps import apenas_superadmin
from app.db.models import RagChunk, RagDocument, User
from app.db.session import SessionLocal
from app.main import app
from app.modules.ai_registry import cliente, embeddings_locais
from app.modules.ai_registry.servico import prefixar_embedding
from app.modules.rag import indexador, rag

DIM = 1024


def _vetor(x: float) -> list[float]:
    v = [0.0] * DIM
    v[0] = x
    v[1] = 1.0
    return v


def test_prefixo_depende_do_modelo():
    assert prefixar_embedding("intfloat/multilingual-e5-large-instruct", "passagem", "oi") == "passage: oi"
    assert prefixar_embedding("intfloat/multilingual-e5-large-instruct", "consulta", "oi").startswith("Instruct:")
    assert prefixar_embedding("Xenova/multilingual-e5-base", "consulta", "oi") == "query: oi"
    # bge-m3 e modelos de API sem prefixo próprio: o texto vai como veio
    assert prefixar_embedding("Xenova/bge-m3", "passagem", "oi") == "oi"
    assert prefixar_embedding("text-embedding-3-small", "consulta", "oi") == "oi"


class _TokFalso:
    def encode_batch(self, frases):
        class _E:
            def __init__(self, t):
                n = len(t)
                self.ids = list(range(1, n + 1)) + [0] * (6 - n)
                self.attention_mask = [1] * n + [0] * (6 - n)
        return [_E(f) for f in frases]


class _SessFalsa:
    def run(self, _saidas, entrada):
        ids = entrada["input_ids"]
        # 1 vetor "oculto" por posição: o do token CLS diferencia as frases pelo tamanho
        oculto = np.zeros((ids.shape[0], ids.shape[1], 4), dtype=np.float32)
        for i, linha in enumerate(ids):
            oculto[i, 0] = [float((linha > 0).sum()), 1.0, 0.0, 0.0]
        return [oculto]


def _motor_falso() -> embeddings_locais._Motor:
    m = embeddings_locais._Motor.__new__(embeddings_locais._Motor)
    m.pooling, m.tok, m.sess, m.entradas = "cls", _TokFalso(), _SessFalsa(), {"input_ids", "attention_mask"}
    return m


def test_motor_local_devolve_na_ordem_original_e_normalizado():
    textos = ["abcd", "a", "abc"]  # fora de ordem de tamanho de propósito
    vetores, tokens = _motor_falso().embed(textos)
    assert tokens == 4 + 1 + 3
    for v in vetores:
        assert abs(np.linalg.norm(v) - 1.0) < 1e-5
    # o vetor de "a" (tamanho 1) é o mais inclinado para o eixo 1; o de "abcd" o menos
    assert vetores[1][1] > vetores[2][1] > vetores[0][1]


def test_chamar_embeddings_local_nao_chama_rede(monkeypatch):
    monkeypatch.setattr(embeddings_locais, "embed", lambda repo, textos: ([[0.1] * 3 for _ in textos], 7))

    class _Conn:
        endpoint, modelo, nome = "local://runtime", "Xenova/bge-m3", "local"

    vetores, usage = cliente.chamar_embeddings(_Conn(), ["a", "b"])
    assert len(vetores) == 2 and usage["total_tokens"] == 7


def test_modelo_local_ausente_vira_erro_claro(monkeypatch):
    monkeypatch.setattr(embeddings_locais, "disponivel", lambda repo: False)
    embeddings_locais._motores.pop("Xenova/inexistente", None)

    class _Conn:
        endpoint, modelo, nome = "local://runtime", "Xenova/inexistente", "local"

    try:
        cliente.chamar_embeddings(_Conn(), ["a"])
        raise AssertionError("devia ter falhado")
    except cliente.AiCallError as e:
        assert "não está na ambiente de execucao" in str(e)


def _doc(db, titulo, textos, tag=None, vetor=None):
    d = RagDocument(titulo=titulo, colecao="__t171__", chunk_count=len(textos))
    db.add(d)
    db.flush()
    for i, t in enumerate(textos):
        db.add(RagChunk(document_id=d.id, colecao="__t171__", chunk_index=i, conteudo=t,
                        embedding=vetor, embedding_modelo=tag))
    db.commit()
    return d.id


def _limpar(*ids):
    db = SessionLocal()
    for i in ids:
        d = db.get(RagDocument, i)
        if d:
            db.delete(d)
    db.commit()
    db.close()


def test_indexador_pula_duplicado_processa_menor_primeiro_e_fecha_documento(monkeypatch):
    chamadas: list[list[str]] = []

    def falso(db, textos, **kw):
        assert kw["somente_primeira"] is True and kw["tipo"] == "passagem"
        chamadas.append(list(textos))
        return [_vetor(float(len(t))) for t in textos], "M"

    monkeypatch.setattr(indexador, "gerar_embeddings", falso)
    db = SessionLocal()
    grande = _doc(db, "grande", ["A", "BB", "A", "CCC", "DDDD"])
    pequeno = _doc(db, "pequeno", ["BB"])
    try:
        tentou: set[int] = set()
        while indexador.processar_um_lote(db, "M", tentou):
            pass
        # o menor vai primeiro; "BB" já tem vetor quando o grande chega, e "A" repetido conta uma vez
        assert [t for lote in chamadas for t in lote] == ["BB", "A", "CCC", "DDDD"]
        db.expire_all()
        for i in (grande, pequeno):
            d = db.get(RagDocument, i)
            assert d.indexado_em is not None and d.erro is None
            assert d.tentativas_indexacao == 1
            assert all(c.embedding_modelo == "M" and c.embedding is not None for c in d.chunks)
    finally:
        db.close()
        _limpar(grande, pequeno)


def test_indexador_refaz_so_o_que_e_de_outro_modelo(monkeypatch):
    chamadas: list[list[str]] = []
    monkeypatch.setattr(
        indexador, "gerar_embeddings",
        lambda db, textos, **kw: (chamadas.append(list(textos)) or [_vetor(1.0) for _ in textos], "M"),
    )
    db = SessionLocal()
    velho = _doc(db, "velho", ["x", "y"], tag="modelo-antigo", vetor=_vetor(9.0))
    novo = _doc(db, "novo", ["z"], tag="M", vetor=_vetor(2.0))
    try:
        tentou: set[int] = set()
        while indexador.processar_um_lote(db, "M", tentou):
            pass
        assert sorted(t for lote in chamadas for t in lote) == ["x", "y"], "o trecho já em M não pode ser refeito"
        prog = indexador.progresso(db, "M")
        assert prog[velho] == 2 and prog[novo] == 1
    finally:
        db.close()
        _limpar(velho, novo)


def test_busca_ignora_vetor_de_outro_modelo(monkeypatch):
    # a consulta se parece MAIS com o vetor do modelo antigo — mas ele não pode entrar
    monkeypatch.setattr(rag, "gerar_embeddings", lambda db, textos, **kw: ([_vetor(5.0)], "M"))
    db = SessionLocal()
    certo = _doc(db, "certo", ["texto do modelo atual"], tag="M", vetor=_vetor(1.0))
    errado = _doc(db, "errado", ["texto do modelo antigo"], tag="antigo", vetor=_vetor(5.0))
    try:
        achados = rag.buscar(db, "qualquer", colecao="__t171__", k=5)
        assert [a["conteudo"] for a in achados] == ["texto do modelo atual"]
    finally:
        db.close()
        _limpar(certo, errado)


def test_reindexar_so_recoloca_na_fila_e_listagem_mostra_progresso():
    app.dependency_overrides[apenas_superadmin] = lambda: User(id=1, nome="A", email="a@t171.local", role="superadmin")
    db = SessionLocal()
    doc_id = _doc(db, "fila", ["a", "b"], tag="antigo", vetor=_vetor(1.0))
    d = db.get(RagDocument, doc_id)
    from datetime import UTC, datetime
    d.indexado_em, d.erro = datetime.now(UTC), "falhou antes"
    db.commit()
    db.close()
    try:
        with TestClient(app) as client:
            r = client.post(f"/api/v1/rag/documentos/{doc_id}/reindexar")
            assert r.status_code == 200, r.text
            assert r.json()["indexado"] is False and r.json()["erro"] is None
            lista = client.get("/api/v1/rag/documentos").json()
            mine = next(x for x in lista if x["id"] == doc_id)
            assert mine["chunk_count"] == 2 and "chunks_prontos" in mine
    finally:
        app.dependency_overrides.pop(apenas_superadmin, None)
        _limpar(doc_id)
