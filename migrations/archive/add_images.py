import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import List

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config.settings import settings
from app.models.product import Product

def get_products_from_db() -> List[Product]:
    """
    Connects to the database and retrieves all products.
    
    Returns:
        A list of Product objects.
    """
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        products = db.query(Product).all()
        return products
    finally:
        db.close()

if __name__ == "__main__":
    print("Connecting to the database and retrieving products...")
    
    try:
        products = get_products_from_db()
        
        if not products:
            print("No products found in the database.")
        else:
            print(f"Successfully retrieved {len(products)} products:")
            for product in products:
                print(f"  - ID: {product.id}, Name: {product.name}, Price (VES): {product.price_ves}, Stock: {product.stock}")
                
    except Exception as e:
        print(f"An error occurred while connecting to the database or retrieving data: {e}")
        print("Please ensure the following:")
        print("  1. The database file 'db.sqlite3' exists in the project root.")
        print("  2. The required libraries are installed (run 'pip install -r requirements.txt').")
        print(f"  3. The DATABASE_URL in 'app/config/settings.py' is correctly set to '{settings.DATABASE_URL}'.")

