from sqlalchemy import Column, Integer, DateTime, func
from sqlalchemy.orm import declarative_mixin
from datetime import datetime
from typing import Optional

from app.database import Base


@declarative_mixin
class TimestampMixin:
    """Mixin to add timestamp fields to models."""
    
    created_at: datetime = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when the record was created"
    )
    updated_at: Optional[datetime] = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        doc="Timestamp when the record was last updated"
    )


class BaseModel(Base, TimestampMixin):
    """Base model with common fields for all entities."""
    
    __abstract__ = True
    
    id: int = Column(
        Integer,
        primary_key=True,
        index=True,
        doc="Primary key identifier"
    )
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"
