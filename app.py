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

# ============================================================
# متغيرات البيئة (Environment Variables)
# ============================================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
AUTH_SECRET = os.environ.get("AUTH_SECRET")

if not AUTH_SECRET:
    raise ValueError("❌ لا يمكن تشغيل السيرفر بدون AUTH_SECRET مضبوط في الإعدادات!")

if not GROQ_API_KEY:
    logger.warning("⚠️ GROQ_API_KEY غير مضبوط. الـ AI لن يعمل حتى تضيف المفتاح.")

# ============================================================
# المستخدمون (ثابتين - للتجربة)
# ============================================================
users = {
    "mohammad": "2026",
    "student": "1234"
}

local_roles = {
    "mohammad": "admin",
    "student": "student"
}

authorized_google_users = {
    "gghuuajjajnn@gmail.com": "admin",
}

serializer = URLSafeTimedSerializer(AUTH_SECRET)


# ============================================================
# دوال المصادقة
# ============================================================
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


# ============================================================
# Routes
# ============================================================
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

        logger.info(f"AI query from {auth_user['email']}: {user_query[:50]}...")

        # ✅ التحقق من مفتاح Groq
        if not GROQ_API_KEY:
            logger.error("GROQ_API_KEY not set")
            return jsonify({
                "response": "❌ مفتاح Groq غير مضبوط في الخادم.\n\nالحل:\n1. ادخل على Render Dashboard\n2. اذهب لـ Environment\n3. أضف متغير: GROQ_API_KEY=gsk_...\n4. اعمل Deploy مرة ثانية"
            }), 500

        if GROQ_API_KEY.startswith("YOUR_") or len(GROQ_API_KEY) < 20:
            logger.error("GROQ_API_KEY appears invalid")
            return jsonify({
                "response": "❌ مفتاح Groq غير صالح.\n\nتأكد من:\n• نسخ المفتاح كامل من console.groq.com\n• عدم وجود مسافات قبل أو بعد المفتاح"
            }), 500

        # ✅ استدعاء Groq
        return ask_groq(user_query)

    except Exception as e:
        logger.error(f"AI error: {e}")
        return jsonify({"response": f"❌ خطأ غير متوقع: {str(e)}"}), 500


def ask_groq(query):
    """استخدام Groq API"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": "أنت مساعد برمجي خبير ومعلم للطلاب. أجب باللغة العربية الفصحى. اكتب الأكواد داخل علامات markdown. كن مفصلاً في الشرح ومختصراً في الكود."
            },
            {
                "role": "user",
                "content": query
            }
        ],
        "temperature": 0.7,
        "max_tokens": 2048
    }
    
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        
        data = response.json()
        ai_text = data['choices'][0]['message']['content']
        
        logger.info("Groq AI response generated successfully")
        return jsonify({"response": ai_text})
        
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else 0
        text = e.response.text if e.response else "No response"
        logger.error(f"Groq HTTP error {status}: {text}")
        
        if status == 401:
            return jsonify({
                "response": "❌ مفتاح Groq غير صالح (401).\n\n• تأكد من صحة المفتاح\n• تأكد أن المفتاح نشط في console.groq.com"
            }), 500
        elif status == 429:
            return jsonify({
                "response": "⏳ تم تجاوز حد الطلبات في Groq.\n\n• انتظر دقيقة وجرب مرة ثانية\n• أو راجع خطتك في console.groq.com"
            }), 500
        else:
            return jsonify({
                "response": f"❌ خطأ في Groq ({status}).\n\nجرب مرة ثانية لاحقاً."
            }), 500
            
    except requests.exceptions.Timeout:
        logger.error("Groq request timeout")
        return jsonify({
            "response": "⏳ استغرق Groq وقتاً طويلاً.\n\nجرب مرة ثانية."
        }), 504
        
    except requests.exceptions.ConnectionError:
        logger.error("Groq connection error")
        return jsonify({
            "response": "❌ لا يمكن الاتصال بـ Groq.\n\n• تأكد من اتصال الإنترنت\n• جرب مرة ثانية"
        }), 502


@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "status": "ok", 
        "message": "Python server running",
        "groq_configured": bool(GROQ_API_KEY and len(GROQ_API_KEY) > 20),
        "groq_key_length": len(GROQ_API_KEY) if GROQ_API_KEY else 0
    })


@app.route('/admin/users', methods=['GET', 'POST', 'DELETE'])
def manage_users():
    auth_user = authenticate_request()
    if not auth_user or auth_user.get('role') != 'admin':
        return jsonify({"error": "غير مصرح. يجب أن تكون أدمن."}), 403
    
    if request.method == 'GET':
        safe_users = {}
        for u in users:
            safe_users[u] = {
                "role": local_roles.get(u, "member"),
                "name": u
            }
        return jsonify(safe_users)
    
    elif request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        role = data.get('role', 'student')
        
        if not username or not password:
            return jsonify({"error": "اسم المستخدم وكلمة المرور مطلوبة"}), 400
        
        if username in users:
            return jsonify({"error": "المستخدم موجود مسبقاً"}), 409
        
        users[username] = password
        local_roles[username] = role
        logger.info(f"Admin added user: {username} as {role}")
        return jsonify({"status": "success"})
    
    elif request.method == 'DELETE':
        username = request.json.get('username')
        if username not in users:
            return jsonify({"error": "المستخدم غير موجود"}), 404
        
        if username == "mohammad":
            return jsonify({"error": "لا يمكن حذف الأدمن الرئيسي"}), 403
        
        del users[username]
        del local_roles[username]
        logger.info(f"Admin deleted user: {username}")
        return jsonify({"status": "success"})


@app.route('/admin/users/<username>/role', methods=['PUT'])
def update_user_role(username):
    auth_user = authenticate_request()
    if not auth_user or auth_user.get('role') != 'admin':
        return jsonify({"error": "غير مصرح"}), 403
    
    if username not in users:
        return jsonify({"error": "المستخدم غير موجود"}), 404
    
    new_role = request.json.get('role')
    if new_role not in ['admin', 'student', 'member']:
        return jsonify({"error": "صلاحية غير صالحة"}), 400
    
    local_roles[username] = new_role
    logger.info(f"Admin changed {username} role to {new_role}")
    return jsonify({"status": "success", "role": new_role})


# ============================================================
# تشغيل السيرفر
# ============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    logger.info(f"Starting Flask server on {host}:{port}...")
    logger.info(f"Groq configured: {bool(GROQ_API_KEY and len(GROQ_API_KEY) > 20)}")
    app.run(host=host, port=port)