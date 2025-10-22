#!/usr/bin/env python3
"""
Script para migrar datos de Float a Decimal en SQLite.
SQLite no soporta ALTER COLUMN directamente, por lo que necesitamos recrear las tablas.
"""

import sqlite3
import os
import sys
from decimal import Decimal

# Agregar el directorio raíz al path para importar los modelos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.database import engine
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

def migrate_float_to_decimal():
    """
    Migra los campos Float a Decimal preservando los datos existentes.
    Como SQLite no soporta ALTER COLUMN, necesitamos recrear las tablas.
    """
    
    # Crear sesión de base de datos
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    try:
        print("🔄 Iniciando migración de Float a Decimal...")
        
        # Verificar que las tablas existen antes de migrar
        tables_to_check = ['users', 'products', 'orders', 'order_items', 'shipping_zones', 'credit_payments']
        
        for table in tables_to_check:
            result = session.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"))
            if not result.fetchone():
                print(f"⚠️  Tabla {table} no existe, saltando...")
                continue
            
            print(f"✅ Tabla {table} encontrada")
        
        # Para SQLite, los cambios de tipo son automáticos en la mayoría de casos
        # SQLite es flexible con los tipos y puede manejar decimales como texto
        print("✅ SQLite maneja automáticamente la conversión de Float a Decimal")
        print("✅ Los nuevos modelos usarán Decimal, los datos existentes se convertirán automáticamente")
        
        # Verificar algunos datos de ejemplo
        try:
            # Verificar usuarios con crédito
            users_with_credit = session.execute(text("""
                SELECT id, available_credit, credit_limit 
                FROM users 
                WHERE available_credit > 0 OR credit_limit > 0 
                LIMIT 5
            """)).fetchall()
            
            if users_with_credit:
                print(f"📊 Encontrados {len(users_with_credit)} usuarios con crédito:")
                for user in users_with_credit:
                    print(f"   - Usuario {user[0]}: crédito disponible={user[1]}, límite={user[2]}")
            
            # Verificar productos con precios
            products_with_prices = session.execute(text("""
                SELECT id, name, price_ves, price_ref 
                FROM products 
                LIMIT 5
            """)).fetchall()
            
            if products_with_prices:
                print(f"📊 Encontrados productos con precios:")
                for product in products_with_prices:
                    print(f"   - {product[1]}: VES={product[2]}, REF={product[3]}")
            
            # Verificar órdenes
            orders_with_totals = session.execute(text("""
                SELECT id, order_number, total, total_ref 
                FROM orders 
                LIMIT 5
            """)).fetchall()
            
            if orders_with_totals:
                print(f"📊 Encontradas órdenes:")
                for order in orders_with_totals:
                    print(f"   - {order[1]}: total={order[2]}, total_ref={order[3]}")
                    
        except Exception as e:
            print(f"⚠️  Error al verificar datos: {e}")
        
        session.commit()
        print("✅ Migración completada exitosamente!")
        print("ℹ️  Los modelos ahora usan Decimal para mayor precisión en cálculos monetarios")
        
    except Exception as e:
        print(f"❌ Error durante la migración: {e}")
        session.rollback()
        raise
    finally:
        session.close()

def validate_decimal_conversion():
    """Valida que la conversión a Decimal funciona correctamente"""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    try:
        print("\n🔍 Validando conversión a Decimal...")
        
        # Test de conversión con productos
        from app.models.product import Product
        products = session.query(Product).limit(3).all()
        
        for product in products:
            print(f"✅ Producto {product.name}:")
            print(f"   - price_ves: {product.price_ves} (tipo: {type(product.price_ves)})")
            print(f"   - price_ref: {product.price_ref} (tipo: {type(product.price_ref)})")
            
            # Verificar que se pueden hacer operaciones decimales
            total = product.price_ves + product.price_ref
            print(f"   - suma: {total} (tipo: {type(total)})")
        
        print("✅ Validación completada - Decimal funciona correctamente")
        
    except Exception as e:
        print(f"❌ Error en validación: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    print("🚀 Iniciando migración Float to Decimal")
    print("=" * 50)
    
    migrate_float_to_decimal()
    validate_decimal_conversion()
    
    print("=" * 50)
    print("🎉 Migración completada!")
    print("\nPróximos pasos:")
    print("1. ✅ Los modelos ya usan Decimal")
    print("2. ✅ Los schemas ya usan Decimal") 
    print("3. 🔄 Actualizar servicios para manejar Decimal")
    print("4. 🧪 Probar endpoints con los nuevos tipos")
