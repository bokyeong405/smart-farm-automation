"""
classify_tomatoes_predictive.py
================================
원본 `../../src/classify_tomatoes.py` (정지 방식) 기반 개선판.

[문제] 원본은 ripe 감지 시 컨베이어 벨트를 '정지'시키고 픽 → 재가동.
       구동영상 측정 결과 객체당 벨트가 ~4초 멈춤(픽 ~3s + 재가동 대기 ~1s).
[개선] 벨트를 멈추지 않고, 토마토의 '속도 벡터'를 추정해 로봇 도달 시점의
       '예측 위치'로 픽한다(무정지 예측 포착, moving pick).
       - 연속 detection 으로 픽셀 속도 추정 v=(Δu,Δv)/Δt
       - affine 의 선형부(2x2)로 로봇 속도(mm/s) 변환
       - 예측위치 = affine(현재) + 로봇속도 × T_LEAD (도달 소요시간 + 통신지연)
       - 벨트 일정 속도(원본 tomato_control 의 스테퍼 1250스텝/s 고정)라 선형 예측이 잘 맞음

흡착식 그리퍼: gripper "close" True/False = 흡입 ON/OFF (여닫기 아님 → 접촉 즉시).

⚠️ 범위: ROS2/Dobot/카메라 없이는 실행 불가. 예측 '로직' 구현이며, 수치 검증은 sim_test.py.
원본 대비 추가/변경부는 [PREDICTIVE] 주석으로 표시.
"""
import os
import sys
import time                       # [PREDICTIVE] 타임스탬프
from collections import deque     # [PREDICTIVE] 추적 버퍼
import rclpy
import numpy as np
import cv2
import socket
from rclpy.action import ActionClient
from rclpy.node import Node
from action_msgs.msg import GoalStatus
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from std_msgs.msg import String

from dobot_msgs.action import PointToPoint
from dobot_msgs.srv import GripperControl
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

# -----------------------------------------------------
# [설정] Windows PC (.env)
# -----------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass
PC_IP = os.environ.get("PC_IP", "127.0.0.1")
PC_PORT = 9999
TOPIC_NAME = '/tomato_results'

# -----------------------------------------------------
# [PREDICTIVE 설정] 예측 파라미터 (구동영상 측정 기반, 조정 가능)
# -----------------------------------------------------
T_APPROACH = 2.0     # 결정→그리퍼 접촉까지 로봇 도달 소요(초). 영상 측정 근사
T_COMM = 0.3         # 통신/처리 지연(초)
T_LEAD = T_APPROACH + T_COMM   # 총 예측 선행시간
MIN_DT = 0.03        # 속도 추정 최소 Δt(초) — 노이즈 방지
MATCH_RADIUS_PX = 80 # 같은 토마토로 볼 최대 픽셀 거리(추적 매칭)


class PredictivePickAndPlace(Node):
    def __init__(self):
        super().__init__('pick_and_place_predictive')

        self._action_client = ActionClient(self, PointToPoint, 'PTP_action', callback_group=ReentrantCallbackGroup())
        self.cli = self.create_client(srv_type=GripperControl, srv_name='dobot_gripper_service', callback_group=ReentrantCallbackGroup())

        self.get_logger().info("⏳ 서비스 연결 대기 중...")
        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('...서비스 대기 중...')
        self.req = GripperControl.Request()
        self.get_logger().info("✅ 서비스 연결 완료!")

        qos_profile = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                                 history=HistoryPolicy.KEEP_LAST, depth=10)
        self.subscription = self.create_subscription(
            String, TOPIC_NAME, self.detection_callback, qos_profile,
            callback_group=ReentrantCallbackGroup())

        # --- 좌표 변환 행렬 (원본 캘리브레이션 값 유지) ---
        pts_camera = np.float32([[375, 244], [277, 228], [487, 240]])
        pts_robot = np.float32([[204.755, -45.942], [196.154, -92.942], [198.284, -7.829]])
        self.transform_matrix = cv2.getAffineTransform(pts_camera, pts_robot)
        self.M_lin = self.transform_matrix[:, :2]   # [PREDICTIVE] 선형부(2x2) — 속도 변환용

        self.tasks_list = []
        self.goal_num = 0
        self.is_running = False
        self.track = deque(maxlen=6)   # [PREDICTIVE] (t, u, v) 최근 ripe 위치 이력

        self.HOME_POS = [150.0, 0.0, 100.0, 0.0]
        self.move_to_home()
        self.get_logger().info("✅ 초기화 완료(예측 모드). 토마토 대기 중...")

    def move_to_home(self):
        self.tasks_list = [["move", self.HOME_POS, 1, "초기 위치 복귀"]]
        self.goal_num = 0
        self.execute()

    # -----------------------------------------------------
    # [PREDICTIVE] 검출 콜백: 항상 추적 갱신 → 속도 추정 → 예측 픽
    # -----------------------------------------------------
    def detection_callback(self, msg):
        raw_data = msg.data
        if not raw_data:
            return

        # 1) ripe 타겟 위치 파싱
        target = None
        for obj_str in raw_data.split(' | '):
            parts = obj_str.split(',')
            if len(parts) < 3:
                continue
            try:
                if 'ripe' in parts[0].strip().lower():
                    target = (float(parts[1]), float(parts[2]))
                    break
            except ValueError:
                continue
        if target is None:
            return

        now = time.time()
        u, v = target

        # 2) 추적 버퍼 갱신 (같은 토마토면 이어붙임 — is_running 중에도 계속 추적)
        if self.track:
            lu, lv = self.track[-1][1], self.track[-1][2]
            if (u - lu) ** 2 + (v - lv) ** 2 > MATCH_RADIUS_PX ** 2:
                self.track.clear()   # 다른 토마토 → 추적 리셋
        self.track.append((now, u, v))

        # 3) 이미 작업 중이면 추적만 하고 새 픽은 시작 안 함
        if self.is_running:
            return

        # 4) 속도 추정 후 예측 픽 시작
        vel = self.estimate_pixel_velocity()
        self.get_logger().info(f"\n🍅 [타겟] ({u:.0f},{v:.0f}) px_vel={vel}")
        self.start_pick_and_place(u, v, vel)

    # [PREDICTIVE] 최근 이력으로 픽셀 속도(px/s) 추정 (없으면 0)
    def estimate_pixel_velocity(self):
        if len(self.track) < 2:
            return np.array([0.0, 0.0])
        t0, u0, v0 = self.track[0]
        t1, u1, v1 = self.track[-1]
        dt = t1 - t0
        if dt < MIN_DT:
            return np.array([0.0, 0.0])
        return np.array([(u1 - u0) / dt, (v1 - v0) / dt])

    def start_pick_and_place(self, u, v, px_vel):
        self.is_running = True

        # 현재 위치 → 로봇 좌표
        cur = cv2.transform(np.array([[[u, v]]], dtype=np.float32), self.transform_matrix)
        cur_x, cur_y = float(cur[0][0][0]), float(cur[0][0][1])

        # [PREDICTIVE] 픽셀 속도 → 로봇 속도(mm/s) = 선형부 @ px_vel
        robot_vel = self.M_lin @ px_vel            # [vx, vy] mm/s
        # 예측 위치 = 현재 + 로봇속도 × 선행시간 (벨트 무정지)
        target_x = cur_x + robot_vel[0] * T_LEAD
        target_y = cur_y + robot_vel[1] * T_LEAD
        PICK_Z = 10.0

        self.get_logger().info(
            f"📍 현재({cur_x:.1f},{cur_y:.1f}) → 예측({target_x:.1f},{target_y:.1f}) "
            f"robot_vel=({robot_vel[0]:.1f},{robot_vel[1]:.1f})mm/s lead={T_LEAD}s")

        # 작업 리스트 (원본과 동일 흐름, 좌표만 '예측 위치'로)
        self.tasks_list = [
            ["move", [target_x, target_y, 50.0, 0.0], 1, "상공 이동(예측)"],
            ["move", [target_x, target_y, PICK_Z, 0.0], 1, "집기 하강(예측)"],
            ["gripper", "close", True, "흡입 ON"],
            ["move", [target_x, target_y, 75.0, 0.0], 1, "상승"],
            ["move", [55.0, -150.0, 75.0, 0.0], 1, "Drop 이동"],
            ["move", [5.0, -150.0, 10.0, 0.0], 1, "Drop 하강"],
            ["gripper", "close", False, "흡입 OFF"],
            ["move", [55.0, -150.0, 75.0, 0.0], 1, "재상승"],
            ["move", [150.0, 0.0, 100.0, 0.0], 1, "Home 복귀"],
        ]
        self.goal_num = 0
        self.execute()
        # NOTE(향후): 더 높은 정확도는 하강 중 재예측(시각 서보잉)으로 가능.

    # ---- 이하 실행/통신부는 원본과 동일 ----
    def execute(self):
        if self.goal_num > len(self.tasks_list) - 1:
            self.get_logger().info('\n✨ [작업 완료] PC로 신호 전송...')
            self.send_signal_to_pc()
            self.is_running = False
            self.tasks_list = []
            self.track.clear()   # [PREDICTIVE] 픽 끝나면 추적 리셋
            return

        task = self.tasks_list[self.goal_num]
        self.get_logger().info(f"👉 [{self.goal_num + 1}/{len(self.tasks_list)}] {task[-1]}")
        if task[0] == "gripper":
            self.send_request(task[1], task[2])
            self.timer = self.create_timer(1.5, self.timer_callback, callback_group=ReentrantCallbackGroup())
            self.goal_num += 1
        elif task[0] == "move":
            self.send_goal(task[1], task[2])
            self.goal_num += 1

    def send_signal_to_pc(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((PC_IP, PC_PORT))
            s.sendall("DONE".encode())
            s.close()
            self.get_logger().info(f"🚀 [전송 성공] {PC_IP}")
        except Exception as e:
            self.get_logger().warn(f"⚠️ [전송 실패] {e}")

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
        if future.result().status == GoalStatus.STATUS_SUCCEEDED:
            self.execute()
        else:
            self.get_logger().error('❌ 이동 실패!')
            self.is_running = False


def main(args=None):
    rclpy.init(args=args)
    node = PredictivePickAndPlace()
    executor = MultiThreadedExecutor()
    try:
        rclpy.spin(node, executor=executor)
    except KeyboardInterrupt:
        node.get_logger().info('종료합니다.')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
