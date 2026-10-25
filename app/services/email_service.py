import os
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any

from jinja2 import Environment, FileSystemLoader

from app.config.logging_config import get_logger, log_error
from app.config.settings import Settings
from app.utils.timezone import get_ve_now

settings = Settings()


class EmailService:
    def __init__(self):
        self.smtp_server = settings.smtp.HOST
        self.smtp_port = settings.smtp.PORT
        self.smtp_user = settings.smtp.USER
        self.smtp_password = settings.smtp.PASSWORD
        self.from_email = settings.smtp.FROM
        self.from_name = settings.smtp.FROM_NAME
        self.email_logger = get_logger("email")
        self.error_logger = get_logger("errors")

        # Setup Jinja2 for HTML templates
        self.template_env = Environment(
            loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "..", "templates", "emails"))
        )

    def _render_template(self, template_name: str, context: dict[str, Any]) -> str:
        """Renders an email template with the given context."""
        template = self.template_env.get_template(template_name)
        return template.render(context)

    async def send_email(self, to_email: str, subject: str, template_name: str, context: dict[str, Any]):
        """
        Sends an email using an HTML template.
        """
        self.email_logger.info(
            "Attempting to send email",
            extra={
                "to_email": to_email,
                "user_email": to_email,  # El destinatario es el usuario
                "subject": subject,
                "template": template_name,
                "event": "email_send_attempt",
            },
        )

        if not all([self.smtp_server, self.smtp_port, self.smtp_user, self.smtp_password, self.from_email]):
            self.email_logger.error(
                "Email service not configured - missing SMTP settings",
                extra={
                    "to_email": to_email,
                    "user_email": to_email,
                    "template": template_name,
                    "reason": "smtp_not_configured",
                    "event": "email_send_failed",
                },
            )
            return

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = formataddr((str(Header(self.from_name, "utf-8")), self.from_email))
        message["To"] = to_email

        # Render the HTML content from the template
        html_body = self._render_template(template_name, context)

        # Attach the HTML part
        message.attach(MIMEText(html_body, "html"))

        try:
            # Configurar timeout más corto para fallar rápido en caso de problemas de red
            self.email_logger.info(
                f"Connecting to SMTP server: {self.smtp_server}:{self.smtp_port}",
                extra={
                    "smtp_server": self.smtp_server,
                    "smtp_port": self.smtp_port,
                    "to_email": to_email,
                    "event": "smtp_connection_attempt",
                },
            )

            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                self.email_logger.info("SMTP connection established, starting TLS...")

                server.starttls()  # Secure the connection
                self.email_logger.info("TLS started, attempting login...")

                server.login(self.smtp_user, self.smtp_password)
                self.email_logger.info("Login successful, sending email...")

                server.sendmail(self.from_email, to_email, message.as_string())

                self.email_logger.info(
                    "Email sent successfully",
                    extra={
                        "to_email": to_email,
                        "user_email": to_email,
                        "subject": subject,
                        "template": template_name,
                        "event": "email_sent_successfully",
                    },
                )
        except (TimeoutError, OSError) as e:
            # Errores de red - logear con más detalles y relanzar el error
            error_details = {
                "to_email": to_email,
                "user_email": to_email,
                "subject": subject,
                "template": template_name,
                "error_type": "network_error",
                "error_class": type(e).__name__,
                "error_message": str(e),
                "smtp_server": self.smtp_server,
                "smtp_port": self.smtp_port,
                "event": "email_send_network_error",
            }

            # Agregar información específica del error
            if hasattr(e, "errno"):
                error_details["error_errno"] = e.errno
            if hasattr(e, "strerror"):
                error_details["error_strerror"] = e.strerror

            self.email_logger.error(f"Network error sending email - {type(e).__name__}: {e!s}", extra=error_details)

            # Log adicional con traceback completo para debugging
            import traceback

            self.email_logger.debug(
                f"Full traceback for network error:\n{traceback.format_exc()}",
                extra={"to_email": to_email, "event": "email_network_error_traceback"},
            )

            # Relanzar el error para que el código que llama pueda manejarlo
            raise
        except smtplib.SMTPException as e:
            # Errores SMTP específicos
            log_error(
                self.error_logger,
                e,
                context={
                    "to_email": to_email,
                    "subject": subject,
                    "template": template_name,
                    "operation": "email_sending",
                    "error_type": "smtp_error",
                },
                user_email=to_email,
            )
            self.email_logger.error(
                "SMTP error sending email",
                extra={
                    "to_email": to_email,
                    "user_email": to_email,
                    "subject": subject,
                    "template": template_name,
                    "error": str(e),
                    "event": "email_send_smtp_error",
                },
            )
            # Relanzar el error para que el código que llama pueda manejarlo
            raise
        except Exception as e:
            log_error(
                self.error_logger,
                e,
                context={
                    "to_email": to_email,
                    "subject": subject,
                    "template": template_name,
                    "operation": "email_sending",
                },
                user_email=to_email,
            )
            self.email_logger.error(
                "Failed to send email",
                extra={
                    "to_email": to_email,
                    "user_email": to_email,
                    "subject": subject,
                    "template": template_name,
                    "error": str(e),
                    "event": "email_send_failed",
                },
            )
            # Relanzar el error para que el código que llama pueda manejarlo
            raise

    async def send_order_tracking_email(self, to_email: str, order_data: dict[str, Any]):
        """
        Sends an order tracking email when a customer completes their order successfully.

        Args:
            to_email: Customer's email address
            order_data: Dictionary containing order information with keys:
                - order_number: Order ID/number
                - order_date: Date when order was placed
                - order_total: Total amount of the order
                - order_status: Current status of the order
                - payment_method: Payment method used
                - estimated_delivery: Estimated delivery date (optional)
                - tracking_link: URL to the order tracking page
        """
        # Prepare context for the template
        current_time = get_ve_now()
        context = {
            "order_number": order_data.get("order_number", "N/A"),
            "order_date": order_data.get("order_date", current_time.strftime("%d/%m/%Y %H:%M")),
            "order_total": order_data.get("order_total", "N/A"),
            "order_status": order_data.get("order_status", "Confirmada"),
            "payment_method": order_data.get("payment_method", "N/A"),
            "estimated_delivery": order_data.get("estimated_delivery"),
            "tracking_link": order_data.get("tracking_link", "#"),
            "year": current_time.year,
        }

        subject = f"Tu orden #{order_data.get('order_number', 'N/A')} ha sido confirmada - Tracking disponible"

        await self.send_email(to_email=to_email, subject=subject, template_name="order_tracking.html", context=context)

    async def send_payment_registered_email(self, to_email: str, payment_data: dict[str, Any]):
        """Enviar email de pago registrado"""
        context = {
            "user_name": payment_data.get("user_name", "Usuario"),
            "amount": payment_data.get("amount", 0),
            "currency": payment_data.get("currency", "USD"),
            "order_number": payment_data.get("order_number", "N/A"),
            "payment_reference": payment_data.get("payment_reference", "N/A"),
            "payment_date": payment_data.get("payment_date", "N/A"),
            "year": get_ve_now().year,
        }

        subject = f"Pago registrado - Orden #{payment_data.get('order_number', 'N/A')} - FarmaPlus"

        await self.send_email(
            to_email=to_email, subject=subject, template_name="payment_registered.html", context=context
        )

    async def send_payment_approved_email(self, to_email: str, payment_data: dict[str, Any]):
        """Enviar email de pago aprobado"""
        context = {
            "user_name": payment_data.get("user_name", "Usuario"),
            "amount": payment_data.get("amount", 0),
            "currency": payment_data.get("currency", "USD"),
            "order_number": payment_data.get("order_number", "N/A"),
            "order_total": payment_data.get("order_total", 0),
            "paid_total": payment_data.get("paid_total", 0),
            "remaining_balance": payment_data.get("remaining_balance", 0),
            "year": get_ve_now().year,
        }

        subject = f"¡Pago aprobado! - Orden #{payment_data.get('order_number', 'N/A')} - FarmaPlus"

        await self.send_email(
            to_email=to_email, subject=subject, template_name="payment_approved.html", context=context
        )

    async def send_payment_rejected_email(self, to_email: str, payment_data: dict[str, Any]):
        """Enviar email de pago rechazado"""
        context = {
            "user_name": payment_data.get("user_name", "Usuario"),
            "amount": payment_data.get("amount", 0),
            "currency": payment_data.get("currency", "USD"),
            "order_number": payment_data.get("order_number", "N/A"),
            "admin_notes": payment_data.get("admin_notes", "No se proporcionó motivo específico"),
            "year": get_ve_now().year,
        }

        subject = f"Pago rechazado - Orden #{payment_data.get('order_number', 'N/A')} - FarmaPlus"

        await self.send_email(
            to_email=to_email, subject=subject, template_name="payment_rejected.html", context=context
        )

    async def send_verification_email(self, to_email: str, verification_data: dict[str, Any]):
        """Enviar email de verificación de correo electrónico"""
        context = {"verification_link": verification_data.get("verification_link", "#"), "year": get_ve_now().year}

        subject = "Verifica tu correo electrónico - FarmaPlus"

        await self.send_email(to_email=to_email, subject=subject, template_name="verify_email.html", context=context)

    async def send_password_reset_email(self, to_email: str, reset_link: str, user_name: str = "Usuario"):
        """Enviar email de recuperación de contraseña"""
        context = {"reset_link": reset_link, "user_name": user_name, "year": get_ve_now().year}

        subject = "Recuperación de contraseña - Grupo Drozainka"

        await self.send_email(to_email=to_email, subject=subject, template_name="password_reset.html", context=context)


# Singleton instance
email_service = EmailService()
