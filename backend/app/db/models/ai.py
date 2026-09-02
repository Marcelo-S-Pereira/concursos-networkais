from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AiConnection(Base):
    """Uma conexão de IA (provedor OpenAI-compatible). Configuração é DADO, não
    código: cadastrar/editar aqui troca provedor/modelo sem deploy.

    Segue skill_conexao_padrao_LLM.md: uma linha por conexão, separadas por
    `categoria`, cada categoria com sua própria conexão ativa e cadeia de
    fallback.
    """

    __tablename__ = "ai_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    endpoint: Mapped[str] = mapped_column(String(500))  # base OpenAI-compatible, ex: https://api.together.xyz/v1
    api_key_cifrada: Mapped[str] = mapped_column(String(1000))  # AES-256-GCM; pode ser "" (provedor local)
    modelo: Mapped[str] = mapped_column(String(200))  # o "model" da chamada de chat/visão

    # categoria: texto | visao | embeddings | transcricao
    categoria: Mapped[str] = mapped_column(String(20), default="texto", index=True)
    # tipo_deploy: serverless | dedicado | local
    tipo_deploy: Mapped[str] = mapped_column(String(20), default="serverless")

    # Ativa = a primeira a tentar naquela categoria. As demais só entram no
    # fallback automático se tiverem ordem_fallback preenchida (2, 3, ...).
    ativa: Mapped[bool] = mapped_column(Boolean, default=False)
    ordem_fallback: Mapped[int | None] = mapped_column(Integer, nullable=True)

    max_tokens: Mapped[int] = mapped_column(Integer, default=4000)   # piso p/ modelo que raciocina
    temperatura: Mapped[float] = mapped_column(Float, default=0.7)

    # Limites e preço cadastrados à mão (o backend não descobre sozinho).
    context_window_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_limit_rpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preco_entrada_por_milhao: Mapped[float | None] = mapped_column(Float, nullable=True)
    preco_saida_por_milhao: Mapped[float | None] = mapped_column(Float, nullable=True)
    moeda: Mapped[str] = mapped_column(String(8), default="USD")

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AiCallLog(Base):
    """Uma linha por chamada de IA. Guarda tokens e QUAL conexão atendeu — o
    custo em dinheiro é DERIVADO na leitura (preço muda; gravar congelaria o
    histórico). Nunca guarda a resposta nem a chave."""

    __tablename__ = "ai_call_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    categoria: Mapped[str] = mapped_column(String(20))
    origem: Mapped[str] = mapped_column(String(60))  # ponto de entrada (ex: tutor_explica)
    modelo: Mapped[str] = mapped_column(String(200))
    sucesso: Mapped[bool] = mapped_column(Boolean)
    latencia_ms: Mapped[int] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unidades: Mapped[int | None] = mapped_column(Integer, nullable=True)  # STT: segundos; TTS: caracteres
    tipo_unidade: Mapped[str | None] = mapped_column(String(16), nullable=True)
    erro: Mapped[str | None] = mapped_column(String(500), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
