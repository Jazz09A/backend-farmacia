#!/usr/bin/env python3
"""
Migración manual para agregar campos de moneda a credit_payments.
SQLite no soporta ALTER COLUMN, por lo que usamos este enfoque.
"""

import sqlite3
import os
import sys
from decimal import Decimal

# Agregar el directorio raíz al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.database import engine
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

def add_currency_fields():
    """
    Agregar campos de moneda a la tabla credit_payments.
    """
    
    # Crear sesión de base de datos
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    try:
        print("🔄 Agregando campos de moneda a credit_payments...")
        
        # Verificar si la tabla credit_payments existe
        result = session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='credit_payments'"))
        if not result.fetchone():
            print("⚠️  Tabla credit_payments no existe, creando...")
            
            # Crear tabla credit_payments con nuevos campos
            session.execute(text("""
                CREATE TABLE credit_payments (
                    id VARCHAR PRIMARY KEY,
                    order_id VARCHAR NOT NULL,
                    user_id VARCHAR NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    amount_ves DECIMAL(10,2),
                    currency VARCHAR DEFAULT 'REF' NOT NULL,
                    exchange_rate_used DECIMAL(10,4),
                    payment_reference VARCHAR NOT NULL,
                    payment_capture_url VARCHAR,
                    status VARCHAR DEFAULT 'pending' NOT NULL,
                    admin_notes TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    approved_at DATETIME,
                    approved_by VARCHAR,
                    FOREIGN KEY (order_id) REFERENCES orders(id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """))
            
            # Crear índices
            session.execute(text("CREATE INDEX ix_credit_payments_order_id ON credit_payments (order_id)"))
            session.execute(text("CREATE INDEX ix_credit_payments_user_id ON credit_payments (user_id)"))
            session.execute(text("CREATE INDEX ix_credit_payments_status ON credit_payments (status)"))
            
            print("✅ Tabla credit_payments creada con campos de moneda")
        
        else:
            # Verificar si los campos nuevos ya existen
            result = session.execute(text("PRAGMA table_info(credit_payments)"))
            columns = [row[1] for row in result.fetchall()]
            
            new_fields = ['amount_ves', 'currency', 'exchange_rate_used']
            missing_fields = [field for field in new_fields if field not in columns]
            
            if missing_fields:
                print(f"📋 Agregando campos faltantes: {missing_fields}")
                
                # Agregar campos nuevos uno por uno
                if 'amount_ves' in missing_fields:
                    session.execute(text("ALTER TABLE credit_payments ADD COLUMN amount_ves DECIMAL(10,2)"))
                    print("✅ Campo amount_ves agregado")
                
                if 'currency' in missing_fields:
                    session.execute(text("ALTER TABLE credit_payments ADD COLUMN currency VARCHAR DEFAULT 'REF' NOT NULL"))
                    print("✅ Campo currency agregado")
                
                if 'exchange_rate_used' in missing_fields:
                    session.execute(text("ALTER TABLE credit_payments ADD COLUMN exchange_rate_used DECIMAL(10,4)"))
                    print("✅ Campo exchange_rate_used agregado")
                
                # Actualizar registros existentes para tener currency = 'REF'
                session.execute(text("UPDATE credit_payments SET currency = 'REF' WHERE currency IS NULL"))
                print("✅ Registros existentes actualizados con currency = 'REF'")
                
            else:
                print("✅ Todos los campos de moneda ya existen")
        
        session.commit()
        
        # Verificar la estructura final
        result = session.execute(text("PRAGMA table_info(credit_payments)"))
        columns = [row[1] for row in result.fetchall()]
        print(f"📊 Estructura final de credit_payments: {columns}")
        
        print("✅ Migración de campos de moneda completada exitosamente!")
        
    except Exception as e:
        print(f"❌ Error durante la migración: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    print("🚀 Iniciando migración de campos de moneda")
    print("=" * 50)
    
    add_currency_fields()
    
    print("=" * 50)
    print("🎉 Migración completada!")
    print("\nNuevos campos agregados a credit_payments:")
    print("- amount_ves: Monto en VES (referencia)")
    print("- currency: Moneda principal (REF por defecto)")
    print("- exchange_rate_used: Tasa de cambio usada en conversión")
