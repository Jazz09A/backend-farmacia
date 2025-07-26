#!/usr/bin/env python3
"""
Script simple para crear usuarios admin para el panel.
Solo campos esenciales, sin complicaciones.
"""
import sys
import getpass
from pathlib import Path
from datetime import datetime

# Path setup
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.insert(0, str(parent_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config.settings import Settings
from app.models.user import User
from app.models.address import UserPreferences
from app.core.security import get_password_hash
import uuid

settings = Settings()

def create_admin():
    """Crear admin con lo mínimo necesario."""
    
    print("🚀 CREAR ADMIN PARA PANEL - SIMPLE")
    print("=================================")
    
    # Solo lo esencial
    email = input("📧 Email: ").strip()
    password = getpass.getpass("🔑 Contraseña: ")
    name = input("👤 Nombre (ej: Juan Admin): ").strip() or "Admin"
    
    # Elegir rol simple
    print("\n1. Admin  2. Super Admin")
    role = "admin" if input("Rol (1/2): ").strip() == "1" else "super_admin"
    
    # Conexión DB
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Verificar duplicado
        if db.query(User).filter(User.email == email).first():
            print("❌ Email ya existe")
            return
        
        # Crear usuario simple
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            hashed_password=get_password_hash(password),
            user_type="natural",
            phone="0000-000-0000",  # Placeholder
            preferred_currency="VES",
            role=role,
            is_active=True,
            is_verified=True,  # Admin pre-verificado
            first_name=name,
            last_name="Admin",
            cedula="V00000000"  # Placeholder para admin
        )
        
        db.add(user)
        db.flush()
        
        # Preferencias básicas
        prefs = UserPreferences(user_id=user.id, preferred_currency="VES")
        db.add(prefs)
        
        db.commit()
        
        print(f"✅ Admin creado: {email} ({role})")
        print(f"🔗 Ahora puede acceder al panel admin")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_admin()