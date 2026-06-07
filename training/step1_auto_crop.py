import torch
import cv2
import os
from pathlib import Path

# --- 설정 (경로 수정됨) ---
YOLO_WEIGHTS = 'best.pt'      
# Roboflow 데이터셋이 풀려있는 절대 경로 (앞에 r을 붙여야 윈도우 경로 인식)
DATASET_ROOT = r'C:\Users\SSAFY\yolov5\tomato_robot\dataset'
SAVE_DIR = 'cropped_dataset/unsorted' 
CONF_THRES = 0.5              

# 저장 폴더 생성
os.makedirs(SAVE_DIR, exist_ok=True)

def auto_crop():
    print(f"Loading YOLOv5 model from {YOLO_WEIGHTS}...")
    # 로컬 경로 문제 방지를 위해 ultralytics 허브 사용
    model = torch.hub.load('ultralytics/yolov5', 'custom', path=YOLO_WEIGHTS, force_reload=False)
    model.conf = CONF_THRES

    print(f"Searching images in: {DATASET_ROOT}")
    
    # rglob를 사용하여 하위 폴더(train, valid, test)의 모든 jpg, png 검색
    image_paths = list(Path(DATASET_ROOT).rglob('*.[jJ][pP][gG]')) + \
                  list(Path(DATASET_ROOT).rglob('*.[pP][nN][gG]'))
    
    print(f"Found {len(image_paths)} images total.")

    count = 0
    for img_path in image_paths:
        # 한글 경로 등이 섞여있을 때 cv2.imread가 실패할 수 있으므로 numpy로 읽기
        img_array = np.fromfile(str(img_path), np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if img is None: continue

        # YOLO 추론
        results = model(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        detections = results.xyxy[0].cpu().numpy()

        for det in detections:
            x1, y1, x2, y2, conf, cls = list(map(int, det[:4])) + list(det[4:])
            h, w, _ = img.shape
            
            # 좌표 보정
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            # 너무 작은 박스 제외
            if (x2 - x1) < 10 or (y2 - y1) < 10: continue

            crop_img = img[y1:y2, x1:x2]
            
            # 파일명 저장 (원본파일 이름 일부를 포함하여 추적 용이하게 함)
            original_stem = img_path.stem 
            save_name = f"{count:05d}_{original_stem}.jpg"
            
            # 저장 (경로 문제 방지를 위해 cv2.imencode 사용 권장)
            result, encoded_img = cv2.imencode('.jpg', crop_img)
            if result:
                with open(os.path.join(SAVE_DIR, save_name), mode='w+b') as f:
                    encoded_img.tofile(f)
            
            count += 1

    print(f"Done! {count} tomatoes cropped to '{SAVE_DIR}'.")
    print("★ 중요: 'cropped_dataset/unsorted' 폴더의 이미지를 확인하고")
    print("   'ripe', 'semi_ripe', 'unripe' 폴더로 분류해서 넣어주세요!")

import numpy as np # numpy import 추가
if __name__ == "__main__":
    auto_crop()