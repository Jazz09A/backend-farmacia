from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index, Boolean, LargeBinary
from sqlalchemy.orm import relationship
from app.config.database import Base
import uuid
from app.utils.timezone import get_ve_now

class BlogCategory(Base):
    __tablename__ = "blog_categories"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Basic information
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    
    # Soft delete
    deleted = Column(Boolean, default=False, nullable=False, index=True)
    
    # Relationships
    posts = relationship("BlogPost", back_populates="category", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<BlogCategory(id={self.id}, name={self.name}, slug={self.slug}, deleted={self.deleted})>"


class BlogPost(Base):
    __tablename__ = "blog_posts"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Basic information
    title = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True, index=True)
    content = Column(Text, nullable=False)
    
    # Relationships
    author_id = Column(String, ForeignKey("users.id"), nullable=True)  # Opcional si se usa author_name
    author_name = Column(String, nullable=True)  # Nombre del autor (si no se usa author_id)
    category_id = Column(String, ForeignKey("blog_categories.id"), nullable=False)
    
    # Media
    featured_image_url = Column(String, nullable=True)
    
    # Status and publishing
    status = Column(String, nullable=True, index=True)  # 'draft', 'published', 'archived'
    published_at = Column(DateTime, nullable=True)
    
    # Soft delete
    deleted = Column(Boolean, default=False, nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=get_ve_now)
    updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)
    
    # Relationships
    author = relationship("User", backref="blog_posts")
    category = relationship("BlogCategory", back_populates="posts")
    
    def __repr__(self):
        return f"<BlogPost(id={self.id}, title={self.title}, slug={self.slug}, status={self.status}, deleted={self.deleted})>"
    
    @property
    def is_published(self) -> bool:
        """Check if post is published."""
        return self.status == "published" and self.published_at is not None
    
    # Relationships
    images = relationship("BlogImage", back_populates="post", cascade="all, delete-orphan")


class BlogImage(Base):
    __tablename__ = "blog_images"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Foreign key to blog post
    blog_post_id = Column(String, ForeignKey("blog_posts.id"), nullable=False, index=True)
    
    # Image data (binary)
    image_data = Column(LargeBinary, nullable=False)
    
    # Image metadata
    image_code = Column(String(10), nullable=False, index=True)  # Código único por post (IMG001, IMG002, etc.)
    description = Column(Text, nullable=True)
    
    # Metadata
    created_by = Column(String, nullable=True)  # Email o ID del usuario que subió la imagen
    created_at = Column(DateTime, default=get_ve_now)
    updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)
    
    # Relationships
    post = relationship("BlogPost", back_populates="images")
    
    def __repr__(self):
        return f"<BlogImage(id={self.id}, blog_post_id={self.blog_post_id}, image_code={self.image_code})>"

