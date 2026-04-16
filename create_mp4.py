# -*- coding: utf-8 -*-
"""
PNG → MP4 バッチ変換（ffmpeg-python 版・バイナリ固定・診断付き）
 - imageio-ffmpeg の ffmpeg を優先使用（PATH 依存を回避）
 - profile/level を厳密に渡し、preset/tune は存在時のみ付与
 - フォルダ自動探索 ("auto") と明示指定 ("list") の両対応
"""

# ====================== USER CONFIG（ここだけ設定）======================
CONFIG = {
    "INPUT_MODE": "auto",   # "list" / "auto"
    "INPUT_DIRS": [
        # r"D:\\koikatsu\\frame\\2025-09-25T22-57-28",
        # r"D:\\koikatsu\\frame\\2025-09-26T00-12-03",
    ],
    "INPUT_ROOT": r"F:\movie\frame",
    "RECURSIVE": True,
    "MIN_PNGS": 2,

    "OUTPUT_DIR": r"F:\movie",
    "SKIP_IF_EXISTS": True,
    "DRY_RUN": False,

    # ===== エンコード設定 =====
    "FPS": 60,
    "START_NUMBER": "auto",      # 数値 or "auto"
    "CRF": 18,                   # 共有向け 18–21 がおすすめ
    "PRESET": "veryslow",        # ultrafast…veryslow
    "KEYINT_SECONDS": 2,         # 例: 2秒ごとにキーフレーム
    "PROFILE": "high",           # 例: "high"
    "LEVEL": "5.1",              # 例: "5.1"（1080p60以上なら 4.2+）
    "TUNE": "",                  # アニメ/レンダ素材なら "animation" 等

    # 出力ファイル名の付け方："folder" / "folder_timestamp" / "timestamp"
    "OUT_NAME_MODE": "timestamp",
}
# ==================== /USER CONFIG（ここだけ設定）======================

from pathlib import Path
from datetime import datetime
import re
import subprocess
import sys
from typing import List, Optional

# ---- ffmpeg バイナリを確定（最優先で imageio-ffmpeg を使う） ----
import os
FFMPEG_BIN: Optional[str] = None
try:
    import imageio_ffmpeg  # pip install imageio-ffmpeg
    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
    os.environ["FFMPEG_BINARY"] = FFMPEG_BIN  # ffmpeg-python が参照
except Exception:
    FFMPEG_BIN = None  # 後で PATH 上の ffmpeg にフォールバック

import ffmpeg  # pip install ffmpeg-python


def print_ffmpeg_diagnostics() -> None:
    """実際に使われる ffmpeg のパスとバージョンを表示（トラブルシュート用）"""
    path = os.environ.get("FFMPEG_BINARY") or "ffmpeg"
    print(f"🛠 Using FFMPEG_BINARY = {path}")
    try:
        out = subprocess.check_output([path, "-version"], stderr=subprocess.STDOUT)
        first = out.decode(errors="ignore").splitlines()[0]
        print(f"   -> {first}")
    except Exception as e:
        print(f"   -> バージョン取得失敗: {e}")


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def guess_start_number(input_dir: Path) -> int:
    """フォルダ内の *.png の最小番号を推定（0,1,1000 始まりなどに対応）"""
    nums = []
    pat = re.compile(r"(\d+)\.png$", re.IGNORECASE)
    for p in input_dir.glob("*.png"):
        m = pat.search(p.name)
        if m:
            nums.append(int(m.group(1)))
    if not nums:
        raise FileNotFoundError(f"PNG が見つかりませんでした: {input_dir}")
    return min(nums)


def list_png_dirs_auto(root: Path, recursive: bool, min_pngs: int) -> List[Path]:
    """root 以下（再帰可）で png を複数含むフォルダを列挙"""
    candidates = []
    it = root.rglob("*.png") if recursive else root.glob("*.png")
    counts = {}
    for p in it:
        if p.is_file():
            counts.setdefault(p.parent, 0)
            counts[p.parent] += 1
    for folder, n in counts.items():
        if n >= min_pngs:
            candidates.append(folder)
    # 更新時刻順（古→新）
    candidates.sort(key=lambda d: d.stat().st_mtime)
    return candidates


def choose_out_path(output_dir: Path, input_dir: Path, name_mode: str) -> Path:
    ensure_dir(output_dir)
    folder_name = input_dir.name
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    if name_mode == "folder":
        base = folder_name
    elif name_mode == "folder_timestamp":
        base = f"{folder_name}_{ts}"
    elif name_mode == "timestamp":
        base = ts
    else:
        raise ValueError(f"Unknown OUT_NAME_MODE: {name_mode}")
    return output_dir / f"{base}.mp4"


def encode_for_sharing(
    input_dir: Path,
    output_file: Path,
    fps: int,
    start_number: int,
    crf: int,
    preset: str,
    keyint_seconds: int,
    profile: str,
    level: str,
    tune: str,
    dry_run: bool = False,
):
    assert input_dir.is_dir(), f"Input dir not found: {input_dir}"
    ensure_dir(output_file.parent)

    g = max(1, int(round(fps * keyint_seconds)))  # GOP 長（キーフレーム間隔）
    input_pattern = str((input_dir / "%d.png").resolve())

    # ffmpeg-python へ渡す kwargs
    out_kwargs = {
        "vcodec": "libx264",
        "crf": crf,
        "pix_fmt": "yuv420p",
        "movflags": "faststart",
        "g": g,
    }
    # 注意: preset は libx264 の一般オプションとして受け付けられる
    if preset:
        out_kwargs["preset"] = preset
    # profile / level は :v を付けて厳密に
    if profile:
        out_kwargs["profile:v"] = profile
    if level:
        out_kwargs["level:v"] = level
    if tune:
        out_kwargs["tune"] = tune

    print(f"\n📦 共有向け MP4 出力: {output_file}")
    print(f"   - src={input_dir}")
    print(f"   - fps={fps}, start_number={start_number}, crf={crf}, preset={preset or '(none)'}")
    print(f"   - g≈{g}（{keyint_seconds}s） profile={profile or '(none)'} level={level or '(none)'} tune={tune or '(none)'}")

    if dry_run:
        print("(DRY_RUN) 実行せず終了")
        return

    (
        ffmpeg
        .input(input_pattern, framerate=fps, start_number=start_number)
        .output(str(output_file), **out_kwargs)
        .overwrite_output()
        .run()
    )
    print(f"✅ 完了: {output_file}")


def main(cfg: dict):
    print_ffmpeg_diagnostics()

    mode = str(cfg["INPUT_MODE"]).lower()
    output_dir = Path(cfg["OUTPUT_DIR"]) if cfg["OUTPUT_DIR"] else Path(".")
    fps = int(cfg["FPS"])
    start_number_cfg = cfg["START_NUMBER"]
    crf = int(cfg["CRF"])
    preset = str(cfg["PRESET"]) if cfg["PRESET"] is not None else ""
    keyint_seconds = int(cfg["KEYINT_SECONDS"])
    profile = str(cfg["PROFILE"]) if cfg["PROFILE"] is not None else ""
    level = str(cfg["LEVEL"]) if cfg["LEVEL"] is not None else ""
    tune = str(cfg["TUNE"]) if cfg["TUNE"] is not None else ""
    skip_if_exists = bool(cfg["SKIP_IF_EXISTS"])
    dry_run = bool(cfg.get("DRY_RUN", False))
    name_mode = str(cfg.get("OUT_NAME_MODE", "folder"))

    # 入力候補フォルダ
    if mode == "list":
        candidates = [Path(p) for p in cfg["INPUT_DIRS"]]
    elif mode == "auto":
        root = Path(cfg["INPUT_ROOT"])
        recursive = bool(cfg["RECURSIVE"])
        min_pngs = int(cfg["MIN_PNGS"])
        candidates = list_png_dirs_auto(root, recursive, min_pngs)
    else:
        raise ValueError("INPUT_MODE は 'list' か 'auto' を指定してください")

    if not candidates:
        print("⚠ 対象フォルダが見つかりませんでした。設定を見直してください。")
        return

    print(f"🔎 処理対象フォルダ数: {len(candidates)}")

    for idx, in_dir in enumerate(candidates, 1):
        try:
            if not in_dir.is_dir():
                print(f"[{idx}/{len(candidates)}] ❌ スキップ（フォルダなし）: {in_dir}")
                continue

            out_path = choose_out_path(output_dir, in_dir, name_mode)
            if skip_if_exists and out_path.exists():
                print(f"[{idx}/{len(candidates)}] ⏭ 既存スキップ: {out_path}")
                continue

            start_number = (
                guess_start_number(in_dir)
                if (isinstance(start_number_cfg, str) and start_number_cfg.lower() == "auto")
                else int(start_number_cfg)
            )

            print(f"[{idx}/{len(candidates)}] ▶ 変換開始: {in_dir} → {out_path}")
            encode_for_sharing(
                in_dir, out_path, fps, start_number, crf, preset,
                keyint_seconds, profile, level, tune, dry_run=dry_run
            )
        except Exception as e:
            print(f"[{idx}/{len(candidates)}] 🔥 エラー: {in_dir} — {e}")
            continue


if __name__ == "__main__":
    try:
        main(CONFIG)
    except KeyboardInterrupt:
        print("\n⛔ 中断されました。")
        sys.exit(130)
