"""يضيف لخط Tajawal المرفق رمزاً فارغاً بلا عرض لعلامتَي الاتجاه RLE (U+202B) وPDF (U+202C).

السبب: Tk يقسّم النص حسب الخط الذي يحوي كل حرف، والعلامتان ليستا في Tajawal الأصلي، فتُرسمان بخط آخر
في نداء رسم منفصل ويضيع أثرهما على ترتيب الكلمات (انظر rtl() في ocr_tool.py). رخصة OFL تسمح بالتعديل،
والخط لم يحجز اسمه (لا Reserved Font Name).

التشغيل (مرة واحدة، يحتاج fonttools):  py tools/patch_font.py
"""
import os

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph

FONTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")
MARKS = (0x202B, 0x202C)
GLYPH = "bidicontrol"

for name in ("Tajawal-Regular.ttf", "Tajawal-Bold.ttf"):
    path = os.path.join(FONTS, name)
    font = TTFont(path)
    if all(mark in font.getBestCmap() for mark in MARKS):
        print(name, "already patched")
        continue
    font["glyf"][GLYPH] = Glyph()
    font["hmtx"][GLYPH] = (0, 0)
    for table in font["cmap"].tables:
        if table.isUnicode():
            for mark in MARKS:
                table.cmap[mark] = GLYPH
    font.save(path)
    assert all(mark in TTFont(path).getBestCmap() for mark in MARKS)
    print(name, "patched")
