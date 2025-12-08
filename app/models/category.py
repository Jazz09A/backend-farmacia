from sqlalchemy import Column, String, Text, Boolean, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.config.database import Base
import uuid
from app.utils.timezone import get_ve_now

class Category(Base):
    __tablename__ = "categories"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Basic information
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    # Hierarchy
    parent_id = Column(String, ForeignKey("categories.id"), nullable=True)
    
    # Status and ordering
    is_active = Column(Boolean, default=True, index=True)
    sort_order = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=get_ve_now)
    updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)
    
    # Relationships
    parent = relationship("Category", remote_side=[id], backref="subcategories")
    
    def __repr__(self):
        return f"<Category(id={self.id}, name={self.name}, slug={self.slug})>"
    
    @property
    def full_path(self):
        """Return full category path for breadcrumbs."""
        if self.parent:
            return f"{self.parent.full_path} > {self.name}"
        return self.name

class Brand(Base):
    __tablename__ = "brands"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Basic information
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    # Status
    is_featured = Column(Boolean, default=False, index=True)
    is_active = Column(Boolean, default=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=get_ve_now)
    updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)
    
    # Relationships - eliminadas porque Product ya no usa brand_obj
    
    def __repr__(self):
        return f"<Brand(id={self.id}, name={self.name}, slug={self.slug})>" 