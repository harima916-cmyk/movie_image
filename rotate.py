from moviepy.editor import VideoFileClip
# 入力と出力ファイルの指定
input_path = r"F:\movie\未投稿\2025-10-04T12-10-24.mp4"  # 回転させたい動画ファイル
output_path =r"F:\movie\2025-10-04T12-10-24.mp4"   # 出力ファイル名

# 動画を読み込み
clip = VideoFileClip(input_path)

# 90度時計回りに回転
rotated_clip = clip.rotate(-90)  # 時計回りは -90, 反時計回りは +90

# 出力（音声付き）
rotated_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")