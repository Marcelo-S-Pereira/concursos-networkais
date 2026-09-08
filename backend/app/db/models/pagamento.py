from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PaymentPlatform(Base):
    """Provedor de pagamento cadastrado pelo admin (Mercado Pago, Stripe, Efí...).

    Molde do cadastro de IA: a credencial (access token/secret) fica CIFRADA no
    banco; a public_key não é secreta. O checkout/webhook usam a plataforma ativa.
    """

    __tablename__ = "payment_platforms"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(120))
    # provedor: mercadopago | stripe | efi | asaas | outro
    provedor: Mapped[str] = mapped_column(String(30), default="mercadopago", index=True)
    access_token_cifrado: Mapped[str] = mapped_column(String(1000))  # AES-256-GCM
    public_key: Mapped[str] = mapped_column(String(300), default="")  # não secreta
    ativa: Mapped[bool] = mapped_column(Boolean, default=False)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
