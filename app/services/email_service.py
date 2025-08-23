import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from typing import List, Dict, Any
from app.config.settings import settings
from app.config.logging_config import get_logger, log_error
import os
from jinja2 import Environment, FileSystemLoader

class EmailService:
    def __init__(self):
        self.smtp_server = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM
        self.from_name = settings.SMTP_FROM_NAME
        self.email_logger = get_logger("email")
        self.error_logger = get_logger("errors")

        # Setup Jinja2 for HTML templates
        self.template_env = Environment(
            loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), '..', 'templates', 'emails'))
        )

    def _render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """Renders an email template with the given context."""
        template = self.template_env.get_template(template_name)
        return template.render(context)

    async def send_email(self, to_email: str, subject: str, template_name: str, context: Dict[str, Any]):
        """
        Sends an email using an HTML template.
        """
        self.email_logger.info(
            f"Attempting to send email",
            extra={
                'to_email': to_email,
                'user_email': to_email,  # El destinatario es el usuario
                'subject': subject,
                'template': template_name,
                'event': 'email_send_attempt'
            }
        )
        
        if not all([self.smtp_server, self.smtp_port, self.smtp_user, self.smtp_password, self.from_email]):
            self.email_logger.error(
                "Email service not configured - missing SMTP settings",
                extra={
                    'to_email': to_email,
                    'user_email': to_email,
                    'template': template_name,
                    'reason': 'smtp_not_configured',
                    'event': 'email_send_failed'
                }
            )
            return

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = formataddr((str(Header(self.from_name, 'utf-8')), self.from_email))
        message["To"] = to_email

        # Render the HTML content from the template
        html_body = self._render_template(template_name, context)
        
        # Attach the HTML part
        message.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()  # Secure the connection
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to_email, message.as_string())
                
                self.email_logger.info(
                    f"Email sent successfully",
                    extra={
                        'to_email': to_email,
                        'user_email': to_email,
                        'subject': subject,
                        'template': template_name,
                        'event': 'email_sent_successfully'
                    }
                )
        except Exception as e:
            log_error(
                self.error_logger,
                e,
                context={
                    'to_email': to_email,
                    'subject': subject,
                    'template': template_name,
                    'operation': 'email_sending'
                },
                user_email=to_email
            )
            self.email_logger.error(
                f"Failed to send email",
                extra={
                    'to_email': to_email,
                    'user_email': to_email,
                    'subject': subject,
                    'template': template_name,
                    'error': str(e),
                    'event': 'email_send_failed'
                }
            )

    async def send_order_tracking_email(self, to_email: str, order_data: Dict[str, Any]):
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
        from datetime import datetime
        
        # Prepare context for the template
        context = {
            "order_number": order_data.get("order_number", "N/A"),
            "order_date": order_data.get("order_date", datetime.now().strftime("%d/%m/%Y %H:%M")),
            "order_total": order_data.get("order_total", "N/A"),
            "order_status": order_data.get("order_status", "Confirmada"),
            "payment_method": order_data.get("payment_method", "N/A"),
            "estimated_delivery": order_data.get("estimated_delivery"),
            "tracking_link": order_data.get("tracking_link", "#"),
            "year": datetime.now().year
        }
        
        subject = f"Tu orden #{order_data.get('order_number', 'N/A')} ha sido confirmada - Tracking disponible"
        
        await self.send_email(
            to_email=to_email,
            subject=subject,
            template_name="order_tracking.html",
            context=context
        )

# Singleton instance
email_service = EmailService()
