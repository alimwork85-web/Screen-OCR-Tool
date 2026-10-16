import json
import os
import re
import shutil
import sys
import tkinter as tk
from tkinter import messagebox, scrolledtext
import ctypes
import time
from datetime import datetime
import threading
import urllib.parse
import webbrowser
from concurrent.futures import ThreadPoolExecutor
import keyboard
import pytesseract
from PIL import Image, ImageGrab, ImageOps, ImageStat
import pystray
import ui_icons
import translator

APP_VERSION = "2.1.0"  # يطابق version_info.txt

# يجب أن يسبق إنشاء أي نافذة Tk، حتى تتطابق إحداثيات الواجهة مع إحداثيات الالتقاط
try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

# هوية مستقلة للتطبيق في شريط المهام: يأخذ أيقونة نافذته بدل أيقونة مخزَّنة قديمة لمسار الملف
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("alimwork85.ScreenOCRTool.2")
except Exception:
    pass

# نسخة واحدة فقط: التشغيل الثاني يطلب من الأولى إظهار نافذتها ثم يخرج (قبل إنشاء أي نافذة)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.restype = kernel32.CreateEventW.restype = kernel32.OpenEventW.restype = ctypes.c_void_p
kernel32.SetEvent.argtypes = [ctypes.c_void_p]
kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
SHOW_EVENT_NAME = "alimwork85.ScreenOCRTool.show"
show_event = None
if __name__ == "__main__":
    try:
        _instance_mutex = kernel32.CreateMutexW(None, False, "alimwork85.ScreenOCRTool.instance")
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            other = kernel32.OpenEventW(0x0002, False, SHOW_EVENT_NAME)  # EVENT_MODIFY_STATE
            if other:
                kernel32.SetEvent(other)
            sys.exit(0)
        show_event = kernel32.CreateEventW(None, False, False, SHOW_EVENT_NAME)
    except Exception:
        pass

# ---- رموز التصميم (ألوان وخطوط): ثيم فاتح وثيم داكن يتبع إعداد Windows ----
THEMES = {
    "light": {
        "bg": "#F3F6F8", "surface": "#FFFFFF", "border": "#D5DEE4",
        "ink": "#12212B", "muted": "#5B6B76",
        "primary": "#0E7C86", "primary_hover": "#0B656E", "primary_press": "#094F57",
        "accent": "#F2A93B", "select": "#CFE9EC",
        "ok": "#167A4C", "warn": "#9A5800", "error": "#C0392B", "info": "#0E7C86",
    },
    "dark": {
        "bg": "#11181D", "surface": "#1A242B", "border": "#2C3A44",
        "ink": "#E6EDF1", "muted": "#9AABB6",
        "primary": "#0E7C86", "primary_hover": "#0B656E", "primary_press": "#094F57",
        "accent": "#F2A93B", "select": "#1F4A50",
        "ok": "#4CC38A", "warn": "#E0A040", "error": "#F0776A", "info": "#4CC2CC",
    },
}

def system_theme():
    """إعداد التطبيقات في Windows: 'light' أو 'dark'."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "dark"
    except Exception:
        return "light"

theme_mode = system_theme()
T = dict(THEMES[theme_mode])  # يُعدَّل في مكانه عند تغيّر الثيم
current_status = ("جاهز للاستخدام", "info")

def resource_path(rel):
    """مسار ملف مرفق، سواء شُغّل البرنامج من الكود أو من ملف EXE."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

def load_font():
    """يسجّل خط Tajawal المرفق لهذا البرنامج فقط (بلا تثبيت)؛ وإلا يُستخدم Segoe UI."""
    loaded = False
    for name in ("Tajawal-Regular.ttf", "Tajawal-Bold.ttf"):
        try:
            FR_PRIVATE = 0x10
            loaded = ctypes.windll.gdi32.AddFontResourceExW(resource_path("assets/fonts/" + name), FR_PRIVATE, 0) > 0 or loaded
        except Exception:
            pass
    return "Tajawal" if loaded else "Segoe UI"

FONT = load_font()

# تحديد مسار Tesseract: المسار الافتراضي أولاً، ثم PATH
DEFAULT_TESSERACT = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
TESSERACT_PATH = DEFAULT_TESSERACT if os.path.exists(DEFAULT_TESSERACT) else shutil.which('tesseract')
if TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# ========================================================
# 1. أداة التحديد والقص (Snipping Tool)
# ========================================================
def get_virtual_screen():
    """مستطيل يغطي كل الشاشات: (x, y, العرض, الارتفاع). قد يبدأ x أو y بقيمة سالبة."""
    user32 = ctypes.windll.user32
    return (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77),
            user32.GetSystemMetrics(78), user32.GetSystemMetrics(79))

class SnippingTool:
    def __init__(self, on_crop_complete, on_cancel):
        self.on_crop_complete = on_crop_complete
        self.on_cancel = on_cancel
        
        self.snip_surface = tk.Toplevel()
        self.snip_surface.attributes('-alpha', 0.3)
        # طبقة بلا إطار تغطي كل الشاشات (وليس الرئيسية فقط)
        self.origin_x, self.origin_y, width, height = get_virtual_screen()
        self.snip_surface.overrideredirect(True)
        # الصيغة +-300 ضرورية: -300 وحدها تعني "من الحافة اليمنى" في Tk
        self.snip_surface.geometry(f"{width}x{height}+{self.origin_x}+{self.origin_y}")
        self.snip_surface.attributes('-topmost', True)
        self.snip_surface.config(cursor="cross")

        self.canvas = tk.Canvas(self.snip_surface, cursor="cross", bg="#333333", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.snip_surface.bind("<Escape>", self.cancel_snip)
        self.snip_surface.focus_force()
        # ويندوز قد يرفض إعطاء التركيز لنافذة تُفتح بالاختصار من برنامج آخر، فلا يصلها Esc؛
        # لذلك نسجّل Esc كاختصار عام طوال مدة التحديد فقط
        self.finished = False
        self.esc_hotkey = None
        try:
            self.esc_hotkey = keyboard.add_hotkey('esc', lambda: root.after(0, self.cancel_snip))
        except Exception:
            pass

        self.start_x = None
        self.start_y = None
        self.rect = None

    def release_esc(self):
        self.finished = True
        if self.esc_hotkey is not None:
            try:
                keyboard.remove_hotkey(self.esc_hotkey)
            except Exception:
                pass
            self.esc_hotkey = None

    def cancel_snip(self, event=None):
        if self.finished:
            return  # أُلغي أو اكتمل من قبل (Esc العام وEsc الخاص بالنافذة قد يصلان معاً)
        self.release_esc()
        if self.snip_surface.winfo_exists():
            self.snip_surface.destroy()
        if self.on_cancel:
            self.on_cancel()

    def on_button_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, 1, 1, outline='red', width=2)

    def on_move_press(self, event):
        cur_x, cur_y = (event.x, event.y)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_button_release(self, event):
        if self.start_x is None:
            return self.cancel_snip()
        self.release_esc()
        end_x, end_y = (event.x, event.y)
        self.snip_surface.destroy()
        # إعطاء الشاشة فرصة لإزالة الطبقة الشفافة قبل الالتقاط
        self.snip_surface.update()

        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        if (x2 - x1) > 20 and (y2 - y1) > 20:
            try:
                time.sleep(0.1)
                # إحداثيات الطبقة نسبية لزاويتها، فنحوّلها إلى إحداثيات الشاشة
                bbox = (x1 + self.origin_x, y1 + self.origin_y, x2 + self.origin_x, y2 + self.origin_y)
                screenshot = ImageGrab.grab(bbox=bbox, all_screens=True)
                self.on_crop_complete(screenshot)
            except Exception as e:
                messagebox.showerror("خطأ في القص", f"فشل التقاط الشاشة: {e}")
                if self.on_cancel:
                    self.on_cancel()
        else:
            if self.on_cancel:
                self.on_cancel("التحديد صغير جداً، حدّد مساحة أكبر", "warn")

# ========================================================
# 2. معالجة النصوص بواسطة Tesseract
# ========================================================
# علامات اتجاه غير مرئية (LRM/RLM...) يضعها Tesseract حول الكلمات الإنجليزية؛ تُنسخ مع النص وتربك اللصق
BIDI_MARKS = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
BRACKETS = {"(": ")", "[": "]", "{": "}"}
TARGET_TEXT_HEIGHT = 24  # ارتفاع السطر (بالبكسل) الذي يقرأ عنده Tesseract أفضل في التجارب

def normalize_for_ocr(image):
    """رمادي، نص داكن على خلفية فاتحة، وتكبير/تصغير حتى يقارب ارتفاع السطر TARGET_TEXT_HEIGHT."""
    g = ImageOps.grayscale(image)
    stat = ImageStat.Stat(g)
    if stat.mean[0] < 128:  # الثيم الداكن: Tesseract أدق مع نص داكن على فاتح
        g = ImageOps.invert(g)
        stat = ImageStat.Stat(g)
    lo, median = g.getextrema()[0], stat.median[0]
    ink = g.point(lambda v: 255 if v < (lo + median) / 2 else 0)
    rows = list(ink.resize((1, ink.height), Image.BOX).getdata())  # متوسط كل صف: > 0 = فيه نص
    runs, n = [], 0
    for v in rows:
        if v > 0:
            n += 1
        elif n:
            runs.append(n)
            n = 0
    if n:
        runs.append(n)
    runs = sorted(r for r in runs if r > 3)
    if runs:
        f = max(0.33, min(4.0, TARGET_TEXT_HEIGHT / runs[len(runs) // 2]))
        if abs(f - 1) > 0.1:
            g = g.resize((max(1, round(g.width * f)), max(1, round(g.height * f))), Image.LANCZOS)
    return ImageOps.expand(g, 20, fill=255)

def read_with_score(image, lang):
    """قراءة واحدة تعيد (الدرجة، النص)؛ الدرجة = مجموع (طول الكلمة × ثقة Tesseract)."""
    d = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
    score, lines, last = 0.0, [], None
    for i, word in enumerate(d["text"]):
        word = word.strip()
        if not word:
            continue
        if float(d["conf"][i]) > 0:
            score += len(word) * float(d["conf"][i])
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        if key != last:
            lines.append([])
            last = key
        lines[-1].append(word)
    return score, "\n".join(" ".join(line) for line in lines)

def fix_brackets(line):
    """في النص العربي قد يخرج القوس مقلوباً: ')476 ميغابايت)' ← '(476 ميغابايت)'."""
    for o, c in BRACKETS.items():
        if line.count(o) == line.count(c):
            continue
        chars, depth = list(line), 0
        for i, ch in enumerate(chars):
            if ch == o:
                depth += 1
            elif ch == c:
                if depth:
                    depth -= 1
                elif c in line[i + 1:]:
                    chars[i] = o
                    depth += 1
        line = "".join(chars)
        j = line.rfind(o)
        if line.count(o) > line.count(c) and j > 0 and line.find(c, j) == -1:
            line = line[:j] + c + line[j + 1:]  # '(خصم 15(' ← '(خصم 15)'
    return line

def clean_text(text):
    text = BIDI_MARKS.sub("", text)
    lines = (re.sub(r"[ \t]+", " ", fix_brackets(l)).strip() for l in text.split("\n"))
    return "\n".join(lines).strip()

NO_TEXT_MSG = "لم يتم التعرف على أي نص"

def perform_ocr(image, lang='ara+eng'):
    """تعيد (النص، نجحت؟) حتى لا تُنسخ رسائل الخطأ إلى الحافظة."""
    try:
        # نقرأ الصورة المهيّأة والأصلية ونأخذ الأوثق: التهيئة أدق غالباً، والأصلية أفضل لبعض اللقطات المختلطة الخلفية
        normalized = normalize_for_ocr(image)
        # كل قراءة عملية Tesseract مستقلة، فتشغيلهما معاً يقارب نصف الزمن والنتيجة نفسها
        with ThreadPoolExecutor(max_workers=2) as pool:
            reads = [pool.submit(read_with_score, img, lang) for img in (normalized, image)]
            _, text = max((r.result() for r in reads), key=lambda r: r[0])
        if not text.strip():
            # القصّ الصغير أو ذو الحواف الداكنة قد يفشل بالوضع الافتراضي؛ نعيد المحاولة كمقطع نصي واحد
            text = pytesseract.image_to_string(normalized, lang=lang, config='--psm 6')
        text = clean_text(text)
        if not text:
            return NO_TEXT_MSG, False
        return text, True
    except Exception as e:
        return f"خطأ في Tesseract: {str(e)}", False

# ========================================================
# 3. التحكم في الأحداث والواجهة
# ========================================================
capture_active = False
window_was_visible = True  # هل كانت النافذة ظاهرة عند بدء الالتقاط؟
ui_visible = True  # نتتبع الظهور بأنفسنا لأن root.state() يتأخر لحظة بعد deiconify
tray_icon = None

def show_window():
    global ui_visible
    ui_visible = True
    root.deiconify()
    root.lift()
    root.focus_force()

# نوع الحالة -> (لون، أيقونة)
STATUS_KINDS = {
    "info": ("muted", None),
    "busy": ("info", "clock"),
    "ok": ("ok", "check"),
    "copied": ("ok", "copy"),
    "warn": ("warn", "alert"),
    "error": ("error", "error"),
}

def set_status(text, kind="info"):
    global current_status
    current_status = (text, kind)
    color_key, icon = STATUS_KINDS[kind]
    color = T[color_key]
    image = ui_icons.tk_icon(icon, px(18), color) if icon else ""
    status_label.config(text=text, fg=color, image=image, compound="right")

def start_capture():
    global capture_active
    if capture_active:
        return
    capture_active = True
    global window_was_visible
    window_was_visible = ui_visible
    root.withdraw()
    SnippingTool(on_crop_complete=process_image, on_cancel=on_capture_cancelled)

def on_capture_cancelled(message=None, kind="warn"):
    global capture_active
    capture_active = False
    if window_was_visible:
        show_window()
    if message:
        set_status(message, kind)

def process_image(screenshot):
    global capture_active
    capture_active = False
    if window_was_visible:
        show_window()
    set_status("جاري قراءة النص", "busy")

    # اللغة تُقرأ هنا في خيط الواجهة، والقراءة في خيط منفصل حتى لا تتجمد الواجهة
    lang = lang_var.get()

    def worker():
        text, ok = perform_ocr(screenshot, lang)
        root.after(0, lambda: update_gui(text, ok))

    threading.Thread(target=worker, daemon=True).start()

def clipboard_image():
    """صورة منسوخة (لقطة أو صورة من المتصفح) أو أول ملف صورة منسوخ من المستكشف؛ وإلا None."""
    try:
        data = ImageGrab.grabclipboard()
    except Exception:
        return None
    if isinstance(data, list):  # ملفات منسوخة: قائمة مسارات
        for path in data:
            try:
                with Image.open(path) as img:
                    return img.convert("RGB")
            except Exception:
                continue
        return None
    # صورة الحافظة تأتي بصيغة DIB لا يقبلها pytesseract، فنحوّلها
    return data.convert("RGB") if isinstance(data, Image.Image) else None

def ocr_from_clipboard():
    global window_was_visible
    if capture_active:
        return
    image = clipboard_image()
    if image is None:
        set_status("لا توجد صورة في الحافظة. انسخ صورة أولاً", "warn")
        notify_if_hidden("لا توجد صورة في الحافظة")
        return
    window_was_visible = ui_visible  # لا تظهر النافذة إن كان الطلب من الشريط وهي مخفية
    process_image(image)

def update_gui(text, ok):
    original_text_area.delete("1.0", tk.END)
    original_text_area.insert(tk.END, text)
    if ok:
        copy_to_clipboard(text)
        add_to_history(text)
        set_status("تم استخراج النص والنسخ بنجاح", "ok")
        notify_if_hidden("تم نسخ النص إلى الحافظة")
    else:
        set_status(text, "warn" if text == NO_TEXT_MSG else "error")
        notify_if_hidden(text)

# ---- الترجمة: Google أولاً، وإن تعذّرت فـ Ollama محلياً (translator.py) ----
translation_busy = False

def translate_text(text):
    """يترجم النص في خيط منفصل ثم يعرضه في مربع الترجمة وينسخه."""
    global translation_busy
    text = text.strip()
    if translation_busy:
        return
    if not text:
        set_status("لا يوجد نص للترجمة", "warn")
        return
    translation_busy = True
    btn_translate.config(state="disabled")
    set_status("جاري الترجمة", "busy")

    def on_fallback(model):
        root.after(0, lambda: set_status(f"Google غير متاح، جاري الترجمة محلياً بـ {model} (قد تستغرق ثوانٍ)", "busy"))

    def worker():
        result = translator.translate(text, on_fallback)
        root.after(0, lambda: show_translation(*result))

    threading.Thread(target=worker, daemon=True).start()

def show_translation(out, source, tl):
    global translation_busy
    translation_busy = False
    btn_translate.config(state="normal")
    if not out:
        set_status(source, "error")  # source هنا سبب الفشل
        return
    if not translation_frame.winfo_manager():  # يظهر المربع بعد أول ترجمة فقط
        translation_frame.pack(side='left', fill='y', before=original_text_area, padx=(0, px(12)))
    translation_label.config(text=f"الترجمة ({source})")
    translation_area.config(state="normal")
    translation_area.delete("1.0", tk.END)
    translation_area.insert(tk.END, out, ("rtl",) if tl == "ar" else ())
    translation_area.config(state="disabled")
    copy_to_clipboard(out)
    set_status("تمت الترجمة ونُسخت إلى الحافظة", "copied")

def translate_all():
    translate_text(original_text_area.get("1.0", tk.END))

# ---- البحث: يفتح بحث Google في المتصفح الافتراضي ----
SEARCH_LIMIT = 500  # طول معقول لعبارة البحث

def search_text(text):
    query = " ".join(text.split())[:SEARCH_LIMIT]  # الأسطر والمسافات الزائدة تصير مسافة واحدة
    if not query:
        set_status("لا يوجد نص للبحث", "warn")
        return
    try:
        webbrowser.open("https://www.google.com/search?" + urllib.parse.urlencode({"q": query}))
        set_status("فُتح البحث في المتصفح", "ok")
    except Exception as e:
        set_status(f"تعذّر فتح المتصفح: {e}", "error")

def search_all():
    search_text(original_text_area.get("1.0", tk.END))

# ---- العمل من شريط المهام ----
def notify_if_hidden(message):
    """النافذة مخفية في الشريط: نعرض إشعاراً بدل أن تظهر النافذة."""
    if tray_icon and not ui_visible:
        try:
            tray_icon.notify(message, "OCR")
        except Exception:
            pass

def make_tray_image():
    try:
        return Image.open(resource_path("assets/app_icon_64.png"))
    except Exception:
        return Image.new("RGBA", (64, 64), T["primary"])

def hide_to_tray():
    global ui_visible
    ui_visible = False
    root.withdraw()
    set_status("التطبيق يعمل في الخلفية (Ctrl+Shift+X)", "info")

def quit_app():
    try:
        keyboard.unhook_all()
    except Exception:
        pass
    if tray_icon:
        tray_icon.stop()
    root.destroy()

def setup_tray():
    """يشغّل أيقونة الشريط؛ إن فشل يبقى الإغلاق العادي (X) ينهي البرنامج."""
    global tray_icon
    # دوال القائمة تُستدعى من خيط الشريط، فنحوّلها إلى خيط الواجهة
    to_ui = lambda fn: (lambda icon=None, item=None: root.after(0, fn))
    menu = pystray.Menu(
        pystray.MenuItem("فتح النافذة", to_ui(show_window), default=True),
        pystray.MenuItem("التقاط نص من الشاشة", to_ui(start_capture)),
        pystray.MenuItem("قراءة صورة من الحافظة", to_ui(ocr_from_clipboard)),
        pystray.MenuItem("خروج", to_ui(quit_app)),
    )
    try:
        tray_icon = pystray.Icon("ocr_tool", make_tray_image(), f"أداة OCR {APP_VERSION}", menu)
        tray_icon.run_detached()
        root.protocol("WM_DELETE_WINDOW", hide_to_tray)
    except Exception:
        tray_icon = None

def copy_to_clipboard(text):
    root.clipboard_clear()
    root.clipboard_append(text)

# ---- بيانات المستخدم في AppData: السجل والإعدادات ----
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "OCR_Tool")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

def read_json(path, convert, default):
    """يقرأ الملف ويحوّله بـ convert؛ الملف التالف يُبقى باسم .broken بدل أن يُكتب فوقه."""
    try:
        with open(path, encoding="utf-8") as f:
            return convert(json.load(f))
    except FileNotFoundError:
        return default
    except Exception:
        try:
            os.replace(path, path + ".broken")
        except Exception:
            pass
        return default

def write_json(path, data):
    """كتابة إلى ملف مؤقت ثم استبدال، فلا يتلف الملف إن انقطع البرنامج أثناء الحفظ. تعيد نجحت؟"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception:
        return False

# الإعدادات: لغة القراءة وحالة أسهم الطي، تُحفظ فور تغييرها
LANG_VALUES = ('ara+eng', 'ara', 'eng')

def load_settings():
    def convert(data):
        collapsed = data.get("collapsed", {})
        return {"lang": data.get("lang") if data.get("lang") in LANG_VALUES else 'ara+eng',
                "collapsed": {k: bool(v) for k, v in collapsed.items()} if isinstance(collapsed, dict) else {}}
    return read_json(SETTINGS_PATH, convert, {"lang": 'ara+eng', "collapsed": {}})

settings = load_settings()

def save_settings():
    write_json(SETTINGS_PATH, settings)

# ---- سجل النتائج: لا يُحذف منه شيء إلا بزر «مسح السجل» ----
history = []  # أحدث نتيجة أولاً: [الوقت بصيغة ISO، النص]

def load_history():
    return read_json(HISTORY_PATH, lambda data: [[str(stamp), str(text)] for stamp, text in data if text], [])

def save_history():
    if not write_json(HISTORY_PATH, history):
        set_status("تعذّر حفظ السجل", "warn")

def history_stamp(iso):
    """الساعة فقط لنتائج اليوم، والتاريخ معها لما قبله."""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return dt.strftime("%H:%M") if dt.date() == datetime.now().date() else dt.strftime("%Y-%m-%d %H:%M")

def refresh_history_list():
    history_list.delete(0, tk.END)
    for stamp, item in history:
        preview = " ".join(item.split())
        if len(preview) > 70:
            preview = preview[:70] + "…"
        history_list.insert(tk.END, f"{history_stamp(stamp)}  |  {preview}")

def add_to_history(text):
    if history and history[0][1] == text:
        return
    history.insert(0, [datetime.now().isoformat(timespec="seconds"), text])
    save_history()
    refresh_history_list()

def clear_history():
    if not history:
        set_status("السجل فارغ", "info")
        return
    if not messagebox.askyesno("مسح السجل", f"حذف كل النتائج المحفوظة في السجل ({len(history)})؟\nلا يمكن التراجع عن ذلك.",
                               icon="warning", default="no", parent=root):
        return
    history.clear()
    save_history()
    refresh_history_list()
    set_status("تم مسح السجل", "ok")

def on_history_select(event=None):
    selection = history_list.curselection()
    if not selection:
        return
    text = history[selection[0]][1]
    original_text_area.delete("1.0", tk.END)
    original_text_area.insert(tk.END, text)
    copy_to_clipboard(text)
    set_status("تم نسخ النص من السجل", "copied")

def watch_show_requests():
    """نسخة ثانية شُغّلت: تُظهر نافذة هذه النسخة بدل أن تعمل بجانبها."""
    if show_event and kernel32.WaitForSingleObject(show_event, 0) == 0:
        show_window()
    root.after(300, watch_show_requests)

def setup_hotkey():
    # مكتبة keyboard تستدعي الدالة من خيطها الخاص، فنحوّل التنفيذ إلى خيط الواجهة
    try:
        keyboard.add_hotkey('ctrl+shift+x', lambda: root.after(0, start_capture))
    except Exception:
        set_status("تعذّر تفعيل الاختصار Ctrl+Shift+X، استخدم الزر", "warn")

# ========================================================
# 4. الواجهة الرسومية
# ========================================================
root = tk.Tk()
root.title(f"أداة قراءة النصوص OCR المتقدمة - {APP_VERSION}")
SCALE = root.winfo_fpixels("1i") / 96  # نسبة تكبير الشاشة (1.5 مثلاً عند 150%)

def px(v):
    return round(v * SCALE)

root.geometry(f"{px(850)}x{px(600)}")
root.minsize(px(560), px(440))
try:
    root.iconbitmap(resource_path("assets/app_icon.ico"))
    # الأيقونة الكبيرة لزر شريط المهام (256) بصيغة PNG
    _window_icon = tk.PhotoImage(file=resource_path("assets/app_icon_256.png"))
    root.iconphoto(True, _window_icon)
except Exception:
    pass  # الأيقونة تحسين شكلي فقط

# ---- ربط العناصر بالثيم: كل عنصر يسجَّل مع خيارات لونها (اسم الرمز في T) ----
_themed = []   # (عنصر، {خيار: رمز})
_icon_labels = []   # (Label، اسم الأيقونة، الحجم، رمز اللون)

def reg(widget, **opts):
    _themed.append((widget, opts))
    widget.configure(**{k: T[v] for k, v in opts.items()})
    return widget

def icon_label(parent, name, size, color_key, **pack_opts):
    lbl = tk.Label(parent, image=ui_icons.tk_icon(name, px(size), T[color_key]))
    reg(lbl, bg="bg")
    _icon_labels.append((lbl, name, size, color_key))
    lbl.pack(**pack_opts)
    return lbl

def set_titlebar_dark(dark):
    """شريط عنوان النافذة يتبع الثيم (Windows 10/11)."""
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), 4)
    except Exception:
        pass

def apply_theme(mode):
    global theme_mode
    theme_mode = mode
    T.clear()
    T.update(THEMES[mode])
    root.configure(bg=T["bg"])
    for widget, opts in _themed:
        widget.configure(**{k: T[v] for k, v in opts.items()})
    for lbl, name, size, color_key in _icon_labels:
        lbl.configure(image=ui_icons.tk_icon(name, px(size), T[color_key]))
    btn_capture.configure(image=ui_icons.tk_icon("capture", px(22), "#FFFFFF"))
    set_status(*current_status)
    set_titlebar_dark(mode == "dark")

def watch_system_theme():
    """يتابع إعداد Windows (فاتح/داكن) ويطبّقه فور تغييره."""
    if system_theme() != theme_mode:
        apply_theme(system_theme())
    root.after(2000, watch_system_theme)

main_frame = reg(tk.Frame(root, padx=px(24), pady=px(18)), bg="bg")
main_frame.pack(expand=True, fill='both')

def style_button(btn):
    """ألوان الحالات: عادي / مرور المؤشر / ضغط / تركيز لوحة المفاتيح."""
    btn.bind("<Enter>", lambda e: btn.config(bg=T["primary_hover"]))
    btn.bind("<Leave>", lambda e: btn.config(bg=T["primary"]))
    reg(btn, bg="primary", activebackground="primary_press", highlightbackground="primary", highlightcolor="accent")
    btn.config(activeforeground="white", highlightthickness=2, takefocus=True)

btn_capture = tk.Button(
    main_frame,
    text="  تحديد وقص الشاشة",
    image=ui_icons.tk_icon("capture", px(22), "#FFFFFF"), compound="right",
    command=start_capture,
    fg='white',
    font=(FONT, 13, 'bold'), relief='flat', bd=0, pady=px(8), cursor="hand2"
)
style_button(btn_capture)
btn_capture.pack(fill='x', pady=(0, px(8)))

def add_hint(parent, label, key):
    """نص عربي ثم اختصار لوحة مفاتيح داخل شريحة؛ يُرتَّب من اليمين."""
    reg(tk.Label(parent, text=label, font=(FONT, 11)), bg="bg", fg="muted").pack(side='right', padx=(px(10), px(4)))
    reg(tk.Label(parent, text=key, font=("Consolas", 10), padx=px(6), pady=px(1), highlightthickness=1),
        bg="surface", fg="ink", highlightbackground="border").pack(side='right')

hint_frame = reg(tk.Frame(main_frame), bg="bg")
hint_frame.pack(anchor='e', pady=(0, px(12)))

def collapse_arrow(parent, content, key):
    """سهم بين العنوان ومحتواه: يطوي المحتوى (يساره) أو يعيده. يُستدعى بعد إنشاء العنوان والمحتوى.

    key: اسم السطر في settings["collapsed"]، فتبقى حالته بين التشغيلات."""
    arrow = reg(tk.Label(parent, cursor="hand2"), bg="bg")
    entry = [arrow, "chevron_right", 16, "muted"]  # قائمة لا صف: الاسم واللون يتغيران، وapply_theme يقرأ الحالي
    _icon_labels.append(entry)

    def paint(color_key):
        entry[3] = color_key
        arrow.config(image=ui_icons.tk_icon(entry[1], px(16), T[color_key]))

    def toggle(event=None):
        if content.winfo_manager():
            content.pack_forget()
            entry[1] = "chevron_left"
        else:
            content.pack(side='right')
            entry[1] = "chevron_right"
        paint("primary")
        settings["collapsed"][key] = not content.winfo_manager()
        save_settings()

    arrow.bind("<Button-1>", toggle)
    arrow.bind("<Enter>", lambda e: paint("primary"))
    arrow.bind("<Leave>", lambda e: paint("muted"))
    paint("muted")
    arrow.pack(side='right', padx=(px(4), px(2)))
    if settings["collapsed"].get(key):
        entry[1] = "chevron_left"
        paint("muted")
    else:
        content.pack(side='right')
    return arrow

reg(tk.Label(hint_frame, text="اختصار التحديد", font=(FONT, 11)), bg="bg", fg="muted").pack(side='right')
hint_content = reg(tk.Frame(hint_frame), bg="bg")
reg(tk.Label(hint_content, text="Ctrl+Shift+X", font=("Consolas", 10), padx=px(6), pady=px(1), highlightthickness=1),
    bg="surface", fg="ink", highlightbackground="border").pack(side='right')
add_hint(hint_content, "للإلغاء", "Esc")
collapse_arrow(hint_frame, hint_content, "hints")

lang_frame = reg(tk.Frame(main_frame), bg="bg")
lang_frame.pack(anchor='e', pady=(0, 8))
lang_var = tk.StringVar(value=settings["lang"])
lang_var.trace_add("write", lambda *_: (settings.update(lang=lang_var.get()), save_settings()))
icon_label(lang_frame, "globe", 18, "muted", side='right', padx=(6, 0))
reg(tk.Label(lang_frame, text="لغة القراءة", font=(FONT, 11, 'bold')), bg="bg", fg="ink").pack(side='right')
lang_content = reg(tk.Frame(lang_frame), bg="bg")
for label, value in zip(("عربي + إنجليزي", "عربي فقط", "إنجليزي فقط"), LANG_VALUES):
    reg(tk.Radiobutton(
        lang_content, text=label, value=value, variable=lang_var,
        font=(FONT, 11), highlightthickness=0, cursor="hand2"
    ), bg="bg", fg="ink", activebackground="bg", activeforeground="primary", selectcolor="surface").pack(side='right', padx=6)
collapse_arrow(lang_frame, lang_content, "lang")

def secondary_button(parent, text, icon, command):
    """زر ثانوي بإطار رفيع (أخف من زر التحديد الرئيسي)، يُرتَّب من اليمين."""
    btn = tk.Button(parent, text="  " + text, command=command, font=(FONT, 11), compound="right",
                    image=ui_icons.tk_icon(icon, px(16), T["ink"]), relief='flat', bd=0,
                    padx=px(10), pady=px(3), highlightthickness=1, cursor="hand2", takefocus=True)
    reg(btn, bg="surface", fg="ink", activebackground="select", activeforeground="ink",
        highlightbackground="border", highlightcolor="primary")
    _icon_labels.append((btn, icon, 16, "ink"))  # تتبدّل أيقونته مع الثيم
    btn.bind("<Enter>", lambda e: btn.config(bg=T["select"]))
    btn.bind("<Leave>", lambda e: btn.config(bg=T["surface"]))
    btn.pack(side='right', padx=(px(8), 0))
    return btn

actions_frame = reg(tk.Frame(main_frame), bg="bg")
actions_frame.pack(anchor='e', pady=(0, px(10)))
btn_clipboard = secondary_button(actions_frame, "قراءة صورة من الحافظة", "copy", ocr_from_clipboard)
btn_translate = secondary_button(actions_frame, "ترجمة", "globe", translate_all)
btn_search = secondary_button(actions_frame, "بحث", "search", search_all)

status_label = reg(tk.Label(main_frame, text="جاهز للاستخدام", font=(FONT, 11), padx=2), bg="bg", fg="muted")
status_label.pack(anchor='e', pady=(0, 10))

history_frame = reg(tk.Frame(main_frame), bg="bg")
history_frame.pack(side='bottom', fill='x', pady=(12, 0))
history_header = reg(tk.Frame(history_frame), bg="bg")
history_header.pack(fill='x', pady=(0, 4))
icon_label(history_header, "history", 16, "muted", side='right', padx=(6, 0))
reg(tk.Label(history_header, text="آخر النتائج (اضغط على نتيجة لعرضها ونسخها)", font=(FONT, 10)),
    bg="bg", fg="muted").pack(side='right', padx=(0, 6))
btn_clear_history = secondary_button(history_header, "مسح السجل", "trash", clear_history)
btn_clear_history.pack_configure(side='left', padx=0)  # في الطرف المقابل لعنوان السجل
history_list = reg(tk.Listbox(
    history_frame, height=5, font=(FONT, 11), activestyle='none', exportselection=False,
    relief='flat', bd=0, highlightthickness=1, selectforeground="white"
), bg="surface", fg="ink", highlightbackground="border", highlightcolor="primary", selectbackground="primary")
history_list.pack(fill='x')
history_list.bind("<<ListboxSelect>>", on_history_select)
history[:] = load_history()  # السجل المحفوظ من التشغيلات السابقة
refresh_history_list()

original_text_area = reg(scrolledtext.ScrolledText(
    main_frame, wrap=tk.WORD, font=(FONT, 13), relief='flat', bd=0,
    padx=px(14), pady=px(12), highlightthickness=1
), bg="surface", fg="ink", highlightbackground="border", highlightcolor="primary",
   selectbackground="select", selectforeground="ink", insertbackground="ink")
original_text_area.pack(fill='both', expand=True)

# مربع الترجمة: للقراءة فقط، ويظهر يسار النص الأصلي بنصف العرض بعد أول ترجمة (show_translation)
translation_frame = reg(tk.Frame(main_frame), bg="bg")
translation_frame.pack_propagate(False)  # عرضه يُضبط بنصف المساحة، لا بحجم محتواه
translation_label = reg(tk.Label(translation_frame, text="الترجمة", font=(FONT, 10)), bg="bg", fg="muted")
translation_label.pack(anchor='e', pady=(0, px(4)))
translation_area = reg(scrolledtext.ScrolledText(
    translation_frame, wrap=tk.WORD, font=(FONT, 13), width=1, height=1, relief='flat', bd=0,
    padx=px(14), pady=px(12), highlightthickness=1, state="disabled"
), bg="surface", fg="ink", highlightbackground="border", highlightcolor="primary",
   selectbackground="select", selectforeground="ink", insertbackground="ink")
translation_area.tag_configure("rtl", justify="right")
translation_area.pack(fill='both', expand=True)
main_frame.bind("<Configure>", lambda e: translation_frame.config(width=(e.width - px(48)) // 2), add="+")

# ---- نافذة التظليل: تظليل نص بالفأرة يُظهر نسخ / ترجمة / بحث للجزء المظلَّل فقط ----
selection_popup = None  # تُنشأ عند أول تظليل ثم تُخفى وتُظهر

def selected_text():
    try:
        return original_text_area.get("sel.first", "sel.last")
    except tk.TclError:  # لا يوجد تظليل
        return ""

def hide_selection_popup(event=None):
    if selection_popup is not None and selection_popup.winfo_exists():
        selection_popup.withdraw()

def on_selection_action(action):
    text = selected_text().strip()
    hide_selection_popup()
    if not text:
        return
    if action == "copy":
        copy_to_clipboard(text)
        set_status("تم نسخ النص المحدد", "copied")
    elif action == "translate":
        translate_text(text)
    else:
        search_text(text)

def build_selection_popup():
    global selection_popup
    pop = tk.Toplevel(root)
    pop.withdraw()
    pop.overrideredirect(True)
    pop.attributes("-topmost", True)
    box = reg(tk.Frame(pop, highlightthickness=1, padx=px(3), pady=px(3)), bg="surface", highlightbackground="border")
    box.pack()
    for label, icon, action in (("نسخ", "copy", "copy"), ("ترجمة", "globe", "translate"), ("بحث", "search", "search")):
        btn = tk.Button(box, text=" " + label, image=ui_icons.tk_icon(icon, px(15), T["ink"]), compound="right",
                        font=(FONT, 10), relief="flat", bd=0, padx=px(8), pady=px(2), cursor="hand2",
                        command=lambda a=action: on_selection_action(a))
        reg(btn, bg="surface", fg="ink", activebackground="select", activeforeground="ink")
        _icon_labels.append((btn, icon, 15, "ink"))
        btn.bind("<Enter>", lambda e, b=btn: b.config(bg=T["select"]))
        btn.bind("<Leave>", lambda e, b=btn: b.config(bg=T["surface"]))
        btn.pack(side="right")
    selection_popup = pop

def show_selection_popup(x_root, y_root):
    """تحت المؤشر مباشرة (أو فوقه قرب أسفل الشاشة)، ولا تخرج عن حدود الشاشات."""
    if not selected_text().strip():
        hide_selection_popup()
        return
    if selection_popup is None:
        build_selection_popup()
    pop = selection_popup
    pop.update_idletasks()
    w, h = pop.winfo_reqwidth(), pop.winfo_reqheight()
    vx, vy, vw, vh = get_virtual_screen()
    x = max(vx, min(x_root - w // 2, vx + vw - w))
    y = y_root + px(16)
    if y + h > vy + vh:
        y = y_root - h - px(16)
    pop.geometry(f"+{x}+{y}")
    pop.deiconify()
    pop.lift()

def hide_popup_if_app_lost_focus(event=None):
    def check():
        try:
            focused = root.focus_get()
        except Exception:
            focused = None
        if focused is None:  # التركيز انتقل إلى برنامج آخر
            hide_selection_popup()
    root.after(150, check)

# التظليل يكتمل بعد إفلات الزر (سحب أو نقر مزدوج)، فنفحصه بعد لحظة
original_text_area.bind("<ButtonRelease-1>",
                        lambda e: root.after(10, lambda: show_selection_popup(e.x_root, e.y_root)), add="+")
original_text_area.bind("<ButtonPress-1>", hide_selection_popup, add="+")
original_text_area.bind("<Key>", hide_selection_popup, add="+")
root.bind("<Unmap>", lambda e: hide_selection_popup() if e.widget is root else None, add="+")
root.bind("<Configure>", lambda e: hide_selection_popup() if e.widget is root else None, add="+")
root.bind("<FocusOut>", hide_popup_if_app_lost_focus, add="+")

apply_theme(system_theme())
root.after(2000, watch_system_theme)

def check_tesseract():
    """رسالة المشكلة إن كان Tesseract أو إحدى حزمتي اللغة (ara/eng) غير مثبّت، وإلا None."""
    if not TESSERACT_PATH:
        return "لم يتم العثور على Tesseract. ثبّته في C:\\Program Files\\Tesseract-OCR"
    try:
        installed = pytesseract.get_languages()
    except Exception:
        return None  # لا نمنع العمل بسبب فشل الفحص نفسه
    missing = [name for code, name in (("ara", "العربية"), ("eng", "الإنجليزية")) if code not in installed]
    if missing:
        what = f"حزمة اللغة {missing[0]} غير مثبّتة" if len(missing) == 1 else "حزمتا اللغتين العربية والإنجليزية غير مثبّتتين"
        return f"{what} في Tesseract. أعد تثبيته واختر اللغة من Additional language data"
    return None

startup_problem = check_tesseract()
if startup_problem:
    set_status(startup_problem, "error")

if __name__ == "__main__":
    setup_hotkey()
    setup_tray()
    watch_show_requests()
    if tray_icon and "--show" not in sys.argv:  # --show: يبدأ بنافذة ظاهرة
        # يبدأ مخفياً: الوجود الوحيد في منطقة الإشعارات (الأيقونات المخفية)، بلا نافذة ولا زر في شريط المهام
        hide_to_tray()
        if startup_problem:  # الإخفاء يكتب حالة «يعمل في الخلفية»، فنعيد رسالة المشكلة ونُشعر بها
            set_status(startup_problem, "error")
        root.after(1500, lambda: notify_if_hidden(startup_problem or "يعمل في الخلفية. اضغط Ctrl+Shift+X لالتقاط نص"))
    root.mainloop()