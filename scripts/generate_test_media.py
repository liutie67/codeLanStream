"""生成测试媒体文件（彩色图片）用于开发验证。

用法: uv run python scripts/generate_test_media.py
"""

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


COLORS = [
    (231, 76, 60), (46, 204, 113), (52, 152, 219),
    (155, 89, 182), (241, 196, 15), (230, 126, 34),
    (26, 188, 156), (192, 57, 43), (41, 128, 185),
    (142, 68, 173), (39, 174, 96), (211, 84, 0),
]

SUBDIRS = ["photos", "screenshots", "downloads"]


def generate_image(path: Path, index: int, width: int, height: int):
    color = random.choice(COLORS)
    img = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(img)

    # 绘制装饰图案
    for _ in range(random.randint(3, 8)):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = x1 + random.randint(30, 200), y1 + random.randint(30, 200)
        r, g, b = [max(0, min(255, c + random.randint(-40, 40))) for c in color]
        draw.ellipse([x1, y1, x2, y2], fill=(r, g, b))

    # 绘制文字标签
    label = f"Test #{index}\n{width}x{height}"
    text_color = (255, 255, 255) if sum(color) < 450 else (0, 0, 0)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except OSError:
        font = ImageFont.load_default()
        small_font = font

    draw.text((20, 20), f"Test #{index}", fill=text_color, font=font)
    draw.text((20, 60), f"{width}x{height}", fill=text_color, font=small_font)

    ext = random.choice([".jpg", ".png"])
    img.save(path.with_suffix(ext), quality=85)


def main():
    base = Path("./test_media")
    total = 0

    for subdir in SUBDIRS:
        dir_path = base / subdir
        dir_path.mkdir(parents=True, exist_ok=True)
        count = random.randint(12, 18)
        for i in range(count):
            total += 1
            width = random.choice([400, 500, 600, 800, 1000, 1200])
            height = random.choice([300, 400, 500, 600, 700, 800])
            filename = f"{subdir}_{i:03d}"
            generate_image(dir_path / filename, total, width, height)
        print(f"  {subdir}/ -> {count} 张图片")

    print(f"\n共生成 {total} 张测试图片到 {base}/")


if __name__ == "__main__":
    main()
