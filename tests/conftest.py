import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def app():
    """يستورد البرنامج (ينشئ نافذته) ثم يخفيها ويغلقها بعد الاختبارات."""
    import ocr_tool
    ocr_tool.root.withdraw()
    yield ocr_tool
    ocr_tool.root.destroy()
