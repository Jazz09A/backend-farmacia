import secrets
import string
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.user import User
from app.core.security import get_password_hash
from app.services.source_system_service import source_system_service
from app.services.email_service import email_service
from app.config.logging_config import get_logger
from datetime import datetime
from app.config.settings import Settings
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
    ) -> Dict[str, Any]:
        try:
            source_customer = source_system_service.get_customer_by_code(customer_code)
            if not source_customer:
                raise ValueError(f"Cliente {customer_code} no encontrado en SourceSystem")
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
            
            # Actualizar contraseña en SourceSystem (base de datos principal)
            try:
                source_system_service.update_customer_password(customer_code, hashed_password)
                self.logger.info(f"Contraseña actualizada en SourceSystem para {customer_code}")
            except Exception as e:
                self.logger.error(f"Error actualizando contraseña en SourceSystem: {str(e)}")
                raise ValueError(f"No se pudo actualizar la contraseña en SourceSystem: {str(e)}")
            
            # Verificar si el usuario ya existe en la base de datos local (temporal)
            existing_user = self.db.query(User).filter(User.email == email).first()
            
            if existing_user:
                # Usuario ya existe en BD local: actualizar contraseña también aquí
                existing_user.hashed_password = hashed_password
                self.db.flush()
                
                customer_name = source_customer.get('customer_name', 'Cliente')
                email_sent = False
                email_error = None
                
                try:
                    await email_service.send_email(
                        to_email=email,
                        subject="Nueva contraseña temporal - FarmaPlus",
                        template_name="source_system_account_created.html",
                        context={
                            "customer_name": customer_name,
                            "email": email,
                            "temporary_password": temp_password,
                            "login_url": f"{settings.FRONTEND_URL}/login",
                            "change_password_url": f"{settings.FRONTEND_URL}/change-password",
                            "year": datetime.now().year,
                        }
                    )
                    email_sent = True
                except Exception as e:
                    email_error = str(e)
                    self.logger.error(f"Error enviando email a {email}: {email_error}")
                
                self.db.commit()
                self.db.refresh(existing_user)
                
                return {
                    "success": True,
                    "user_id": existing_user.id,
                    "email": email,
                    "customer_code": customer_code,
                    "customer_name": customer_name,
                    "email_sent": email_sent,
                    "email_error": email_error,
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
            new_user = User(**user_data)
            self.db.add(new_user)
            self.db.flush()  # Para obtener el ID sin commit
            email_sent = False
            email_error = None
            try:
                await email_service.send_email(
                    to_email=email,
                    subject="Bienvenido a FarmaPlus - Tu cuenta ha sido creada",
                    template_name="source_system_account_created.html",
                    context={
                        "customer_name": source_customer.get('customer_name', 'Cliente'),
                        "email": email,
                        "temporary_password": temp_password,
                        "login_url": f"{settings.FRONTEND_URL}/login",
                        "change_password_url": f"{settings.FRONTEND_URL}/change-password",
                        "year": datetime.now().year,
                    }
                )
                email_sent = True
            except Exception as e:
                email_error = str(e)
                self.logger.error(f"Error enviando email a {email}: {email_error}")
            self.db.commit()
            self.db.refresh(new_user)
            return {
                "success": True,
                "user_id": new_user.id,
                "email": email,
                "customer_code": customer_code,
                "customer_name": source_customer.get('customer_name'),
                "email_sent": email_sent,
                "email_error": email_error,
                "temporary_password": temp_password,
                "error": None
            }
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error creando usuario desde SourceSystem {customer_code}: {str(e)}")
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
        customer_codes: List[str],
        use_alternate_emails: bool = False
    ) -> Dict[str, Any]:
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
