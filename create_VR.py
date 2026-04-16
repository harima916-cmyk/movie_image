import os
import ffmpeg

def encode_360_from_sequence(input_dir, output_file, fps=60, start_number=0, crf=18, preset="veryslow"):
    input_dir = input_dir.replace("\\", "/")
    pattern = "%d.png"  # ← ゼロ埋め無し
    input_pattern = f"{input_dir}/{pattern}"

    (
        ffmpeg
        .input(input_pattern, framerate=fps, start_number=start_number, format='image2', vcodec='png')
        .filter('format', 'rgb24')
        .output(
            output_file,
            vcodec='libx264',
            crf=crf,
            preset=preset,
            pix_fmt='yuv420p',
            r=fps,
            g=fps*2,
            bf=2,
            profile='high',
            level='5.2',
            movflags='faststart'
        )
        .overwrite_output()
        .run()
    )

if __name__ == "__main__":
    input_dir = r"F:\movie\frame\2025-10-22T23-19-26"  # フォルダパス
    output_file = r"F:\movie\output_360_deliverable.mp4"
    encode_360_from_sequence(input_dir, output_file, fps=60)
    print("✅ 配布用MP4の作成完了:", output_file)