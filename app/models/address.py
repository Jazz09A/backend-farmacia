import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.config.database import Base
from app.utils.timezone import get_ve_now


class Address(Base):
    __tablename__ = "addresses"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # User reference
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    # Address information
    street = Column(String, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    postal_code = Column(String, nullable=True)
    country = Column(String, nullable=False, default='Venezuela')
    
    # Contact information
    recipient_name = Column(String, nullable=False)
    recipient_phone = Column(String, nullable=False)
    
    # Address details
    address_type = Column(String, nullable=True)  # home, office, etc.
    delivery_instructions = Column(Text, nullable=True)
    
    # Address status
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=get_ve_now)
    updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)
    # shipping_zone_id eliminado - ShippingZone no se usa con Profit Plus
    
    # Relationships
    user = relationship("User", back_populates="addresses")
    
    def __repr__(self):
        return f"<Address(id={self.id}, city={self.city}, recipient={self.recipient_name})>"
    
    @property
    def full_address(self):
        """Return formatted full address."""
        parts = [self.street, self.city, self.state]
        if self.postal_code:
            parts.append(self.postal_code)
        parts.append(self.country)
        return ", ".join(parts)
    
    @property
    def short_address(self):
        """Return short version of address."""
        return f"{self.city}, {self.state}"

class UserPreferences(Base):
    __tablename__ = "user_preferences"
    
    # Primary key
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # User reference
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    
    # Notification preferences
    email_notifications = Column(Boolean, default=True)
    sms_notifications = Column(Boolean, default=False)
    push_notifications = Column(Boolean, default=True)
    
    # Marketing preferences
    promotional_emails = Column(Boolean, default=True)
    product_recommendations = Column(Boolean, default=True)
    
    # Shopping preferences
    preferred_currency = Column(String, default='VES')
    preferred_language = Column(String, default='es')
    
    # Privacy preferences
    show_reviews_publicly = Column(Boolean, default=True)
    share_data_for_recommendations = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=get_ve_now)
    updated_at = Column(DateTime, default=get_ve_now, onupdate=get_ve_now)
    
    # Relationships
    user = relationship("User", back_populates="preferences")
    
    def __repr__(self):
        return f"<UserPreferences(id={self.id}, user_id={self.user_id})>" 