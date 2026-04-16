# -*- coding: utf-8 -*-
"""
PNG 連番 → MP4 (H.265 / libx265 専用) バッチ変換スクリプト
- libx265 のみ使用（GPU/HWエンコは使いません）
- 進捗バー（tqdm）表示：ffmpeg の stderr を逐次パースして frame をカウント
- 日本語/スペース含むパス安全（リスト引数 + shell=False）
- "auto" でサブフォルダからPNGを含むフォルダを自動検出 or "list" で明示列挙
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple
import subprocess
import sys
import re
from tqdm import tqdm

# ====================== USER CONFIG（ここだけ設定）======================
CONFIG = {
    # 入力モード："auto"（再帰探索） / "list"（明示列挙）
    "INPUT_MODE": "auto",

    # INPUT_MODE == "list" のときに処理するフォルダ
    "INPUT_DIRS": [
        # r"D:\frames\2025-09-25T22-57-28",
    ],

    # INPUT_MODE == "auto" の探索ルートと条件
    "INPUT_ROOT": r"F:\movie\frame",
    "RECURSIVE": True,     # サブフォルダ再帰探索
    "MIN_PNGS": 2,         # PNGがこの枚数以上で「動画フォルダ」と見なす

    # 出力

    
    "OUTPUT_DIR": r"F:\movie",
    # 出力ファイル名："folder" / "folder_timestamp" / "timestamp"
    "OUT_NAME_MODE": "timestamp",

    # 既存ファイルがあればスキップ
    "SKIP_IF_EXISTS": True,

    # 実行せず予定だけ表示（ffmpegは走らない）
    "DRY_RUN": False,

    # 変換パラメータ（libx265 用）
    "FPS": 60,
    "START_NUMBER": "auto",   # "auto" または 数値（0/1など）
    "KEYINT_SECONDS": 2,      # キーフレーム間隔（秒）→ GOP = FPS * 秒
    "CRF": 20,                # 低いほど高画質・大容量（20〜24目安）
    "PRESET": "veryslow",         # "ultrafast"〜"veryslow"（遅いほど圧縮効率↑）
    "PIX_FMT": "yuv420p",     # 互換性重視（10bitは "yuv420p10le"）
    "X265_TUNE": "",          # 例: "grain"（通常は空でOK）
}
# ==================== /USER CONFIG（ここだけ設定）======================


# ---------- Utility ----------
def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def count_pngs(input_dir: Path) -> int:
    return sum(1 for _ in input_dir.glob("*.png"))


def guess_start_number(input_dir: Path) -> int:
    """*.png の最小番号を推定（0/1/1000始まりなど対応）"""
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
    # 変更時刻でソート（新しい順にしたければ reverse=True）
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


# ---------- FFmpeg Runner with Progress ----------
def run_ffmpeg_with_progress(cmd: List[str], total_frames: int) -> None:
    """
    ffmpeg の stderr を読み取りながら tqdm を更新する。
    - 画像列→動画のとき、stderr に "frame=   123" のような行が定期的に出るので、それをパース。
    - 期待する総フレーム数はフォルダ内の PNG 枚数。
    """
    # バッファリングしないで逐次読む
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
    )

    # stderr を逐次パース
    frame_pat = re.compile(r"frame=\s*(\d+)")
    pbar = tqdm(total=total_frames, unit="f", desc="encoding", leave=True)

    last_reported = 0
    try:
        assert proc.stderr is not None
        for line in proc.stderr:
            # tqdm.write(line.rstrip())  # デバッグ用に行を出したいとき
            m = frame_pat.search(line)
            if m:
                f = int(m.group(1))
                # 逆流防止：ffmpegの再配置ログ等で小さくなることがある
                if f > last_reported:
                    pbar.update(f - last_reported)
                    last_reported = f
        proc.wait()
    finally:
        # 念のため埋め切る
        if last_reported < total_frames:
            pbar.update(total_frames - last_reported)
        pbar.close()

    if proc.returncode != 0:
        # 失敗時はエラーメッセージをまとめて出す
        err = ""
        if proc.stderr:
            try:
                proc.stderr.seek(0)  # StringIO ではないので多くは無効
            except Exception:
                pass
        # プロセス終了後に stderr をもう一度読めないことがあるので、簡易メッセージ
        raise RuntimeError("ffmpeg でエラーが発生しました（詳細は上部ログを参照）")


# ---------- Command Builder (libx265 only) ----------
def build_ffmpeg_cmd_libx265(
    input_pattern: str,
    output_path: str,
    fps: int,
    start_number: int,
    gop: int,
    cfg: dict,
) -> List[str]:
    crf = str(int(cfg["CRF"]))
    preset = str(cfg["PRESET"])
    pix = str(cfg["PIX_FMT"])
    tune = str(cfg["X265_TUNE"]).strip()

    x265_params = f"keyint={gop}:min-keyint={gop}:scenecut=40"
    if tune:
        x265_params += f":tune={tune}"

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-framerate", str(fps),
        "-start_number", str(start_number),
        "-i", input_pattern,               # （リスト引数なのでクォート不要）
        "-c:v", "libx265",
        "-preset", preset,
        "-crf", crf,
        "-pix_fmt", pix,
        "-x265-params", x265_params,
        "-movflags", "faststart",
        output_path,
    ]
    return cmd


# ---------- Main per-folder encode ----------
def encode_folder_with_libx265(input_dir: Path, output_file: Path, cfg: dict) -> None:
    assert input_dir.is_dir(), f"Input dir not found: {input_dir}"
    ensure_dir(output_file.parent)

    fps = int(cfg["FPS"])
    gop = max(1, int(fps * int(cfg["KEYINT_SECONDS"])))

    # PNG 総枚数
    total_frames = count_pngs(input_dir)
    if total_frames == 0:
        raise FileNotFoundError(f"PNG が見つかりませんでした: {input_dir}")

    # start_number 決定
    start_cfg = cfg["START_NUMBER"]
    if isinstance(start_cfg, str) and start_cfg.lower() == "auto":
        start_number = guess_start_number(input_dir)
    else:
        start_number = int(start_cfg)

    input_pattern = str((input_dir / "%d.png").resolve())

    print(f"\n📦 出力: {output_file}")
    print(f"   src = {input_dir}")
    print(f"   fps = {fps}, start_number = {start_number}, GOP ≈ {gop}")
    print(f"   frames = {total_frames}, encoder = libx265, crf = {cfg['CRF']}, preset = {cfg['PRESET']}")

    cmd = build_ffmpeg_cmd_libx265(
        input_pattern=input_pattern,
        output_path=str(output_file),
        fps=fps,
        start_number=start_number,
        gop=gop,
        cfg=cfg,
    )

    run_ffmpeg_with_progress(cmd, total_frames)
    print("✅ 完了（libx265）")


def main(cfg: dict):
    mode = cfg["INPUT_MODE"].lower()
    output_dir = Path(cfg["OUTPUT_DIR"]) if cfg["OUTPUT_DIR"] else Path(".")
    name_mode = str(cfg.get("OUT_NAME_MODE", "folder"))
    ensure_dir(output_dir)

    # 入力フォルダ集め
    if mode == "list":
        candidates = [Path(p) for p in cfg["INPUT_DIRS"]]
    elif mode == "auto":
        root = Path(cfg["INPUT_ROOT"])
        candidates = list_png_dirs_auto(root, bool(cfg["RECURSIVE"]), int(cfg["MIN_PNGS"]))
    else:
        raise ValueError("INPUT_MODE は 'auto' か 'list' を指定してください。")

    if not candidates:
        print("⚠ 対象フォルダが見つかりませんでした。設定を見直してください。")
        return

    print(f"🔎 処理対象フォルダ数: {len(candidates)}")

    for i, in_dir in enumerate(candidates, 1):
        try:
            if not in_dir.is_dir():
                print(f"[{i}/{len(candidates)}] ❌ スキップ（フォルダなし）: {in_dir}")
                continue

            out_path = choose_out_path(output_dir, in_dir, name_mode)
            if cfg["SKIP_IF_EXISTS"] and out_path.exists():
                print(f"[{i}/{len(candidates)}] ⏭ スキップ（既存）: {out_path}")
                continue

            print(f"[{i}/{len(candidates)}] ▶ 変換: {in_dir} → {out_path}")
            if cfg["DRY_RUN"]:
                print("   （DRY_RUN）実行せず予定のみ表示")
                continue

            encode_folder_with_libx265(in_dir, out_path, cfg)

        except Exception as e:
            print(f"[{i}/{len(candidates)}] 🔥 エラー: {in_dir} — {e}")
            continue


if __name__ == "__main__":
    main(CONFIG)
