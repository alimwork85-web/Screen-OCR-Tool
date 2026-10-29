"""الترجمة: Google عبر الإنترنت أولاً، وإن تعذّرت فنموذج Ollama محلي على الجهاز.

كل دالة تعيد None عند أي فشل (لا اتصال، مهلة، نموذج غير موجود، رد غير متوقع)، فلا يتوقف البرنامج.
"""
import json
import re
import time
import urllib.parse
import urllib.request

GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"
OLLAMA_URL = "http://127.0.0.1:11434"
GOOGLE_TIMEOUT = 8
OLLAMA_TIMEOUT = 90  # أول طلب يحمّل النموذج في الذاكرة (نحو 15 ث لـ gemma3:4b)

# الأدق أولاً في التجربة على نص عربي/إنجليزي مختلط؛ يُستخدم أول نموذج مثبّت منها
OLLAMA_MODELS = ["gemma3:4b", "kaelri/hy-mt2", "gemma4:e4b", "llama3.1:8b", "qwen3:8b"]
LANG_NAMES = {"ar": "Arabic", "en": "English"}
UI_EN = False  # يضبطه ocr_tool حسب لغة الواجهة، لرسائل الفشل فقط

ARABIC = re.compile("[؀-ۿ]")
LATIN = re.compile("[A-Za-z]")


def target_lang(text):
    """العربي يُترجم إلى الإنجليزية، وغيره إلى العربية."""
    arabic = len(ARABIC.findall(text))
    return "en" if arabic and arabic >= len(LATIN.findall(text)) else "ar"


def google_translate(text, tl):
    try:
        url = GOOGLE_URL + "?" + urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": tl, "dt": "t"})
        body = urllib.parse.urlencode({"q": text}).encode()  # النص في جسم الطلب لا في الرابط
        req = urllib.request.Request(url, body, {"User-Agent": "Mozilla/5.0",
                                                 "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
        with urllib.request.urlopen(req, timeout=GOOGLE_TIMEOUT) as r:
            data = json.load(r)
        out = "".join(seg[0] for seg in data[0] if seg and isinstance(seg[0], str))
        return out.strip() or None
    except Exception:
        return None


_models = (0.0, [])  # (وقت القراءة، الأسماء): /api/tags تُقرأ مرة كل 60 ث


def installed_models():
    global _models
    if time.time() - _models[0] > 60:
        try:
            with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=2) as r:
                names = [m["name"] for m in json.load(r).get("models", [])]
        except Exception:
            names = []
        _models = (time.time(), names)
    return _models[1]


def ollama_model():
    """أول نموذج مفضّل مثبّت، أو None إن كان Ollama متوقفاً أو بلا نموذج مناسب."""
    names = installed_models()
    for pref in OLLAMA_MODELS:
        for name in names:
            if name == pref or name.startswith(pref + ":"):
                return name
    return None


def ollama_translate(text, tl, model):
    body = {
        "model": model, "stream": False, "options": {"temperature": 0.2},
        "messages": [{"role": "user", "content":
                      f"Translate the following text into {LANG_NAMES[tl]}, without additional explanation. "
                      f"Keep numbers, names and line breaks as they are.\n\n{text}"}],
    }
    if model.startswith("qwen3"):
        body["think"] = False  # وإلا يستهلك الوقت في التفكير
    try:
        req = urllib.request.Request(OLLAMA_URL + "/api/chat", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as r:
            out = json.load(r)["message"]["content"].strip()
        return out or None
    except Exception:
        return None


def translate(text, on_fallback=None):
    """تعيد (الترجمة، المصدر، رمز اللغة الهدف)، أو (None، سبب الفشل، رمز اللغة).

    on_fallback(model) تُستدعى قبل اللجوء إلى Ollama، لإخبار المستخدم أن الترجمة قد تتأخر.
    """
    tl = target_lang(text)
    out = google_translate(text, tl)
    if out:
        return out, "Google", tl
    model = ollama_model()
    if not model:
        return None, ("Translation failed: no internet connection and Ollama is unavailable" if UI_EN else
                      "تعذّرت الترجمة: لا اتصال بالإنترنت، وOllama غير متاح"), tl
    if on_fallback:
        on_fallback(model)
    out = ollama_translate(text, tl, model)
    if out:
        return out, f"Ollama · {model}", tl
    return None, (f"Translation failed: no internet connection and Ollama ({model}) did not respond" if UI_EN else
                  f"تعذّرت الترجمة: لا اتصال بالإنترنت، ولم يرد Ollama ({model})"), tl
