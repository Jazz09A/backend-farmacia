from sqlalchemy import Column, String, Integer, Float, Boolean
from app.config.database import Base
import uuid

class ShippingZone(Base):
    __tablename__ = "shipping_zones"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False, index=True)
    
    # Can be a country, state, or a group of postal codes
    country = Column(String, nullable=False, default='Venezuela')
    states = Column(String, nullable=True) # Comma-separated list of states
    postal_codes = Column(String, nullable=True) # Comma-separated list of postal codes

    shipping_cost = Column(Float, nullable=False)
    estimated_delivery_days_min = Column(Integer, nullable=True)
    estimated_delivery_days_max = Column(Integer, nullable=True)
    
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<ShippingZone(name='{self.name}', cost={self.shipping_cost})>" 