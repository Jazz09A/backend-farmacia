from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.config.database import Base
import uuid
from datetime import datetime

class BlogCategory(Base):
    __tablename__ = "blog_categories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False, index=True)
    slug = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)

    posts = relationship("BlogPost", back_populates="category")

    def __repr__(self):
        return f"<BlogCategory(name='{self.name}')>"

class BlogPost(Base):
    __tablename__ = "blog_posts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    content = Column(Text, nullable=False)
    
    author_id = Column(String, ForeignKey("users.id"), nullable=False)
    category_id = Column(String, ForeignKey("blog_categories.id"), nullable=False)

    featured_image_url = Column(String, nullable=True)
    status = Column(String, default='draft', index=True) # draft, published
    
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    author = relationship("User")
    category = relationship("BlogCategory", back_populates="posts")

    def __repr__(self):
        return f"<BlogPost(title='{self.title}', status='{self.status}')>" 