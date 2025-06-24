from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.config.database import Base
import uuid
from datetime import datetime

class UserNotification(Base):
    __tablename__ = "user_notifications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    
    type = Column(String, nullable=True, index=True) # e.g., 'order_update', 'new_promotion', 'security_alert'
    
    is_read = Column(Boolean, default=False, index=True)
    read_at = Column(DateTime, nullable=True)
    
    # You can add a link to a relevant page
    link = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")

    def __repr__(self):
        return f"<UserNotification(id={self.id}, user_id='{self.user_id}', title='{self.title}')>" 