"""يولّد شعار README وعناوينه (docs/banner.svg وdocs/headings/*.svg).

التشغيل:  py -3.14 tools/make_readme_assets.py   (الإصدار يُقرأ من APP_VERSION في ocr_tool.py)
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
INK, PAPER, RED, VIOLET = "#0F0F0F", "#F5F5F2", "#E5352B", "#6B4FBB"
FONT = "'Segoe UI', Tahoma, Arial, sans-serif"
VERSION = re.search(r'APP_VERSION = "([\d.]+)"', open(os.path.join(ROOT, "ocr_tool.py"), encoding="utf-8").read()).group(1)

# أيقونات 24x24 بخط 1.8 (نفس لغة أيقونات الواجهة)
ICONS = {
    "about": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.1"/>',
    "features": '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    "how": '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>',
    "usage": '<path d="M7 4v16l5-4 3 5 3-1.5-3-5 6-.5z"/>',
    "requirements": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="m8.5 10 1.5 1.5L13 8.500M8.500 16h7"/>',
    "running": '<path d="M12 3v12M7 11l5 5 5-5M5 20h14"/>',
    "layout": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "trouble": '<path d="M14.500 6.500a4 4 0 0 0-5 5L4 17l3 3 5.500-5.500a4 4 0 0 0 5-5l-2.500 2.500-2-.5-.5-2z"/>',
    "limits": '<path d="M12 4 2.800 19.500h18.400zM12 10v4.500M12 17.200v.1"/>',
    "credits": '<path d="M12 20s-7-4.400-7-10a4 4 0 0 1 7-2.500A4 4 0 0 1 19 10c0 5.600-7 10-7 10z"/>',
    "license": '<path d="M12 3v18M5 7h14M7 7l-3 7a3 3 0 0 0 6 0zM17 7l-3 7a3 3 0 0 0 6 0z"/>',
    "new": '<path d="M13 3 5 13h6l-1 8 8-10h-6z"/>',
    "shots": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 9h18"/>',
    "prebuilt": '<path d="M12 3v12M7 11l5 5 5-5M5 20h14"/>',
    "source": '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M13.500 5l-3 14"/>',
    "build": '<path d="M12 3 4 7v10l8 4 8-4V7zM4 7l8 4 8-4M12 11v10"/>',
}
H2 = {  # المفتاح: (عنوان إنجليزي، عنوان عربي)
    "about": ("About", "نبذة عن البرنامج"), "features": ("Features", "المميزات"), "how": ("How it works", "كيف يعمل"),
    "usage": ("Usage", "طريقة الاستخدام"), "requirements": ("Requirements", "المتطلبات"), "running": ("Running", "التشغيل"),
    "layout": ("Project layout", "بنية المشروع"), "trouble": ("Troubleshooting", "استكشاف الأخطاء"),
    "limits": ("Known limitations", "حدود معروفة"), "credits": ("Credits", "الشكر والمصادر"), "license": ("License", "الترخيص"),
    "new": ("What's new", "ما الجديد"), "shots": ("Screenshots", "لقطات الواجهة"),
}
H3 = {
    "prebuilt": ("Option 1: the prebuilt app", "الخيار الأول: البرنامج الجاهز"),
    "source": ("Option 2: from source", "الخيار الثاني: من الكود المصدري"),
    "build": ("Build the EXE yourself", "بناء ملف EXE بنفسك"),
}


def icon(key, x, y, size, stroke):
    s = size / 24
    return (f'<g transform="translate({x} {y}) scale({s})" fill="none" stroke="{stroke}" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONS[key]}</g>')


def h2(key, title, ar):
    # شريط داكن يُقرأ على الخلفيتين الفاتحة والداكنة؛ الأيقونة في مربع أحمر من جهة بداية القراءة
    box_x, text_x, anchor = (856, 840, "end") if ar else (8, 60, "start")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 52" role="img" aria-label="{title}">'
            f'<rect x="0.5" y="0.5" width="899" height="51" rx="10" fill="{INK}" stroke="#3D3D3D"/>'
            f'<rect x="{box_x}" y="8" width="36" height="36" rx="8" fill="{RED}"/>{icon(key, box_x + 6, 14, 24, "#fff")}'
            f'<text x="{text_x}" y="34" font-family="{FONT}" font-size="24" font-weight="700" fill="#fff" text-anchor="{anchor}">{title}</text></svg>')


def h3(key, title, ar):
    icon_x, text_x, anchor = (868, 852, "end") if ar else (4, 40, "start")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 42" role="img" aria-label="{title}">'
            f'{icon(key, icon_x, 6, 26, RED)}'
            f'<text x="{text_x}" y="27" font-family="{FONT}" font-size="20" font-weight="700" fill="{RED}" text-anchor="{anchor}">{title}</text>'
            f'<rect x="0" y="38" width="900" height="2" rx="1" fill="{RED}" fill-opacity="0.35"/></svg>')


def banner():
    chips = [("Arabic + English", 410, 150), ("Ctrl+Shift+X", 574, 130), ("Windows", 718, 100)]
    chip_svg = "".join(
        f'<rect x="{x}" y="296" width="{w}" height="38" rx="19" fill="none" stroke="#fff" stroke-opacity="0.35"/>'
        f'<text x="{x + w / 2}" y="321" font-size="18" fill="#fff" fill-opacity="0.85" text-anchor="middle">{t}</text>' for t, x, w in chips)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 360" width="1280" height="360" role="img" aria-label="OCR Tool {VERSION}">
  <rect x="0.5" y="0.5" width="1279" height="359" rx="28" fill="{INK}" stroke="#3D3D3D"/>
  <g transform="translate(90 40) scale(0.27)">
    <rect width="1024" height="1024" rx="230" fill="#1A1A1A"/>
    <g fill="none" stroke="{PAPER}" stroke-width="64" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="250,400 250,250 400,250"/><polyline points="624,250 774,250 774,400"/>
      <polyline points="774,624 774,774 624,774"/><polyline points="400,774 250,774 250,624"/>
    </g>
    <rect x="330" y="358" width="364" height="112" rx="26" fill="{RED}"/>
    <g stroke-linecap="round" stroke-width="44">
      <line x1="400" y1="414" x2="634" y2="414" stroke="#fff"/>
      <line x1="456" y1="552" x2="634" y2="552" stroke="{PAPER}"/>
      <line x1="520" y1="640" x2="634" y2="640" stroke="{PAPER}"/>
    </g>
  </g>
  <g font-family="Tajawal, {FONT}" fill="#fff">
    <text x="410" y="135" font-size="64" font-weight="700">أداة قراءة النصوص من الشاشة</text>
    <text x="410" y="200" font-size="40" font-weight="700">OCR Tool · Screen Text Extractor</text>
    <text x="410" y="252" font-size="24" fill="{PAPER}" fill-opacity="0.7">Select, read, copy and translate text from anywhere on screen</text>
  </g>
  <g font-family="{FONT}">
    {chip_svg}
    <rect x="1110" y="296" width="120" height="38" rx="19" fill="{RED}"/>
    <text x="1170" y="322" font-size="20" font-weight="700" fill="#fff" text-anchor="middle">v{VERSION}</text>
    <rect x="1090" y="40" width="140" height="6" rx="3" fill="{VIOLET}"/>
  </g>
</svg>
'''


def main():
    out = os.path.join(DOCS, "headings")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(DOCS, "banner.svg"), "w", encoding="utf-8") as f:
        f.write(banner())
    for table, fn in ((H2, h2), (H3, h3)):
        for key, (en, ar) in table.items():
            for lang, title in (("en", en), ("ar", ar)):
                with open(os.path.join(out, f"{'h2' if table is H2 else 'h3'}-{key}-{lang}.svg"), "w", encoding="utf-8") as f:
                    f.write(fn(key, title, lang == "ar"))
    print("done:", len(H2) * 2 + len(H3) * 2, "headings + banner, version", VERSION)


if __name__ == "__main__":
    main()
