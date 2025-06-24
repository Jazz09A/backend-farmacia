from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.config.database import Base
import uuid
from datetime import datetime

class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    code = Column(String, unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    
    discount_type = Column(String, nullable=False)  # 'percentage' or 'fixed_amount'
    discount_value = Column(Float, nullable=False)
    
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime, nullable=True)
    
    min_purchase_amount = Column(Float, default=0)
    
    usage_limit = Column(Integer, default=1) # How many times a user can use it
    total_usage_limit = Column(Integer, nullable=True) # How many times it can be used in total
    
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<Promotion(code='{self.code}', type='{self.discount_type}', value={self.discount_value})>"

# You might also want a table to track usage
class PromotionUsage(Base):
    __tablename__ = "promotion_usage"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    promotion_id = Column(String, ForeignKey("promotions.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False, index=True)
    
    used_at = Column(DateTime, default=datetime.utcnow)

    promotion = relationship("Promotion")
    user = relationship("User")
    order = relationship("Order")
    
    def __repr__(self):
        return f"<PromotionUsage(user_id='{self.user_id}', promotion_id='{self.promotion_id}')>" 