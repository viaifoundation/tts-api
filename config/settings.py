from dotenv import load_dotenv
import os

load_dotenv()
class Settings:
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp-relay.brevo.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER = os.getenv("SMTP_USER", "contact@viaifoundation.org")
    SMTP_PASS = os.getenv("SMTP_PASS")
    TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET", "0x4AAAAAAB7sgMz8ljJIL_Zx8HIApnHYnx8")
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    SECRET_KEY = os.getenv("SECRET_KEY")
    API_URL = os.getenv("API_URL", "http://localhost:8000/api/")

settings = Settings()