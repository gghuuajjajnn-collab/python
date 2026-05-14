import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import logging
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# المتغيرات
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
AUTH_SECRET = os.environ.get("AUTH_SECRET")

if not AUTH_SECRET:
    raise ValueError("❌ لا يمكن تشغيل السيرفر بدون AUTH_SECRET!")

if not OPENROUTER_API_KEY:
    logger.warning("⚠️ OPENROUTER_API_KEY غير مضبوط")

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

# ... (دوال المصادقة نفسها)

@app.route('/ask-ai', methods=['POST'])
def ask_ai():
    try:
        auth_user = authenticate_request()
        if not auth_user:
            return jsonify({"response": "غير مصرح. الرجاء تسجيل الدخول."}), 401

        user_query = request.json.get('query', '').strip()
        if not user_query:
            return jsonify({"response": "الرجاء إدخال سؤال صحيح."}), 400

        if not OPENROUTER_API_KEY:
            return jsonify({
                "response": "❌ مفتاح OpenRouter غير مضبوط.\n\nسجل مجاناً في openrouter.ai واحصل على مفتاح"
            }), 500

        return ask_openrouter(user_query)

    except Exception as e:
        logger.error(f"AI error: {e}")
        return jsonify({"response": f"❌ خطأ: {str(e)}"}), 500


def ask_openrouter(query):
    """OpenRouter API - متاح عالمياً ومجاني"""
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    payload = {
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "messages": [
            {
                "role": "system",
                "content": "أنت مساعد برمجي خبير ومعلم للطلاب. أجب باللغة العربية الفصحى. اكتب الأكواد داخل علامات markdown. كن مفصلاً في الشرح ومختصراً في الكود."
            },
            {
                "role": "user",
                "content": query
            }
        ]
    }
    
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://relaxed-elf-ebc5ea.netlify.app",
                "X-Title": "Code Repository"
            },
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        
        data = response.json()
        ai_text = data['choices'][0]['message']['content']
        return jsonify({"response": ai_text})
        
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else 0
        logger.error(f"OpenRouter error {status}")
        return jsonify({"response": f"❌ خطأ OpenRouter ({status})"}), 500
        
    except Exception as e:
        logger.error(f"OpenRouter exception: {e}")
        return jsonify({"response": "❌ فشل الاتصال"}), 500


@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "status": "ok",
        "ai_service": "OpenRouter",
        "configured": bool(OPENROUTER_API_KEY)
    })


# ... (باقي الـ Routes)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)