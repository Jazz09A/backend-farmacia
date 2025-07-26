#!/usr/bin/env python3
"""
Script rápido para operaciones básicas de usuarios
Uso: python quick_user_ops.py [comando] [argumentos]
"""

import sys
import os
import argparse
from datetime import datetime

# Agregar el directorio raíz al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from app.config.database import SessionLocal
from app.models.user import User

def list_users():
    """Listar usuarios de forma rápida"""
    db = SessionLocal()
    try:
        users = db.query(User).all()
        
        if not users:
            print("No hay usuarios registrados.")
            return
        
        print(f"{'='*100}")
        print(f"{'ID':<8} | {'Email':<30} | {'Tipo':<10} | {'Nombre/Empresa':<25} | {'Estado':<10}")
        print(f"{'='*100}")
        
        for user in users:
            name = user.display_name[:24]
            status = "Activo" if user.is_active else "Inactivo"
            print(f"{user.id[:8]:<8} | {user.email[:29]:<30} | {user.user_type:<10} | {name:<25} | {status:<10}")
        
        print(f"{'='*100}")
        print(f"Total: {len(users)} usuarios")
        
    finally:
        db.close()

def show_user(user_id):
    """Mostrar detalles de un usuario específico"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            print(f"❌ Usuario con ID '{user_id}' no encontrado.")
            return
        
        print(f"\n{'='*60}")
        print(f"USUARIO: {user.display_name}")
        print(f"{'='*60}")
        print(f"🆔 ID: {user.id}")
        print(f"📧 Email: {user.email}")
        print(f"👤 Tipo: {user.user_type}")
        print(f"🔑 Rol: {user.role}")
        print(f"📱 Teléfono: {user.phone}")
        print(f"📊 Estado: {'Activo' if user.is_active else 'Inactivo'}")
        print(f"🔐 Verificado: {'Sí' if user.is_verified else 'No'}")
        print(f"📅 Creado: {user.created_at}")
        print(f"🔄 Último login: {user.last_login or 'Nunca'}")
        
    finally:
        db.close()

def find_user_by_email(email):
    """Buscar usuario por email"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            print(f"❌ Usuario con email '{email}' no encontrado.")
            return
        
        print(f"✅ Usuario encontrado:")
        show_user(user.id)
        
    finally:
        db.close()

def delete_user_by_id(user_id, force=False):
    """Eliminar usuario por ID"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            print(f"❌ Usuario con ID '{user_id}' no encontrado.")
            return
        
        if not force:
            print(f"⚠️ Vas a eliminar al usuario: {user.display_name} ({user.email})")
            confirm = input("¿Estás seguro? (escribe 'confirmar'): ").strip()
            if confirm != 'confirmar':
                print("❌ Operación cancelada.")
                return
        
        db.delete(user)
        db.commit()
        print(f"✅ Usuario '{user.display_name}' eliminado exitosamente.")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error al eliminar usuario: {str(e)}")
    finally:
        db.close()

def count_users():
    """Contar usuarios por tipo y estado"""
    db = SessionLocal()
    try:
        total = db.query(User).count()
        juridicos = db.query(User).filter(User.user_type == 'juridico').count()
        naturales = db.query(User).filter(User.user_type == 'natural').count()
        activos = db.query(User).filter(User.is_active == True).count()
        verificados = db.query(User).filter(User.is_verified == True).count()
        
        print(f"📊 ESTADÍSTICAS DE USUARIOS")
        print(f"{'='*40}")
        print(f"Total usuarios: {total}")
        print(f"Usuarios jurídicos: {juridicos}")
        print(f"Usuarios naturales: {naturales}")
        print(f"Usuarios activos: {activos}")
        print(f"Usuarios verificados: {verificados}")
        
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(description='Operaciones rápidas de usuarios')
    parser.add_argument('command', choices=['list', 'show', 'find', 'delete', 'count'], 
                       help='Comando a ejecutar')
    parser.add_argument('--id', help='ID del usuario (para show/delete)')
    parser.add_argument('--email', help='Email del usuario (para find)')
    parser.add_argument('--force', action='store_true', help='Forzar eliminación sin confirmación')
    
    args = parser.parse_args()
    
    try:
        if args.command == 'list':
            list_users()
        elif args.command == 'show':
            if not args.id:
                print("❌ Se requiere --id para mostrar usuario")
                return
            show_user(args.id)
        elif args.command == 'find':
            if not args.email:
                print("❌ Se requiere --email para buscar usuario")
                return
            find_user_by_email(args.email)
        elif args.command == 'delete':
            if not args.id:
                print("❌ Se requiere --id para eliminar usuario")
                return
            delete_user_by_id(args.id, args.force)
        elif args.command == 'count':
            count_users()
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    main() 