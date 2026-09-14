"""[125]: catálogo de prompts — a base de dados é a ÚNICA fonte de verdade do
texto enviado à IA. Nenhuma string de prompt fica hardcoded em código Python;
todo ponto de uso chama `buscar()`. Editar `texto` pela aba Prompts (admin)
muda o comportamento na próxima chamada, sem deploy."""

from sqlalchemy.orm import Session

from app.db.models import Prompt


class PromptNaoEncontrado(RuntimeError):
    """Uma chave de prompt esperada não existe na base — é falta real de
    dado (linha apagada ou nunca semeada), nunca deve ser mascarada com um
    texto vazio ou um padrão silencioso escondido no código."""


def buscar(db: Session, chave: str) -> str:
    prompt = db.get(Prompt, chave)
    if prompt is None:
        raise PromptNaoEncontrado(f"Prompt '{chave}' não está cadastrado na base de dados.")
    return prompt.texto
