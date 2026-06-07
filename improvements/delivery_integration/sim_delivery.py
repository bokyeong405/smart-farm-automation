"""
sim_delivery.py — 검출→픽→적재→TTS→[AMR 출발 훅]→이송→복귀 전체 사이클 시뮬

목적: 'AMR 출발 연결 훅'을 끼웠을 때 파이프라인이 end-to-end로 이어지는지 + 파이프라이닝
      (로봇이 다음 토마토 픽하는 동안 AMR이 백그라운드로 배달)으로 처리량이 어떻게 되는지 확인.

⚠️ 순수 파이썬 시뮬(ROS2/turtlebot 실제 호출 X). 실 구동 아님 — 흐름·타이밍 모델링만.
   T_PICK=측정, 나머지(TTS·AMR 이동/복귀)=가정값(라벨 표시).
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# --- 파라미터 ---
T_PICK = 3.0      # 🎥 측정 (픽 동작)
T_TTS = 1.5       # ❓ 가정 (음성 알림)
T_TRAVEL = 12.0   # ❓ 가정 (AMR 배달지까지 편도 자율주행)
T_RETURN = 12.0   # ❓ 가정 (AMR 복귀)
N = 5             # 토마토 개수


def sim_without_integration():
    """미통합: 적재까지만. AMR 출발이 파이프라인에 연결 안 됨(수동/끊김)."""
    print("\n[미통합] 검출→픽→적재→TTS 까지만 자동. AMR 출발은 연결 안 됨(수동 개입 필요).")
    t = 0.0
    for i in range(N):
        t += T_PICK + T_TTS
        print(f"  토마토{i+1}: 적재완료 @ {t:.1f}s  → (AMR 출발 ❌ 연결 없음)")
    print(f"  적재 {N}개 완료 {t:.1f}s. 배달은 별도 수동.")


def sim_with_integration():
    """통합(훅): 적재 완료 시 AMR 자동 출발. 로봇은 다음 픽 진행(파이프라이닝)."""
    print("\n[통합(훅)] 적재완료 → AMR 자동 출발(nav goal). 로봇은 다음 토마토 픽 계속.")
    amr_free_at = 0.0   # AMR이 다음 배달 가능한 시각(1대 가정)
    robot_t = 0.0
    last_delivery_done = 0.0
    for i in range(N):
        robot_t += T_PICK + T_TTS          # 픽 + 적재 + 알림
        dispatch = robot_t                  # 적재 완료 = AMR 출발 트리거
        start = max(dispatch, amr_free_at)  # AMR이 비어있어야 출발
        done = start + T_TRAVEL + T_RETURN  # 배달 후 복귀
        amr_free_at = done
        last_delivery_done = done
        print(f"  토마토{i+1}: 적재 @ {dispatch:5.1f}s → AMR 출발 @ {start:5.1f}s → 배달완료 @ {done:5.1f}s")
    print(f"  로봇 적재 {N}개 완료 @ {robot_t:.1f}s (AMR 배달과 병행) / 마지막 배달 완료 @ {last_delivery_done:.1f}s")
    return robot_t, last_delivery_done


def main():
    print("=" * 64)
    print(f"AMR 이송 통합 시뮬  (T_PICK={T_PICK}s🎥 / T_TTS={T_TTS}s❓ / AMR 편도={T_TRAVEL}s❓ 복귀={T_RETURN}s❓)")
    print("=" * 64)
    sim_without_integration()
    robot_t, deliv = sim_with_integration()
    print("\n[요점]")
    print(f"  - 훅 연결 시 적재 완료가 자동으로 AMR 출발로 이어짐(end-to-end 연결).")
    print(f"  - 로봇 픽({robot_t:.1f}s)과 AMR 배달이 병행 → 로봇은 AMR 복귀를 기다리지 않음(파이프라이닝).")
    print(f"  - AMR 1대 기준 배달이 병목이면 last 배달({deliv:.1f}s)이 전체 완료 시각.")
    print("\n⚠️ 시뮬레이션(흐름·타이밍 모델). 실 turtlebot 미구동. AMR 시간은 가정값.")


if __name__ == "__main__":
    main()
