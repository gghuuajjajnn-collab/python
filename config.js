// ==========================================
// إعدادات النشر المزدوج (GitHub Pages + Render)
// ==========================================

// 🔴 مهم: غيّر هذا الرابط إلى رابط Render الخاص بك
const BACKEND_BASE_URL = 'https://python-m901.onrender.com';

// Google OAuth Client ID
const GOOGLE_CLIENT_ID = '255147968868-vee93tfeiau2diibtp96ko39higle47d.apps.googleusercontent.com';

// Groq API Key - للاستخدام المباشر من المتصفح (اختياري)
// احصل على مفتاح مجاني من: https://console.groq.com
// ⚠️ تحذير أمني: وضع المفتاح هنا يعني أي شخص يقدر يراه
// الحل الأفضل: استخدم Backend دائماً للـ AI
const GROQ_API_KEY = ''; // اتركه فارغ إذا تبي تستخدم Backend فقط

// دالة مساعدة
function getBackendBaseUrl() {
    return BACKEND_BASE_URL;
}

// التحقق من الاتصال بالـ Backend
async function checkBackendStatus() {
    try {
        const response = await fetch(`${BACKEND_BASE_URL}/status`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        console.log('Backend Status:', data);
        return data.status === 'ok';
    } catch (error) {
        console.warn('Backend not available:', error);
        return false;
    }
}