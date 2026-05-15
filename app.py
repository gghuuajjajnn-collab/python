import os
import logging
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

app = Flask(__name__)

# CORS: allow any origin + Authorization header (required for Bearer tokens)
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "allow_headers": ["Authorization", "Content-Type", "Accept"],
        "methods": ["GET", "POST", "OPTIONS"]
    }
})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ======================
# Environment Variables
# ======================
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
AUTH_SECRET = os.environ.get("AUTH_SECRET")

if not AUTH_SECRET:
    raise ValueError("AUTH_SECRET environment variable is required")

# ======================
# Local Auth Data
# ======================
LOCAL_USERS = {
    "mohammad": {"password": "2026", "role": "admin", "name": "Mohammad"},
    "student": {"password": "1234", "role": "student", "name": "Student"}
}

GOOGLE_AUTHORIZED = {
    "gghuuajjajnn@gmail.com": "admin"
}

# Token serializer for local auth
serializer = URLSafeTimedSerializer(AUTH_SECRET)

# ======================
# Helper: Auth
# ======================
def authenticate_request():
    """
    Extract and verify Bearer token from Authorization header.
    Supports:
      1. Local tokens (signed by itsdangerous)
      2. Google ID tokens (verified via Google tokeninfo endpoint)
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    parts = auth_header.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1]

    # 1. Try local token
    try:
        payload = serializer.loads(token, max_age=604800)  # 7 days
        return {
            "email": payload.get("email"),
            "name": payload.get("name"),
            "role": payload.get("role", "student"),
            "provider": "local"
        }
    except (BadSignature, SignatureExpired):
        pass

    # 2. Try Google ID token
    try:
        resp = requests.get(
            f"https://oauth2.googleapis.com/tokeninfo?id_token={token}",
            timeout=10
        )
        if resp.status_code == 200:
            gdata = resp.json()
            if GOOGLE_CLIENT_ID and gdata.get("aud") != GOOGLE_CLIENT_ID:
                logger.warning("Google token aud mismatch")
                return None
            email = gdata.get("email")
            return {
                "email": email,
                "name": gdata.get("name", email),
                "role": GOOGLE_AUTHORIZED.get(email, "student"),
                "provider": "google"
            }
    except Exception as e:
        logger.error(f"Google token verification failed: {e}")

    return None

# ======================
# Routes
# ======================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "Code Repository API",
        "version": "1.0.0",
        "endpoints": ["/login", "/tokeninfo", "/ask-ai", "/status"]
    })

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "status": "ok",
        "ai_service": "OpenRouter",
        "ai_configured": bool(OPENROUTER_API_KEY),
        "cors": "enabled"
    })

@app.route("/login", methods=["POST"])
def login():
    """
    Local username/password login.
    Returns a Bearer token to be used in Authorization header.
    """
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"status": "error", "message": "Username and password required"}), 400

    user = LOCAL_USERS.get(username)
    if not user or user["password"] != password:
        return jsonify({"status": "error", "message": "Invalid credentials"}), 401

    token = serializer.dumps({
        "email": f"{username}@local",
        "name": user["name"],
        "role": user["role"]
    })

    return jsonify({
        "status": "success",
        "token": token,
        "email": f"{username}@local",
        "name": user["name"],
        "role": user["role"]
    })

@app.route("/tokeninfo", methods=["POST"])
def tokeninfo():
    """
    Verify Google ID token (from Google One Tap/Sign-In).
    Returns user profile so frontend can store auth state.
    """
    data = request.get_json(silent=True) or {}
    id_token = data.get("id_token")

    if not id_token:
        return jsonify({"error": "id_token is required"}), 400

    try:
        resp = requests.get(
            f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}",
            timeout=10
        )
        if resp.status_code != 200:
            return jsonify({"error": "Invalid token"}), 401

        gdata = resp.json()

        if GOOGLE_CLIENT_ID and gdata.get("aud") != GOOGLE_CLIENT_ID:
            return jsonify({"error": "Invalid client ID"}), 401

        email = gdata.get("email")
        role = GOOGLE_AUTHORIZED.get(email, "student")

        return jsonify({
            "email": email,
            "name": gdata.get("name", email),
            "picture": gdata.get("picture"),
            "role": role
        })

    except Exception as e:
        logger.error(f"tokeninfo error: {e}")
        return jsonify({"error": "Verification failed"}), 500

@app.route("/ask-ai", methods=["POST"])
def ask_ai():
    """
    Protected AI endpoint.
    Expects JSON: {"query": "..."}
    """
    user = authenticate_request()
    if not user:
        return jsonify({"response": "Unauthorized. Please login first."}), 401

    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"response": "Query cannot be empty."}), 400

    if not OPENROUTER_API_KEY:
        return jsonify({
            "response": "OpenRouter API key is not configured on the server."
        }), 500

    return ask_openrouter(query)

def ask_openrouter(query):
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "messages": [
            {
                "role": "system",
                "content": (
                    "أنت مساعد برمجي خبير ومعلم للطلاب. "
                    "أجب باللغة العربية الفصحى. "
                    "اكتب الأكواد داخل علامات markdown. "
                    "كن مفصلاً في الشرح ومختصراً في الكود."
                )
            },
            {"role": "user", "content": query}
        ]
    }

    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": request.headers.get("Origin", "https://relaxed-elf-ebc5ea.netlify.app"),
                "X-Title": "Code Repository"
            },
            json=payload,
            timeout=60
        )
        resp.raise_for_status()
        result = resp.json()
        ai_text = result["choices"][0]["message"]["content"]
        return jsonify({"response": ai_text})

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else 0
        detail = ""
        try:
            detail = e.response.json().get("error", {}).get("message", "")
        except Exception:
            pass
        logger.error(f"OpenRouter HTTP {status}: {detail}")
        return jsonify({"response": f"OpenRouter error ({status}): {detail}"}), 500

    except Exception as e:
        logger.error(f"OpenRouter exception: {e}")
        return jsonify({"response": "Failed to connect to AI service."}), 500

# ======================
# Entry Point
# ======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)