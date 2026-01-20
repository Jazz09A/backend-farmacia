from typing import Dict, Any
from app.config.settings import Settings
from app.config.logging_config import get_logger
import os
from jinja2 import Environment, FileSystemLoader
from app.utils.timezone import get_ve_now
import resend


settings = Settings()


class EmailService:
    def __init__(self):
        self.resend_api_key = settings.RESEND_API_KEY
        self.from_email = settings.EMAIL_FROM
        self.from_name = settings.EMAIL_FROM_NAME
        self.email_logger = get_logger("email")
        
        # Setup Jinja2 for HTML templates
        self.template_env = Environment(
            loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), '..', 'templates', 'emails'))
        )
        # Verificar configuración
        if not self.resend_api_key:
            self.email_logger.error("RESEND_API_KEY not configured - emails will fail")
            raise ValueError("RESEND_API_KEY not configured in environment variables")
        
        # Configurar Resend
        resend.api_key = self.resend_api_key
        self.email_logger.info("Email service initialized with Resend API")

    def _render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """Renders an email template with the given context."""
        template = self.template_env.get_template(template_name)
        return template.render(context)

    async def send_email(self, to_email: str, subject: str, template_name: str, context: Dict[str, Any]):
        """
        Envía un email usando Resend API.
        
        Args:
            to_email: Destinatario
            subject: Asunto del email
            template_name: Nombre del template HTML (ej: 'welcome.html')
            context: Variables para el template
        """
        self.email_logger.info(
            f"📧 Sending email to {to_email}",
            extra={
                'to_email': to_email,
                'user_email': to_email,
                'subject': subject,
                'template': template_name,
                'event': 'email_send_attempt'
            }
        )
        
        # Verificar que está configurado
        if not self.resend_api_key:
            self.email_logger.error(
                "❌ Cannot send email - RESEND_API_KEY not configured",
                extra={
                    'to_email': to_email,
                    'template': template_name,
                    'event': 'email_send_failed'
                }
            )
            raise ValueError("RESEND_API_KEY not configured in environment variables")
        
        try:
            # Render HTML template
            html_body = self._render_template(template_name, context)
            
            # Preparar parámetros para Resend
            params = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [settings.EMAIL_TEST],
                "subject": subject,
                "html": html_body,
            }
            
            # Enviar email
            response = resend.Emails.send(params)
            
            # Log éxito
            self.email_logger.info(
                "✅ Email sent successfully",
                extra={
                    'to_email': to_email,
                    'user_email': to_email,
                    'subject': subject,
                    'template': template_name,
                    'email_id': response.get('id') if isinstance(response, dict) else str(response),
                    'event': 'email_sent_successfully'
                }
            )
            
        except Exception as e:
            self.email_logger.error(
                f"❌ Failed to send email: {str(e)}",
                extra={
                    'to_email': to_email,
                    'user_email': to_email,
                    'subject': subject,
                    'template': template_name,
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'event': 'email_send_failed'
                }
            )
            raise

    async def send_order_tracking_email(self, to_email: str, order_data: Dict[str, Any]):
        """
        Sends an order tracking email when a customer completes their order successfully.
        
        Args:
            to_email: Customer's email address
            order_data: Dictionary containing order information
        """
        current_time = get_ve_now()
        context = {
            "order_number": order_data.get("order_number", "N/A"),
            "order_date": order_data.get("order_date", current_time.strftime("%d/%m/%Y %H:%M")),
            "order_total": order_data.get("order_total", "N/A"),
            "order_status": order_data.get("order_status", "Confirmada"),
            "payment_method": order_data.get("payment_method", "N/A"),
            "estimated_delivery": order_data.get("estimated_delivery"),
            "tracking_link": order_data.get("tracking_link", "#"),
            "year": current_time.year
        }
        
        subject = f"Tu orden #{order_data.get('order_number', 'N/A')} ha sido confirmada - Tracking disponible"
        
        await self.send_email(
            to_email=to_email,
            subject=subject,
            template_name="order_tracking.html",
            context=context
        )

    async def send_payment_registered_email(self, to_email: str, payment_data: Dict[str, Any]):
        """Enviar email de pago registrado"""
        context = {
            "user_name": payment_data.get("user_name", "Usuario"),
            "amount": payment_data.get("amount", 0),
            "currency": payment_data.get("currency", "USD"),
            "order_number": payment_data.get("order_number", "N/A"),
            "payment_reference": payment_data.get("payment_reference", "N/A"),
            "payment_date": payment_data.get("payment_date", "N/A"),
            "year": get_ve_now().year
        }
        
        subject = f"Pago registrado - Orden #{payment_data.get('order_number', 'N/A')} - FarmaPlus"
        
        await self.send_email(
            to_email=to_email,
            subject=subject,
            template_name="payment_registered.html",
            context=context
        )

    async def send_payment_approved_email(self, to_email: str, payment_data: Dict[str, Any]):
        """Enviar email de pago aprobado"""
        context = {
            "user_name": payment_data.get("user_name", "Usuario"),
            "amount": payment_data.get("amount", 0),
            "currency": payment_data.get("currency", "USD"),
            "order_number": payment_data.get("order_number", "N/A"),
            "order_total": payment_data.get("order_total", 0),
            "paid_total": payment_data.get("paid_total", 0),
            "remaining_balance": payment_data.get("remaining_balance", 0),
            "year": get_ve_now().year
        }
        
        subject = f"¡Pago aprobado! - Orden #{payment_data.get('order_number', 'N/A')} - FarmaPlus"
        
        await self.send_email(
            to_email=to_email,
            subject=subject,
            template_name="payment_approved.html",
            context=context
        )

    async def send_payment_rejected_email(self, to_email: str, payment_data: Dict[str, Any]):
        """Enviar email de pago rechazado"""
        context = {
            "user_name": payment_data.get("user_name", "Usuario"),
            "amount": payment_data.get("amount", 0),
            "currency": payment_data.get("currency", "USD"),
            "order_number": payment_data.get("order_number", "N/A"),
            "admin_notes": payment_data.get("admin_notes", "No se proporcionó motivo específico"),
            "year": get_ve_now().year
        }
        
        subject = f"Pago rechazado - Orden #{payment_data.get('order_number', 'N/A')} - FarmaPlus"
        
        await self.send_email(
            to_email=to_email,
            subject=subject,
            template_name="payment_rejected.html",
            context=context
        )

    async def send_verification_email(self, to_email: str, verification_data: Dict[str, Any]):
        """Enviar email de verificación de correo electrónico"""
        context = {
            "verification_link": verification_data.get("verification_link", "#"),
            "year": get_ve_now().year
        }
        
        subject = "Verifica tu correo electrónico - FarmaPlus"
        
        await self.send_email(
            to_email=to_email,
            subject=subject,
            template_name="verify_email.html",
            context=context
        )

    async def send_password_reset_email(self, to_email: str, reset_link: str, user_name: str = "Usuario"):
        """Enviar email de recuperación de contraseña"""
        context = {
            "reset_link": reset_link,
            "user_name": user_name,
            "year": get_ve_now().year
        }
        
        subject = "Recuperación de contraseña - Grupo Drozainka"
        
        await self.send_email(
            to_email=to_email,
            subject=subject,
            template_name="password_reset.html",
            context=context
        )


# Singleton instance
email_service = EmailService()
