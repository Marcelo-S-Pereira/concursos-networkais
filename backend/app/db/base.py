from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base declarativa. Todo modelo herda daqui para o Alembic enxergá-lo."""
