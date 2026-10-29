"""قياس دقة وسرعة Tesseract مقابل محرك Windows OCR على عيّنات tools/bench_samples.

قياس فقط: لا يُدمج شيء في التطبيق. حزمة winrt تُثبَّت في بيئة القياس وحدها ولا تُضاف إلى requirements.txt:
    py -3.14 -m pip install winrt-runtime winrt-Windows.Foundation winrt-Windows.Foundation.Collections winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging winrt-Windows.Storage winrt-Windows.Storage.Streams winrt-Windows.Globalization

كل صورة معها ملف .txt بالنص الصحيح. CER = مسافة التحرير بالحروف ÷ طول النص الصحيح.
زمن Windows يشمل تحويل الصورة إلى SoftwareBitmap، وزمن Tesseract هو perform_ocr كما يستخدمه التطبيق.
ملاحظة: السطر العربي الخالص يعود من Windows OCR بترتيب كلمات معكوس (ترتيب عرضي) فيُعاد قلبه قبل القياس.
للتشغيل بلا مساس ببياناتك الحقيقية: اضبط APPDATA على مجلد مؤقت، وأضف مجلد حزم المستخدم إلى PYTHONPATH.
"""
import os
import re
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "tools", "bench_samples")
BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def normalize(text):
    return " ".join(BIDI.sub("", text).split())


def edit_distance(first, second):
    previous = list(range(len(second) + 1))
    for i, char_a in enumerate(first, 1):
        current = [i]
        for j, char_b in enumerate(second, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b)))
        previous = current
    return previous[-1]


def cer(reference, hypothesis):
    reference = normalize(reference)
    return edit_distance(reference, normalize(hypothesis)) / max(1, len(reference))


def arabic_share(text):
    arabic = sum(1 for ch in text if "\u0600" <= ch <= "\u06ff")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return arabic > latin


def windows_reader():
    """يعيد دالة (صورة، لغة) ← (نص، مللي ثانية)، أو None إن لم تتوفر حزمة winrt."""
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter
    except ImportError:
        return None

    available = {lang.language_tag for lang in OcrEngine.available_recognizer_languages}
    if "ar-SA" not in available:
        print("حزمة اللغة العربية لمحرك Windows OCR غير مثبّتة (ar-SA). ثبّتها من إعدادات Windows ← اللغة ← OCR ثم أعد المحاولة.")
        sys.exit(1)

    engines = {}

    def engine_for(tag):
        if tag not in engines:
            engines[tag] = OcrEngine.try_create_from_language(Language(tag))
            if engines[tag] is None:
                sys.exit(f"محرك Windows OCR لا يدعم اللغة {tag}")
        return engines[tag]

    def read(image, tag):
        # خيط منفصل: خيط Tk الرئيسي STA وويندوز OCR يرفض الانتظار فيه
        box = {}

        def work():
            try:
                start = time.perf_counter()
                rgba = image.convert("RGBA")
                raw = rgba.tobytes()
                bgra = bytearray(raw)
                bgra[0::4], bgra[2::4] = raw[2::4], raw[0::4]  # RGBA ← BGRA
                writer = DataWriter()
                writer.write_bytes(bytes(bgra))
                bitmap = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.BGRA8,
                                                                image.width, image.height, BitmapAlphaMode.PREMULTIPLIED)
                result = engine_for(tag).recognize_async(bitmap).get()
                box["text"] = windows_text(result)
                box["ms"] = (time.perf_counter() - start) * 1000
            except BaseException as error:  # يمرّر الخطأ إلى الخيط الرئيسي
                box["error"] = error

        worker = threading.Thread(target=work)
        worker.start()
        worker.join()
        if "error" in box:
            raise box["error"]
        return box["text"], box["ms"]

    return read


def windows_text(result):
    """نص Windows OCR بترتيب منطقي: السطر العربي الخالص يعود بترتيب معكوس (عرضي) من المحرك."""
    lines = []
    for line in result.lines:
        words = [word.text for word in line.words]
        has_arabic = any("\u0600" <= ch <= "\u06ff" for ch in line.text)
        has_latin = any(ch.isascii() and ch.isalpha() for ch in line.text)
        if has_arabic and not has_latin:
            words.reverse()
        lines.append(" ".join(words))
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", default=SAMPLES, help="مجلد الصور والنصوص الصحيحة")
    args = parser.parse_args()

    sys.path.insert(0, ROOT)  # مجلد المشروع حتى يوجد ocr_tool عند تشغيل السكربت من tools/
    import ocr_tool  # نافذة التطبيق تُنشأ عند الاستيراد؛ نخفيها ونستخدم دالة القراءة نفسها
    ocr_tool.root.withdraw()

    read_windows = windows_reader()
    if read_windows is None:
        print("حزمة winrt غير مثبّتة في هذه البيئة. ثبّتها بالأمر المذكور في أول الملف (لا تُضاف إلى requirements.txt).")
        sys.exit(1)

    names = sorted(name[:-4] for name in os.listdir(args.samples) if name.lower().endswith(".png"))
    if not names:
        sys.exit(f"لا صور في {args.samples}")

    from PIL import Image

    print(f"{'sample':14s} {'engine':10s} {'lang':6s} {'CER':>6s} {'ms':>8s}")
    totals = {"Tesseract": [], "Windows": []}
    for name in names:
        with open(os.path.join(args.samples, name + ".txt"), encoding="utf-8") as f:
            truth = f.read()
        with Image.open(os.path.join(args.samples, name + ".png")) as image:
            picture = image.convert("RGB")

        start = time.perf_counter()
        text, _ = ocr_tool.perform_ocr(picture, "ara+eng")
        ms_tess = (time.perf_counter() - start) * 1000
        score_tess = cer(truth, text)
        totals["Tesseract"].append(score_tess)
        print(f"{name:14s} {'Tesseract':10s} {'-':6s} {score_tess:6.3f} {ms_tess:8.1f}")

        tag = "ar-SA" if arabic_share(truth) else "en-US"
        text, ms_win = read_windows(picture, tag)
        score_win = cer(truth, text)
        totals["Windows"].append(score_win)
        print(f"{name:14s} {'Windows':10s} {tag:6s} {score_win:6.3f} {ms_win:8.1f}")

    print("-" * 50)
    for engine, scores in totals.items():
        print(f"{engine:10s} متوسط CER {sum(scores) / len(scores):.3f} على {len(scores)} صورة")


if __name__ == "__main__":
    main()
