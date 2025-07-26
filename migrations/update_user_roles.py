"""
Script de migración para actualizar usuarios existentes al sistema de roles.

Ejecutar este script después de implementar el sistema de roles para:
1. Asignar rol "user" a usuarios que no tengan rol
2. Migrar usuarios con is_admin=True a rol "admin"
3. Asegurar que todos los usuarios tengan un rol válido
"""

import sys
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Agregar el directorio raíz al path para importar modules
 .append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.database import SQLALCHEMY_DATABASE_URL
from app.models.user import User

def migrate_user_roles():
    """Migra usuarios existentes al sistema de roles."""
    
    # Crear conexión a la base de datos
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        print("🔄 Iniciando migración de roles de usuario...")
        
        # 1. Agregar columna role si no existe (SQLite)
        try:
            db.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'user'"))
            print("✅ Columna 'role' agregada a la tabla users")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("ℹ️  Columna 'role' ya existe en la tabla users")
            else:
                print(f"⚠️  Error al agregar columna role: {e}")
        
        # 2. Obtener todos los usuarios
        users = db.query(User).all()
        updated_count = 0
        admin_count = 0
        
        print(f"📊 Encontrados {len(users)} usuarios para procesar")
        
        for user in users:
            updates_made = False
            
            # Si el usuario no tiene rol, asignar "user"
            if not hasattr(user, 'role') or user.role is None or user.role == '':
                user.role = "user"
                updates_made = True
            
            # Si el usuario tiene is_admin=True, promover a admin
            if hasattr(user, 'is_admin') and user.is_admin and user.role == "user":
                user.role = "admin"
                admin_count += 1
                updates_made = True
                print(f"👑 Usuario {user.email} promovido a admin")
            
            if updates_made:
                updated_count += 1
        
        # 3. Commit todos los cambios
        db.commit()
        
        print(f"✅ Migración completada:")
        print(f"   - {updated_count} usuarios actualizados")
        print(f"   - {admin_count} usuarios promovidos a admin")
        
        # 4. Mostrar estadísticas finales
        stats = {}
        for role in ["user", "manager", "admin", "super_admin"]:
            count = db.query(User).filter(User.role == role).count()
            if count > 0:
                stats[role] = count
        
        print("\n📈 Estadísticas de roles después de la migración:")
        for role, count in stats.items():
            print(f"   - {role}: {count} usuarios")
        
        # 5. Verificar que no hay usuarios sin rol
        users_without_role = db.query(User).filter(
            (User.role == None) | (User.role == '')
        ).count()
        
        if users_without_role > 0:
            print(f"⚠️  ADVERTENCIA: {users_without_role} usuarios aún sin rol")
        else:
            print("✅ Todos los usuarios tienen un rol asignado")
            
    except Exception as e:
        print(f"❌ Error durante la migración: {e}")
        db.rollback()
    finally:
        db.close()

def create_super_admin():
    """Crea un super administrador si no existe."""
    
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Buscar si ya existe un super_admin
        super_admin = db.query(User).filter(User.role == "super_admin").first()
        
        if super_admin:
            print(f"ℹ️  Ya existe un super administrador: {super_admin.email}")
            return
        
        # Buscar el primer admin para promover
        admin_user = db.query(User).filter(User.role == "admin").first()
        
        if admin_user:
            admin_user.role = "super_admin"
            db.commit()
            print(f"🚀 Usuario {admin_user.email} promovido a super_admin")
        else:
            print("⚠️  No se encontraron usuarios admin para promover a super_admin")
            print("💡 Puedes crear manualmente un super_admin o promover un usuario existente")
            
    except Exception as e:
        print(f"❌ Error al crear super_admin: {e}")
        db.rollback()
    finally:
        db.close()

def show_migration_info():
    """Muestra información sobre la migración."""
    print("""
🔧 MIGRACIÓN DE SISTEMA DE ROLES
===============================

Este script realizará las siguientes acciones:

1. ✅ Agregar columna 'role' a la tabla users (si no existe)
2. 🎭 Asignar rol 'user' a usuarios sin rol
3. 👑 Promover usuarios con is_admin=True a rol 'admin'
4. 📊 Mostrar estadísticas de la migración
5. 🚀 Crear super_admin si no existe

⚠️  IMPORTANTE:
- Haz un backup de tu base de datos antes de ejecutar
- Esta migración es segura pero irreversible
- Los usuarios existentes mantendrán todos sus datos

¿Deseas continuar? (y/n): """)

if __name__ == "__main__":
    show_migration_info()
    
    response = input().lower().strip()
    
    if response in ['y', 'yes', 'sí', 's']:
        print("\n🚀 Iniciando migración...")
        migrate_user_roles()
        
        print("\n🔧 Configurando super administrador...")
        create_super_admin()
        
        print("\n🎉 ¡Migración completada exitosamente!")
        print("\n💡 Próximos pasos:")
        print("   1. Reinicia tu aplicación")
        print("   2. Verifica que las rutas de admin funcionen")
        print("   3. Prueba la promoción de usuarios")
        
    else:
        print("❌ Migración cancelada") 