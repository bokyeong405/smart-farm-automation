import rclpy
from rclpy.node import Node

import cv2
import numpy as np
import os
import sys
import warnings
import pathlib
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image

import pyrealsense2 as rs
from std_msgs.msg import String
from sensor_msgs.msg import Image as RosImage
from cv_bridge import CvBridge

# ---------------------------------------------------------
# [설정] 경로 및 경고 제어
# ---------------------------------------------------------
temp = pathlib.PosixPath
pathlib.WindowsPath = pathlib.PosixPath
warnings.filterwarnings("ignore", category=FutureWarning)

class TomatoHarvestNode(Node):
    def __init__(self):
        super().__init__('tomato_harvest_node')

        # =========================================================
        # 1. 파일 경로 설정
        # =========================================================
        self.yolo_repo = '/home/ssafy/yolov5' 
        self.yolo_weights = '/home/ssafy/yolov5/runs/train/panel_detection/weights/best.pt'
        self.classifier_weights = '/home/ssafy/tomato_robot/classifier_model.pth'
        self.class_names = ['ripe', 'semi_ripe', 'unripe']

        # =========================================================
        # 2. AI 모델 로드
        # =========================================================
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.get_logger().info(f"Using Device: {self.device}")

        # [A] YOLOv5
        self.get_logger().info(f"Loading YOLOv5 from: {self.yolo_weights}")
        try:
            self.yolo_model = torch.hub.load(self.yolo_repo, 'custom', path=self.yolo_weights, source='local')
            self.yolo_model.conf = 0.4
            self.get_logger().info("✅ YOLOv5 Model loaded successfully!")
        except Exception as e:
            self.get_logger().error(f"❌ Failed to load YOLO: {e}")
            sys.exit()

        # [B] MobileNetV3
        self.get_logger().info(f"Loading Classifier from: {self.classifier_weights}")
        try:
            self.classifier = models.mobilenet_v3_small(pretrained=False)
            in_features = self.classifier.classifier[3].in_features
            self.classifier.classifier[3] = nn.Linear(in_features, len(self.class_names))
            self.classifier.load_state_dict(torch.load(self.classifier_weights, map_location=self.device))
            self.classifier.to(self.device)
            self.classifier.eval()
            
            self.preprocess = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
            ])
            self.get_logger().info("✅ MobileNet Classifier loaded successfully!")
        except Exception as e:
            self.get_logger().error(f"❌ Failed to load Classifier: {e}")
            sys.exit()

        # =========================================================
        # 3. RealSense 및 ROS 설정
        # =========================================================
        self.pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
        
        try:
            self.pipeline.start(config)
            self.get_logger().info("📷 RealSense Stream Started")
        except Exception as e:
            self.get_logger().error(f"Camera Error: {e}")
            sys.exit()

        self.detection_publisher = self.create_publisher(String, 'tomato_results', 10)
        self.image_publisher = self.create_publisher(RosImage, 'tomato_image', 10)
        self.bridge = CvBridge()
        self.timer = self.create_timer(0.1, self.timer_callback)

    def timer_callback(self):
        frames = self.pipeline.wait_for_frames()
        color_frame = frames.get_color_frame()
        if not color_frame:
            return
        
        color_image = np.asanyarray(color_frame.get_data())

        # YOLO 추론
        results = self.yolo_model(cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB))
        detection_info_list = []

        for det in results.xyxy[0]:
            x1, y1, x2, y2 = map(int, det[:4])
            
            h, w, _ = color_image.shape
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            if x2 - x1 < 10 or y2 - y1 < 10:
                continue

            # 분류
            roi = color_image[y1:y2, x1:x2]
            roi_pil = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
            input_tensor = self.preprocess(roi_pil).unsqueeze(0).to(self.device)

            with torch.no_grad():
                outputs = self.classifier(input_tensor)
                probs = torch.nn.functional.softmax(outputs, dim=1)
                score, predicted_idx = torch.max(probs, 1)
                
                class_name = self.class_names[predicted_idx.item()]
                confidence = score.item() * 100

            # 색상 설정
            if class_name == 'ripe':
                box_color = (0, 255, 0)
                status_text = f"Harvest ({confidence:.1f}%)"
            elif class_name == 'semi_ripe':
                box_color = (0, 165, 255)
                status_text = f"Wait ({confidence:.1f}%)"
            else:
                box_color = (0, 0, 255)
                status_text = f"Unripe ({confidence:.1f}%)"

            # 중심 좌표
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2

            detection_info_list.append(f"{class_name},{center_x},{center_y},{confidence:.1f}")

            # -----------------------------------------------------
            # [시각화 수정] 박스, 중심점, 텍스트 그리기
            # -----------------------------------------------------
            # 1. 박스 그리기
            cv2.rectangle(color_image, (x1, y1), (x2, y2), box_color, 2)
            
            # 2. 중심점 찍기
            cv2.circle(color_image, (center_x, center_y), 5, box_color, -1)
            
            # 3. 박스 위: 상태 텍스트 (예: Harvest 99.0%)
            cv2.putText(color_image, status_text, (x1, y1 - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2)
            
            # 4. [추가됨] 박스 아래: 좌표 텍스트 (예: (320, 240))
            coord_text = f"({center_x}, {center_y})"
            cv2.putText(color_image, coord_text, (x1, y2 + 25), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2)
            # -----------------------------------------------------

        if detection_info_list:
            msg = String()
            msg.data = " | ".join(detection_info_list)
            self.detection_publisher.publish(msg)
            self.get_logger().info(f"Detected: {msg.data}")

        ros_image = self.bridge.cv2_to_imgmsg(color_image, encoding='bgr8')
        ros_image.header.stamp = self.get_clock().now().to_msg()
        ros_image.header.frame_id = "camera_link"
        self.image_publisher.publish(ros_image)

        cv2.imshow("Tomato Robot Vision", color_image)
        cv2.waitKey(1)

    def destroy_node(self):
        self.pipeline.stop()
        super().destroy_node()
        cv2.destroyAllWindows()

def main(args=None):
    rclpy.init(args=args)
    node = TomatoHarvestNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()