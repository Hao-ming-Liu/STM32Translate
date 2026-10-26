from pathlib import Path
import os
import sys
import tempfile

CACHE_NAMESPACE = 'argos-en_zh-1.9:433e7c4f:protection-v4'


def app_root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]


def data_directory() -> Path:
    local = app_root() / 'data'
    try:
        local.mkdir(exist_ok=True)
        with tempfile.TemporaryFile(dir=local):
            pass
        return local
    except OSError:
        fallback = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'STM32Translate'
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def make_icon():
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((1, 1, 63, 63), radius=14, fill='#2563eb')
    try:
        font = ImageFont.truetype(str(Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts/msyh.ttc'), 43)
        draw.text((32, 28), '译', anchor='mm', fill='white', font=font)
    except OSError:
        draw.text((19, 17), 'T', fill='white', font=ImageFont.load_default(size=30))
    return image
