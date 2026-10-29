"""ينسخ Tesseract المثبّت محليًا إلى vendor/tesseract ليبني منه ocr_tool.spec.

vendor/ غير مرفوع إلى git (حجمه ~72MB)، فهذا السكربت يعيد إنتاجه على أي جهاز فيه Tesseract:
    py -3.14 tools/prepare_tesseract.py
    py -3.14 tools/prepare_tesseract.py --from "D:\\Tesseract"
"""
import argparse
import os
import shutil
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "vendor", "tesseract")
SYSTEM = r"C:\Program Files\Tesseract-OCR"
LANGS = ("ara", "eng", "osd")


def imports_of(path):
    """أسماء DLLs في جدول استيراد ملف PE."""
    with open(path, "rb") as f:
        data = f.read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        return set()
    sections_count = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    dirs = opt + (112 if magic == 0x20B else 96)  # DataDirectory بعد OptionalHeader
    import_rva = struct.unpack_from("<I", data, dirs + 8)[0]
    if not import_rva:
        return set()
    sections, offset = [], opt + opt_size
    for i in range(sections_count):
        vsize, vaddr, rsize, roff = struct.unpack_from("<IIII", data, offset + i * 40 + 8)
        sections.append((vaddr, max(vsize, rsize), roff))

    def file_offset(rva):
        for vaddr, size, roff in sections:
            if vaddr <= rva < vaddr + size:
                return roff + (rva - vaddr)
        return None

    names, offset = set(), file_offset(import_rva)
    while offset is not None:
        entry = data[offset:offset + 20]
        if len(entry) < 20 or entry == b"\0" * 20:
            break
        name_rva = struct.unpack_from("<I", entry, 12)[0]
        name_offset = file_offset(name_rva) if name_rva else None
        if name_offset:
            end = data.index(b"\0", name_offset)
            names.add(data[name_offset:end].decode("ascii", "ignore").lower())
        offset += 20
    return names


def required_dlls(source):
    """كل DLL يحتاجه tesseract.exe فعليًا، متتابعًا عبر التبعيات."""
    available = {name.lower(): name for name in os.listdir(source) if name.lower().endswith(".dll")}
    needed, queue = set(), ["tesseract.exe"]
    while queue:
        current = queue.pop()
        path = os.path.join(source, current)
        for name in imports_of(path):
            if name in available and name not in needed:
                needed.add(name)
                queue.append(available[name])
    return sorted(available[name] for name in needed)  # بالاسم كما هو على القرص لا بحروف صغيرة


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source", default="", help=f"مجلد تثبيت Tesseract (افتراضي: {SYSTEM})")
    args = parser.parse_args()
    source = args.source or (SYSTEM if os.path.exists(SYSTEM) else "")
    if not source:
        found = shutil.which("tesseract")
        source = os.path.dirname(found) if found else ""
    if not source or not os.path.exists(os.path.join(source, "tesseract.exe")):
        sys.exit(f"لم أجد Tesseract في: {source or 'PATH'}\nثبّته أو مرّر مساره بـ --from")

    missing_langs = [lang for lang in LANGS if not os.path.exists(os.path.join(source, "tessdata", lang + ".traineddata"))]
    if missing_langs:
        sys.exit(f"حزم اللغات الناقصة في {source}: {', '.join(missing_langs)}")

    os.makedirs(os.path.join(DEST, "tessdata"), exist_ok=True)
    shutil.copy2(os.path.join(source, "tesseract.exe"), DEST)
    dlls = required_dlls(source)
    for name in dlls:
        shutil.copy2(os.path.join(source, name), DEST)
    for lang in LANGS:
        shutil.copy2(os.path.join(source, "tessdata", lang + ".traineddata"), os.path.join(DEST, "tessdata"))

    total = sum(os.path.getsize(os.path.join(DEST, name)) for name in os.listdir(DEST)
                if os.path.isfile(os.path.join(DEST, name)))
    total += sum(os.path.getsize(os.path.join(DEST, "tessdata", name)) for name in os.listdir(os.path.join(DEST, "tessdata")))
    print(f"تم: {DEST}\n{len(dlls)} DLL + tesseract.exe + {len(LANGS)} حزم لغات، الحجم {total / 1048576:.1f} MB")


if __name__ == "__main__":
    main()
