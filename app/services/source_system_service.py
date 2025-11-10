import pymssql
from typing import List, Optional, Dict, Any
from app.config.settings import Settings
from app.config.logging_config import get_logger

settings = Settings()
class SourceSystemService:
    """Servicio para conectar y consultar la base de datos SourceSystem"""
    def __init__(self):
        self.logger = get_logger("source_system")
        self.server = settings.SOURCE_SYSTEM_SERVER
        self.port = settings.SOURCE_SYSTEM_PORT
        self.database = settings.SOURCE_SYSTEM_DATABASE
        # Limpiar espacios en blanco de usuario y contraseña para evitar errores de autenticación
        self.user = settings.SOURCE_SYSTEM_USER.strip() if settings.SOURCE_SYSTEM_USER else None
        self.password = settings.SOURCE_SYSTEM_PASSWORD.strip() if settings.SOURCE_SYSTEM_PASSWORD else None

    def get_connection(self):
        try:
            # Validar que los parámetros básicos estén configurados
            if not self.server:
                raise ValueError("SOURCE_SYSTEM_SERVER no está configurado")
            if not self.database:
                raise ValueError("SOURCE_SYSTEM_DATABASE no está configurado")
            
            connect_kwargs = {
                "server": self.server.strip() if isinstance(self.server, str) else self.server,
                "port": self.port,
                "database": self.database.strip() if isinstance(self.database, str) else self.database,
                "as_dict": True,
                "login_timeout": 15,  # Segundos para establecer conexión
                "timeout": 30,        # Segundos para queries
            }
            # Solo agregar credenciales si están configuradas
            # Asegurar que se limpien espacios en blanco
            if self.user and self.password:
                user_clean = self.user.strip() if isinstance(self.user, str) else self.user
                password_clean = self.password.strip() if isinstance(self.password, str) else self.password
                
                if not user_clean or not password_clean:
                    self.logger.warning("Usuario o contraseña están vacíos después de limpiar espacios")
                else:
                    connect_kwargs["user"] = user_clean
                    connect_kwargs["password"] = password_clean
                    self.logger.debug(f"Conectando con usuario: {user_clean[:3]}*** (longitud: {len(user_clean)})")
            
            self.logger.debug(f"Conectando a {connect_kwargs['server']}:{connect_kwargs['port']}/{connect_kwargs['database']}")
            conn = pymssql.connect(**connect_kwargs)
            self.logger.info("Conexión a SourceSystem establecida exitosamente")
            return conn
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Error conectando a SourceSystem: {error_msg}")
            
            # Proporcionar información adicional para debugging
            if "18456" in error_msg:
                self.logger.error("Error 18456: Fallo de autenticación. Verificar usuario y contraseña.")
            if "20002" in error_msg:
                self.logger.error("Error 20002: No se pudo conectar al servidor. Verificar conectividad de red.")
            
            raise

    def get_all_customers(
        self,
        include_inactive: bool = False,
        only_with_email: bool = True,
        limit: int = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            query = """
            SELECT 
                co_cli AS customer_code,
                cli_des AS customer_name,
                email,
                email_alterno AS alternate_email,
                rif,
                telefonos AS phones,
                direc1 AS address1,
                direc2 AS address2,
                inactivo AS inactive,
                juridico AS is_juridico,
                fecha_reg AS registration_date
            FROM saCliente
            WHERE 1=1
            """

            if not include_inactive:
                query += " AND inactivo = 0"
            if only_with_email:
                query += " AND (email IS NOT NULL AND email != '' OR email_alterno IS NOT NULL AND email_alterno != '')"
                
            query += " ORDER BY cli_des"

            if limit:
                query += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"

            cursor.execute(query)
            customers = cursor.fetchall()

            cursor.close()
            conn.close()

            return customers
        except Exception as e:
            self.logger.error(f"Error obteniendo clientes de SourceSystem: {str(e)}")
            raise

    def get_customer_by_code(self, customer_code: str) -> Optional[Dict[str, Any]]:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            query = """
            SELECT 
                co_cli AS customer_code,
                cli_des AS customer_name,
                email,
                email_alterno AS alternate_email,
                rif,
                telefonos AS phones,
                direc1 AS address1,
                direc2 AS address2,
                inactivo AS inactive,
                juridico AS is_juridico,
                fecha_reg AS registration_date
            FROM saCliente
            WHERE co_cli = %s
            """
            cursor.execute(query, (customer_code,))
            customer = cursor.fetchone()
            cursor.close()
            conn.close()
            return customer
        except Exception as e:
            self.logger.error(f"Error obteniendo cliente {customer_code}: {str(e)}")
            raise

    def get_customer_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            query = """
            SELECT 
                co_cli AS customer_code,
                cli_des AS customer_name,
                email,
                email_alterno AS alternate_email,
                rif,
                telefonos AS phones,
                direc1 AS address1,
                direc2 AS address2,
                inactivo AS inactive,
                juridico AS is_juridico,
                fecha_reg AS registration_date
            FROM saCliente
            WHERE email = %s OR email_alterno = %s
            """
            cursor.execute(query, (email, email))
            customer = cursor.fetchone()
            cursor.close()
            conn.close()
            return customer
        except Exception as e:
            self.logger.error(f"Error obteniendo cliente por email {email}: {str(e)}")
            raise

    def update_customer_password(self, customer_code: str, hashed_password: str) -> bool:
        """
        Actualiza la contraseña de un cliente en SourceSystem
        
        Args:
            customer_code: Código del cliente
            hashed_password: Contraseña hasheada
            
        Returns:
            bool: True si se actualizó correctamente
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            query = """
            UPDATE saCliente
            SET password = %s
            WHERE co_cli = %s
            """
            
            cursor.execute(query, (hashed_password, customer_code))
            conn.commit()
            
            rows_affected = cursor.rowcount
            cursor.close()
            conn.close()
            
            if rows_affected > 0:
                self.logger.info(f"Contraseña actualizada para cliente {customer_code}")
                return True
            else:
                self.logger.warning(f"No se encontró cliente {customer_code} para actualizar")
                return False
                
        except Exception as e:
            self.logger.error(f"Error actualizando contraseña para cliente {customer_code}: {str(e)}")
            raise

# Singleton instance
source_system_service = SourceSystemService()
