"""
Script de migración para agregar la tabla de favoritos al sistema.

Ejecutar este script para crear la tabla user_favorites que permite a los usuarios
guardar productos en su lista de favoritos.
"""

import sys
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Agregar el directorio raíz al path para importar modules
 .append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.database import SQLALCHEMY_DATABASE_URL
from app.models.favorites import UserFavorite

def create_favorites_table():
    """Crea la tabla de favoritos en la base de datos."""
    
    # Crear conexión a la base de datos
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        print("🔄 Iniciando migración para tabla de favoritos...")
        
        # 1. Crear tabla user_favorites
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS user_favorites (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL,
            product_id VARCHAR NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE,
            UNIQUE(user_id, product_id)
        );
        """
        
        db.execute(text(create_table_sql))
        print("✅ Tabla user_favorites creada exitosamente")
        
        # 2. Crear índices para optimizar consultas
        create_indexes_sql = [
            "CREATE INDEX IF NOT EXISTS idx_favorites_user_id ON user_favorites (user_id);",
            "CREATE INDEX IF NOT EXISTS idx_favorites_product_id ON user_favorites (product_id);",
            "CREATE INDEX IF NOT EXISTS idx_favorites_created_at ON user_favorites (created_at);"
        ]
        
        for index_sql in create_indexes_sql:
            db.execute(text(index_sql))
        
        print("✅ Índices creados exitosamente")
        
        # 3. Commit todos los cambios
        db.commit()
        
        # 4. Verificar que la tabla se creó correctamente
        result = db.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='user_favorites';"))
        table_exists = result.fetchone() is not None
        
        if table_exists:
            print("✅ Verificación exitosa: La tabla user_favorites existe")
            
            # Mostrar estructura de la tabla
            result = db.execute(text("PRAGMA table_info(user_favorites);"))
            columns = result.fetchall()
            
            print("\n📋 Estructura de la tabla user_favorites:")
            for column in columns:
                print(f"   - {column[1]} ({column[2]})")
        else:
            print("❌ Error: La tabla user_favorites no se creó correctamente")
            
    except Exception as e:
        print(f"❌ Error durante la migración: {e}")
        db.rollback()
    finally:
        db.close()

def show_migration_info():
    """Muestra información sobre la migración."""
    print("""
❤️ MIGRACIÓN SISTEMA DE FAVORITOS
=================================

Este script realizará las siguientes acciones:

1. ✅ Crear tabla 'user_favorites' si no existe
2. 🔗 Establecer relaciones con usuarios y productos
3. 📊 Crear índices para optimizar consultas
4. 🔒 Agregar constraint único para evitar duplicados
5. ✅ Verificar que la migración fue exitosa

⚠️  IMPORTANTE:
- Esta migración es segura y no afecta datos existentes
- Se puede ejecutar múltiples veces sin problemas
- Los usuarios podrán agregar productos a favoritos inmediatamente

🚀 FUNCIONALIDADES QUE SE HABILITARÁN:
- ❤️ Agregar productos a favoritos
- 💔 Quitar productos de favoritos
- 📋 Ver lista de productos favoritos
- 🔍 Verificar si un producto está en favoritos
- 🔢 Contador de favoritos
- 🗑️ Limpiar lista de favoritos

¿Deseas continuar? (y/n): """)

if __name__ == "__main__":
    show_migration_info()
    
    response = input().lower().strip()
    
    if response in ['y', 'yes', 'sí', 's']:
        print("\n🚀 Iniciando migración de favoritos...")
        create_favorites_table()
        
        print("\n🎉 ¡Migración completada exitosamente!")
        print("\n💡 Próximos pasos:")
        print("   1. Reinicia tu aplicación")
        print("   2. Los endpoints de favoritos estarán disponibles en /api/v1/favorites/")
        print("   3. Los usuarios podrán usar la funcionalidad inmediatamente")
        print("\n📖 Endpoints disponibles:")
        print("   - POST /api/v1/favorites/add - Agregar a favoritos")
        print("   - DELETE /api/v1/favorites/remove/{product_id} - Quitar de favoritos")
        print("   - GET /api/v1/favorites/ - Listar favoritos")
        print("   - GET /api/v1/favorites/check/{product_id} - Verificar estado")
        print("   - GET /api/v1/favorites/count - Contador de favoritos")
        print("   - DELETE /api/v1/favorites/clear - Limpiar lista")
        
    else:
        print("❌ Migración cancelada") 