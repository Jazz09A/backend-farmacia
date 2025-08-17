import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from typing import List, Dict, Any
from app.config.settings import settings
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
        if not all([self.smtp_server, self.smtp_port, self.smtp_user, self.smtp_password, self.from_email]):
            print("Email service is not configured. Skipping email sending.")
            # In a real app, you might want to log this as a warning or error.
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
                print(f"Email sent successfully to {to_email}")
        except Exception as e:
            print(f"Failed to send email to {to_email}: {e}")
            # Depending on the use case, you might want to re-raise the exception or handle it.
            
# Singleton instance
email_service = EmailService()
