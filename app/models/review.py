from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.config.database import Base
import uuid
from datetime import datetime

class Review(Base):
    __tablename__ = "reviews"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # References
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(String, ForeignKey("products.id"), nullable=False, index=True)
    
    # Review content
    rating = Column(Integer, nullable=False)  # 1-5 stars
    title = Column(String, nullable=True)
    comment = Column(Text, nullable=True)
    
    # Review status
    is_verified_purchase = Column(Boolean, default=False)  # If user actually bought the product
    is_approved = Column(Boolean, default=True)  # For moderation
    is_featured = Column(Boolean, default=False)  # To highlight good reviews
    
    # Helpful votes
    helpful_votes = Column(Integer, default=0)
    total_votes = Column(Integer, default=0)
    
    # Additional information
    reviewer_name = Column(String, nullable=True)  # User might want to show different name
    reviewer_age_group = Column(String, nullable=True)  # 18-25, 26-35, etc.
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="reviews")
    product = relationship("Product", back_populates="reviews")
    
    def __repr__(self):
        return f"<Review(id={self.id}, rating={self.rating}, product_id={self.product_id})>"
    
    @property
    def helpful_percentage(self):
        """Calculate percentage of helpful votes."""
        if self.total_votes == 0:
            return 0
        return round((self.helpful_votes / self.total_votes) * 100, 1)
    
    @property
    def display_name(self):
        """Return name to display for the review."""
        if self.reviewer_name:
            return self.reviewer_name
        return self.user.name if self.user else "Usuario Anónimo" 