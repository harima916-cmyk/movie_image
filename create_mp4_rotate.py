import os
import ffmpeg
from datetime import datetime

def create_lossless_mp4(input_dir, output_file, fps=60, start_number=0, rotate=1):
    input_dir = input_dir.replace("\\", "/")
    input_pattern = f"{input_dir}/%d.png"

    print("🟢 無劣化MP4を作成中（crf=0, 回転付き）...")
    (
        ffmpeg
        .input(input_pattern, framerate=fps, start_number=start_number)
        .filter("transpose", rotate)  # 回転はここだけ適用
        .output(
            output_file,
            vcodec='libx264',
            crf=0,
            preset='veryslow',
            pix_fmt='yuv420p',
            movflags='faststart'
        )
        .run(overwrite_output=True)
    )
    print(f"✅ 無劣化MP4作成完了: {output_file}")


def compress_mp4(input_file, output_dir, crf=18, preset="slow"):
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    output_file = os.path.join(output_dir, f"{timestamp}.mp4")

    print(f"🟠 圧縮版MP4を作成中（{output_file}）...")
    (
        ffmpeg
        .input(input_file)
        .output(
            output_file,
            vcodec='libx264',
            crf=crf,
            preset=preset,
            pix_fmt='yuv420p',
            movflags='faststart'
        )
        .run(overwrite_output=True)
    )
    print(f"✅ 圧縮MP4作成完了: {output_file}")


if __name__ == "__main__":
    input_dir = r"D:\koikatsu\frame\test\2025-10-02T19-50-52"
    output_dir = "."
    lossless_output = "output_crf0.mp4"
    fps = 60
    start_number = 0

    # === 回転指定 ===
    # 1: 90°時計回り, 2: 90°反時計回り, 0: 上下反転＋90°CW, 3: 上下反転＋90°CCW
    rotate = 1  

    # 無劣化版は回転あり
    create_lossless_mp4(input_dir, lossless_output, fps, start_number, rotate)

    # 圧縮版は回転なし（そのまま）
    compress_mp4(lossless_output, output_dir, crf=18, preset="slow")
