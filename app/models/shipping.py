from sqlalchemy import Column, String, Float
from app.config.database import Base

class ShippingZone(Base):
    __tablename__ = "shipping_zones"
    
    # Primary key, using the string identifier like 'caracas'
    id = Column(String, primary_key=True, index=True)
    
    # Zone details
    name = Column(String, nullable=False, unique=True)
    price = Column(Float, nullable=False)
    delivery_days = Column(String, nullable=True)
    
    def __repr__(self):
        return f"<ShippingZone(id={self.id}, name={self.name}, price={self.price})>"
