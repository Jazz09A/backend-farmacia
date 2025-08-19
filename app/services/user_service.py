from sqlalchemy.orm import Session
from app.models.user import User

class UserService:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_id(self, user_id: str) -> User:
        return self.db.query(User).filter(User.id == user_id).first()
    
    