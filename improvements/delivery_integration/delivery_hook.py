"""
delivery_hook.py — 적재 완료 → AMR(TurtleBot) 자율주행 출발 '연결 훅'

[배경] 원본 파이프라인은 검출→픽→적재(+TTS)까지만 동작하고, 그 뒤 AMR 이송 출발이
       파이프라인에 '연결'되어 있지 않았다(미통합). 이 훅이 그 끊긴 고리를 잇는다.

[방식] 적재 완료 이벤트가 오면 nav2 표준 목표 토픽 `/goal_pose` 로 배달 지점 PoseStamped
       를 발행 → TurtleBot이 SLAM 맵 상에서 자율주행으로 배달지로 이동.

⚠️ 범위: ROS2/turtlebot 없이는 실행 불가(=실 구동 미수행). 이 파일은 '연결 로직' 구현이며,
   전체 흐름 검증은 sim_delivery.py. turtlebot 내비는 표준 nav2 가정(커스텀 SLAM 코드는 유실).
   DELIVERY_POSE 는 실제 맵 좌표를 모르므로 placeholder(TODO).
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped

# 배달 지점 (SLAM 맵 좌표) — `TODO: 실제 맵 좌표 측정값으로 교체`
DELIVERY_POSE = {"x": 1.5, "y": 0.0, "yaw": 0.0, "frame": "map"}


class DeliveryDispatcher(Node):
    def __init__(self):
        super().__init__("delivery_dispatcher")
        self.pub = self.create_publisher(PoseStamped, "/goal_pose", 10)

    def dispatch(self, pose=DELIVERY_POSE):
        """적재 완료 시 호출 → AMR 배달 출발 목표 발행."""
        msg = PoseStamped()
        msg.header.frame_id = pose["frame"]
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.position.x = float(pose["x"])
        msg.pose.position.y = float(pose["y"])
        # yaw → quaternion (z,w) 평면 회전
        import math
        msg.pose.orientation.z = math.sin(pose["yaw"] / 2.0)
        msg.pose.orientation.w = math.cos(pose["yaw"] / 2.0)
        self.pub.publish(msg)
        self.get_logger().info(f"🚚 [AMR] 배달 출발 목표 발행 → ({pose['x']}, {pose['y']})")


# -----------------------------------------------------------------------------
# 통합 지점 (classify_tomatoes_predictive.py 의 execute() 완료부에 끼움):
#
#   def execute(self):
#       if self.goal_num > len(self.tasks_list) - 1:
#           self.send_signal_to_pc()          # 기존: PC로 DONE(→RoboDK·TTS)
#           self.dispatcher.dispatch()        # [추가] 적재 완료 → AMR 출발  ← 이 훅
#           self.is_running = False
#           ...
#
# (self.dispatcher = DeliveryDispatcher() 를 __init__ 에서 생성)
# -----------------------------------------------------------------------------
def main(args=None):
    rclpy.init(args=args)
    node = DeliveryDispatcher()
    node.dispatch()      # 단독 테스트용 1회 발행 (ROS2 환경 필요)
    rclpy.spin_once(node, timeout_sec=1.0)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
