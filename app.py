import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import logging
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# إعداد السجلات (Logging)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# متغيرات المصادقة
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDIERB7bPel-OTMxQxSE8ELX9diJ4kD16c")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
AUTH_SECRET = os.environ.get("AUTH_SECRET")
if not AUTH_SECRET:
    raise ValueError("لا يمكن تشغيل السيرفر بدون AUTH_SECRET مضبوط في الإعدادات!")

users = {
    "mohammad": "2026",
    "student": "1234"
}

local_roles = {
    "mohammad": "admin",
    "student": "student"
}

authorized_google_users = {
    # اضف هنا ايميلات المستخدمين المسموح لها وصلاحياتهم
     "gghuuajjajnn@gmail.com": "admin",
    # "student@example.com": "student"
}

serializer = URLSafeTimedSerializer(AUTH_SECRET)


def create_local_token(username, role):
    return serializer.dumps({"username": username, "role": role, "name": username})


def verify_local_token(token):
    try:
        data = serializer.loads(token, max_age=7 * 24 * 3600)
        return {
            "email": f"{data['username']}@local",
            "name": data.get("name", data['username']),
            "role": data.get("role", "member"),
            "provider": "local"
        }
    except (BadSignature, SignatureExpired):
        return None


def verify_google_token(id_token):
    try:
        response = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
            timeout=15
        )
        response.raise_for_status()
        data = response.json()

        if GOOGLE_CLIENT_ID and data.get("aud") != GOOGLE_CLIENT_ID:
            logger.error("Google token audience does not match.")
            return None

        email = data.get("email")
        if not email:
            return None

        return {
            "email": email,
            "name": data.get("name", email.split("@")[0]),
            "role": authorized_google_users.get(email, "member"),
            "provider": "google"
        }
    except Exception as e:
        logger.error(f"Google token verification failed: {e}")
        return None


def authenticate_request():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ", 1)[1]
    google_user = verify_google_token(token)
    if google_user:
        return google_user

    local_user = verify_local_token(token)
    if local_user:
        return local_user

    return None

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        u, p = data.get('username'), data.get('password')
        if u in users and users[u] == p:
            role = local_roles.get(u, 'member')
            token = create_local_token(u, role)
            logger.info(f"Local user {u} logged in successfully")
            return jsonify({
                "status": "success",
                "email": f"{u}@local",
                "name": u,
                "role": role,
                "token": token
            })
        
        logger.warning(f"Failed login attempt for user: {u}")
        return jsonify({"status": "error", "message": "بيانات الدخول غير صحيحة"}), 401
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/tokeninfo', methods=['POST'])
def tokeninfo():
    try:
        id_token = request.json.get('id_token', '').strip()
        if not id_token:
            return jsonify({"error": "مفتاح المصادقة مفقود."}), 400

        user = verify_google_token(id_token)
        if not user:
            return jsonify({"error": "فشل التحقق من Google token."}), 401

        return jsonify(user)
    except Exception as e:
        logger.error(f"Token info error: {e}")
        return jsonify({"error": "حدث خطأ في التحقق من المصادقة."}), 500

@app.route('/ask-ai', methods=['POST'])
def ask_ai():
    try:
        auth_user = authenticate_request()
        if not auth_user:
            return jsonify({"response": "غير مصرح. الرجاء تسجيل الدخول."}), 401

        user_query = request.json.get('query', '').strip()
        if not user_query:
            return jsonify({"response": "الرجاء إدخال سؤال صحيح."}), 400

        if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("YOUR_"):
            logger.error("Missing Gemini API key")
            return jsonify({"response": "مفتاح الذكاء الاصطناعي غير مضبوط. اضبط GEMINI_API_KEY ثم أعد تشغيل الخادم."}), 500

        logger.info(f"AI query received from {auth_user['email']}: {user_query[:50]}...")

        url = f"https://generativelanguage.googleapis.com/v1beta2/models/gemini-2.5-flash:generateText?key={GEMINI_API_KEY}"
        payload = {
            "prompt": {
                "text": f"أنت مساعد برمجي خبير في موقع 'مستودع الأكواد'. أجب باللغة العربية الفصحى، واكتب الأكواد البرمجية داخل بلوكات نصية واضحة، وكن مختصراً ومفيداً: {user_query}"
            }
        }

        response = requests.post(url, json=payload, timeout=40)
        response.raise_for_status()

        data = response.json()
        ai_text = ""

        if isinstance(data, dict) and 'candidates' in data and data['candidates']:
            candidate = data['candidates'][0]
            ai_text = candidate.get('output') or (candidate.get('content', [{}])[0].get('text') if isinstance(candidate.get('content'), list) else '')

        if not ai_text:
            ai_text = "عذراً، لم أتمكن من معالجة الرد حالياً. حاول صياغة السؤال بشكل آخر."

        logger.info("AI response generated successfully")
        return jsonify({"response": ai_text})

    except requests.exceptions.Timeout:
        logger.error("AI request timeout")
        return jsonify({"response": "استغرق الذكاء الاصطناعي وقتاً طويلاً، حاول مرة أخرى."}), 504
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"AI HTTP error: {http_err} - {response.text}")
        return jsonify({"response": "خطأ في خدمة الذكاء الاصطناعي. تأكد من مفتاح الـ API وإعدادات الشبكة."}), response.status_code
    except Exception as e:
        logger.error(f"AI error: {e}")
        return jsonify({"response": "حدث خطأ أثناء الاتصال بالعقل الاصطناعي، تأكد من مفتاح الـ API."}), 500

@app.route('/status', methods=['GET'])
def status():
    return jsonify({"status": "ok", "message": "Python server running"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    logger.info(f"Starting Flask server on {host}:{port}...")
    app.run(host=host, port=port)