VI AI Foundation TTS API
This public repository hosts the FastAPI backend for the VI AI Foundation TTS Devotional Audio service, served at tts-api.viaifoundation.org. The frontend is at tts.viaifoundation.org (Cloudflare Pages), and static assets are at tts-cdn.viaifoundation.org (GitHub Pages). This backend handles authentication, registration, usage tracking, and audio generation metrics.
Project Structure

main.py: FastAPI backend for authentication (email/password, Google OAuth), registration with email verification, manual approval, and audio generation.
setup_vps.sh: Script to deploy the backend on the IONOS VPS (Debian 12, SQLite).
.env: Environment variables for API keys (e.g., Brevo SMTP, Google OAuth).
README.md: This documentation.

Setup

Clone:
git clone git@github.com:viaifoundation/tts-api.git
cd tts-api


Deploy to VPS:

Copy to /var/www/tts-api on the IONOS VPS.
Run ./setup_vps.sh as root.
Ensure .env is configured with:
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=contact@viaifoundation.org
SMTP_PASS=your_brevo_smtp_key
TURNSTILE_SECRET=0x4AAAAAAB7sgMz8ljJIL_Zx8HIApnHYnx8
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
SECRET_KEY=your_jwt_secret




Configure:

Set up Brevo (https://www.brevo.com/) for email verification.
Configure Google OAuth in Google Cloud Console (https://console.cloud.google.com/).
Update Nginx to proxy /api/ to the FastAPI app.



Features

Authentication: Email/password login and Google OAuth 2.0.
Registration: Email verification and manual approval by admin.
Usage Tracking: Logs endpoint usage per email.
Generation Metrics: Tracks audio generation (time, file size, input text size).
Bot Prevention: Cloudflare Turnstile and rate limiting.

Contact

Email: contact@viaifoundation.org
Phone: 707-560-1777
Address: PO Box 3333, Saratoga, CA 95070

License
MIT License