#!/usr/bin/env python3
"""
Script para gestionar usuarios de la base de datos
Permite listar, ver detalles y eliminar usuarios
"""

import sys
import os
from datetime import datetime
from typing import List, Optional

# Agregar el directorio raíz al path para importar módulos de la app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from app.config.database import SessionLocal
from app.models.user import User

class UserManager:
    def __init__(self):
        self.db: Session = SessionLocal()
        
    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()
    
    def get_all_users(self) -> List[User]:
        """Obtener todos los usuarios de la base de datos"""
        return self.db.query(User).all()
    
    def format_user_info(self, user: User, index: int) -> str:
        """Formatear información del usuario para mostrar"""
        # Nombre según tipo de usuario
        if user.user_type == 'natural':
            name = f"{user.first_name} {user.last_name}" if user.first_name and user.last_name else "N/A"
        else:
            name = user.company_name or "N/A"
        
        # Status
        status = "✅ Activo" if user.is_active else "❌ Inactivo"
        verified = "✅ Verificado" if user.is_verified else "❌ No verificado"
        
        # Fecha de creación
        created = user.created_at.strftime("%Y-%m-%d %H:%M") if user.created_at else "N/A"
        last_login = user.last_login.strftime("%Y-%m-%d %H:%M") if user.last_login else "Nunca"
        
        return f"""[{index}] {name}
    📧 Email: {user.email}
    👤 Tipo: {user.user_type.title()}
    🔑 Rol: {user.role}
    📱 Teléfono: {user.phone}
    {status} | {verified}
    📅 Creado: {created}
    🔄 Último login: {last_login}
    🆔 ID: {user.id}"""
    
    def show_user_details(self, user: User):
        """Mostrar detalles completos de un usuario"""
        print(f"\n{'='*60}")
        print(f"DETALLES DEL USUARIO")
        print(f"{'='*60}")
        
        # Información básica
        print(f"🆔 ID: {user.id}")
        print(f"📧 Email: {user.email}")
        print(f"👤 Tipo: {user.user_type.title()}")
        print(f"🔑 Rol: {user.role}")
        print(f"📱 Teléfono: {user.phone}")
        print(f"💰 Moneda preferida: {user.preferred_currency}")
        
        # Status
        status = "✅ Activo" if user.is_active else "❌ Inactivo"
        verified = "✅ Verificado" if user.is_verified else "❌ No verificado"
        print(f"📊 Estado: {status}")
        print(f"🔐 Verificación: {verified}")
        
        # Información específica según tipo
        if user.user_type == 'natural':
            print(f"\n--- INFORMACIÓN PERSONAL ---")
            print(f"👤 Nombre: {user.first_name} {user.last_name}")
            print(f"🆔 Cédula: {user.cedula or 'N/A'}")
            print(f"🎂 Fecha nacimiento: {user.birth_date or 'N/A'}")
            print(f"📍 Dirección: {user.address or 'N/A'}")
        else:
            print(f"\n--- INFORMACIÓN EMPRESA ---")
            print(f"🏢 Empresa: {user.company_name or 'N/A'}")
            print(f"📋 RIF: {user.rif or 'N/A'}")
            print(f"📄 Registro Mercantil: {user.registro_mercantil or 'N/A'}")
            print(f"👨‍💼 Rep. Legal: {user.representante_legal_nombre or 'N/A'}")
            print(f"🆔 Cédula Rep.: {user.representante_legal_cedula or 'N/A'}")
            print(f"📍 Dirección establecimiento: {user.direccion_establecimiento or 'N/A'}")
            
            if user.codigo_sicm:
                print(f"🏥 Código SICM: {user.codigo_sicm}")
            if user.pagina_web:
                print(f"🌐 Página web: {user.pagina_web}")
            if user.redes_sociales:
                print(f"📱 Redes sociales: {user.redes_sociales}")
        
        # Fechas
        print(f"\n--- FECHAS ---")
        print(f"📅 Creado: {user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else 'N/A'}")
        print(f"🔄 Actualizado: {user.updated_at.strftime('%Y-%m-%d %H:%M:%S') if user.updated_at else 'N/A'}")
        print(f"🔑 Último login: {user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else 'Nunca'}")
        
    def list_users(self):
        """Listar todos los usuarios"""
        users = self.get_all_users()
        
        if not users:
            print("❌ No hay usuarios registrados en la base de datos.")
            return []
        
        print(f"\n{'='*80}")
        print(f"📋 USUARIOS REGISTRADOS ({len(users)} total)")
        print(f"{'='*80}")
        
        for i, user in enumerate(users):
            print(self.format_user_info(user, i))
            print("-" * 80)
        
        return users
    
    def delete_user(self, user: User) -> bool:
        """Eliminar un usuario de la base de datos"""
        try:
            # Mostrar detalles antes de eliminar
            self.show_user_details(user)
            
            print(f"\n{'⚠️ '*20}")
            print(f"ADVERTENCIA: Esta acción eliminará permanentemente el usuario y todos sus datos relacionados:")
            print(f"- Direcciones")
            print(f"- Órdenes de compra")
            print(f"- Reseñas")
            print(f"- Carrito de compras")
            print(f"- Preferencias")
            print(f"- Tickets de soporte")
            print(f"- Notificaciones")
            print(f"- Posts de blog")
            print(f"- Favoritos")
            print(f"{'⚠️ '*20}")
            
            # Triple confirmación
            confirm1 = input(f"\n¿Estás SEGURO que quieres eliminar a '{user.display_name}'? (escribe 'ELIMINAR'): ").strip()
            if confirm1 != 'ELIMINAR':
                print("❌ Operación cancelada.")
                return False
            
            confirm2 = input(f"¿REALMENTE quieres eliminar PERMANENTEMENTE este usuario? (escribe 'SI'): ").strip().upper()
            if confirm2 != 'SI':
                print("❌ Operación cancelada.")
                return False
            
            confirm3 = input(f"Última confirmación. Escribe el email del usuario para confirmar: ").strip()
            if confirm3 != user.email:
                print("❌ Email incorrecto. Operación cancelada.")
                return False
            
            # Proceder con la eliminación
            print(f"\n🗑️ Eliminando usuario...")
            self.db.delete(user)
            self.db.commit()
            
            print(f"✅ Usuario '{user.display_name}' eliminado exitosamente.")
            return True
            
        except Exception as e:
            self.db.rollback()
            print(f"❌ Error al eliminar usuario: {str(e)}")
            return False
    
    def run(self):
        """Ejecutar el gestor de usuarios"""
        print(f"""
{'='*60}
🔧 GESTOR DE USUARIOS - FarmaPlus
{'='*60}
Este script permite gestionar usuarios de la base de datos.
Funciones disponibles:
- Listar usuarios
- Ver detalles de usuarios  
- Eliminar usuarios (con confirmación)
{'='*60}
""")
        
        while True:
            try:
                # Listar usuarios
                users = self.list_users()
                
                if not users:
                    break
                
                print(f"\n📋 OPCIONES:")
                print(f"- Ingresa el ÍNDICE [0-{len(users)-1}] para VER DETALLES y opcionalmente ELIMINAR")
                print(f"- 'r' para REFRESCAR lista")
                print(f"- 'q' para SALIR")
                
                choice = input(f"\n👉 Elige una opción: ").strip().lower()
                
                if choice == 'q':
                    print("👋 ¡Hasta luego!")
                    break
                elif choice == 'r':
                    continue
                elif choice.isdigit():
                    index = int(choice)
                    if 0 <= index < len(users):
                        selected_user = users[index]
                        
                        # Mostrar detalles
                        self.show_user_details(selected_user)
                        
                        # Opciones para el usuario seleccionado
                        print(f"\n📋 OPCIONES PARA ESTE USUARIO:")
                        print(f"- 'd' para ELIMINAR este usuario")
                        print(f"- ENTER para volver al menú principal")
                        
                        action = input(f"\n👉 ¿Qué quieres hacer? ").strip().lower()
                        
                        if action == 'd':
                            self.delete_user(selected_user)
                            input("\nPresiona ENTER para continuar...")
                        
                    else:
                        print(f"❌ Índice inválido. Debe estar entre 0 y {len(users)-1}")
                else:
                    print("❌ Opción inválida.")
                
            except KeyboardInterrupt:
                print(f"\n\n👋 ¡Hasta luego!")
                break
            except Exception as e:
                print(f"❌ Error inesperado: {str(e)}")


def main():
    """Función principal"""
    try:
        manager = UserManager()
        manager.run()
    except Exception as e:
        print(f"❌ Error fatal: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main() 