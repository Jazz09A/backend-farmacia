from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
from app.config.database import Base
import uuid
from app.utils.timezone import get_ve_now

class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    subject = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    
    status = Column(String, nullable=False, default='open', index=True)  # open, pending, resolved, closed
    priority = Column(String, nullable=False, default='medium', index=True) # low, medium, high, urgent
    category = Column(String, nullable=True, index=True) # billing, technical, general
    
    created_at = Column(DateTime, default=get_ve_now)
    updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)

    user = relationship("User", back_populates="support_tickets")
    responses = relationship("SupportResponse", back_populates="ticket", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SupportTicket(id={self.id}, subject='{self.subject}', status='{self.status}')>"

class SupportResponse(Base):
    __tablename__ = "support_responses"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(String, ForeignKey("support_tickets.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True) # ID of the staff member responding
    
    message = Column(Text, nullable=False)
    
    created_at = Column(DateTime, default=get_ve_now)

    ticket = relationship("SupportTicket", back_populates="responses")
    author = relationship("User")

    def __repr__(self):
        return f"<SupportResponse(id={self.id}, ticket_id='{self.ticket_id}')>" 