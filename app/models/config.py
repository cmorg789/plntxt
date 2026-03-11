from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
