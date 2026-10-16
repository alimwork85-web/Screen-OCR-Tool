"""اختبارات الدوال الخالصة في مسار القراءة: تصحيح الأقواس، تنظيف النص، تهيئة الصورة، والقراءة الكاملة."""
import os

import pytest
from PIL import Image, ImageDraw, ImageFont, ImageStat

from conftest import ROOT


# ---- fix_brackets ----
@pytest.mark.parametrize("line, expected", [
    (")476 ميغابايت)", "(476 ميغابايت)"),   # قوس فتح مقلوب
    ("(خصم 15(", "(خصم 15)"),                # قوس إغلاق مقلوب
    ("(سليم) [سليم]", "(سليم) [سليم]"),      # متوازن: لا يتغير
    ("بلا أقواس 123", "بلا أقواس 123"),
    ("]قائمة]", "[قائمة]"),
])
def test_fix_brackets(app, line, expected):
    assert app.fix_brackets(line) == expected


# ---- clean_text ----
def test_clean_text_removes_bidi_marks(app):
    assert app.clean_text("\u200fنسخة\u200e GitHub\u202b") == "نسخة GitHub"


def test_clean_text_collapses_spaces_and_trims_lines(app):
    assert app.clean_text("  سطر   أول \t\n\n   second  line  \n") == "سطر أول\n\nsecond line"


def test_clean_text_empty(app):
    assert app.clean_text(" \n \u200e ") == ""


# ---- normalize_for_ocr ----
def text_image(size, fg, bg, lines=("Sample text line 123",) * 3, width=900):
    font = ImageFont.truetype(os.path.join(ROOT, "assets/fonts/Tajawal-Regular.ttf"), size)
    img = Image.new("RGB", (width, int(size * 2.2 * len(lines)) + 40), bg)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((20, 20 + i * int(size * 2.2)), line, fill=fg, font=font)
    return img


def test_normalize_is_grayscale_with_white_padding(app):
    out = app.normalize_for_ocr(text_image(24, "black", "white"))
    assert out.mode == "L"
    assert out.getpixel((0, 0)) == 255 and out.getpixel((out.width - 1, out.height - 1)) == 255


def test_normalize_inverts_dark_theme(app):
    out = app.normalize_for_ocr(text_image(24, "white", "#1A242B"))
    assert ImageStat.Stat(out).mean[0] > 128  # صار نصاً داكناً على خلفية فاتحة


def test_normalize_shrinks_large_text(app):
    img = text_image(90, "black", "white", width=2400)
    out = app.normalize_for_ocr(img)
    assert out.height < img.height  # النص الكبير يُصغَّر نحو TARGET_TEXT_HEIGHT


def test_normalize_enlarges_small_text(app):
    img = text_image(9, "black", "white", width=400)
    out = app.normalize_for_ocr(img)
    assert out.height > img.height + 40  # أكبر من مجرد إضافة الحواف


# ---- القراءة الكاملة (تحتاج Tesseract) ----
needs_tesseract = pytest.mark.skipif(
    not __import__("shutil").which("tesseract") and not os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    reason="Tesseract غير مثبّت")


@needs_tesseract
def test_perform_ocr_reads_english_and_numbers(app):
    lines = ("Download the latest release (version 2.0.3)", "Press Ctrl+Shift+X then drag the mouse.")
    text, ok = app.perform_ocr(text_image(22, "black", "white", lines), "ara+eng")
    assert ok
    assert text.split("\n") == list(lines)


@needs_tesseract
def test_perform_ocr_dark_background(app):
    lines = ("Dark theme text 4567",)
    text, ok = app.perform_ocr(text_image(22, "#E6EDF1", "#1A242B", lines), "eng")
    assert ok and text == lines[0]


@needs_tesseract
def test_perform_ocr_blank_image(app):
    text, ok = app.perform_ocr(Image.new("RGB", (300, 100), "white"), "eng")
    assert not ok and text == app.NO_TEXT_MSG
