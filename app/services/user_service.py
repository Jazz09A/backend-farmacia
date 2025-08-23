from sqlalchemy.orm import Session
from app.models.user import User

class UserService:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_id(self, user_id: str) -> User:
        return self.db.query(User).filter(User.id == user_id).first()
    
    def get_user_stats_by_id(self, user_id: str) -> dict:
        user = self.get_user_by_id(user_id)
        return {
            "total_orders": user.get_total_orders(),
            "total_spent": user.get_total_spent(),
            "total_products_purchased": user.get_total_products_purchased(),
        }