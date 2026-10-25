import sys
import os
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models.user import User
from app.config.settings import settings

def verify_user_emails():
    """
    Verify the emails of unverified users.
    """
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        unverified_users = db.query(User).filter(User.is_verified == False).all()
        
        if not unverified_users:
            print("No unverified users found.")
            return

        print(f"Found {len(unverified_users)} unverified users. Verifying emails...")

        for idx, user in enumerate(unverified_users):
            print(f"({idx + 1}/{len(unverified_users)}) Verifying user: {user.email}")
            user.is_verified = True
        
        db.commit()
        print("All unverified users have been successfully verified.")
        
    except Exception as e:
        db.rollback()
        print(f"An error occurred: {e}")
        
    finally:
        db.close()
        print("Database connection closed.")

if __name__ == "__main__":
    verify_user_emails()
