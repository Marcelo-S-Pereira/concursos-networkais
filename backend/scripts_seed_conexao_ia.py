"""Cadastra a primeira conexão de IA a partir do ambiente.

Uso:
    ./.venv/bin/python scripts_seed_conexao_ia.py

Lê TOGETHER_API_KEY do .env, cifra e grava como conexão 'texto' ativa. A chave
passa a viver cifrada no banco — depois disso pode esvaziar TOGETHER_API_KEY do
.env. Não duplica: se já existir conexão com o mesmo nome, atualiza a chave.
"""

import os

from sqlalchemy import select

from app.core.crypto import cifrar_ia
from app.db.models import AiConnection
from app.db.session import SessionLocal

NOME = "Together (texto)"
ENDPOINT = "https://api.together.xyz/v1"
MODELO_PADRAO = os.getenv("TOGETHER_MODELO", "meta-llama/Llama-3.3-70B-Instruct-Turbo")


def main() -> None:
    chave = os.getenv("TOGETHER_API_KEY", "").strip()
    if not chave:
        print("TOGETHER_API_KEY vazia no .env — preencha antes de rodar o seed.")
        raise SystemExit(1)

    with SessionLocal() as db:
        conn = db.execute(select(AiConnection).where(AiConnection.nome == NOME)).scalar_one_or_none()
        if conn:
            conn.api_key_cifrada = cifrar_ia(chave)
            acao = "chave atualizada"
        else:
            db.add(
                AiConnection(
                    nome=NOME, endpoint=ENDPOINT, api_key_cifrada=cifrar_ia(chave),
                    modelo=MODELO_PADRAO, categoria="texto", tipo_deploy="serverless", ativa=True,
                )
            )
            acao = "conexão criada"
        db.commit()
    print(f"{acao}: {NOME} ({MODELO_PADRAO}). Pode esvaziar TOGETHER_API_KEY do .env agora.")


if __name__ == "__main__":
    main()
