"""Aponta a suíte para um banco SEPARADO, nunca o de produção.

Motivo: as fixtures precisam de uma tabela limpa para isolar o caso de teste.
Enquanto os testes rodavam no banco real, isso significava apagar dados do
usuário — foi assim que a conexão de IA dele foi perdida uma vez (Registro de
Atividades [034]). Agora o `pytest` cria e usa `concursos_test_db`, e o banco de
produção fica intocado mesmo que um teste apague tudo.

A variável precisa ser trocada ANTES de qualquer import do app, porque
`app/db/session.py` monta o engine no import.
"""

import os
from urllib.parse import urlparse, urlunparse

_url = os.environ.get("DATABASE_URL") or ""
if not _url:
    from dotenv import dotenv_values  # type: ignore[import-not-found]
    raiz = os.path.join(os.path.dirname(__file__), "..", "..")
    _url = (dotenv_values(os.path.join(raiz, ".env")) or {}).get("DATABASE_URL", "")

if not _url:
    raise RuntimeError("DATABASE_URL não encontrada — os testes não sabem em que banco rodar.")

_p = urlparse(_url)
if not _p.path.endswith("_test_db"):
    _url = urlunparse(_p._replace(path="/concursos_test_db"))
os.environ["DATABASE_URL"] = _url

from app.db import models  # noqa: E402,F401  - popula o metadata; sem isso create_all não cria nada
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402

assert engine.url.database.endswith("_test_db"), (
    f"SALVAGUARDA: os testes tentaram usar o banco '{engine.url.database}'. "
    "Só rodam em um banco terminado em _test_db."
)

Base.metadata.create_all(engine)
