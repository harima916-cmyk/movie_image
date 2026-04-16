#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ez_recompress_mp4_progress_noblock.py
-progress pipe:1 + stderr 非ブロック排出でハングを防ぐ版
"""

from __future__ import annotations
import os, re, sys, json, shutil, subprocess, threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Tuple

try:
    from tqdm import tqdm
except Exception:
    tqdm = None  # tqdm が無ければテキスト進捗にフォールバック

# ====================== ここだけ編集（ユーザー設定）======================
CONFIG = {
    "INPUT_FILE": r"C:\Users\harim\Downloads\from-PixAI-1972419401845119153.mp4",
    "OUTPUT_DIR": r"F:\movie\output",
    "PRESET": "fanbox_h264",  # fanbox_h264 / size_hevc_cpu / speed_hevc_amf
    "OVERRIDE": {
        "codec": "libx264", "mode": "crf", "crf": 24, "bitrate": None,
        "preset": "veryslow", "tune": None,
        "audio": None, "audio_bitrate": None,
        "pix_fmt": None, "faststart": None,
    },
    "SHOW_PROGRESS": True,
    "DRY_RUN": False,
}
# ======================================================================

PRESETS: Dict[str, Dict[str, Optional[str]]] = {
    "fanbox_h264": {
        "codec": "libx264", "mode": "crf", "crf": 22, "bitrate": None,
        "preset": "slow", "tune": None,
        "audio": "aac", "audio_bitrate": "160k",
        "pix_fmt": "yuv420p", "faststart": True,
    },
    "size_hevc_cpu": {
        "codec": "libx265", "mode": "crf", "crf": 26, "bitrate": None,
        "preset": "slow", "tune": None,
        "audio": "aac", "audio_bitrate": "160k",
        "pix_fmt": "yuv420p", "faststart": True,
    },
    "speed_hevc_amf": {
        "codec": "hevc_amf", "mode": "crf", "crf": 26, "bitrate": None,
        "preset": None, "tune": None,
        "audio": "aac", "audio_bitrate": "160k",
        "pix_fmt": "yuv420p", "faststart": True,
    },
}

@dataclass
class Settings:
    input_file: Path; output_dir: Path
    codec: str; mode: str
    crf: Optional[int]; bitrate: Optional[str]
    preset: Optional[str]; tune: Optional[str]
    audio: str; audio_bitrate: Optional[str]
    pix_fmt: Optional[str]; faststart: bool
    show_progress: bool; dry_run: bool

def which(exe: str) -> str:
    p = shutil.which(exe)
    if not p: raise FileNotFoundError(f"{exe} が見つかりません。PATH を確認してください。")
    return p

def list_encoders(ffmpeg_exe: str) -> str:
    return subprocess.run(
        [ffmpeg_exe, "-hide_banner", "-encoders"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    ).stdout

def has_encoder(txt: str, name: str) -> bool:
    return any(name in line for line in txt.splitlines())

def ts() -> str: return datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

def out_path_for(in_path: Path, out_dir: Path, codec: str, mode: str, value: str) -> Path:
    return (out_dir / f"{in_path.stem.strip()}_{codec}_{mode}{value}_{ts()}.mp4").resolve()

def probe_duration(ffprobe: str, f: Path) -> Optional[float]:
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "format=duration", "-of", "json", str(f)],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        ).stdout
        data = json.loads(out)
        return max(0.0, float(data["format"]["duration"]))
    except Exception:
        return None

def parse_out_time_ms(line: str) -> Optional[float]:
    m = re.match(r"out_time_ms=(\d+)", line.strip())
    return (int(m.group(1))/1_000_000.0) if m else None

def resolve_settings() -> Settings:
    in_file = Path(CONFIG["INPUT_FILE"]).expanduser().resolve()
    out_dir = Path(CONFIG["OUTPUT_DIR"]).expanduser().resolve()
    preset = CONFIG.get("PRESET") or "fanbox_h264"
    if preset not in PRESETS: raise ValueError(f"未知の PRESET: {preset}")
    base = PRESETS[preset].copy()
    for k, v in (CONFIG.get("OVERRIDE") or {}).items():
        if v is not None: base[k] = v
    return Settings(
        input_file=in_file, output_dir=out_dir,
        codec=str(base["codec"]), mode=str(base["mode"]),
        crf=(int(base["crf"]) if base.get("crf") is not None else None),
        bitrate=(str(base["bitrate"]) if base.get("bitrate") else None),
        preset=(str(base["preset"]) if base.get("preset") else None),
        tune=(str(base["tune"]) if base.get("tune") else None),
        audio=str(base["audio"]), audio_bitrate=(str(base["audio_bitrate"]) if base.get("audio_bitrate") else None),
        pix_fmt=(str(base["pix_fmt"]) if base.get("pix_fmt") else None),
        faststart=bool(base.get("faststart", True)),
        show_progress=bool(CONFIG.get("SHOW_PROGRESS", True)),
        dry_run=bool(CONFIG.get("DRY_RUN", False)),
    )

def build_cmds(s: Settings, src: Path, dst: Path) -> List[Tuple[List[str], bool]]:
    base_in = ["-y", "-hide_banner", "-i", str(src)]
    common_out = []
    if s.pix_fmt: common_out += ["-pix_fmt", s.pix_fmt]
    if s.faststart: common_out += ["-movflags", "+faststart"]
    common_out += ["-map_metadata", "0"]

    cmds: List[Tuple[List[str], bool]] = []

    if s.codec in ("libx264", "libx265"):
        if s.mode == "crf":
            v = ["-c:v", s.codec, "-crf", str(s.crf if s.crf is not None else 26)]
            if s.preset: v += ["-preset", s.preset]
            if s.tune: v += ["-tune", s.tune]
            a = (["-c:a", "copy"] if s.audio=="copy" else ["-c:a", "aac", "-b:a", s.audio_bitrate or "160k"])
            cmd = ["ffmpeg", *base_in, *v, *a, *common_out,
                   "-progress", "pipe:1", "-nostats", "-loglevel", "error", str(dst)]
            cmds.append((cmd, True))  # 単発: 進捗ON
        else:
            br = s.bitrate or "3500k"; passlog = str(dst.with_suffix(""))
            # 1パス目（進捗OFF）
            v1 = ["-c:v", s.codec, "-b:v", br, "-pass", "1"]
            if s.preset: v1 += ["-preset", s.preset]
            if s.tune: v1 += ["-tune", s.tune]
            a1 = ["-an"]
            cmd1 = ["ffmpeg", *base_in, *v1, *a1, *common_out,
                    "-f", "mp4", ("NUL" if os.name=="nt" else "/dev/null"),
                    "-passlogfile", passlog, "-nostats", "-loglevel", "error"]
            cmds.append((cmd1, False))
            # 2パス目（進捗ON）
            v2 = ["-c:v", s.codec, "-b:v", br, "-pass", "2"]
            if s.preset: v2 += ["-preset", s.preset]
            if s.tune: v2 += ["-tune", s.tune]
            a2 = (["-c:a","copy"] if s.audio=="copy" else ["-c:a","aac","-b:a", s.audio_bitrate or "160k"])
            cmd2 = ["ffmpeg", *base_in, *v2, *a2, *common_out,
                    "-passlogfile", passlog,
                    "-progress", "pipe:1", "-nostats", "-loglevel", "error", str(dst)]
            cmds.append((cmd2, True))
    elif s.codec == "hevc_amf":
        v = ["-c:v", "hevc_amf"]
        if s.mode == "crf":
            qp = max(0, min(int(s.crf if s.crf is not None else 26), 51))
            v += ["-rc","cqp","-qp_i",str(qp),"-qp_p",str(qp),"-qp_b",str(qp),"-quality","balanced"]
        else:
            v += ["-rc","vbr","-b:v", s.bitrate or "3500k","-quality","balanced"]
        a = (["-c:a","copy"] if s.audio=="copy" else ["-c:a","aac","-b:a", s.audio_bitrate or "160k"])
        cmd = ["ffmpeg", *base_in, *v, *a, *common_out,
               "-progress","pipe:1","-nostats","-loglevel","error", str(dst)]
        cmds.append((cmd, True))
    else:
        raise ValueError(f"未対応 codec: {s.codec}")

    return cmds

def _drain(pipe):
    """stderr を並行で読み捨ててバッファ詰まりを防止"""
    try:
        for _ in iter(pipe.readline, ""):
            pass
    finally:
        try:
            pipe.close()
        except Exception:
            pass

def run_with_progress(cmd: List[str], total_sec: Optional[float]) -> None:
    # 逐次行読み + stderr を別スレッドで排出
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, encoding="utf-8", errors="replace"
    )
    # stderr を読み捨て
    t = threading.Thread(target=_drain, args=(proc.stderr,), daemon=True)
    t.start()

    if total_sec and tqdm is not None:
        with tqdm(total=total_sec, unit="s", desc="encoding", leave=True) as bar:
            last = 0.0
            for line in proc.stdout:  # type: ignore
                tsec = parse_out_time_ms(line)
                if tsec is not None and tsec > last:
                    inc = min(tsec - last, max(total_sec - bar.n, 0))
                    if inc > 0: bar.update(inc)
                    last = tsec
            proc.wait()
            if bar.n < (total_sec or 0):
                bar.update((total_sec or 0) - bar.n)
    else:
        # テキスト簡易表示
        last_pct = -1
        current = 0.0
        for line in proc.stdout:  # type: ignore
            tsec = parse_out_time_ms(line)
            if tsec is not None:
                current = tsec
                if total_sec:
                    pct = int(100 * min(max(current/total_sec, 0.0), 1.0))
                    if pct != last_pct:
                        print(f"\rencoding ... {pct:3d}%", end="", flush=True)
                        last_pct = pct
                else:
                    print(f"\rencoding time={current:.1f}s", end="", flush=True)
        proc.wait(); print("")

    if proc.returncode != 0:
        raise RuntimeError("ffmpeg 実行に失敗しました。")

def main():
    try:
        s = resolve_settings()
        ffmpeg_exe = which("ffmpeg"); ffprobe_exe = which("ffprobe")
        if not s.input_file.exists():
            raise FileNotFoundError(f"入力ファイルが見つかりません: {s.input_file}")
        s.output_dir.mkdir(parents=True, exist_ok=True)

        encs = list_encoders(ffmpeg_exe)
        if not has_encoder(encs, s.codec):
            raise RuntimeError(f"エンコーダ '{s.codec}' が利用できません。ffmpeg -encoders で確認してください。")

        value = str(s.crf) if s.mode=="crf" else (s.bitrate or "3500k")
        dst = out_path_for(s.input_file, s.output_dir, s.codec, s.mode, value)
        cmds = build_cmds(s, s.input_file, dst)

        total = probe_duration(ffprobe_exe, s.input_file) if s.show_progress else None

        print("=== 設定 ===")
        print(json.dumps({
            "input": str(s.input_file), "output": str(dst),
            "codec": s.codec, "mode": s.mode, "crf": s.crf, "bitrate": s.bitrate,
            "preset": s.preset, "tune": s.tune,
            "audio": s.audio, "audio_bitrate": s.audio_bitrate,
            "pix_fmt": s.pix_fmt, "faststart": s.faststart,
            "progress": bool(s.show_progress), "tqdm": bool(tqdm is not None),
            "dry_run": s.dry_run,
        }, ensure_ascii=False, indent=2))

        if s.dry_run:
            print("\n[DRY-RUN] 実行コマンド")
            for i,(c,use_prog) in enumerate(cmds,1):
                print(f" (pass {i}) [{'progress' if use_prog else 'no-progress'}]  {' '.join(c)}")
            return

        for i,(cmd,use_prog) in enumerate(cmds,1):
            print(f"\n--- エンコード実行 (pass {i}/{len(cmds)}) ---")
            if use_prog and s.show_progress:
                run_with_progress(cmd, total)
            else:
                subprocess.run(cmd, check=True)

        print(f"\n✅ 完了: {dst}")

    except Exception as e:
        print(f"❌ エラー: {e}", file=sys.stderr); sys.exit(1)

if __name__ == "__main__":
    main()
