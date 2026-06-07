import torch
import cv2
import numpy as np
import os
from torchvision import models, transforms
from PIL import Image
from glob import glob
import sys

# ---------------------------------------------------------
# [설정] 윈도우 환경에 맞춘 경로 설정
# ---------------------------------------------------------
# 1. YOLOv5 레포지토리 (폴더) 위치
# (tomato_robot 폴더 바로 상위에 yolov5가 있다고 가정)
YOLO_REPO = r'C:\Users\SSAFY\yolov5' 

# 2. 모델 파일 경로 (현재 폴더에 있다고 가정)
YOLO_WEIGHTS = 'best.pt'
CLASSIFIER_WEIGHTS = 'classifier_model.pth'

# 3. 테스트할 이미지가 있는 폴더
# (dataset 폴더가 현재 위치에 있어야 함)
INPUT_IMAGE_DIR = r'dataset\test\images' 

# 4. 결과 저장 폴더
OUTPUT_DIR = 'output_results'

CLASS_NAMES = ['ripe', 'semi_ripe', 'unripe']
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def validate():
    # 저장 폴더 생성
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"결과가 저장될 폴더: {os.path.abspath(OUTPUT_DIR)}")

    # --- 1. 모델 로드 ---
    print("모델을 불러오는 중입니다...")
    try:
        # 로컬 YOLOv5 폴더를 사용하여 로드
        yolo_model = torch.hub.load(YOLO_REPO, 'custom', path=YOLO_WEIGHTS, source='local')
        yolo_model.conf = 0.4
    except Exception as e:
        print(f"YOLO 로드 실패! 경로를 확인하세요: {e}")
        return

    # MobileNet 로드
    classifier = models.mobilenet_v3_small(pretrained=False)
    in_features = classifier.classifier[3].in_features
    classifier.classifier[3] = torch.nn.Linear(in_features, len(CLASS_NAMES))
    
    if os.path.exists(CLASSIFIER_WEIGHTS):
        classifier.load_state_dict(torch.load(CLASSIFIER_WEIGHTS, map_location=DEVICE))
    else:
        print(f"오류: {CLASSIFIER_WEIGHTS} 파일이 없습니다!")
        return
        
    classifier.to(DEVICE)
    classifier.eval()

    preprocess = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

    # --- 2. 이미지 불러오기 ---
    # jpg, png 등 찾기
    image_paths = glob(os.path.join(INPUT_IMAGE_DIR, '*.*'))
    # 이미지만 필터링
    image_paths = [p for p in image_paths if p.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    if len(image_paths) == 0:
        print(f"오류: {INPUT_IMAGE_DIR} 폴더에 이미지가 없습니다.")
        return

    print(f"총 {len(image_paths)}장의 이미지를 발견했습니다.")

    # --- 3. 추론 및 시각화 ---
    for i, img_path in enumerate(image_paths):
        # 한글 경로 에러 방지용 읽기
        img_array = np.fromfile(img_path, np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if frame is None: continue

        # YOLO 추론
        results = yolo_model(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        
        # 그리기용 복사본
        draw_frame = frame.copy()
        
        detections = results.xyxy[0].cpu().numpy()
        for det in detections:
            x1, y1, x2, y2 = map(int, det[:4])
            
            # 좌표 보정
            h, w, _ = frame.shape
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            if x2 - x1 < 10 or y2 - y1 < 10: continue

            # MobileNet 분류
            roi = frame[y1:y2, x1:x2]
            roi_pil = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
            input_tensor = preprocess(roi_pil).unsqueeze(0).to(DEVICE)

            with torch.no_grad():
                outputs = classifier(input_tensor)
                probs = torch.nn.functional.softmax(outputs, dim=1)
                score, predicted_idx = torch.max(probs, 1)
                class_name = CLASS_NAMES[predicted_idx.item()]
                conf = score.item() * 100

            # 색상 설정
            if class_name == 'ripe':
                color = (0, 255, 0)     # 초록
            elif class_name == 'semi_ripe':
                color = (0, 165, 255)   # 주황
            else:
                color = (0, 0, 255)     # 빨강
            
            # 박스 그리기
            cv2.rectangle(draw_frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(draw_frame, f"{class_name} {conf:.0f}%", (x1, y1-5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # 결과 저장
        file_name = os.path.basename(img_path)
        save_path = os.path.join(OUTPUT_DIR, "result_" + file_name)
        
        # 한글 경로 에러 방지용 저장
        extension = os.path.splitext(file_name)[1]
        result, encoded_img = cv2.imencode(extension, draw_frame)
        if result:
            with open(save_path, mode='w+b') as f:
                encoded_img.tofile(f)
        
        if (i+1) % 5 == 0:
            print(f"진행 중... ({i+1}/{len(image_paths)})")

    print("완료! 'output_results' 폴더를 확인해보세요.")

if __name__ == "__main__":
    validate()