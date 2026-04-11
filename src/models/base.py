from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import func
from uuid import UUID, uuid4
from datetime import datetime


class Base(DeclarativeBase):
    pass
