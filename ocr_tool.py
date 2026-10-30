import json
import os
import re
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
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

APP_VERSION = "2.3.1"  # يطابق version_info.txt

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
kernel32.SetEvent.argtypes = kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
SHOW_EVENT_NAME = "alimwork85.ScreenOCRTool.show"
show_event = _instance_mutex = None
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
        "bg": "#F5F5F3", "surface": "#FFFFFF", "border": "#E1E1DD",
        "ink": "#0A0A0A", "muted": "#6B6B68",
        "primary": "#0A0A0A", "primary_hover": "#262626", "primary_press": "#3A3A3A", "on_primary": "#FFFFFF",
        "accent": "#E5352B", "select": "#FDECEA", "vio": "#6B4FBB", "chip": "#EDEDEA",
        "ok": "#1B7A4B", "warn": "#8A5A00", "error": "#C0392B", "info": "#0A0A0A",
    },
    "dark": {
        "bg": "#0B0B0B", "surface": "#141414", "border": "#2A2A2A",
        "ink": "#F5F5F5", "muted": "#9A9A9A",
        "primary": "#F5F5F5", "primary_hover": "#E0E0E0", "primary_press": "#CCCCCC", "on_primary": "#0A0A0A",
        "accent": "#E5352B", "select": "#2A1512", "vio": "#A58BFF", "chip": "#1E1E1E",
        "ok": "#5FBF8A", "warn": "#E0A040", "error": "#F0776A", "info": "#F5F5F5",
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
current_status = ("", "info")  # تُضبط بلغة الواجهة عند إنشاء سطر الحالة

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

# تحديد مسار Tesseract: النسخة المرفقة مع البرنامج أولاً، ثم التثبيت الافتراضي، ثم PATH
BUNDLED_TESSERACT = resource_path("tesseract/tesseract.exe")
DEFAULT_TESSERACT = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
if os.path.exists(BUNDLED_TESSERACT):
    TESSERACT_PATH = BUNDLED_TESSERACT
    os.environ["TESSDATA_PREFIX"] = resource_path("tesseract/tessdata")  # حزم اللغات المرفقة
else:
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
        self.snip_surface.attributes('-alpha', 0.5)
        # طبقة بلا إطار تغطي كل الشاشات (وليس الرئيسية فقط)
        self.origin_x, self.origin_y, width, height = get_virtual_screen()
        self.snip_surface.overrideredirect(True)
        # الصيغة +-300 ضرورية: -300 وحدها تعني "من الحافة اليمنى" في Tk
        self.snip_surface.geometry(f"{width}x{height}+{self.origin_x}+{self.origin_y}")
        self.snip_surface.attributes('-topmost', True)
        self.snip_surface.config(cursor="cross")

        self.canvas = tk.Canvas(self.snip_surface, cursor="cross", bg="#333333", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # شريط التلميح في أعلى الشاشة الرئيسية (وليس منتصف كل الشاشات)، ويختفي عند بدء السحب.
        # الجملتان نصّان منفصلان: خلط العربية واللاتينية في سطر واحد يقلب ترتيب القراءة على لوحة الرسم
        parts = [self.canvas.create_text(0, px(40), fill="white", font=(FONT, 14), text=t)
                 for t in L(("اسحب لتحديد المنطقة", "للإلغاء Esc"), ("Drag to select the area", "Esc to cancel"))]
        gap = px(28)
        widths = [self.canvas.bbox(t)[2] - self.canvas.bbox(t)[0] for t in parts]
        total = sum(widths) + gap * (len(parts) - 1)
        x = -self.origin_x + root.winfo_screenwidth() // 2 + (total // 2 if not UI_EN else -total // 2)
        for t, w in zip(parts, widths):
            self.canvas.coords(t, x, px(40))
            self.canvas.itemconfigure(t, anchor="e" if not UI_EN else "w")
            x += (-(w + gap) if not UI_EN else (w + gap))
        x1, y1, x2, y2 = self.canvas.bbox(*parts)
        pill = self.canvas.create_rectangle(x1 - px(16), y1 - px(8), x2 + px(16), y2 + px(8), fill="#0A0A0A", outline="")
        self.canvas.tag_raise("all")
        self.canvas.tag_lower(pill)
        self.canvas.tag_raise(parts[0]); self.canvas.tag_raise(parts[1])
        self.hint_items = (pill, *parts)

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
        self.canvas.delete(*self.hint_items)
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, 1, 1, outline=T["accent"], width=2)
        self.handles = [self.canvas.create_rectangle(0, 0, 0, 0, fill="white", outline=T["accent"], width=2) for _ in range(4)]
        self.badge_bg = self.canvas.create_rectangle(0, 0, 0, 0, fill="#0A0A0A", outline="")
        self.badge = self.canvas.create_text(0, 0, fill="white", font=("Consolas", 11), anchor="w")
        self.draw_selection(event.x, event.y)

    def draw_selection(self, cur_x, cur_y):
        """الإطار الأحمر وأربعة مقابض في زواياه وشارة بالمقاس (عرض × ارتفاع) فوقه."""
        x1, x2 = sorted((self.start_x, cur_x))
        y1, y2 = sorted((self.start_y, cur_y))
        self.canvas.coords(self.rect, x1, y1, x2, y2)
        r = px(4)
        for h, (cx, cy) in zip(self.handles, ((x1, y1), (x2, y1), (x1, y2), (x2, y2))):
            self.canvas.coords(h, cx - r, cy - r, cx + r, cy + r)
        ty = y1 - px(16) if y1 > px(36) else y2 + px(16)
        self.canvas.itemconfigure(self.badge, text=f"{x2 - x1} × {y2 - y1}")
        self.canvas.coords(self.badge, x1 + px(8), ty)
        bx1, by1, bx2, by2 = self.canvas.bbox(self.badge)
        self.canvas.coords(self.badge_bg, bx1 - px(6), by1 - px(3), bx2 + px(6), by2 + px(3))
        self.canvas.tag_raise(self.badge)

    def on_move_press(self, event):
        self.draw_selection(event.x, event.y)

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
                settings["last_region"] = list(bbox)  # لإعادة قراءة المنطقة نفسها من الاختصار الثاني
                save_settings()
                self.on_crop_complete(screenshot)
            except Exception as e:
                messagebox.showerror(L("خطأ في القص", "Capture error"),
                                     L(f"فشل التقاط الشاشة: {e}", f"Could not capture the screen: {e}"))
                if self.on_cancel:
                    self.on_cancel()
        else:
            if self.on_cancel:
                self.on_cancel(L("التحديد صغير جداً، حدّد مساحة أكبر", "Selection too small, select a larger area"), "warn")

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
        return L(f"خطأ في Tesseract: {str(e)}", f"Tesseract error: {str(e)}"), False

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
    status_label.config(text=text, fg=color, image=image, compound=SIDE)

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
    set_status(L("جاري قراءة النص", "Reading text"), "busy")

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
        set_status(L("لا توجد صورة في الحافظة. انسخ صورة أولاً", "No image on the clipboard. Copy an image first"), "warn")
        notify_if_hidden(L("لا توجد صورة في الحافظة", "No image on the clipboard"))
        return
    window_was_visible = ui_visible  # لا تظهر النافذة إن كان الطلب من الشريط وهي مخفية
    process_image(image)

def capture_last_region():
    """يقرأ منطقة آخر تحديد مرة أخرى بلا طبقة تحديد؛ مفيد لترجمة الشرائح والفيديو."""
    global window_was_visible
    if capture_active:
        return
    bbox = settings["last_region"]
    vx, vy, vw, vh = get_virtual_screen()
    if not bbox or not (vx <= bbox[0] < bbox[2] <= vx + vw and vy <= bbox[1] < bbox[3] <= vy + vh):
        message = L("لا توجد منطقة محفوظة تناسب الشاشات الحالية. حدّد منطقة أولاً",
                    "No saved region fits the current screens. Select an area first")
        set_status(message, "warn")
        notify_if_hidden(message)
        return
    window_was_visible = ui_visible
    if window_was_visible:  # نُخفي نافذتنا فلا تظهر داخل الصورة المقروءة، ويعيدها process_image
        root.withdraw()
        root.update()
        time.sleep(0.15)
    try:
        image = ImageGrab.grab(bbox=tuple(bbox), all_screens=True)
    except Exception as e:
        if window_was_visible:
            show_window()
        set_status(L(f"تعذّر التقاط المنطقة: {e}", f"Could not capture the region: {e}"), "error")
        return
    process_image(image)

def rtl_tags(text):
    """وسم المحاذاة اليمنى للنص العربي الغالب (target_lang تعيد en للنص العربي)."""
    return ("rtl",) if translator.target_lang(text) == "en" else ()

def show_original(text):
    """يكتب النص الأصلي ويحاذيه حسب لغته، لا حسب لغة الواجهة."""
    original_text_area.delete("1.0", tk.END)
    original_text_area.insert(tk.END, text, rtl_tags(text))

def update_gui(text, ok):
    show_original(text)
    if ok:
        copy_to_clipboard(text)
        add_to_history(text)
        set_status(L("تم استخراج النص والنسخ بنجاح", "Text extracted and copied"), "ok")
        notify_if_hidden(L("تم نسخ النص إلى الحافظة", "Text copied to the clipboard"))
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
        set_status(L("لا يوجد نص للترجمة", "No text to translate"), "warn")
        return
    translation_busy = True
    btn_translate.config(state="disabled")
    set_status(L("جاري الترجمة", "Translating"), "busy")

    def on_fallback(model):
        root.after(0, lambda: set_status(L(f"Google غير متاح، جاري الترجمة محلياً بـ {model} (قد تستغرق ثوانٍ)",
                                           f"Google unavailable, translating locally with {model} (may take a few seconds)"), "busy"))

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
        translation_frame.pack(side=END_SIDE, fill='y', before=original_text_area,
                               padx=(px(12), 0) if UI_EN else (0, px(12)))
    translation_label.config(text=L(f"الترجمة ({source})", f"Translation ({source})"))
    translation_area.config(state="normal")
    translation_area.delete("1.0", tk.END)
    translation_area.insert(tk.END, out, ("rtl",) if tl == "ar" else ())
    translation_area.config(state="disabled")
    copy_to_clipboard(out)
    set_status(L("تمت الترجمة ونُسخت إلى الحافظة", "Translated and copied to the clipboard"), "copied")

def translate_all():
    translate_text(original_text_area.get("1.0", tk.END))

# ---- البحث: يفتح بحث Google في المتصفح الافتراضي ----
SEARCH_LIMIT = 500  # طول معقول لعبارة البحث

def search_text(text):
    query = " ".join(text.split())[:SEARCH_LIMIT]  # الأسطر والمسافات الزائدة تصير مسافة واحدة
    if not query:
        set_status(L("لا يوجد نص للبحث", "No text to search"), "warn")
        return
    try:
        webbrowser.open("https://www.google.com/search?" + urllib.parse.urlencode({"q": query}))
        set_status(L("فُتح البحث في المتصفح", "Search opened in the browser"), "ok")
    except Exception as e:
        set_status(L(f"تعذّر فتح المتصفح: {e}", f"Could not open the browser: {e}"), "error")

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
    set_status(L(f"التطبيق يعمل في الخلفية ({pretty_hotkey(settings['hotkey'])})",
                 f"Running in the background ({pretty_hotkey(settings['hotkey'])})"), "info")

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
    # الإجراءات أولاً باختصاراتها (بعد \t يعرضها ويندوز في الطرف)، ثم النافذة والخروج
    keyed = lambda text, combo: (lambda item: f"{text}\t{pretty_hotkey(combo())}")
    menu = pystray.Menu(
        pystray.MenuItem(keyed(L("التقاط نص من الشاشة", "Capture text from screen"), lambda: settings["hotkey"]), to_ui(start_capture)),
        pystray.MenuItem(keyed(L("قراءة آخر منطقة", "Read last region"), lambda: LAST_REGION_HOTKEY), to_ui(capture_last_region)),
        pystray.MenuItem(L("قراءة صورة من الحافظة", "Read image from clipboard"), to_ui(ocr_from_clipboard)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(L("فتح النافذة", "Open window"), to_ui(show_window), default=True),
        pystray.MenuItem(L("خروج", "Exit"), to_ui(quit_app)),
    )
    try:
        tray_icon = pystray.Icon("ocr_tool", make_tray_image(), L(f"أداة OCR {APP_VERSION}", f"OCR Tool {APP_VERSION}"), menu)
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

# الإعدادات: لغة القراءة وحالة أسهم الطي ولغة الواجهة، تُحفظ فور تغييرها
LANG_VALUES = ('ara+eng', 'ara', 'eng')
HOTKEY_DEFAULT = "ctrl+shift+x"
LAST_REGION_HOTKEY = "ctrl+shift+z"  # ثابت لقراءة آخر منطقة، لا يقبل التغيير
HOTKEY_MODIFIERS = ("ctrl", "alt", "shift", "windows", "win")

def valid_hotkey(combo):
    """تركيبة مقبولة: مفتاح تعديل ومفتاح آخر على الأقل."""
    parts = str(combo).lower().split("+")
    return len(parts) > 1 and any(part in HOTKEY_MODIFIERS for part in parts)

def same_hotkey(first, second):
    """مقارنة بكود المسح لا بالحرف، فتتساوى 'ctrl+shift+z' مع ما يقرأه نفس الضغط في لغة أخرى."""
    try:
        return keyboard.parse_hotkey_combinations(first) == keyboard.parse_hotkey_combinations(second)
    except Exception:
        return first == second

def pretty_hotkey(combo):
    """'ctrl+shift+x' ← 'Ctrl+Shift+X' للعرض في الواجهة."""
    return "+".join(part.capitalize() for part in combo.split("+"))

def load_settings():
    def convert(data):
        collapsed = data.get("collapsed", {})
        hotkey = str(data.get("hotkey", "")).lower()
        region = data.get("last_region")
        if not (isinstance(region, list) and len(region) == 4 and all(isinstance(v, int) for v in region)):
            region = None
        return {"lang": data.get("lang") if data.get("lang") in LANG_VALUES else 'ara+eng',
                "collapsed": {k: bool(v) for k, v in collapsed.items()} if isinstance(collapsed, dict) else {},
                "ui": "en" if data.get("ui") == "en" else "ar",
                "autostart": data.get("autostart") is True,
                "hotkey": hotkey if valid_hotkey(hotkey) else HOTKEY_DEFAULT,
                "last_region": region}
    return read_json(SETTINGS_PATH, convert, {"lang": 'ara+eng', "collapsed": {}, "ui": "ar",
                                              "autostart": False, "hotkey": HOTKEY_DEFAULT, "last_region": None})

settings = load_settings()

# لغة الواجهة تُقرأ مرة عند البدء؛ الإنجليزية تقلب الترتيب إلى اليسار، وتغييرها يعيد التشغيل (switch_ui_language)
UI_EN = settings["ui"] == "en"
SIDE, END_SIDE, ANCHOR = ('left', 'right', 'w') if UI_EN else ('right', 'left', 'e')
translator.UI_EN = UI_EN

def L(ar, en):
    """النص بلغة الواجهة."""
    return en if UI_EN else ar

def mirror(pad):
    """هامش (يسار، يمين) مكتوب للعربية؛ يُعكس في الإنجليزية."""
    return pad[::-1] if UI_EN else pad

# سهم الطي يشير نحو المحتوى وهو ظاهر، وعكسه وهو مطوي
CHEVRON_OPEN, CHEVRON_CLOSED = ("chevron_left", "chevron_right") if UI_EN else ("chevron_right", "chevron_left")

NO_TEXT_MSG = L("لم يتم التعرف على أي نص", "No text recognized")

def save_settings():
    write_json(SETTINGS_PATH, settings)

# ---- التشغيل مع Windows: قيمة في مفتاح Run تحت HKCU، ولا معنى لها عند العمل من الكود ----
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "OCR_Tool"

def autostart_command():
    """الأمر المسجَّل في السجل، أو None عند تشغيل الكود (لا مسار EXE بعد)."""
    return f'"{sys.executable}"' if getattr(sys, "frozen", False) else None

def read_autostart():
    """القيمة المسجَّلة حالياً، أو None إن لم توجد."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, RUN_VALUE)[0]
    except Exception:
        return None

def set_autostart(on):
    """يكتب القيمة أو يحذفها. تعيد نجحت العملية؟"""
    command = autostart_command()
    if on and not command:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, command)
            else:
                winreg.DeleteValue(key, RUN_VALUE)
    except FileNotFoundError:
        pass  # لا قيمة لحذفها، فالإلغاء محقَّق
    except Exception:
        return False
    return True

def sync_autostart():
    """المستخدم نقل مجلد البرنامج: يُحدَّث المسار المسجَّل عند كل بدء."""
    command = autostart_command()
    if settings["autostart"] and command and read_autostart() != command:
        settings["autostart"] = set_autostart(True)
        save_settings()

# ---- سجل النتائج: لا يُحذف منه شيء إلا بزر «مسح السجل» ----
history = []  # أحدث نتيجة أولاً: [الوقت بصيغة ISO، النص]

def load_history():
    return read_json(HISTORY_PATH, lambda data: [[str(stamp), str(text)] for stamp, text in data if text], [])

def save_history():
    if not write_json(HISTORY_PATH, history):
        set_status(L("تعذّر حفظ السجل", "Could not save the history"), "warn")

def history_stamp(iso):
    """الساعة فقط لنتائج اليوم، والتاريخ معها لما قبله."""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return dt.strftime("%H:%M") if dt.date() == datetime.now().date() else dt.strftime("%Y-%m-%d %H:%M")

def refresh_history_list():
    history_list.delete(*history_list.get_children())
    for i, (stamp, item) in enumerate(history):
        preview = " ".join(item.split())
        if len(preview) > 70:
            preview = preview[:70] + "…"
        history_list.insert("", tk.END, iid=str(i), values=(history_stamp(stamp), preview))

def add_to_history(text):
    if history and history[0][1] == text:
        return
    history.insert(0, [datetime.now().isoformat(timespec="seconds"), text])
    save_history()
    refresh_history_list()

def clear_history():
    if not history:
        set_status(L("السجل فارغ", "History is empty"), "info")
        return
    if not messagebox.askyesno(L("مسح السجل", "Clear history"),
                               L(f"حذف كل النتائج المحفوظة في السجل ({len(history)})؟\nلا يمكن التراجع عن ذلك.",
                                 f"Delete all saved results in the history ({len(history)})?\nThis cannot be undone."),
                               icon="warning", default="no", parent=root):
        return
    history.clear()
    save_history()
    refresh_history_list()
    set_status(L("تم مسح السجل", "History cleared"), "ok")

def on_history_select(event=None):
    selection = history_list.selection()
    if not selection:
        return
    text = history[int(selection[0])][1]
    show_original(text)
    copy_to_clipboard(text)
    set_status(L("تم نسخ النص من السجل", "Text copied from the history"), "copied")

def watch_show_requests():
    """نسخة ثانية شُغّلت: تُظهر نافذة هذه النسخة بدل أن تعمل بجانبها."""
    if show_event and kernel32.WaitForSingleObject(show_event, 0) == 0:
        show_window()
    root.after(300, watch_show_requests)

# ---- اختصار الالتقاط: يُسجَّل من settings، ويُحفظ مقبض التسجيل لحذفه عند التغيير ----
hotkey_handle = None
hotkey_capturing = False
hotkey_chip: "tk.Label | None" = None  # يُنشأ مع الواجهة، ويُحدَّث نصه بعد كل تغيير

def on_hotkey():
    """مكتبة keyboard تستدعي الدالة من خيطها الخاص، فنحوّل التنفيذ إلى خيط الواجهة."""
    root.after(0, start_capture)

def register_hotkey(combo):
    """يسجّل الاختصار. تعيد نجح التسجيل؟"""
    global hotkey_handle
    try:
        hotkey_handle = keyboard.add_hotkey(combo, on_hotkey)
        return True
    except Exception:
        hotkey_handle = None
        return False

def unregister_hotkey():
    global hotkey_handle
    if hotkey_handle is not None:
        try:
            keyboard.remove_hotkey(hotkey_handle)
        except Exception:
            pass
        hotkey_handle = None

# اختصار ثابت لقراءة آخر منطقة محددة بلا طبقة تحديد (LAST_REGION_HOTKEY أعلاه)
last_region_handle = None

def on_last_region_hotkey():
    root.after(0, capture_last_region)

def register_last_region_hotkey():
    """تسجيله اختياري: فشله لا يمنع باقي البرنامج، ولذلك بلا رسالة."""
    global last_region_handle
    try:
        last_region_handle = keyboard.add_hotkey(LAST_REGION_HOTKEY, on_last_region_hotkey)
    except Exception:
        last_region_handle = None

def unregister_last_region_hotkey():
    global last_region_handle
    if last_region_handle is not None:
        try:
            keyboard.remove_hotkey(last_region_handle)
        except Exception:
            pass
        last_region_handle = None

def setup_hotkey():
    if not register_hotkey(settings["hotkey"]):
        set_status(L(f"تعذّر تفعيل الاختصار {pretty_hotkey(settings['hotkey'])}، استخدم زر «تغيير»",
                     f"Could not register {pretty_hotkey(settings['hotkey'])}, use the Change button"), "warn")
    register_last_region_hotkey()

LATIN_KEYS = "abcdefghijklmnopqrstuvwxyz0123456789"

def base_scans(name):
    """أكواد المسح الأساسية بلا بت الامتداد، لمقارنة المفاتيح التي تختلف صيغتها بين الأسماء."""
    try:
        return {code & 0xFF for code in keyboard.key_to_scan_codes(name)}
    except Exception:
        return set()

def latin_hotkey(combo):
    """الاسم بالحروف اللاتينية: المكتبة تقرأ المفتاح بحروف لغة الكيبورد (ctrl+alt+ن)، فنرجعه لمفتاحه اللاتيني بكود المسح نفسه."""
    parts = []
    for part in combo.split("+"):
        if part.isascii():
            parts.append(part)
            continue
        scans = base_scans(part)
        match = next((key for key in LATIN_KEYS if scans and base_scans(key) == scans), None)
        parts.append(match or part)
    return "+".join(parts)

def read_combo():
    """ينتظر التركيبة التالية؛ '' إن فشل الانتظار."""
    try:
        return latin_hotkey(keyboard.read_hotkey(suppress=False))
    except Exception:
        return ""

def change_hotkey():
    """يقرأ تركيبة جديدة في خيط منفصل. نُوقف التسجيل الحالي أولاً كي لا يفتح التحديد أثناء القراءة."""
    global hotkey_capturing
    if hotkey_capturing:
        return
    hotkey_capturing = True
    unregister_hotkey()
    unregister_last_region_hotkey()  # وإلا قرأ آخر منطقة أثناء انتظار التركيبة الجديدة
    set_status(L("اضغط الاختصار الجديد الآن، أو Esc للإلغاء", "Press the new shortcut now, or Esc to cancel"), "info")
    threading.Thread(target=lambda: root.after(0, apply_hotkey, read_combo()), daemon=True).start()

def apply_hotkey(combo):
    """يثبّت التركيبة المقروءة، أو يعيد القديمة عند الإلغاء أو الرفض أو الفشل."""
    global hotkey_capturing
    hotkey_capturing = False
    old = settings["hotkey"]
    problem = None
    if combo in ("", "esc"):
        problem = (L("أُلغي تغيير الاختصار", "Shortcut change cancelled"), "info")
    elif not valid_hotkey(combo):
        problem = (L("لا يُقبل اختصار بلا مفتاح تعديل (Ctrl أو Alt أو Shift)", "Use a modifier key as well (Ctrl, Alt or Shift)"), "warn")
    elif same_hotkey(combo, LAST_REGION_HOTKEY):
        problem = (L(f"{pretty_hotkey(LAST_REGION_HOTKEY)} محفوظ لقراءة آخر منطقة، اختر غيره",
                     f"{pretty_hotkey(LAST_REGION_HOTKEY)} is reserved for reading the last region, choose another"), "warn")
    elif not register_hotkey(combo):
        problem = (L("تعذّر تسجيل الاختصار الجديد، بقي القديم", "Could not register the new shortcut, the old one is kept"), "warn")
    if problem:
        register_hotkey(old)
        register_last_region_hotkey()
        set_status(*problem)
        return
    settings["hotkey"] = combo
    save_settings()
    if tray_icon:
        tray_icon.update_menu()  # اختصار التقاط يظهر في القائمة
    register_last_region_hotkey()
    if hotkey_chip is not None:
        hotkey_chip.config(text=pretty_hotkey(combo))
    set_status(L(f"صار الاختصار {pretty_hotkey(combo)}", f"Shortcut is now {pretty_hotkey(combo)}"), "ok")

def switch_ui_language():
    """يحفظ اللغة الأخرى ثم يعيد تشغيل البرنامج، لأن اتجاه الواجهة كله يُبنى مرة عند البدء."""
    settings["ui"] = "ar" if UI_EN else "en"
    save_settings()
    # نحرّر قفل النسخة الواحدة أولاً، وإلا ترى النسخة الجديدة هذه النسخة فتخرج
    for handle in (_instance_mutex, show_event):
        if handle:
            kernel32.CloseHandle(handle)
    script = [] if getattr(sys, "frozen", False) else [os.path.abspath(__file__)]
    try:
        subprocess.Popen([sys.executable, *script, "--show"])
    except Exception as e:
        set_status(L(f"تعذّرت إعادة التشغيل: {e}", f"Could not restart: {e}"), "error")
        return
    quit_app()

# ========================================================
# 4. الواجهة الرسومية
# ========================================================
root = tk.Tk()
root.title(L(f"أداة قراءة النصوص OCR المتقدمة - {APP_VERSION}", f"Advanced OCR Text Reader - {APP_VERSION}"))
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

# شريط تمرير ttk على ثيم clam: شريط Windows الافتراضي يتجاهل الألوان فيبقى أبيض في الثيم الداكن
style = ttk.Style(root)
style.theme_use("clam")
SCROLLBAR_STYLE = "Theme.Vertical.TScrollbar"
HISTORY_STYLE = "History.Treeview"

def theme_scrollbar(box):
    """يستبدل شريط ScrolledText بشريط ttk يتبع ألوان الثيم، في مكانه نفسه (يمين المربع)."""
    box.vbar.destroy()
    bar = ttk.Scrollbar(box.frame, orient="vertical", command=box.yview, style=SCROLLBAR_STYLE)
    bar.pack(side="right", fill="y")
    box.vbar = bar
    box.configure(yscrollcommand=bar.set)
    return bar

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
    style.configure(SCROLLBAR_STYLE, background=T["surface"], troughcolor=T["bg"], bordercolor=T["border"],
                    arrowcolor=T["muted"], lightcolor=T["surface"], darkcolor=T["surface"])
    style.map(SCROLLBAR_STYLE, background=[("active", T["select"])], arrowcolor=[("active", T["ink"])])
    style.configure(HISTORY_STYLE, background=T["surface"], fieldbackground=T["surface"], foreground=T["ink"],
                    borderwidth=0, bordercolor=T["surface"], lightcolor=T["surface"], darkcolor=T["surface"],
                    rowheight=px(30), font=(FONT, 11))
    style.map(HISTORY_STYLE, background=[("selected", T["select"])], foreground=[("selected", T["ink"])])
    for widget, opts in _themed:
        widget.configure(**{k: T[v] for k, v in opts.items()})
    for lbl, name, size, color_key in _icon_labels:
        lbl.configure(image=ui_icons.tk_icon(name, px(size), T[color_key]))
    btn_capture.configure(image=ui_icons.tk_icon("capture", px(22), T["on_primary"]))
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
    reg(btn, bg="primary", fg="on_primary", activebackground="primary_press", activeforeground="on_primary",
        highlightbackground="primary", highlightcolor="accent")
    btn.config(highlightthickness=2, takefocus=True)

btn_capture = tk.Button(
    main_frame,
    text="  " + L("تحديد وقص الشاشة", "Select screen area"),
    image=ui_icons.tk_icon("capture", px(22), T["on_primary"]), compound=SIDE,
    command=start_capture,
    fg='white',
    font=(FONT, 13, 'bold'), relief='flat', bd=0, pady=px(8), cursor="hand2"
)
style_button(btn_capture)
btn_capture.pack(fill='x', pady=(0, px(8)))

def add_hint(parent, label, key):
    """«للإلغاء Esc» بالعربية، و«Esc to cancel» بالإنجليزية؛ الاختصار داخل شريحة، من بداية السطر."""
    text = reg(tk.Label(parent, text=label, font=(FONT, 11)), bg="bg", fg="muted")
    chip = reg(tk.Label(parent, text=key, font=("Consolas", 10), padx=px(6), pady=px(1), highlightthickness=1),
               bg="surface", fg="ink", highlightbackground="border")
    if UI_EN:
        chip.pack(side=SIDE, padx=(px(10), 0))
        text.pack(side=SIDE, padx=(px(4), 0))
    else:
        text.pack(side=SIDE, padx=(px(10), px(4)))
        chip.pack(side=SIDE)

hint_frame = reg(tk.Frame(main_frame), bg="bg")
hint_frame.pack(anchor=ANCHOR, pady=(0, px(12)))

def collapse_arrow(parent, content, key):
    """سهم بين العنوان ومحتواه: يطوي المحتوى (بعده في السطر) أو يعيده. يُستدعى بعد إنشاء العنوان والمحتوى.

    key: اسم السطر في settings["collapsed"]، فتبقى حالته بين التشغيلات."""
    arrow = reg(tk.Label(parent, cursor="hand2"), bg="bg")
    entry = [arrow, CHEVRON_OPEN, 16, "muted"]  # قائمة لا صف: الاسم واللون يتغيران، وapply_theme يقرأ الحالي
    _icon_labels.append(entry)

    def paint(color_key):
        entry[3] = color_key
        arrow.config(image=ui_icons.tk_icon(entry[1], px(16), T[color_key]))

    def toggle(event=None):
        if content.winfo_manager():
            content.pack_forget()
            entry[1] = CHEVRON_CLOSED
        else:
            content.pack(side=SIDE)
            entry[1] = CHEVRON_OPEN
        paint("primary")
        settings["collapsed"][key] = not content.winfo_manager()
        save_settings()

    arrow.bind("<Button-1>", toggle)
    arrow.bind("<Enter>", lambda e: paint("primary"))
    arrow.bind("<Leave>", lambda e: paint("muted"))
    paint("muted")
    arrow.pack(side=SIDE, padx=mirror((px(4), px(2))))
    if settings["collapsed"].get(key):
        entry[1] = CHEVRON_CLOSED
        paint("muted")
    else:
        content.pack(side=SIDE)
    return arrow

reg(tk.Label(hint_frame, text=L("اختصار التحديد", "Capture shortcut"), font=(FONT, 11)), bg="bg", fg="muted").pack(side=SIDE)
hint_content = reg(tk.Frame(hint_frame), bg="bg")
hotkey_chip = reg(tk.Label(hint_content, text=pretty_hotkey(settings["hotkey"]), font=("Consolas", 10),
                           padx=px(6), pady=px(1), highlightthickness=1),
                  bg="surface", fg="ink", highlightbackground="border")
hotkey_chip.pack(side=SIDE)
btn_change_hotkey = tk.Button(hint_content, text=L("تغيير", "Change"), font=(FONT, 10), relief='flat', bd=0,
                              padx=px(6), pady=px(1), highlightthickness=1, cursor="hand2", command=change_hotkey)
reg(btn_change_hotkey, bg="surface", fg="ink", activebackground="select", activeforeground="ink",
    highlightbackground="border", highlightcolor="primary")
btn_change_hotkey.pack(side=SIDE, padx=mirror((px(4), 0)))
add_hint(hint_content, L("للإلغاء", "to cancel"), "Esc")
collapse_arrow(hint_frame, hint_content, "hints")

lang_frame = reg(tk.Frame(main_frame), bg="bg")
lang_frame.pack(anchor=ANCHOR, pady=(0, 8))
lang_var = tk.StringVar(value=settings["lang"])
lang_var.trace_add("write", lambda *_: (settings.update(lang=lang_var.get()), save_settings()))
icon_label(lang_frame, "languages", 18, "muted", side=SIDE, padx=mirror((6, 0)))
reg(tk.Label(lang_frame, text=L("لغة القراءة", "Reading language"), font=(FONT, 11, 'bold')), bg="bg", fg="ink").pack(side=SIDE)
lang_content = reg(tk.Frame(lang_frame, padx=3, pady=3), bg="chip")  # شريط اختيار: الخيار المحدد يبرز بلون السطح
for label, value in zip(L(("عربي + إنجليزي", "عربي فقط", "إنجليزي فقط"),
                          ("Arabic + English", "Arabic only", "English only")), LANG_VALUES):
    reg(tk.Radiobutton(
        lang_content, text=label, value=value, variable=lang_var,
        font=(FONT, 11), highlightthickness=0, cursor="hand2", indicatoron=False, bd=0, padx=px(12), pady=px(4)
    ), bg="chip", fg="ink", activebackground="chip", activeforeground="ink", selectcolor="surface").pack(side=SIDE, padx=1)
collapse_arrow(lang_frame, lang_content, "lang")

# التشغيل مع Windows: يُسجَّل مسار EXE في مفتاح Run، ويعود المربع لحاله إن فشل التسجيل
autostart_var = tk.BooleanVar(value=settings["autostart"])
autostart_frame = reg(tk.Frame(main_frame), bg="bg")
autostart_frame.pack(side='bottom', fill='x', pady=(px(8), 0))  # أسفل النافذة تحت السجل (يُرزم قبل السجل ليبقى الأخير)

def toggle_autostart():
    on = autostart_var.get()
    if not set_autostart(on):
        autostart_var.set(not on)
        set_status(L("تعذّر تعديل إعداد التشغيل مع Windows", "Could not change the Start with Windows setting"), "warn")
        return
    settings["autostart"] = on
    save_settings()
    set_status(L("سيعمل مع Windows عند تسجيل الدخول" if on else "لن يعمل مع Windows عند تسجيل الدخول",
                 "Will start with Windows at sign-in" if on else "Will not start with Windows at sign-in"), "ok")

autostart_box = reg(tk.Checkbutton(
    autostart_frame, text="  " + L("التشغيل مع Windows", "Start with Windows"), variable=autostart_var,
    command=toggle_autostart, font=(FONT, 11), highlightthickness=0, cursor="hand2"
), bg="bg", fg="ink", activebackground="bg", activeforeground="primary", selectcolor="surface")
autostart_box.pack(side=SIDE)
if not autostart_command():  # من الكود لا مسار EXE يُسجَّل، فنوضّح ذلك بجانب المربع
    autostart_box.config(state="disabled", cursor="arrow")
    reg(autostart_box, disabledforeground="muted")  # نص المربع المعطَّل يتبع الثيم
    reg(tk.Label(autostart_frame, text=L("من نسخة EXE فقط", "Built app only"), font=(FONT, 10)),
        bg="bg", fg="muted").pack(side=SIDE, padx=px(6))
# تلميح الاختصار الثابت في الطرف المقابل من السطر السفلي
last_region_hint = reg(tk.Frame(autostart_frame), bg="bg")
last_region_hint.pack(side=END_SIDE)
add_hint(last_region_hint, L("قراءة آخر منطقة", "Read last region"), pretty_hotkey(LAST_REGION_HOTKEY))

def secondary_button(parent, text, icon, command):
    """زر ثانوي بإطار رفيع (أخف من زر التحديد الرئيسي)، يُرتَّب من بداية السطر."""
    btn = tk.Button(parent, text="  " + text, command=command, font=(FONT, 11), compound=SIDE,
                    image=ui_icons.tk_icon(icon, px(16), T["ink"]), relief='flat', bd=0,
                    padx=px(10), pady=px(3), highlightthickness=1, cursor="hand2", takefocus=True)
    reg(btn, bg="surface", fg="ink", activebackground="select", activeforeground="ink",
        highlightbackground="border", highlightcolor="primary")
    _icon_labels.append((btn, icon, 16, "ink"))  # تتبدّل أيقونته مع الثيم
    btn.bind("<Enter>", lambda e: btn.config(bg=T["select"]))
    btn.bind("<Leave>", lambda e: btn.config(bg=T["surface"]))
    btn.pack(side=SIDE, padx=mirror((px(8), 0)))
    return btn

actions_frame = reg(tk.Frame(main_frame), bg="bg")
actions_frame.pack(anchor=ANCHOR, pady=(0, px(10)))
btn_clipboard = secondary_button(actions_frame, L("قراءة صورة من الحافظة", "Read image from clipboard"), "copy", ocr_from_clipboard)
# رأس بطاقة النتيجة: العنوان والحالة من البداية، وأزرار الترجمة والبحث في الطرف المقابل
result_head = reg(tk.Frame(main_frame), bg="bg")
btn_translate = secondary_button(result_head, L("ترجمة", "Translate"), "globe", translate_all)
btn_search = secondary_button(result_head, L("بحث", "Search"), "search", search_all)
for _b in (btn_translate, btn_search):
    _b.pack_configure(side=END_SIDE, padx=mirror((px(8), 0)))
# اسم اللغة الأخرى بلغتها، ليجده من لا يقرأ لغة الواجهة الحالية
btn_ui_lang = secondary_button(actions_frame, L("English", "العربية"), "language", switch_ui_language)

current_status = (L("جاهز للاستخدام", "Ready"), "info")
reg(tk.Label(result_head, text=L("النص المستخرج", "Extracted text"), font=(FONT, 12, 'bold')), bg="bg", fg="ink").pack(side=SIDE)
status_label = reg(tk.Label(result_head, text=current_status[0], font=(FONT, 11), padx=px(8)), bg="chip", fg="muted")
status_label.pack(side=SIDE, padx=px(10))
result_head.pack(fill='x', pady=(0, px(6)))

history_frame = reg(tk.Frame(main_frame), bg="bg")
history_frame.pack(side='bottom', fill='x', pady=(12, 0))
history_header = reg(tk.Frame(history_frame), bg="bg")
history_header.pack(fill='x', pady=(0, 4))
icon_label(history_header, "history", 16, "muted", side=SIDE, padx=mirror((6, 0)))
reg(tk.Label(history_header, text=L("آخر النتائج (اضغط على نتيجة لعرضها ونسخها)", "Recent results (click one to view and copy it)"),
             font=(FONT, 10)), bg="bg", fg="muted").pack(side=SIDE, padx=mirror((0, 6)))
btn_clear_history = secondary_button(history_header, L("مسح السجل", "Clear history"), "trash", clear_history)
btn_clear_history.pack_configure(side=END_SIDE, padx=0)  # في الطرف المقابل لعنوان السجل
# جدول من عمودين (الوقت والنص): الوقت من بداية السطر، والعربية من اليمين والإنجليزية من اليسار
history_box = reg(tk.Frame(history_frame, highlightthickness=1), bg="surface", highlightbackground="border")
history_box.pack(fill='x')
history_list = ttk.Treeview(history_box, columns=("t", "x"), show="", height=5, selectmode="browse", style=HISTORY_STYLE,
                            displaycolumns=("t", "x") if UI_EN else ("x", "t"))
history_list.column("t", width=px(120), stretch=False, anchor="w" if UI_EN else "e")
history_list.column("x", anchor="w" if UI_EN else "e")
history_list.pack(fill='x')
history_list.bind("<<TreeviewSelect>>", on_history_select)  # التحديد بلوحة المفاتيح
history_list.bind("<ButtonRelease-1>", on_history_select)  # الضغط على نتيجة محددة مسبقاً لا يغيّر التحديد فلا يطلق الحدث الأول
history[:] = load_history()  # السجل المحفوظ من التشغيلات السابقة
refresh_history_list()

original_text_area = reg(scrolledtext.ScrolledText(
    main_frame, wrap=tk.WORD, font=(FONT, 13), relief='flat', bd=0,
    padx=px(14), pady=px(12), highlightthickness=1
), bg="surface", fg="ink", highlightbackground="border", highlightcolor="primary",
   selectbackground="select", selectforeground="ink", insertbackground="ink")
original_text_area.pack(fill='both', expand=True)
original_text_area.tag_configure("rtl", justify="right")  # يُطبَّق في show_original حسب لغة النص
theme_scrollbar(original_text_area)

# مربع الترجمة: للقراءة فقط، ويظهر بعد النص الأصلي (يساره في العربية) بنصف العرض بعد أول ترجمة (show_translation)
translation_frame = reg(tk.Frame(main_frame), bg="bg")
translation_frame.pack_propagate(False)  # عرضه يُضبط بنصف المساحة، لا بحجم محتواه
translation_label = reg(tk.Label(translation_frame, text=L("الترجمة", "Translation"), font=(FONT, 10)), bg="bg", fg="vio")
translation_label.pack(anchor=ANCHOR, pady=(0, px(4)))
translation_area = reg(scrolledtext.ScrolledText(
    translation_frame, wrap=tk.WORD, font=(FONT, 13), width=1, height=1, relief='flat', bd=0,
    padx=px(14), pady=px(12), highlightthickness=1, state="disabled"
), bg="surface", fg="ink", highlightbackground="border", highlightcolor="vio",
   selectbackground="select", selectforeground="ink", insertbackground="ink")
translation_area.tag_configure("rtl", justify="right")
translation_area.pack(fill='both', expand=True)
theme_scrollbar(translation_area)
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
        set_status(L("تم نسخ النص المحدد", "Selected text copied"), "copied")
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
    for label, icon, action in ((L("نسخ", "Copy"), "copy", "copy"), (L("ترجمة", "Translate"), "globe", "translate"),
                                (L("بحث", "Search"), "search", "search")):
        btn = tk.Button(box, text=" " + label, image=ui_icons.tk_icon(icon, px(15), T["ink"]), compound=SIDE,
                        font=(FONT, 10), relief="flat", bd=0, padx=px(8), pady=px(2), cursor="hand2",
                        command=lambda a=action: on_selection_action(a))
        reg(btn, bg="surface", fg="ink", activebackground="select", activeforeground="ink")
        _icon_labels.append((btn, icon, 15, "ink"))
        btn.bind("<Enter>", lambda e, b=btn: b.config(bg=T["select"]))
        btn.bind("<Leave>", lambda e, b=btn: b.config(bg=T["surface"]))
        btn.pack(side=SIDE)
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
    """رسالة المشكلة إن كان Tesseract أو إحدى حزمتي اللغة (ara/eng) ناقصًا، وإلا None."""
    if not TESSERACT_PATH:
        return L("لم يتم العثور على Tesseract المرفق. أعد تثبيت البرنامج، أو ثبّت Tesseract في C:\\Program Files\\Tesseract-OCR",
                 "The bundled Tesseract was not found. Reinstall the app, or install Tesseract in C:\\Program Files\\Tesseract-OCR")
    try:
        installed = pytesseract.get_languages()
    except Exception:
        return None  # لا نمنع العمل بسبب فشل الفحص نفسه
    missing = [name for code, name in (("ara", L("العربية", "Arabic")), ("eng", L("الإنجليزية", "English")))
               if code not in installed]
    if missing:
        if UI_EN:
            what = f"The {missing[0]} language data is" if len(missing) == 1 else "The Arabic and English language data are"
            return f"{what} missing from the bundled Tesseract. Reinstall the app"
        what = f"حزمة اللغة {missing[0]} ناقصة" if len(missing) == 1 else "حزمتا اللغتين العربية والإنجليزية ناقصتان"
        return f"{what} في Tesseract المرفق. أعد تثبيت البرنامج"
    return None

startup_problem = check_tesseract()
if startup_problem:
    set_status(startup_problem, "error")

if __name__ == "__main__":
    sync_autostart()
    setup_hotkey()
    setup_tray()
    watch_show_requests()
    if tray_icon and "--show" not in sys.argv:  # --show: يبدأ بنافذة ظاهرة
        # يبدأ مخفياً: الوجود الوحيد في منطقة الإشعارات (الأيقونات المخفية)، بلا نافذة ولا زر في شريط المهام
        hide_to_tray()
        if startup_problem:  # الإخفاء يكتب حالة «يعمل في الخلفية»، فنعيد رسالة المشكلة ونُشعر بها
            set_status(startup_problem, "error")
        root.after(1500, lambda: notify_if_hidden(startup_problem or L(f"يعمل في الخلفية. اضغط {pretty_hotkey(settings['hotkey'])} لالتقاط نص",
                                                                         f"Running in the background. Press {pretty_hotkey(settings['hotkey'])} to capture text")))
    root.mainloop()