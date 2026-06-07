import torch
import cv2
import numpy as np
from torchvision import models, transforms
from PIL import Image

# --- 설정 ---
YOLO_PATH = 'best.pt'
CLASSIFIER_PATH = 'classifier_model.pth'
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# 중요: Step 2 실행 시 출력된 순서대로 적어야 함 (보통 알파벳순)
CLASS_NAMES = ['ripe', 'semi_ripe', 'unripe'] 

def main():
    print("Loading Models...")
    yolo_model = torch.hub.load('ultralytics/yolov5', 'custom', path=YOLO_PATH, force_reload=False)
    yolo_model.conf = 0.5

    classifier = models.mobilenet_v3_small(pretrained=False)
    in_features = classifier.classifier[3].in_features
    classifier.classifier[3] = torch.nn.Linear(in_features, len(CLASS_NAMES))
    classifier.load_state_dict(torch.load(CLASSIFIER_PATH, map_location=DEVICE))
    classifier.to(DEVICE)
    classifier.eval()

    preprocess = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

    cap = cv2.VideoCapture(0) 
    if not cap.isOpened():
        print("Webcam not found!")
        return

    print("Running... Press 'q' to quit.")
    while True:
        ret, frame = cap.read()
        if not ret: break

        results = yolo_model(frame)
        detections = results.xyxy[0].cpu().numpy()

        for det in detections:
            x1, y1, x2, y2, conf, cls_idx = map(int, det[:4]) + list(det[4:])
            h, w, _ = frame.shape
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            if x2 - x1 < 10 or y2 - y1 < 10: continue

            crop_pil = Image.fromarray(cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2RGB))
            input_tensor = preprocess(crop_pil).unsqueeze(0).to(DEVICE)

            with torch.no_grad():
                outputs = classifier(input_tensor)
                probs = torch.nn.functional.softmax(outputs, dim=1)
                score, predicted_idx = torch.max(probs, 1)
                class_name = CLASS_NAMES[predicted_idx.item()]

            color = (0, 255, 0) if class_name == 'ripe' else (0, 0, 255)
            if class_name == 'semi_ripe': color = (0, 165, 255)

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{class_name} {score.item()*100:.1f}%", (x1, y1-10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        cv2.imshow('Robot Vision', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()