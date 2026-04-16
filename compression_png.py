#!/usr/bin/env python3
"""
png_bulk_shrinker_simple.py
──────────────────────────
VS Code で F5 実行するだけで OK な PNG 圧縮スクリプト。

1. INPUT_DIR  : 元 PNG があるフォルダ
2. OUTPUT_DIR : 圧縮後 PNG を保存するフォルダ
3. MAX_SIDE   : 長辺の最大ピクセル数 (0 ならリサイズしない)
4. COLORS     : パレット色数 (1–256)。256 なら色数変更しない
5. COMPRESS_LEVEL : PNG 圧縮レベル 0–9（9 が最強圧縮）
6. WORKERS    : 並列スレッド数
"""

from __future__ import annotations
import pathlib
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple, List
from PIL import Image
from tqdm import tqdm   # pip install pillow tqdm

# ───── ここを書き換える ─────────────────────────────────────────
INPUT_DIR       = pathlib.Path(r"F:\cap\転生したら第七王子だったので、気ままに魔術を極めます\20251229")
OUTPUT_DIR      = pathlib.Path(r"F:\cap\転生したら第七王子だったので、気ままに魔術を極めます\圧縮")
MAX_SIDE        = 0      # 例: 1600 なら長辺 1600 px まで縮小、0 でリサイズ無し
COLORS          = 256    # 例: 128 なら 128 色パレット化、256 で変更無し
COMPRESS_LEVEL  = 9      # 0 (速い) – 9 (最小ファイル)
WORKERS         = 4      # 並列スレッド数
# ────────────────────────────────────────────────────────────


def shrink_png(
    src: pathlib.Path,
    dst: pathlib.Path,
    max_side: int,
    colors: int,
    compress_level: int,
) -> None:
    """1 枚の PNG をリサイズ & パレット化 & 再圧縮して保存"""
    img = Image.open(src)

    # ① リサイズ（長辺を max_side 以内に）
    if max_side > 0:
        w, h = img.size
        scale = min(max_side / w, max_side / h, 1.0)
        if scale < 1.0:
            new_size = (int(w * scale), int(h * scale))
            img = img.resize(new_size, Image.LANCZOS)

    # ② パレット化（色数削減）
    if 1 <= colors < 256:
        img = img.convert("P", palette=Image.ADAPTIVE, colors=colors)

    # ③ 保存（圧縮オプション）
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(
        dst,
        format="PNG",
        optimize=True,          # ハフマン最適化
        compress_level=compress_level,
    )


def main() -> None:
    if not INPUT_DIR.is_dir():
        raise FileNotFoundError(f"INPUT_DIR が見つかりません: {INPUT_DIR}")

    png_files: List[pathlib.Path] = list(INPUT_DIR.rglob("*.png"))
    if not png_files:
        print(f"⚠️ PNG が見つかりませんでした: {INPUT_DIR}")
        return

    def _task(src: pathlib.Path):
        rel = src.relative_to(INPUT_DIR)      # 入力フォルダからの相対パス
        dst = OUTPUT_DIR / rel                # 階層を維持して保存
        shrink_png(src, dst, MAX_SIDE, COLORS, COMPRESS_LEVEL)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(tqdm(ex.map(_task, png_files), total=len(png_files)))

    print(f"✔ 圧縮完了: {len(png_files)} 枚 → {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
