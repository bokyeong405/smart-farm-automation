import os
import sys
import rclpy
import numpy as np
import cv2
import socket  # [추가] 통신용
from rclpy.action import ActionClient
from rclpy.node import Node
from action_msgs.msg import GoalStatus
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from std_msgs.msg import String # [반영] TOPIC_TYPE

from dobot_msgs.action import PointToPoint
from dobot_msgs.srv import GripperControl
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

# -----------------------------------------------------
# [설정] Windows PC 정보 (.env 에서 로드)
# -----------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass
PC_IP = os.environ.get("PC_IP", "127.0.0.1") # [반영] PC_IP
PC_PORT = 9999
TOPIC_NAME = '/tomato_results' # [반영] TOPIC_NAME

class PickAndPlace(Node):
    def __init__(self):
        super().__init__('pick_and_place_demo')

        # --- ROS2 통신 설정 ---
        self._action_client = ActionClient(self, PointToPoint, 'PTP_action', callback_group=ReentrantCallbackGroup())
        self.cli = self.create_client(srv_type=GripperControl, srv_name='dobot_gripper_service', callback_group=ReentrantCallbackGroup())
        
        self.get_logger().info("⏳ 서비스 연결 대기 중...")
        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('...서비스 대기 중...')
        self.req = GripperControl.Request()
        self.get_logger().info("✅ 서비스 연결 완료!")

        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

        # [반영] 토픽 이름 설정
        self.subscription = self.create_subscription(
            String,
            TOPIC_NAME, 
            self.detection_callback,
            qos_profile,
            callback_group=ReentrantCallbackGroup()
        )

        # --- 좌표 변환 행렬 설정 ---
        # (기존 값 유지)
        pts_camera = np.float32([[375, 244], [277, 228], [487, 240]])
        pts_robot = np.float32([[204.755, -45.942], [196.154, -92.942], [198.284, -7.829]])
        self.transform_matrix = cv2.getAffineTransform(pts_camera, pts_robot)
        
        self.get_logger().info("✅ 초기화 완료. 토마토 대기 중...")
        
        self.tasks_list = []
        self.goal_num = 0
        self.is_running = False 

        self.HOME_POS = [150.0, 0.0, 100.0, 0.0]
        self.move_to_home()

    def move_to_home(self):
        self.tasks_list = [["move", self.HOME_POS, 1, "초기 위치 복귀"]]
        self.goal_num = 0
        self.execute()

    def detection_callback(self, msg):
        if self.is_running:
            return

        raw_data = msg.data
        if not raw_data:
            return

        objects = raw_data.split(' | ')
        target_found = False
        cam_u, cam_v = 0.0, 0.0

        for obj_str in objects:
            try:
                parts = obj_str.split(',')
                if len(parts) < 3: continue

                label = parts[0].strip()
                cx = float(parts[1])
                cy = float(parts[2])
                
                if 'ripe' in label.lower():
                    cam_u, cam_v = cx, cy
                    target_found = True
                    self.get_logger().info(f"\n🍅 [타겟 발견] {label} at ({cx}, {cy})")
                    break 

            except ValueError:
                continue

        if target_found:
            self.start_pick_and_place(cam_u, cam_v)

    def start_pick_and_place(self, u, v):
        self.is_running = True

        # 좌표 변환
        point = np.array([[[u, v]]], dtype=np.float32)
        transformed = cv2.transform(point, self.transform_matrix)
        target_x = float(transformed[0][0][0])
        target_y = float(transformed[0][0][1])
        PICK_Z = 10.0 

        self.get_logger().info(f"📍 작업 시작: X={target_x:.1f}, Y={target_y:.1f}")

        # [작업 리스트]
        self.tasks_list = [
            ["move", [target_x, target_y, 50.0, 0.0], 1, "상공 이동"],
            ["move", [target_x, target_y, PICK_Z, 0.0], 1, "집기 하강"],
            ["gripper", "close", True, "흡입 ON"],
            ["move", [target_x, target_y, 75.0, 0.0], 1, "상승"],
            ["move", [55.0, -150.0, 75.0, 0.0], 1, "Drop 이동"],
            ["move", [5.0, -150.0, 10.0, 0.0], 1, "Drop 하강"],
            ["gripper", "close", False, "흡입 OFF"],
            ["move", [55.0, -150.0, 75.0, 0.0], 1, "재상승"],
            ["move", [150.0, 0.0, 100.0, 0.0], 1, "Home 복귀"]
        ]
        self.goal_num = 0
        self.execute()

    def execute(self):
        # [핵심 변경] 모든 작업이 끝났을 때
        if self.goal_num > len(self.tasks_list) - 1:
            self.get_logger().info('\n✨ [작업 완료] PC로 신호 전송 시도...')
            
            # --- Windows PC로 신호 전송 ---
            self.send_signal_to_pc()
            # ------------------------------

            self.is_running = False 
            self.tasks_list = []
            return

        task = self.tasks_list[self.goal_num]
        task_type = task[0]
        step_desc = task[-1]
        
        self.get_logger().info(f"👉 [{self.goal_num + 1}/{len(self.tasks_list)}] {step_desc}")

        if task_type == "gripper":
            self.send_request(task[1], task[2])
            self.timer = self.create_timer(1.5, self.timer_callback, callback_group=ReentrantCallbackGroup())
            self.goal_num += 1
            
        elif task_type == "move":
            self.send_goal(task[1], task[2])
            self.goal_num += 1

    # [추가됨] PC로 완료 신호 보내는 함수
    def send_signal_to_pc(self):
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(2.0) # 2초 안에 연결 안되면 패스
            client_socket.connect((PC_IP, PC_PORT))
            client_socket.sendall("DONE".encode())
            client_socket.close()
            self.get_logger().info(f"🚀 [전송 성공] {PC_IP}에게 'DONE' 보냄")
        except Exception as e:
            self.get_logger().warn(f"⚠️ [전송 실패] PC가 켜져 있나요? 에러: {e}")

    def timer_callback(self):
        self.timer.cancel()
        self.execute()

    def send_request(self, gripper_state, keep_compressor_running):
        self.req.gripper_state = gripper_state
        self.req.keep_compressor_running = keep_compressor_running
        self.cli.call_async(self.req)

    def send_goal(self, _target, _type):
        goal_msg = PointToPoint.Goal()
        goal_msg.target_pose = _target
        goal_msg.motion_type = _type

        if not self._action_client.wait_for_server(timeout_sec=2.0):
            self.get_logger().error('❌ Action server 응답 없음')
            self.is_running = False 
            return

        self._send_goal_future = self._action_client.send_goal_async(goal_msg)
        self._send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn('⚠️ 이동 거부됨')
            self.is_running = False
            return
        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        status = future.result().status
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.execute()
        else:
            self.get_logger().error(f'❌ 이동 실패! Status: {status}')
            self.is_running = False
    
def main(args=None):
    rclpy.init(args=args)
    pick_and_place = PickAndPlace()
    executor = MultiThreadedExecutor()
    try:
        rclpy.spin(pick_and_place, executor=executor)
    except KeyboardInterrupt:
        pick_and_place.get_logger().info('종료합니다.')
    finally:
        pick_and_place.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()