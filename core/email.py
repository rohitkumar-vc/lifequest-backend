from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr
from pathlib import Path
from core.config import settings

# Load env variables for settings
conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_FROM_NAME="LifeQuest HQ",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
    TEMPLATE_FOLDER=Path(__file__).parent.parent.parent / 'backend/templates/email'
)

async def send_welcome_email(email_to: EmailStr, user_name: str, setup_link: str):
    """Send welcome email to new user created by Admin"""
    subject = "Welcome to LifeQuest - Setup Your Character"
    body = {
        "user_name": user_name,
        "action_url": setup_link, 
        "company_name": "LifeQuest"
    }
    message = MessageSchema(
        subject=subject,
        recipients=[email_to],
        template_body=body,
        subtype=MessageType.html
    )
    fm = FastMail(conf)
    await fm.send_message(message, template_name="welcome_email.html")
