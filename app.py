#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Movie Image Tools - GUI ランチャー

使い方:
  python app.py   または   launch.bat をダブルクリック

依存:
  pip install -r requirements.txt
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

BASE_DIR = Path(__file__).parent
PROGRAMS_DIR = BASE_DIR / "programs"
SETTINGS_FILE = BASE_DIR / "settings.json"

# ──── 設定の保存・読み込み ────────────────────────────────────────────────────

def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_settings(data: dict) -> None:
    try:
        SETTINGS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

# ──── 共通定数 ────────────────────────────────────────────────────────────────

_ALL_ENCODERS = [
    "H.264 CPU (libx264)",
    "H.265 CPU (libx265)",
    "H.264 NVENC (NVIDIA)",
    "H.265 NVENC (NVIDIA)",
    "H.264 AMF (AMD)",
    "H.265 AMF (AMD)",
    "H.264 QSV (Intel)",
    "H.265 QSV (Intel)",
]
_H264_ENCODERS = [
    "H.264 CPU (libx264)",
    "H.264 NVENC (NVIDIA)",
    "H.264 AMF (AMD)",
    "H.264 QSV (Intel)",
]
_ENCODER_CODEC = {
    "H.264 CPU (libx264)":  "libx264",
    "H.265 CPU (libx265)":  "libx265",
    "H.264 NVENC (NVIDIA)": "h264_nvenc",
    "H.265 NVENC (NVIDIA)": "hevc_nvenc",
    "H.264 AMF (AMD)":      "h264_amf",
    "H.265 AMF (AMD)":      "hevc_amf",
    "H.264 QSV (Intel)":    "h264_qsv",
    "H.265 QSV (Intel)":    "hevc_qsv",
}
_PRESETS      = ["ultrafast", "superfast", "veryfast", "faster",
                 "fast", "medium", "slow", "veryslow"]
_ROTATE_DIR   = ["なし", "1: 90°時計回り", "2: 90°反時計回り",
                 "0: 上下反転+90°CW", "3: 上下反転+90°CCW"]
_ROTATE_VIDEO = ["-90: 時計回り", "90: 反時計回り", "180: 上下反転"]
_AUDIO_OPTS   = ["AAC 128k", "AAC 192k", "AAC 256k", "コピー（再エンコードなし）"]

# ──── 生成スクリプトに埋め込む共通 ffmpeg 引数ビルダ ─────────────────────────
# ※ この文字列は生成スクリプト内の関数として展開されます

_ENC_ARGS_CODE = """\
def _enc_args(codec, crf, preset):
    if codec in ("h264_nvenc", "hevc_nvenc"):
        return ["-c:v", codec, "-preset", "p4", "-cq", str(crf)]
    if codec in ("h264_amf", "hevc_amf"):
        return ["-c:v", codec, "-quality", "quality",
                "-qp_i", str(crf), "-qp_p", str(crf)]
    if codec in ("h264_qsv", "hevc_qsv"):
        return ["-c:v", codec, "-global_quality", str(crf)]
    return ["-c:v", codec, "-preset", preset, "-crf", str(crf)]
"""

_FFMPEG_INIT_CODE = """\
try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = "ffmpeg"
"""

# ──── ランナー生成関数 ────────────────────────────────────────────────────────

def _build_runner_png_to_mp4(values: dict) -> str:
    """PNG → MP4 統合ランナー（CPU/GPU・回転・VRモード対応）"""
    codec   = _ENCODER_CODEC.get(str(values.get("ENCODER", "")), "libx264")
    fps     = int(values.get("FPS", 60))
    crf     = int(values.get("CRF", 18))
    preset  = repr(str(values.get("PRESET", "slow")))
    dry_run = repr(bool(values.get("DRY_RUN", False)))

    rotate_str = str(values.get("ROTATE", "なし"))
    rotate_val = repr(None if rotate_str == "なし" else int(rotate_str.split(":")[0]))

    vr_mode = repr(bool(values.get("VR_MODE", False)))
    ir = repr(str(values.get("INPUT_ROOT", "")))
    od = repr(str(values.get("OUTPUT_DIR", ".")))

    return f"""\
import re, subprocess
from pathlib import Path
from datetime import datetime

{_FFMPEG_INIT_CODE}
{_ENC_ARGS_CODE}

def _find_png_dirs(root):
    counts = {{}}
    for p in Path(root).rglob("*.png"):
        counts.setdefault(p.parent, 0)
        counts[p.parent] += 1
    return sorted([d for d, n in counts.items() if n >= 2],
                  key=lambda d: d.stat().st_mtime)

def _guess_start(d):
    nums = [int(m.group(1)) for p in d.glob("*.png")
            if (m := re.search(r"(\\d+)\\.png$", p.name))]
    return min(nums) if nums else 0

input_root = Path({ir})
output_dir = Path({od})
output_dir.mkdir(parents=True, exist_ok=True)
codec, fps, crf, preset = {repr(codec)}, {fps}, {crf}, {preset}
rotate, vr_mode, dry_run = {rotate_val}, {vr_mode}, {dry_run}

dirs = _find_png_dirs(input_root)
print(f"対象フォルダ数: {{len(dirs)}}")

for d in dirs:
    start = _guess_start(d)
    ts  = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    out = output_dir / f"{{ts}}.mp4"
    pat = str(d / "%d.png")

    enc     = _enc_args(codec, crf, preset)
    vf_args = ["-vf", f"transpose={{rotate}}"] if rotate is not None else []
    vr_args = (["-g", str(fps * 2), "-bf", "2",
                "-profile:v", "high", "-level", "5.2"] if vr_mode else [])

    cmd = [FFMPEG, "-y", "-hide_banner",
           "-framerate", str(fps), "-start_number", str(start), "-i", pat,
           *enc, *vf_args, *vr_args,
           "-pix_fmt", "yuv420p", "-movflags", "faststart", str(out)]

    print(f"▶ {{d.name}} -> {{out.name}}")
    if dry_run:
        print("  [DRY RUN]", " ".join(cmd))
    else:
        subprocess.run(cmd, check=True)
        print(f"  ✅ 完了: {{out}}")
"""


def _build_runner_compress_mp4(values: dict) -> str:
    """MP4 圧縮ランナー（コーデック・品質・音声を自由設定）"""
    codec  = _ENCODER_CODEC.get(str(values.get("ENCODER", "")), "libx264")
    crf    = int(values.get("CRF", 23))
    preset = repr(str(values.get("PRESET", "slow")))

    audio_raw = str(values.get("AUDIO", "AAC 128k"))
    audio_args = (
        ["-c:a", "copy"] if audio_raw == "コピー（再エンコードなし）"
        else ["-c:a", "aac", "-b:a", audio_raw.split()[-1].lower()]
    )

    inf  = repr(str(values.get("INPUT_FILE", "")))
    od   = repr(str(values.get("OUTPUT_DIR", ".")))
    dry_run = repr(bool(values.get("DRY_RUN", False)))

    return f"""\
import subprocess
from pathlib import Path
from datetime import datetime

{_FFMPEG_INIT_CODE}
{_ENC_ARGS_CODE}

input_file = Path({inf})
output_dir = Path({od})
output_dir.mkdir(parents=True, exist_ok=True)
codec, crf, preset = {repr(codec)}, {crf}, {preset}
audio_args = {repr(audio_args)}
dry_run = {dry_run}

ts  = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
out = output_dir / f"{{input_file.stem}}_{{codec}}_crf{{crf}}_{{ts}}.mp4"

enc = _enc_args(codec, crf, preset)
cmd = [FFMPEG, "-y", "-hide_banner", "-i", str(input_file),
       *enc, *audio_args,
       "-pix_fmt", "yuv420p", "-movflags", "faststart", str(out)]

print(f"入力   : {{input_file.name}}")
print(f"エンコーダー: {{codec}},  品質(CRF): {{crf}}")
print(f"音声   : {{' '.join(audio_args)}}")
print(f"出力   : {{out}}")
if dry_run:
    print("[DRY RUN]", " ".join(cmd))
else:
    subprocess.run(cmd, check=True)
    orig = input_file.stat().st_size / 1024 / 1024
    new  = out.stat().st_size / 1024 / 1024
    print(f"✅ 完了: {{orig:.1f}} MB -> {{new:.1f}} MB  (削減率 {{(1-new/orig)*100:.1f}}}%)")
"""


def _build_runner_rotate_video(values: dict) -> str:
    """MP4 回転ランナー（ffmpeg GPU 対応・音声コピー）"""
    codec = _ENCODER_CODEC.get(str(values.get("ENCODER", "")), "libx264")
    crf   = int(values.get("CRF", 18))

    angle_str = str(values.get("ROTATE_ANGLE", "-90: 時計回り"))
    angle = int(angle_str.split(":")[0])
    if angle == -90:
        vf = "transpose=1"
    elif angle == 90:
        vf = "transpose=2"
    else:
        vf = "vflip,hflip"

    inf = repr(str(values.get("INPUT_FILE", "")))
    od  = repr(str(values.get("OUTPUT_DIR", ".")))

    return f"""\
import subprocess
from pathlib import Path
from datetime import datetime

{_FFMPEG_INIT_CODE}
{_ENC_ARGS_CODE}

input_file = Path({inf})
output_dir = Path({od})
output_dir.mkdir(parents=True, exist_ok=True)
codec, crf = {repr(codec)}, {crf}

ts  = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
out = output_dir / f"{{ts}}.mp4"

enc = _enc_args(codec, crf, "slow")
cmd = [FFMPEG, "-y", "-hide_banner", "-i", str(input_file),
       "-vf", {repr(vf)},
       *enc, "-c:a", "copy",
       "-pix_fmt", "yuv420p", "-movflags", "faststart", str(out)]

print(f"▶ {{input_file.name}} -> {{out.name}}  ({{codec}})")
subprocess.run(cmd, check=True)
print(f"✅ 完了: {{out}}")
"""


def _build_runner_png_resize(values: dict) -> str:
    """PNG リサイズ（OpenCV）"""
    pd = repr(str(PROGRAMS_DIR))
    return (
        f"import sys\n"
        f"sys.path.insert(0, {pd})\n"
        f"import png_compress as _m\n"
        f"_m.resize_images_opencv_parallel(\n"
        f"    {repr(str(values['INPUT_DIR']))},\n"
        f"    {repr(str(values['OUTPUT_DIR']))},\n"
        f"    {int(values['WIDTH'])}, {int(values['HEIGHT'])},\n"
        f"    max_workers={int(values['WORKERS'])}\n"
        f")\nprint('完了')\n"
    )

# ──── 汎用ランナービルダー ────────────────────────────────────────────────────

def build_runner(tool: dict, values: dict) -> str:
    cfg_type = tool["config_type"]

    if cfg_type == "INLINE":
        return tool["runner_fn"](values)

    pd     = repr(str(PROGRAMS_DIR))
    module = tool["module"]

    if cfg_type == "CONFIG_ONLY":
        full = {**tool.get("extra_config", {}), **values}
        return (f"import sys\nsys.path.insert(0, {pd})\n"
                f"import {module} as _m\n"
                f"_m.CONFIG.update({repr(full)})\n"
                f"_m.main()\n")

    # VARS
    var_types = tool.get("var_types", {})
    lines = ["import sys", f"sys.path.insert(0, {pd})",
             f"import {module} as _m", "import pathlib"]
    for k, v in values.items():
        vtype = var_types.get(k, "str")
        if vtype == "Path":
            lines.append(f"_m.{k} = pathlib.Path({repr(str(v))})")
        elif vtype == "int":
            lines.append(f"_m.{k} = {int(v)}")
        else:
            lines.append(f"_m.{k} = {repr(v)}")
    lines.append("_m.main()")
    return "\n".join(lines) + "\n"

# ──── ツール定義（7ツール）────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "PNG → MP4",
        "desc": "PNG 連番フォルダを MP4 に変換します。コーデック・GPU・回転・360°VR を一括設定できます。",
        "config_type": "INLINE",
        "runner_fn": _build_runner_png_to_mp4,
        "params": [
            {"key": "INPUT_ROOT", "label": "入力フォルダ（自動探索）",           "type": "dir"},
            {"key": "OUTPUT_DIR", "label": "出力フォルダ（空=入力と同じ場所）",  "type": "dir"},
            {"key": "FPS",        "label": "FPS",                               "type": "int",   "default": 60},
            {"key": "ENCODER",    "label": "エンコーダー",                       "type": "combo", "default": "H.264 CPU (libx264)", "values": _ALL_ENCODERS},
            {"key": "CRF",        "label": "品質 CRF（低いほど高品質・大容量）", "type": "int",   "default": 18},
            {"key": "PRESET",     "label": "プリセット（CPU のみ有効）",          "type": "combo", "default": "slow", "values": _PRESETS},
            {"key": "ROTATE",     "label": "回転",                               "type": "combo", "default": "なし", "values": _ROTATE_DIR},
            {"key": "VR_MODE",    "label": "360° VR モード",                    "type": "bool",  "default": False},
            {"key": "DRY_RUN",    "label": "ドライラン（実行しない）",           "type": "bool",  "default": False},
        ],
    },
    {
        "name": "MP4 圧縮",
        "desc": "MP4 ファイルを再エンコードして圧縮します。エンコーダー・品質・音声を自由に設定できます。",
        "config_type": "INLINE",
        "runner_fn": _build_runner_compress_mp4,
        "params": [
            {"key": "INPUT_FILE", "label": "入力 MP4 ファイル",                  "type": "file",
             "filetypes": [("MP4 ファイル", "*.mp4"), ("すべて", "*.*")]},
            {"key": "OUTPUT_DIR", "label": "出力フォルダ（空=入力と同じ場所）",  "type": "dir"},
            {"key": "ENCODER",    "label": "エンコーダー",                        "type": "combo", "default": "H.264 CPU (libx264)", "values": _ALL_ENCODERS},
            {"key": "CRF",        "label": "品質 CRF（H.264: 18-28 / H.265: 22-32）", "type": "int", "default": 23},
            {"key": "PRESET",     "label": "プリセット（CPU のみ有効）",          "type": "combo", "default": "slow", "values": _PRESETS},
            {"key": "AUDIO",      "label": "音声",                               "type": "combo", "default": "AAC 128k", "values": _AUDIO_OPTS},
            {"key": "DRY_RUN",    "label": "ドライラン（実行しない）",            "type": "bool",  "default": False},
        ],
    },
    {
        "name": "MP4 → GIF",
        "desc": "MP4 ファイルを GIF アニメーションに変換します。",
        "module": "mp4_to_gif",
        "config_type": "CONFIG_ONLY",
        "params": [
            {"key": "INPUT_VIDEO",   "label": "入力 MP4 ファイル",                  "type": "file",
             "filetypes": [("MP4 ファイル", "*.mp4"), ("すべて", "*.*")]},
            {"key": "OUTPUT_DIR",    "label": "出力フォルダ（空=入力と同じ場所）",  "type": "dir"},
            {"key": "FPS",           "label": "GIF FPS",                             "type": "int",   "default": 15},
            {"key": "SCALE_PERCENT", "label": "リサイズ (%)",                        "type": "int",   "default": 100},
            {"key": "START_SEC",     "label": "開始秒（空=先頭）",                  "type": "entry", "default": ""},
            {"key": "END_SEC",       "label": "終了秒（空=末尾）",                  "type": "entry", "default": ""},
        ],
        "extra_config": {"ENGINE": "ffmpeg", "LOOP": True, "SHOW_PROGRESS": True, "FIXED_SIZE": ()},
        "transforms": {
            "START_SEC":     lambda v: None if str(v).strip() == "" else float(v),
            "END_SEC":       lambda v: None if str(v).strip() == "" else float(v),
            "SCALE_PERCENT": lambda v: int(v) if str(v).strip() else None,
        },
    },
    {
        "name": "MP4 回転",
        "desc": "MP4 動画を回転させます。GPU エンコーダーを選択すると高速に処理できます。音声はコピーします。",
        "config_type": "INLINE",
        "runner_fn": _build_runner_rotate_video,
        "params": [
            {"key": "INPUT_FILE",   "label": "入力 MP4 ファイル",                  "type": "file",
             "filetypes": [("MP4 ファイル", "*.mp4"), ("すべて", "*.*")]},
            {"key": "OUTPUT_DIR",   "label": "出力フォルダ（空=入力と同じ場所）",  "type": "dir"},
            {"key": "ROTATE_ANGLE", "label": "回転方向",                            "type": "combo",
             "default": "-90: 時計回り", "values": _ROTATE_VIDEO},
            {"key": "ENCODER",      "label": "エンコーダー",                        "type": "combo",
             "default": "H.264 CPU (libx264)", "values": _H264_ENCODERS},
            {"key": "CRF",          "label": "品質 CRF",                            "type": "int", "default": 18},
        ],
    },
    {
        "name": "PNG → JPEG",
        "desc": "PNG ファイルを一括で JPEG に変換します（透過 PNG 対応）。",
        "module": "convert_png_to_jpeg",
        "config_type": "VARS",
        "params": [
            {"key": "INPUT_DIR",  "label": "入力フォルダ",                      "type": "dir"},
            {"key": "OUTPUT_DIR", "label": "出力フォルダ（空=入力と同じ場所）", "type": "dir"},
            {"key": "QUALITY",    "label": "JPEG 品質 (1-95)",                  "type": "int", "default": 95},
            {"key": "WORKERS",    "label": "並列スレッド数",                    "type": "int", "default": 4},
        ],
        "var_types": {
            "INPUT_DIR": "Path", "OUTPUT_DIR": "Path",
            "QUALITY": "int", "WORKERS": "int",
        },
    },
    {
        "name": "PNG 圧縮",
        "desc": "PNG 画像を一括圧縮・リサイズします（Pillow 使用）。",
        "module": "compression_png",
        "config_type": "VARS",
        "params": [
            {"key": "INPUT_DIR",      "label": "入力フォルダ",                      "type": "dir"},
            {"key": "OUTPUT_DIR",     "label": "出力フォルダ（空=入力と同じ場所）", "type": "dir"},
            {"key": "MAX_SIDE",       "label": "最大辺長 px（0=リサイズなし）",     "type": "int", "default": 0},
            {"key": "COLORS",         "label": "色数（256=変更なし）",              "type": "int", "default": 256},
            {"key": "COMPRESS_LEVEL", "label": "PNG 圧縮レベル (0-9)",              "type": "int", "default": 9},
            {"key": "WORKERS",        "label": "並列スレッド数",                    "type": "int", "default": 4},
        ],
        "var_types": {
            "INPUT_DIR": "Path", "OUTPUT_DIR": "Path",
            "MAX_SIDE": "int", "COLORS": "int",
            "COMPRESS_LEVEL": "int", "WORKERS": "int",
        },
    },
    {
        "name": "PNG リサイズ (OpenCV)",
        "desc": "PNG 画像を OpenCV で高速並列リサイズします。",
        "config_type": "INLINE",
        "runner_fn": _build_runner_png_resize,
        "params": [
            {"key": "INPUT_DIR",  "label": "入力フォルダ",                      "type": "dir"},
            {"key": "OUTPUT_DIR", "label": "出力フォルダ（空=入力と同じ場所）", "type": "dir"},
            {"key": "WIDTH",      "label": "出力幅 (px)",                       "type": "int", "default": 1920},
            {"key": "HEIGHT",     "label": "出力高さ (px)",                     "type": "int", "default": 1080},
            {"key": "WORKERS",    "label": "並列数",                            "type": "int", "default": 8},
        ],
    },
]

# ──── GUI アプリ ──────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Movie Image Tools")
        self.minsize(740, 600)
        self.geometry("920x740")
        self._proc: subprocess.Popen | None = None
        self._widgets: dict[str, tk.Variable] = {}
        self._settings: dict = load_settings()
        self._setup_ui()
        self._on_tool_change()

    # ── UI 構築 ──────────────────────────────────────────────────────────────

    def _setup_ui(self):
        hdr = ttk.Frame(self, padding=(8, 6))
        hdr.pack(fill=tk.X)
        ttk.Label(hdr, text="Movie Image Tools", font=("", 14, "bold")).pack(side=tk.LEFT)

        sel = ttk.Frame(self, padding=(8, 2))
        sel.pack(fill=tk.X)
        ttk.Label(sel, text="ツール:").pack(side=tk.LEFT)
        self._tool_combo = ttk.Combobox(
            sel, values=[t["name"] for t in TOOLS], state="readonly", width=28)
        self._tool_combo.current(0)
        self._tool_combo.pack(side=tk.LEFT, padx=6)
        self._tool_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_tool_change())

        self._desc_var = tk.StringVar()
        ttk.Label(self, textvariable=self._desc_var, foreground="#555555",
                  wraplength=880, justify=tk.LEFT, padding=(8, 2)).pack(fill=tk.X)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=4)

        form_wrap = ttk.LabelFrame(self, text="設定", padding=(6, 4))
        form_wrap.pack(fill=tk.X, padx=8, pady=(0, 4))
        canvas = tk.Canvas(form_wrap, highlightthickness=0)
        vsb = ttk.Scrollbar(form_wrap, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._form_frame = ttk.Frame(canvas)
        self._canvas_win = canvas.create_window((0, 0), window=self._form_frame, anchor=tk.NW)

        def _on_frame_cfg(_e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.configure(height=min(self._form_frame.winfo_reqheight(), 280))
        def _on_canvas_cfg(e):
            canvas.itemconfig(self._canvas_win, width=e.width)

        self._form_frame.bind("<Configure>", _on_frame_cfg)
        canvas.bind("<Configure>", _on_canvas_cfg)
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=4)

        btn_row = ttk.Frame(self, padding=(8, 0))
        btn_row.pack(fill=tk.X)
        self._run_btn = ttk.Button(btn_row, text="▶  実行", command=self._run, width=10)
        self._run_btn.pack(side=tk.LEFT, padx=4)
        self._stop_btn = ttk.Button(btn_row, text="■  停止", command=self._stop,
                                    state=tk.DISABLED, width=10)
        self._stop_btn.pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="クリア", command=self._clear, width=8).pack(side=tk.LEFT, padx=4)
        self._status_var = tk.StringVar(value="待機中")
        ttk.Label(btn_row, textvariable=self._status_var, foreground="#777777").pack(
            side=tk.RIGHT, padx=8)

        self._progress = ttk.Progressbar(self, mode="indeterminate")
        self._progress.pack(fill=tk.X, padx=8, pady=(4, 0))

        con = ttk.LabelFrame(self, text="コンソール出力", padding=(4, 2))
        con.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))
        self._console = scrolledtext.ScrolledText(
            con, height=12, font=("Courier New", 9), wrap=tk.WORD, state=tk.DISABLED)
        self._console.pack(fill=tk.BOTH, expand=True)

    # ── ツール切り替え ───────────────────────────────────────────────────────

    def _on_tool_change(self):
        tool = TOOLS[self._tool_combo.current()]
        self._desc_var.set(tool["desc"])
        self._build_form(tool)
        saved = self._settings.get(tool["name"], {})
        for key, var in self._widgets.items():
            if key in saved:
                try:
                    var.set(saved[key])
                except Exception:
                    pass

    def _build_form(self, tool: dict):
        for w in self._form_frame.winfo_children():
            w.destroy()
        self._widgets.clear()
        self._form_frame.columnconfigure(1, weight=1)

        for row, param in enumerate(tool["params"]):
            ttk.Label(self._form_frame, text=param["label"] + ":", anchor=tk.E).grid(
                row=row, column=0, sticky=tk.E, padx=(4, 8), pady=4)

            p_type  = param["type"]
            default = param.get("default", "")

            if p_type in ("dir", "file"):
                var  = tk.StringVar(value=str(default))
                cell = ttk.Frame(self._form_frame)
                cell.grid(row=row, column=1, sticky=tk.EW, padx=4, pady=4)
                cell.columnconfigure(0, weight=1)
                ttk.Entry(cell, textvariable=var).grid(row=0, column=0, sticky=tk.EW)
                if p_type == "dir":
                    ttk.Button(cell, text="参照…", width=6,
                               command=lambda v=var: self._pick_dir(v)).grid(
                                   row=0, column=1, padx=(4, 0))
                else:
                    ft = param.get("filetypes", [("すべて", "*.*")])
                    ttk.Button(cell, text="参照…", width=6,
                               command=lambda v=var, f=ft: self._pick_file(v, f)).grid(
                                   row=0, column=1, padx=(4, 0))
                self._widgets[param["key"]] = var

            elif p_type == "combo":
                var = tk.StringVar(value=str(default))
                ttk.Combobox(self._form_frame, textvariable=var,
                             values=param.get("values", []), state="readonly", width=28).grid(
                    row=row, column=1, sticky=tk.W, padx=4, pady=4)
                self._widgets[param["key"]] = var

            elif p_type in ("int", "entry"):
                var = tk.StringVar(value=str(default))
                ttk.Entry(self._form_frame, textvariable=var, width=14).grid(
                    row=row, column=1, sticky=tk.W, padx=4, pady=4)
                self._widgets[param["key"]] = var

            elif p_type == "bool":
                var = tk.BooleanVar(value=bool(default))
                ttk.Checkbutton(self._form_frame, variable=var).grid(
                    row=row, column=1, sticky=tk.W, padx=4, pady=4)
                self._widgets[param["key"]] = var

    # ── ファイル / フォルダ選択 ──────────────────────────────────────────────

    def _pick_dir(self, var: tk.StringVar):
        d = filedialog.askdirectory(title="フォルダを選択")
        if d:
            var.set(d)

    def _pick_file(self, var: tk.StringVar, filetypes):
        f = filedialog.askopenfilename(title="ファイルを選択", filetypes=filetypes)
        if f:
            var.set(f)

    # ── 設定値収集 ──────────────────────────────────────────────────────────

    def _collect_values(self) -> dict:
        tool   = TOOLS[self._tool_combo.current()]
        values: dict = {}
        for param in tool["params"]:
            key    = param["key"]
            raw    = self._widgets[key].get()
            p_type = param["type"]
            if p_type == "int":
                try:
                    values[key] = int(raw)
                except ValueError:
                    values[key] = param.get("default", 0)
            elif p_type == "bool":
                values[key] = bool(self._widgets[key].get())
            else:
                values[key] = raw
        for key, fn in tool.get("transforms", {}).items():
            if key in values:
                values[key] = fn(values[key])
        return values

    # ── 入力チェック ────────────────────────────────────────────────────────

    def _validate(self, tool: dict, values: dict) -> list:
        errors = []
        for param in tool["params"]:
            if param["type"] not in ("dir", "file"):
                continue
            key = param["key"]
            if not key.startswith("INPUT"):
                continue
            val = str(values.get(key, "")).strip()
            if not val:
                errors.append(f"「{param['label']}」を指定してください")
            elif not Path(val).exists():
                errors.append(f"「{param['label']}」が見つかりません:\n  {val}")
        return errors

    # ── 出力フォルダのデフォルト設定 ────────────────────────────────────────

    def _apply_output_default(self, values: dict) -> None:
        if str(values.get("OUTPUT_DIR", "")).strip():
            return
        for key in ("INPUT_ROOT", "INPUT_DIR", "INPUT_FILE", "INPUT_VIDEO"):
            if values.get(key):
                p = Path(str(values[key]))
                default_out = str(p if p.is_dir() else p.parent)
                values["OUTPUT_DIR"] = default_out
                self._log(f"出力先を自動設定: {default_out}\n")
                if "OUTPUT_DIR" in self._widgets:
                    self.after(0, lambda v=default_out: self._widgets["OUTPUT_DIR"].set(v))
                break

    # ── 設定保存 ────────────────────────────────────────────────────────────

    def _save_current(self, tool: dict) -> None:
        saved = {}
        for key, var in self._widgets.items():
            try:
                saved[key] = var.get()
            except Exception:
                pass
        self._settings[tool["name"]] = saved
        save_settings(self._settings)

    # ── 実行 ────────────────────────────────────────────────────────────────

    def _run(self):
        tool = TOOLS[self._tool_combo.current()]
        try:
            values = self._collect_values()
        except Exception as exc:
            messagebox.showerror("エラー", f"設定エラー: {exc}")
            return

        errors = self._validate(tool, values)
        if errors:
            messagebox.showerror("入力エラー", "\n".join(errors))
            return

        self._apply_output_default(values)
        self._save_current(tool)

        try:
            script = build_runner(tool, values)
        except Exception as exc:
            messagebox.showerror("エラー", f"ランナー生成エラー: {exc}")
            return

        self._log(f"\n{'=' * 52}\n▶  {tool['name']}  開始\n{'=' * 52}\n")

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8")
        tmp.write(script)
        tmp.close()

        self._run_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self._tool_combo.config(state=tk.DISABLED)
        self._status_var.set("実行中…")
        self._progress.start(12)

        def _worker():
            try:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUTF8"] = "1"
                self._proc = subprocess.Popen(
                    [sys.executable, "-X", "utf8", tmp.name],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    env=env,
                )
                for line in self._proc.stdout:
                    self._log(line)
                self._proc.wait()
                rc = self._proc.returncode
                if rc == 0:
                    self._log("\n✅ 完了\n")
                    self.after(0, lambda: self._status_var.set("完了"))
                else:
                    self._log(f"\n❌ エラー（終了コード {rc}）\n")
                    self.after(0, lambda: self._status_var.set(f"エラー (code={rc})"))
            except Exception as exc:
                self._log(f"\n❌ 例外: {exc}\n")
                self.after(0, lambda: self._status_var.set("例外エラー"))
            finally:
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass
                self.after(0, self._on_done)

        threading.Thread(target=_worker, daemon=True).start()

    def _stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._log("\n⛔ ユーザーによって停止されました\n")
            self._status_var.set("停止")

    def _on_done(self):
        self._progress.stop()
        self._run_btn.config(state=tk.NORMAL)
        self._stop_btn.config(state=tk.DISABLED)
        self._tool_combo.config(state="readonly")
        self._proc = None

    # ── コンソール ──────────────────────────────────────────────────────────

    def _log(self, text: str):
        def _upd():
            self._console.config(state=tk.NORMAL)
            self._console.insert(tk.END, text)
            self._console.see(tk.END)
            self._console.config(state=tk.DISABLED)
        self.after(0, _upd)

    def _clear(self):
        self._console.config(state=tk.NORMAL)
        self._console.delete("1.0", tk.END)
        self._console.config(state=tk.DISABLED)
        self._status_var.set("待機中")


# ──── エントリポイント ────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
