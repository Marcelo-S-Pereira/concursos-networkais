"""Busca de vídeos no YouTube: salvar/apagar a chave, parsing do resultado real
da API (mockado — sem chave de teste), e o caminho sem chave configurada."""

import httpx
import pytest

from app.db.models import YoutubeConfig
from app.db.session import SessionLocal
from app.modules.youtube import youtube


@pytest.fixture
def db():
    d = SessionLocal()
    yield d
    d.query(YoutubeConfig).delete()
    d.commit()
    d.close()


def test_sem_chave_erro_claro(db):
    assert youtube.configurada(db) is False
    with pytest.raises(youtube.YoutubeError):
        youtube.buscar(db, "aula de física")


def test_salvar_apagar_e_mascara(db):
    youtube.salvar_chave(db, "youtube-chave-ficticia-1234")
    assert youtube.configurada(db) is True
    assert youtube.chave_mascarada(db) == "****1234"
    youtube.apagar_chave(db)
    assert youtube.configurada(db) is False


RESPOSTA_API = {
    "items": [
        {
            "id": {"videoId": "abc123"},
            "snippet": {
                "title": "Aula de Física — Cinemática",
                "channelTitle": "Canal Exemplo",
                "thumbnails": {"medium": {"url": "https://img.example/abc123.jpg"}},
            },
        },
        {"id": {}, "snippet": {}},  # sem videoId — deve ser descartado
    ]
}


def test_buscar_parseia_resultado_real_da_api(db, monkeypatch):
    youtube.salvar_chave(db, "chave-de-teste")

    def fake_get(url, params=None, timeout=None):
        assert params["key"] == "chave-de-teste"
        assert params["q"] == "cinemática"
        return httpx.Response(200, json=RESPOSTA_API, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    resultados = youtube.buscar(db, "cinemática")
    assert len(resultados) == 1  # o item sem videoId foi descartado
    assert resultados[0] == {
        "video_id": "abc123",
        "titulo": "Aula de Física — Cinemática",
        "canal": "Canal Exemplo",
        "miniatura": "https://img.example/abc123.jpg",
        "url": "https://www.youtube.com/watch?v=abc123",
    }


def test_chave_recusada_vira_erro_sem_vazar_a_chave(db, monkeypatch):
    youtube.salvar_chave(db, "chave-secreta-xyz")

    def fake_get(url, params=None, timeout=None):
        return httpx.Response(403, json={}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(youtube.YoutubeError) as exc:
        youtube.buscar(db, "algo")
    assert "chave-secreta-xyz" not in str(exc.value)


@pytest.mark.parametrize(("iso", "segundos"), [
    ("PT15M33S", 933), ("PT1H2M3S", 3723), ("PT45S", 45), ("PT2H", 7200), ("lixo", None), ("", None),
])
def test_parse_duracao_iso8601(iso, segundos):
    assert youtube._duracao_para_segundos(iso) == segundos


def test_duracao_video_sem_chave_da_none(db):
    assert youtube.duracao_video(db, "abc123") is None  # [113]: nunca lança, só não estima


def test_duracao_video_parseia_contentdetails_real(db, monkeypatch):
    youtube.salvar_chave(db, "chave-de-teste")

    def fake_get(url, params=None, timeout=None):
        assert url.endswith("/videos")
        assert params["id"] == "abc123"
        return httpx.Response(200, json={"items": [{"contentDetails": {"duration": "PT9M12S"}}]},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    assert youtube.duracao_video(db, "abc123") == 552


def test_duracao_video_id_inexistente_da_none(db, monkeypatch):
    youtube.salvar_chave(db, "chave-de-teste")

    def fake_get(url, params=None, timeout=None):
        return httpx.Response(200, json={"items": []}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    assert youtube.duracao_video(db, "naoexiste") is None
