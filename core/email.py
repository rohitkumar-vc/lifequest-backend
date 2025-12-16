import requests
from pydantic import EmailStr
from pathlib import Path
from core.config import settings
from jinja2 import Environment, FileSystemLoader

# Setup Jinja2 for manual template rendering
template_dir = Path(__file__).parent.parent / 'templates/email'
env = Environment(loader=FileSystemLoader(str(template_dir)))

async def send_welcome_email(email_to: EmailStr, user_name: str, setup_link: str):
    """Send welcome email using Mailgun API"""
    try:
        # Render Template
        template = env.get_template("welcome_email.html")
        html_content = template.render(
            user_name=user_name,
            action_url=setup_link,
            company_name="LifeQuest"
        )
        
        # Mailgun API Request
        response = requests.post(
            f"https://api.mailgun.net/v3/{settings.MAILGUN_DOMAIN}/messages",
            auth=("api", settings.MAILGUN_API_KEY),
            data={
                "from": settings.MAIL_FROM,
                "to": [email_to],
                "subject": "Welcome to LifeQuest - Setup Your Character",
                "html": html_content
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Mailgun API Error: {response.text}")
            
    except Exception as e:
        # Re-raise the exception to be handled by the caller
        raise Exception(f"Failed to send email: {str(e)}")

