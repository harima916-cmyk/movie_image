"""
MP4 → GIF 変換スクリプト（日本語・スペース・長いパス対応／進捗バー付き）
- Windows/macOS/Linux 共通。特に Windows の日本語/スペースを含むパスでも安全に動作。
- FFmpeg は `imageio-ffmpeg` 同梱の実行ファイルを優先的に使用（PATH設定不要）。
- `subprocess.run([...])` を **リスト引数 + shell=False** で実行 → クォート問題を根本回避。
- CONFIG の「ここだけ編集」を変えるだけで使えます。

必要:
  pip install imageio-ffmpeg tqdm
  moviepy は ENGINE="moviepy" を使う場合のみ必要
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple
import json
import os
import subprocess
import sys
import re
from tqdm import tqdm

# 可能なら imageio-ffmpeg から ffmpeg の絶対パスを取得
try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_EXE = "ffmpeg"  # 最悪 PATH にある ffmpeg を使用

# ffprobe は ffmpeg と同じディレクトリにある
_ffmpeg_dir = os.path.dirname(FFMPEG_EXE)
_ffprobe_name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
_ffprobe_candidate = os.path.join(_ffmpeg_dir, _ffprobe_name)
FFPROBE_EXE = _ffprobe_candidate if os.path.exists(_ffprobe_candidate) else "ffprobe"

try:
    from moviepy.editor import VideoFileClip
except Exception:
    VideoFileClip = None

# ====================== ユーザー設定（ここだけ編集）======================
CONFIG = {
    # 1) 入力MP4（日本語・スペースOK。絶対/相対いずれも可）
    "INPUT_VIDEO": r"F:\movie\output\画面録画 2026-04-16 222720 - Trim.mp4",
    # 2) 出力フォルダ（空文字 "" なら入力と同じ場所）
    "OUTPUT_DIR": r"",

    # 3) GIF のフレームレート
    "FPS": 15,

    # 4) リサイズ指定（固定サイズ 優先 / ％指定 / 省略で原寸）
    "SCALE_PERCENT":20,   # 1〜100。
    "FIXED_SIZE": (),      # 例: (640, 360)／未使用なら空のまま

    # 5) 切り出し（秒） 未使用は None
    "START_SEC": None,
    "END_SEC": None,

    # 6) エンジン："ffmpeg"（推奨・高品質） or "moviepy"（簡単）
    "ENGINE": "ffmpeg",

    # 7) ループ設定：True=無限、False=1回
    "LOOP": True,

    # 8) 進捗バー表示（True で tqdm を表示）
    "SHOW_PROGRESS": True,
}
# ====================== ここまで設定 ================================


# ---------------- 内部関数（編集不要） ----------------

def _even_size(w: int, h: int) -> Tuple[int, int]:
    return (max(2, w) // 2 * 2, max(2, h) // 2 * 2)


def _calc_newsize(orig: Tuple[int, int], scale_pct: Optional[int], fixed: Optional[Tuple[int, int]]) -> Tuple[int, int]:
    if fixed and len(fixed) == 2:
        w, h = int(fixed[0]), int(fixed[1])
    elif scale_pct is not None:
        w, h = orig
        w = int(w * int(scale_pct) / 100)
        h = int(h * int(scale_pct) / 100)
    else:
        w, h = orig
    return _even_size(w, h)


def _validate_config(cfg: dict):
    if cfg["FPS"] <= 0:
        raise ValueError("FPS は 1 以上にしてください")
    sp = cfg.get("SCALE_PERCENT")
    if sp not in (None, "") and not (1 <= int(sp) <= 100):
        raise ValueError("SCALE_PERCENT は 1〜100 の整数で指定してください")
    fs = cfg.get("FIXED_SIZE")
    if fs and (int(fs[0]) <= 0 or int(fs[1]) <= 0):
        raise ValueError("FIXED_SIZE の幅・高さは正の整数で指定してください")
    if cfg["ENGINE"] not in ("ffmpeg", "moviepy"):
        raise ValueError('ENGINE は "ffmpeg" または "moviepy" を指定してください')


def _probe_video(mp4: Path) -> Tuple[float, int, int]:
    """ffprobe で動画の duration・幅・高さを取得（MoviePy 不要）。"""
    try:
        result = subprocess.run(
            [FFPROBE_EXE, "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", str(mp4)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        data = json.loads(result.stdout)
        w = h = 0
        dur = 0.0
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                w, h = int(s.get("width", 0)), int(s.get("height", 0))
                dur = float(s.get("duration") or 0)
                break
        if dur <= 0:
            dur = float(data.get("format", {}).get("duration") or 0)
        if w > 0 and h > 0 and dur > 0:
            return dur, w, h
    except Exception:
        pass
    raise RuntimeError("動画情報の取得に失敗しました。ffprobe が利用できるか確認してください。")


def _probe_and_plan(mp4: Path, start: Optional[float], end: Optional[float], scale_pct, fixed):
    dur, in_w, in_h = _probe_video(mp4)
    if start is None:
        start = 0.0
    if end is None or end > dur:
        end = dur
    if end <= start:
        raise ValueError("切り出し区間が不正です（END_SEC は START_SEC より大きく）")
    new_size = _calc_newsize((in_w, in_h), scale_pct, fixed)
    return dur, (in_w, in_h), new_size, float(start), float(end)


def _build_outpath(src: Path, outdir: Optional[Path], size: Tuple[int, int], fps: int) -> Path:
    stem = f"{src.stem}_{size[0]}x{size[1]}_{fps}fps"
    if outdir and str(outdir) != "":
        outdir.mkdir(parents=True, exist_ok=True)
        return outdir / f"{stem}.gif"
    return src.with_name(f"{stem}.gif")


def _run_with_progress(cmd, total_sec: float, desc: str):
    """
    FFmpeg の -progress pipe:2 出力（out_time_ms=...）を読み取り tqdm に反映。
    - out_time_ms はマイクロ秒（μs）単位
    - 端末の改行／エンコーディングの差異に強い（text=True, errors="replace"）
    """
    if not CONFIG.get("SHOW_PROGRESS", True) or total_sec <= 0:
        subprocess.run(cmd, check=True)
        return

    # out_time_ms=123456789 の形式をパース
    out_time_re = re.compile(r"out_time_ms=(\d+)")
    with subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,   # -progress pipe:2 は stderr に出る
        stdout=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    ) as proc:
        with tqdm(total=total_sec, desc=desc, unit="s", leave=False) as bar:
            last_sec = 0.0
            for line in proc.stderr:  # type: ignore
                m = out_time_re.search(line)
                if m:
                    cur_us = int(m.group(1))
                    cur_sec = cur_us / 1_000_000.0
                    if cur_sec > last_sec:
                        last_sec = cur_sec
                        bar.n = min(cur_sec, total_sec)
                        bar.refresh()
        proc.wait()
        if 'bar' in locals() and bar.n < total_sec:
            bar.n = total_sec
            bar.refresh()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)


def _moviepy_gif(mp4: Path, out_gif: Path, size: Tuple[int, int], fps: int, start: float, end: float):
    if VideoFileClip is None:
        raise RuntimeError("MoviePy が見つかりません。pip install moviepy してください。")
    print(f"▶ MoviePy: {mp4.name} → {out_gif.name} (fps={fps}, size={size[0]}x{size[1]}, {start:.2f}s–{end:.2f}s)")
    with VideoFileClip(str(mp4)) as clip:
        sub = clip.subclip(start, end).resize(newsize=size)
        # MoviePy 側の進捗が表示されます（本スクリプトの tqdm ではありません）
        sub.write_gif(str(out_gif), fps=fps, program="ffmpeg", logger='bar')


def _ffmpeg_gif(mp4: Path, out_gif: Path, size: Tuple[int, int], fps: int, start: float, end: float, loop: bool):
    # 2パス: palettegen → paletteuse（tqdm で進捗表示）
    print(f"▶ FFmpeg: {mp4.name} → {out_gif.name} (fps={fps}, size={size[0]}x{size[1]}, {start:.2f}s–{end:.2f}s)")
    palette = out_gif.with_suffix(".palette.png")
    t = max(0.0, end - start)
    scale_filter = f"scale={size[0]}:{size[1]}:flags=lanczos"
    loop_flag = "0" if loop else "1"  # 0: 無限, 1: 1回

    # pass1 (palettegen)
    cmd1 = [
        FFMPEG_EXE, "-y", "-hide_banner",
        "-v", "quiet", "-progress", "pipe:2",  # ← 進捗出力を有効化（stderr）
        "-ss", str(start), "-t", str(t),
        "-i", str(mp4),
        "-vf", f"fps={fps},{scale_filter},palettegen=max_colors=256:stats_mode=full",
        str(palette)
    ]

    # pass2 (paletteuse)
    vf2 = f"fps={fps},{scale_filter},split[s0][s1];[s0]palettegen=max_colors=256:stats_mode=full[p];[s1][p]paletteuse=new=1"
    cmd2 = [
        FFMPEG_EXE, "-y", "-hide_banner",
        "-v", "quiet", "-progress", "pipe:2",  # ← 進捗出力を有効化（stderr）
        "-ss", str(start), "-t", str(t),
        "-i", str(mp4), "-i", str(palette),
        "-lavfi", vf2,
        "-loop", loop_flag,
        str(out_gif)
    ]

    _run_with_progress(cmd1, t, desc="palettegen")
    _run_with_progress(cmd2, t, desc="paletteuse")

    try:
        palette.unlink(missing_ok=True)
    except Exception:
        pass


def main():
    cfg = CONFIG
    _validate_config(cfg)

    mp4 = Path(cfg["INPUT_VIDEO"]).expanduser().resolve()
    if not mp4.exists():
        raise FileNotFoundError(f"入力ファイルが見つかりません: {mp4}")

    outdir = Path(cfg["OUTPUT_DIR"]).expanduser().resolve() if cfg["OUTPUT_DIR"] else mp4.parent

    dur, in_size, new_size, start, end = _probe_and_plan(
        mp4,
        cfg.get("START_SEC"),
        cfg.get("END_SEC"),
        cfg.get("SCALE_PERCENT"),
        cfg.get("FIXED_SIZE") if cfg.get("FIXED_SIZE") else None,
    )

    out_gif = _build_outpath(mp4, outdir, new_size, cfg["FPS"])

    print("\n===== 変換プラン =====")
    print(f"入力: {mp4}")
    print(f"動画長: {dur:.2f}s, 元サイズ: {in_size[0]}x{in_size[1]}")
    print(f"切り出し: {start:.2f}s – {end:.2f}s")
    print(f"出力先: {out_gif}")
    print(f"出力サイズ: {new_size[0]}x{new_size[1]}, FPS: {cfg['FPS']}")
    print(f"エンジン: {cfg['ENGINE']} (loop={'∞' if cfg['LOOP'] else '1回'})")
    print("====================\n")

    out_gif.parent.mkdir(parents=True, exist_ok=True)

    if cfg["ENGINE"] == "moviepy":
        _moviepy_gif(mp4, out_gif, new_size, cfg["FPS"], start, end)
    else:
        _ffmpeg_gif(mp4, out_gif, new_size, cfg["FPS"], start, end, cfg["LOOP"])

    print(f"✔ 完了: {out_gif}")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        print("[エラー]", e)
        print("→ パスの綴り・アクセス権を確認してください（日本語/スペースは対応済み）。")
    except subprocess.CalledProcessError:
        print("[エラー] FFmpeg の実行に失敗しました。imageio-ffmpeg の導入や ffmpeg の実体を確認してください。")
        print("  対策: pip install imageio-ffmpeg / conda install -c conda-forge imageio-ffmpeg")
    except Exception as e:
        print("[エラー]", e)
        print("→ CONFIG の値（FPS、SCALE_PERCENT、FIXED_SIZE、切り出し時間など）をご確認ください。")
