"""[118]: login por senha, opcional, ao lado do código por e-mail.
`senha_hash` nulo = sem senha cadastrada (comportamento de hoje, sem
mudança); `senha_habilitada` é o único toggle real (o código por e-mail
continua sempre disponível, é a base de recuperação da conta — nunca
desligável); `senha_tentativas_falhas`/`senha_bloqueada_ate` são um lockout
de força bruta a mais, no mesmo espírito do `LoginCode.tentativas`;
`senha_prompt_dispensado` guarda que o aluno já disse "agora não" pro
convite de cadastrar senha, pra não insistir de novo.

Revision ID: 0040_login_senha
Revises: 0039_chat_multi_caderno
"""

import sqlalchemy as sa

from alembic import op

revision = "0040_login_senha"
down_revision = "0039_chat_multi_caderno"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("senha_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("senha_habilitada", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("senha_tentativas_falhas", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("senha_bloqueada_ate", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("senha_prompt_dispensado", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("users", "senha_prompt_dispensado")
    op.drop_column("users", "senha_bloqueada_ate")
    op.drop_column("users", "senha_tentativas_falhas")
    op.drop_column("users", "senha_habilitada")
    op.drop_column("users", "senha_hash")
