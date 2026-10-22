import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.config.database import Base
from app.utils.timezone import get_ve_now


class UserFavorite(Base):  # type: ignore[valid-type, misc]
    __tablename__ = "user_favorites"

    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # References
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(String, ForeignKey("products.id"), nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime, default=get_ve_now)
    updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)

    # Relationships
    user = relationship("User", back_populates="favorites")
    product = relationship("Product", back_populates="favorited_by")

    # Unique constraint to prevent duplicate favorites
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="unique_user_product_favorite"),)

    def __repr__(self):
        return f"<UserFavorite(id={self.id}, user_id={self.user_id}, product_id={self.product_id})>"
