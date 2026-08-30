import secrets
import string
from typing import Any

from sqlalchemy.orm import Session

from app.config.logging_config import get_logger
from app.config.settings import Settings
from app.core.security import get_password_hash
from app.models.user import User
from app.services.email_service import email_service
from app.services.source_system_service import source_system_service
from app.utils.timezone import get_ve_now

settings = Settings()
class SourceSystemUserCreationService:
    """Servicio para crear usuarios desde SourceSystem y enviarles passwords"""
    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger("source_system_user_creation")

    def generate_temporary_password(self, length: int = 12) -> str:
        alphabet = string.ascii_letters + string.digits + "!@#$%&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        return password

    async def create_user_from_source_system(
        self,
        customer_code: str,
        use_alternate_email: bool = False
    ) -> dict[str, Any]:
        try:
            # Validar que el código de cliente no esté vacío
            if not customer_code or not customer_code.strip():
                raise ValueError("El código de cliente no puede estar vacío")
            
            customer_code = customer_code.strip()
            self.logger.info(f"Verificando existencia del cliente {customer_code} en SourceSystem")
            
            # Verificar que el cliente exista en SourceSystem ANTES de continuar
            try:
                source_customer = source_system_service.get_customer_by_code(customer_code)
            except Exception as e:
                error_msg = f"Error al consultar SourceSystem para el cliente {customer_code}: {e!s}"
                self.logger.error(error_msg)
                raise ValueError(f"No se pudo verificar el cliente en SourceSystem. Error de conexión: {e!s}")
            
            if not source_customer:
                error_msg = f"Cliente {customer_code} no encontrado en SourceSystem. Verifique que el código sea correcto."
                self.logger.warning(error_msg)
                raise ValueError(error_msg)
            
            self.logger.info(f"Cliente {customer_code} encontrado en SourceSystem: {source_customer.get('customer_name', 'N/A')}")
            # Email principal o alterno
            email = None
            if use_alternate_email and source_customer.get('alternate_email'):
                email = source_customer['alternate_email']
            elif source_customer.get('email'):
                email = source_customer['email']
            elif source_customer.get('alternate_email'):
                email = source_customer['alternate_email']
            if not email or email.strip() == '':
                raise ValueError(f"Cliente {customer_code} no tiene email válido")
            email = email.strip().lower()
            # Generar contraseña temporal
            temp_password = self.generate_temporary_password()
            hashed_password = get_password_hash(temp_password)
            
            # Verificar si el usuario ya existe en la base de datos local
            existing_user = self.db.query(User).filter(User.email == email).first()
            
            if existing_user:
                # Usuario ya existe en BD local: actualizar contraseña solo en BD local
                # PERO primero debemos enviar el email antes de hacer commit
                customer_name = source_customer.get('customer_name', 'Cliente')
                
                # Intentar enviar el email PRIMERO, antes de actualizar la BD
                try:
                    self.logger.info(f"Enviando email con contraseña temporal a {email}")
                    await email_service.send_email(
                        to_email=email,
                        subject="Nueva contraseña temporal - FarmaPlus",
                        template_name="source_system_account_created.html",
                        context={
                            "customer_name": customer_name,
                            "email": email,
                            "temporary_password": temp_password,
                            "login_url": f"{settings.app.FRONTEND_URL}/login",
                            "change_password_url": f"{settings.app.FRONTEND_URL}/change-password",
                            "year": get_ve_now().year,
                        }
                    )
                    self.logger.info(f"Email enviado exitosamente a {email}")
                except Exception as e:
                    email_error = str(e)
                    self.logger.error(f"Error enviando email a {email}: {email_error}")
                    # Si el email falla, NO actualizamos la contraseña
                    raise ValueError(f"No se pudo enviar el email con la contraseña temporal. El usuario no fue actualizado. Error: {email_error}")
                
                # Solo si el email se envió exitosamente, actualizamos la contraseña
                existing_user.hashed_password = hashed_password
                self.db.commit()
                self.db.refresh(existing_user)
                
                return {
                    "success": True,
                    "user_id": existing_user.id,
                    "email": email,
                    "customer_code": customer_code,
                    "customer_name": customer_name,
                    "email_sent": True,
                    "email_error": None,
                    "temporary_password": temp_password,
                    "error": None
                }
            user_type = 'juridico' if source_customer.get('is_juridico') else 'natural'
            user_data = {
                "email": email,
                "hashed_password": hashed_password,
                "user_type": user_type,
                "phone": source_customer.get('phones', '') or 'N/A',
                "is_active": True,
                "is_verified": True,
                "role": "user",
                "company_name": source_customer.get('customer_name') if user_type == 'juridico' else None,
                "rif": source_customer.get('rif') if source_customer.get('rif') else None,
                "address": source_customer.get('address1') or source_customer.get('address2') or None,
            }
            if user_type == 'natural' and source_customer.get('customer_name'):
                name_parts = source_customer['customer_name'].split(maxsplit=1)
                if len(name_parts) >= 2:
                    user_data["first_name"] = name_parts[0]
                    user_data["last_name"] = name_parts[1]
                else:
                    user_data["first_name"] = name_parts[0]
            # Preparar el usuario pero NO hacer commit aún
            new_user = User(**user_data)
            self.db.add(new_user)
            self.db.flush()  # Para obtener el ID sin commit
            
            # Intentar enviar el email PRIMERO, antes de hacer commit
            try:
                self.logger.info(f"Enviando email con contraseña temporal a {email}")
                await email_service.send_email(
                    to_email=email,
                    subject="Bienvenido a FarmaPlus - Tu cuenta ha sido creada",
                    template_name="source_system_account_created.html",
                    context={
                        "customer_name": source_customer.get('customer_name', 'Cliente'),
                        "email": email,
                        "temporary_password": temp_password,
                        "login_url": f"{settings.app.FRONTEND_URL}/login",
                        "change_password_url": f"{settings.app.FRONTEND_URL}/change-password",
                        "year": get_ve_now().year,
                    }
                )
                self.logger.info(f"Email enviado exitosamente a {email}")
            except Exception as e:
                email_error = str(e)
                self.logger.error(f"Error enviando email a {email}: {email_error}")
                # Si el email falla, hacemos rollback y NO creamos el usuario
                self.db.rollback()
                raise ValueError(f"No se pudo enviar el email con la contraseña temporal. El usuario no fue creado. Error: {email_error}")
            
            # Solo si el email se envió exitosamente, hacemos commit
            self.db.commit()
            self.db.refresh(new_user)
            return {
                "success": True,
                "user_id": new_user.id,
                "email": email,
                "customer_code": customer_code,
                "customer_name": source_customer.get('customer_name'),
                "email_sent": True,
                "email_error": None,
                "temporary_password": temp_password,
                "error": None
            }
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error creando usuario desde SourceSystem {customer_code}: {e!s}")
            return {
                "success": False,
                "error": str(e),
                "customer_code": customer_code,
                "customer_name": None,
                "email": None,
                "user_id": None,
                "email_sent": None,
                "email_error": None
            }

    async def create_multiple_users_from_source_system(
        self,
        customer_codes: list[str],
        use_alternate_emails: bool = False
    ) -> dict[str, Any]:
        results = {
            "total": len(customer_codes),
            "successful": [],
            "failed": []
        }
        for code in customer_codes:
            result = await self.create_user_from_source_system(code, use_alternate_emails)
            if result["success"]:
                results["successful"].append(result)
            else:
                results["failed"].append(result)
        return results
