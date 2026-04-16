import os
import cv2
from concurrent.futures import ProcessPoolExecutor
from functools import partial

def extract_number(filename):
    return int(os.path.splitext(filename)[0])

def resize_and_save_opencv(input_dir, output_dir, target_size, filename):
    input_path = os.path.join(input_dir, filename)
    output_path = os.path.join(output_dir, filename)

    try:
        img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            return f"❌ 読み込み失敗: {filename}"

        resized = cv2.resize(img, target_size, interpolation=cv2.INTER_AREA)
        cv2.imwrite(output_path, resized)

        return f"✅ {filename} → {target_size[0]}x{target_size[1]}"
    except Exception as e:
        return f"❌ エラー: {filename} - {str(e)}"

def resize_images_opencv_parallel(input_dir, output_dir, width, height, max_workers=8):
    input_dir = input_dir.replace("\\", "/")
    output_dir = output_dir.replace("\\", "/")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    png_files = [f for f in os.listdir(input_dir) if f.lower().endswith(".png")]
    png_files.sort(key=extract_number)
    target_size = (width, height)

    print(f"🔄 OpenCV 並列リサイズ開始（{max_workers}並列）")

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        resize_fn = partial(resize_and_save_opencv, input_dir, output_dir, target_size)
        for result in executor.map(resize_fn, png_files):
            print(result)


if __name__ == "__main__":
    # === 設定 ===
    input_folder = r"C:\illusion\Koikatu\UserData\VideoExport\Frames\2025-06-15T00-56-19"
    output_folder = r"C:\illusion\Koikatu\UserData\VideoExport\Frames\comp"
    width = 1920
    height = 1080
    max_workers = 8

    resize_images_opencv_parallel(input_folder, output_folder, width, height, max_workers)

