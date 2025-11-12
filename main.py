from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from passlib.context import CryptContext
import sqlite3
import requests
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
import os
from datetime import datetime
import aiosmtplib
from email.mime.text import MIMEText
import time
import os.path
import secrets

app = FastAPI()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
load_dotenv()
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    access_token_url='https://oauth2.googleapis.com/token',
    userinfo_endpoint='https://www.googleapis.com/oauth2/v3/userinfo',
    client_kwargs={'scope': 'openid email profile'}
)

TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET")
API_URL = os.getenv("API_URL", "http://localhost:8000/api/")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{API_URL}token")

def verify_turnstile(token: str):
    response = requests.post(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data={"secret": TURNSTILE_SECRET, "response": token}
    )
    return response.json()["success"]

class RegisterRequest(BaseModel):
    email: str
    password: str
    turnstile_token: str

class GenerateAudioRequest(BaseModel):
    language: str
    paragraphs: list[dict]
    turnstile_token: str

async def send_verification_email(email: str, token: str):
    verification_url = f"https://tts.viaifoundation.org/verify?token={token}"
    msg = MIMEText(f"Please verify your email by clicking this link: {verification_url}\n\nIf you did not request this, ignore this email.")
    msg['Subject'] = "Verify Your TTS Account"
    msg['From'] = "no-reply@viaifoundation.org"
    msg['To'] = email
    await aiosmtplib.send(
        msg,
        hostname=os.getenv("SMTP_HOST"),
        port=int(os.getenv("SMTP_PORT")),
        username=os.getenv("SMTP_USER"),
        password=os.getenv("SMTP_PASS"),
        use_tls=True
    )

def log_usage(email: str, endpoint: str, conn):
    cursor = conn.cursor()
    cursor.execute("SELECT count FROM usage WHERE email = ? AND endpoint = ?", (email, endpoint))
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE usage SET count = count + 1, timestamp = ? WHERE email = ? AND endpoint = ?",
                       (datetime.now(), email, endpoint))
    else:
        cursor.execute("INSERT INTO usage (email, endpoint, timestamp, count) VALUES (?, ?, ?, ?)",
                       (email, endpoint, datetime.now(), 1))
    conn.commit()
    cursor.close()

def log_generation(email: str, processing_time: float, mp3_file_size: int, input_text_size: int, output_file: str, status: str, conn):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO generation_logs (email, processing_time, mp3_file_size, input_text_size, output_file, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (email, processing_time, mp3_file_size, input_text_size, output_file, status))
    conn.commit()
    cursor.close()

@app.post("/api/register")
async def register(request: RegisterRequest, background_tasks: BackgroundTasks):
    if not verify_turnstile(request.turnstile_token):
        raise HTTPException(status_code=400, detail="Challenge failed")
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM users WHERE email = ?", (request.email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Email exists")
    hashed_password = pwd_context.hash(request.password)
    verification_token = secrets.token_urlsafe(32)
    cursor.execute("""
        INSERT INTO users (email, password, verification_token, create_time, update_time)
        VALUES (?, ?, ?, ?, ?)
    """, (request.email, hashed_password, verification_token, datetime.now(), datetime.now()))
    conn.commit()
    log_usage(request.email, "/api/register", conn)
    conn.close()
    background_tasks.add_task(send_verification_email, request.email, verification_token)
    return {"message": "Registration successful. Check your email for verification."}

@app.get("/api/verify")
async def verify_email(token: str):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM users WHERE verification_token = ? AND verified = 0", (token,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    cursor.execute("UPDATE users SET verified = 1, verification_token = NULL WHERE email = ?", (user[0],))
    conn.commit()
    log_usage(user[0], "/api/verify", conn)
    conn.close()
    return {"message": "Email verified. Awaiting admin approval."}

@app.post("/api/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if not verify_turnstile(form_data.cf_turnstile_response):
        raise HTTPException(status_code=400, detail="Challenge failed")
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT password, verified, approved FROM users WHERE email = ?", (form_data.username,))
    user = cursor.fetchone()
    conn.close()
    if not user or not user[1] or not user[2]:
        raise HTTPException(status_code=401, detail="Email not verified or approved")
    if not user[0] or not pwd_context.verify(form_data.password, user[0]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    log_usage(form_data.username, "/api/token", conn)
    return {"access_token": "dummy_token", "token_type": "bearer"}

@app.post("/api/google/login")
async def google_login(token: dict):
    try:
        token_response = await oauth.google.fetch_token(
            token_url='https://oauth2.googleapis.com/token',
            grant_type='authorization_code',
            code=token['token'],
            redirect_uri=f"{API_URL}google/callback"
        )
        user_info = await oauth.google.userinfo()
        google_id = user_info['sub']
        email = user_info['email']

        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, verified, approved FROM users WHERE google_id = ?", (google_id,))
        user = cursor.fetchone()
        if not user:
            verification_token = secrets.token_urlsafe(32)
            cursor.execute("""
                INSERT INTO users (email, google_id, verification_token, create_time, update_time)
                VALUES (?, ?, ?, ?, ?)
            """, (email, google_id, verification_token, datetime.now(), datetime.now()))
            conn.commit()
            log_usage(email, "/api/google/login", conn)
            await send_verification_email(email, verification_token)
            conn.close()
            return {"message": "Registration successful. Check your email for verification."}
        elif not user[1] or not user[2]:
            conn.close()
            raise HTTPException(status_code=401, detail="Email not verified or approved")
        log_usage(email, "/api/google/login", conn)
        conn.close()
        return {"access_token": "dummy_token", "token_type": "bearer"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/approve")
async def approve_account(email: str):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET approved = 1, update_time = ? WHERE email = ?", (datetime.now(), email))
    conn.commit()
    log_usage(email, "/api/approve", conn)
    conn.close()
    return {"message": f"Account {email} approved"}

@app.get("/api/usage")
async def get_usage():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT email, endpoint, timestamp, count FROM usage")
    usage = cursor.fetchall()
    conn.close()
    return {"usage": [{"email": u[0], "endpoint": u[1], "timestamp": u[2], "count": u[3]} for u in usage]}

@app.post("/api/generate_audio")
async def generate_audio(request: GenerateAudioRequest, token: str = Depends(oauth2_scheme)):
    if not verify_turnstile(request.turnstile_token):
        raise HTTPException(status_code=400, detail="Challenge failed")
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT email, verified, approved FROM users WHERE email = (SELECT email FROM users WHERE id = (SELECT id FROM users WHERE token = ?))", (token,))
    user = cursor.fetchone()
    if not user or not user[1] or not user[2]:
        raise HTTPException(status_code=401, detail="User not verified or approved")

    start_time = time.time()
    import edge_tts
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
        combined_text = "\n".join(p["text"] for p in request.paragraphs)
        communicate = edge_tts.Communicate(text=combined_text, voice=voices[request.language][0])
        await communicate.save(temp_file.name)
        temp_file_path = temp_file.name
    processing_time = time.time() - start_time
    mp3_file_size = os.path.getsize(temp_file_path)
    input_text_size = sum(len(p["text"]) for p in request.paragraphs)
    output_file = f"/output/{secrets.token_hex(8)}.mp3"
    os.rename(temp_file_path, output_file)

    status = "success"
    conn = sqlite3.connect("users.db")
    log_generation(user[0], processing_time, mp3_file_size, input_text_size, output_file, status, conn)
    log_usage(user[0], "/api/generate_audio", conn)
    conn.close()

    return {"file": f"{API_URL[:-1]}{output_file}"}

# Initialize database schema
def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT PRIMARY KEY,
            password TEXT,
            google_id TEXT UNIQUE,
            verified INTEGER DEFAULT 0,
            approved INTEGER DEFAULT 0,
            verification_token TEXT,
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            count INTEGER DEFAULT 1,
            FOREIGN KEY (email) REFERENCES users(email)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS generation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            generation_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            processing_time REAL,
            mp3_file_size INTEGER,
            input_text_size INTEGER,
            audio_duration REAL,
            output_file TEXT,
            status TEXT,
            FOREIGN KEY (email) REFERENCES users(email)
        )
    """)
    conn.commit()
    conn.close()

init_db()