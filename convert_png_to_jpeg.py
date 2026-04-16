#!/usr/bin/env python3
"""
png_to_jpeg_bulk_simple.py
VS Code でそのまま実行（F5）できる簡易版。

1. 変換元 PNG があるフォルダを INPUT_DIR にセット
2. 変換後 JPEG を置きたいフォルダを OUTPUT_DIR にセット
3. F5 (Run) で実行
"""

import pathlib
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple
from PIL import Image
from tqdm import tqdm  # pip install pillow tqdm

# ───── ここを書き換えて自分の環境に合わせる ─────
INPUT_DIR  = pathlib.Path(r"E:\images\BangDream\奥沢美咲\20260402")
OUTPUT_DIR = pathlib.Path(r"E:\images\BangDream\奥沢美咲\output")
QUALITY    = 95   # JPEG 品質 (1–95)
WORKERS    = 4    # 並列スレッド数
# ───────────────────────────────────────

def png_to_jpeg(
    src: pathlib.Path,
    dst: pathlib.Path,
    quality: int = 90,
    bg_color: Tuple[int, int, int] = (255, 255, 255),
) -> None:
    """PNG → JPEG 変換（透過は単色背景に合成）"""
    img = Image.open(src).convert("RGBA")

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        bg = Image.new("RGB", img.size, bg_color)
        bg.paste(img, mask=img.split()[-1])  # α合成
        img = bg
    else:
        img = img.convert("RGB")

    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)

def main() -> None:
    if not INPUT_DIR.is_dir():
        raise FileNotFoundError(f"INPUT_DIR が見つかりません: {INPUT_DIR}")

    png_files = list(INPUT_DIR.rglob("*.png"))
    if not png_files:
        print(f"⚠️  PNG が見つかりませんでした: {INPUT_DIR}")
        return

    def _task(src: pathlib.Path):
        rel = src.relative_to(INPUT_DIR).with_suffix(".jpg")
        dst = OUTPUT_DIR / rel
        png_to_jpeg(src, dst, quality=QUALITY)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(tqdm(ex.map(_task, png_files), total=len(png_files)))

    print(f"✔ 変換完了: {len(png_files)} 枚 → {OUTPUT_DIR}")

if __name__ == "__main__":
    main()