#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Movie Image Tools - GUI ランチャー

使い方:
  python app.py

依存:
  pip install -r requirements.txt
"""

import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, scrolledtext, ttk

BASE_DIR = Path(__file__).parent
PROGRAMS_DIR = BASE_DIR / "programs"

# ──── ツール定義 ──────────────────────────────────────────────────────────────
#
# config_type の意味:
#   CONFIG_ARG  … スクリプトが main(cfg) 形式（create_mp4, create_mp4_list）
#   CONFIG_ONLY … スクリプトが main() でモジュール変数 CONFIG を直読み
#   VARS        … スクリプトがモジュールレベル変数を直読み（CONFIG dict なし）
#
TOOLS = [
    {
        "name": "PNG → MP4 (H.264)",
        "desc": "PNG 連番フォルダを H.264 MP4 に一括変換します",
        "module": "create_mp4",
        "config_type": "CONFIG_ARG",
        "params": [
            {"key": "INPUT_ROOT",  "label": "入力フォルダ（自動探索）",               "type": "dir"},
            {"key": "OUTPUT_DIR",  "label": "出力フォルダ",                           "type": "dir"},
            {"key": "FPS",         "label": "FPS",                                    "type": "int",   "default": 60},
            {"key": "CRF",         "label": "CRF（0=無損失 / 18=高品質 / 51=低品質）", "type": "int",   "default": 18},
            {"key": "PRESET",      "label": "プリセット（速い ←→ 遅い/小さい）",      "type": "combo", "default": "veryslow",
             "values": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "veryslow"]},
            {"key": "PROFILE",     "label": "H.264 プロファイル",                     "type": "entry", "default": "high"},
            {"key": "LEVEL",       "label": "H.264 レベル",                           "type": "entry", "default": "5.1"},
            {"key": "DRY_RUN",     "label": "ドライラン（実行しない）",                "type": "bool",  "default": False},
        ],
        "extra_config": {
            "INPUT_MODE": "auto", "INPUT_DIRS": [], "RECURSIVE": True, "MIN_PNGS": 2,
            "SKIP_IF_EXISTS": True, "OUT_NAME_MODE": "timestamp",
            "START_NUMBER": "auto", "KEYINT_SECONDS": 2, "TUNE": "",
        },
    },
    {
        "name": "PNG → MP4 (H.265)",
        "desc": "PNG 連番フォルダを H.265 MP4 に一括変換します（高圧縮・低ファイルサイズ）",
        "module": "create_mp4_list",
        "config_type": "CONFIG_ARG",
        "params": [
            {"key": "INPUT_ROOT", "label": "入力フォルダ（自動探索）",          "type": "dir"},
            {"key": "OUTPUT_DIR", "label": "出力フォルダ",                      "type": "dir"},
            {"key": "FPS",        "label": "FPS",                               "type": "int",   "default": 60},
            {"key": "CRF",        "label": "CRF（品質 20〜24 目安）",            "type": "int",   "default": 20},
            {"key": "PRESET",     "label": "プリセット",                         "type": "combo", "default": "veryslow",
             "values": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "veryslow"]},
            {"key": "DRY_RUN",    "label": "ドライラン（実行しない）",           "type": "bool",  "default": False},
        ],
        "extra_config": {
            "INPUT_MODE": "auto", "INPUT_DIRS": [], "RECURSIVE": True, "MIN_PNGS": 2,
            "SKIP_IF_EXISTS": True, "OUT_NAME_MODE": "timestamp",
            "START_NUMBER": "auto", "KEYINT_SECONDS": 2,
            "PIX_FMT": "yuv420p", "X265_TUNE": "",
        },
    },
    {
        "name": "MP4 圧縮",
        "desc": "MP4 ファイルを再エンコードして圧縮します",
        "module": "compress_mp4",
        "config_type": "CONFIG_ONLY",
        "params": [
            {"key": "INPUT_FILE", "label": "入力 MP4 ファイル", "type": "file",
             "filetypes": [("MP4 ファイル", "*.mp4"), ("すべて", "*.*")]},
            {"key": "OUTPUT_DIR", "label": "出力フォルダ",      "type": "dir"},
            {"key": "PRESET",     "label": "プリセット",         "type": "combo", "default": "fanbox_h264",
             "values": ["fanbox_h264", "size_hevc_cpu", "speed_hevc_amf"]},
            {"key": "DRY_RUN",    "label": "ドライラン（実行しない）", "type": "bool", "default": False},
        ],
        "extra_config": {
            "SHOW_PROGRESS": True,
            "OVERRIDE": {},
        },
    },
    {
        "name": "MP4 → GIF",
        "desc": "MP4 ファイルを GIF アニメーションに変換します",
        "module": "mp4_to_gif",
        "config_type": "CONFIG_ONLY",
        "params": [
            {"key": "INPUT_VIDEO",    "label": "入力 MP4 ファイル",                   "type": "file",
             "filetypes": [("MP4 ファイル", "*.mp4"), ("すべて", "*.*")]},
            {"key": "OUTPUT_DIR",     "label": "出力フォルダ（空 = 入力と同じ場所）", "type": "dir"},
            {"key": "FPS",            "label": "GIF FPS",                             "type": "int",   "default": 15},
            {"key": "SCALE_PERCENT",  "label": "リサイズ (%)",                        "type": "int",   "default": 100},
            {"key": "START_SEC",      "label": "開始秒（空 = 先頭）",                 "type": "entry", "default": ""},
            {"key": "END_SEC",        "label": "終了秒（空 = 末尾）",                 "type": "entry", "default": ""},
        ],
        "extra_config": {
            "ENGINE": "ffmpeg", "LOOP": True, "SHOW_PROGRESS": True, "FIXED_SIZE": (),
        },
        "transforms": {
            "START_SEC":     lambda v: None if str(v).strip() == "" else float(v),
            "END_SEC":       lambda v: None if str(v).strip() == "" else float(v),
            "SCALE_PERCENT": lambda v: int(v) if str(v).strip() else None,
        },
    },
    {
        "name": "PNG → JPEG",
        "desc": "PNG ファイルを一括で JPEG に変換します（透過 PNG 対応）",
        "module": "convert_png_to_jpeg",
        "config_type": "VARS",
        "params": [
            {"key": "INPUT_DIR",  "label": "入力フォルダ",        "type": "dir"},
            {"key": "OUTPUT_DIR", "label": "出力フォルダ",        "type": "dir"},
            {"key": "QUALITY",    "label": "JPEG 品質 (1-95)",    "type": "int", "default": 95},
            {"key": "WORKERS",    "label": "並列スレッド数",       "type": "int", "default": 4},
        ],
        "var_types": {
            "INPUT_DIR": "Path", "OUTPUT_DIR": "Path",
            "QUALITY": "int", "WORKERS": "int",
        },
    },
    {
        "name": "PNG 圧縮",
        "desc": "PNG 画像を一括圧縮・リサイズします",
        "module": "compression_png",
        "config_type": "VARS",
        "params": [
            {"key": "INPUT_DIR",       "label": "入力フォルダ",                   "type": "dir"},
            {"key": "OUTPUT_DIR",      "label": "出力フォルダ",                   "type": "dir"},
            {"key": "MAX_SIDE",        "label": "最大辺長 px（0 = リサイズなし）", "type": "int", "default": 0},
            {"key": "COLORS",          "label": "色数（256 = 変更なし）",          "type": "int", "default": 256},
            {"key": "COMPRESS_LEVEL",  "label": "PNG 圧縮レベル (0-9)",           "type": "int", "default": 9},
            {"key": "WORKERS",         "label": "並列スレッド数",                  "type": "int", "default": 4},
        ],
        "var_types": {
            "INPUT_DIR": "Path", "OUTPUT_DIR": "Path",
            "MAX_SIDE": "int", "COLORS": "int",
            "COMPRESS_LEVEL": "int", "WORKERS": "int",
        },
    },
]


# ──── ランナースクリプト生成 ──────────────────────────────────────────────────

def build_runner(tool: dict, values: dict) -> str:
    """GUI フォームの値からサブプロセス実行用 Python スクリプトを生成する。"""
    prog_dir = repr(str(PROGRAMS_DIR))
    module = tool["module"]
    cfg_type = tool["config_type"]

    if cfg_type in ("CONFIG_ARG", "CONFIG_ONLY"):
        extra = tool.get("extra_config", {})
        full = {**extra, **values}
        call = f"_m.main(_m.CONFIG)" if cfg_type == "CONFIG_ARG" else "_m.main()"
        return (
            f"import sys\n"
            f"sys.path.insert(0, {prog_dir})\n"
            f"import {module} as _m\n"
            f"_m.CONFIG.update({repr(full)})\n"
            f"{call}\n"
        )

    # VARS: モジュールレベル変数を上書きして main() を呼ぶ
    var_types = tool.get("var_types", {})
    lines = [
        "import sys",
        f"sys.path.insert(0, {prog_dir})",
        f"import {module} as _m",
        "import pathlib",
    ]
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


# ──── GUI アプリ ──────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Movie Image Tools")
        self.minsize(720, 560)
        self.geometry("880x700")
        self._proc: subprocess.Popen | None = None
        self._widgets: dict[str, tk.Variable] = {}
        self._setup_ui()
        self._on_tool_change()

    # ── UI 構築 ──────────────────────────────────────────────────────────────

    def _setup_ui(self):
        # ── ヘッダー
        hdr = ttk.Frame(self, padding=(8, 6))
        hdr.pack(fill=tk.X)
        ttk.Label(hdr, text="Movie Image Tools", font=("", 14, "bold")).pack(side=tk.LEFT)

        # ── ツール選択
        sel = ttk.Frame(self, padding=(8, 2))
        sel.pack(fill=tk.X)
        ttk.Label(sel, text="ツール:").pack(side=tk.LEFT)
        self._tool_combo = ttk.Combobox(
            sel, values=[t["name"] for t in TOOLS],
            state="readonly", width=30,
        )
        self._tool_combo.current(0)
        self._tool_combo.pack(side=tk.LEFT, padx=6)
        self._tool_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_tool_change())

        # ── ツール説明
        self._desc_var = tk.StringVar()
        ttk.Label(
            self, textvariable=self._desc_var,
            foreground="#555555", wraplength=840, justify=tk.LEFT, padding=(8, 2),
        ).pack(fill=tk.X, anchor=tk.W)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=4)

        # ── 設定フォーム
        self._form_outer = ttk.LabelFrame(self, text="設定", padding=(6, 4))
        self._form_outer.pack(fill=tk.X, padx=8, pady=(0, 4))
        self._form_frame = ttk.Frame(self._form_outer)
        self._form_frame.pack(fill=tk.X)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=4)

        # ── ボタン行
        btn_row = ttk.Frame(self, padding=(8, 0))
        btn_row.pack(fill=tk.X)
        self._run_btn = ttk.Button(btn_row, text="▶  実行", command=self._run, width=10)
        self._run_btn.pack(side=tk.LEFT, padx=4)
        self._stop_btn = ttk.Button(
            btn_row, text="■  停止", command=self._stop,
            state=tk.DISABLED, width=10,
        )
        self._stop_btn.pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="クリア", command=self._clear, width=8).pack(side=tk.LEFT, padx=4)
        self._status_var = tk.StringVar(value="待機中")
        ttk.Label(btn_row, textvariable=self._status_var, foreground="#777777").pack(
            side=tk.RIGHT, padx=8)

        # ── コンソール
        con = ttk.LabelFrame(self, text="コンソール出力", padding=(4, 2))
        con.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self._console = scrolledtext.ScrolledText(
            con, height=12, font=("Courier New", 9),
            wrap=tk.WORD, state=tk.DISABLED,
        )
        self._console.pack(fill=tk.BOTH, expand=True)

    # ── ツール切り替え ───────────────────────────────────────────────────────

    def _on_tool_change(self):
        tool = TOOLS[self._tool_combo.current()]
        self._desc_var.set(tool["desc"])
        self._build_form(tool)

    def _build_form(self, tool: dict):
        for w in self._form_frame.winfo_children():
            w.destroy()
        self._widgets.clear()
        self._form_frame.columnconfigure(1, weight=1)

        for row, param in enumerate(tool["params"]):
            ttk.Label(self._form_frame, text=param["label"] + ":", anchor=tk.E).grid(
                row=row, column=0, sticky=tk.E, padx=(4, 8), pady=4,
            )

            p_type = param["type"]
            default = param.get("default", "")

            if p_type in ("dir", "file"):
                var = tk.StringVar(value=str(default))
                cell = ttk.Frame(self._form_frame)
                cell.grid(row=row, column=1, sticky=tk.EW, padx=4, pady=4)
                cell.columnconfigure(0, weight=1)
                ttk.Entry(cell, textvariable=var).grid(row=0, column=0, sticky=tk.EW)
                if p_type == "dir":
                    ttk.Button(
                        cell, text="参照…", width=6,
                        command=lambda v=var: self._pick_dir(v),
                    ).grid(row=0, column=1, padx=(4, 0))
                else:
                    ft = param.get("filetypes", [("すべて", "*.*")])
                    ttk.Button(
                        cell, text="参照…", width=6,
                        command=lambda v=var, f=ft: self._pick_file(v, f),
                    ).grid(row=0, column=1, padx=(4, 0))
                self._widgets[param["key"]] = var

            elif p_type == "combo":
                var = tk.StringVar(value=str(default))
                ttk.Combobox(
                    self._form_frame, textvariable=var,
                    values=param.get("values", []), state="readonly", width=24,
                ).grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)
                self._widgets[param["key"]] = var

            elif p_type in ("int", "entry"):
                var = tk.StringVar(value=str(default))
                ttk.Entry(self._form_frame, textvariable=var, width=14).grid(
                    row=row, column=1, sticky=tk.W, padx=4, pady=4,
                )
                self._widgets[param["key"]] = var

            elif p_type == "bool":
                var = tk.BooleanVar(value=bool(default))
                ttk.Checkbutton(self._form_frame, variable=var).grid(
                    row=row, column=1, sticky=tk.W, padx=4, pady=4,
                )
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
        tool = TOOLS[self._tool_combo.current()]
        values: dict = {}
        for param in tool["params"]:
            key = param["key"]
            raw = self._widgets[key].get()
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

    # ── 実行 ────────────────────────────────────────────────────────────────

    def _run(self):
        tool = TOOLS[self._tool_combo.current()]
        try:
            values = self._collect_values()
        except Exception as exc:
            self._log(f"❌ 設定エラー: {exc}\n")
            return

        script = build_runner(tool, values)
        self._log(f"\n{'=' * 52}\n▶  {tool['name']}  開始\n{'=' * 52}\n")

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8")
        tmp.write(script)
        tmp.close()

        self._run_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self._tool_combo.config(state=tk.DISABLED)
        self._status_var.set("実行中…")

        def _worker():
            try:
                self._proc = subprocess.Popen(
                    [sys.executable, tmp.name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
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
