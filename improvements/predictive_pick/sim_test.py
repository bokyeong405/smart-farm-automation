"""
sim_test.py — 무정지 예측 포착(predictive pick) 검증 (하드웨어 없이)

두 가지를 정량화한다:
  A. 시간/처리량 개선율  — 정지 방식 vs 무정지 예측, 객체 간격(spacing)별
  B. 위치 정확도 민감도  — 예측이 '움직이는 벨트' 오차를 얼마나 없애는지

[입력값 출처]
  - 픽 동작 T_PICK = 3.0s        🎥 구동영상 측정 (벨트 정지 ~4s − 재가동 1s)
  - 재가동 대기 T_RESTART = 1.0s ✅ 코드 (tomato_control TARGET_COUNT 1000 × 1ms)
  - 예측 선행시간 T_LEAD = 2.3s   🎥 접근 2.0s + 통신 0.3s
  - affine 변환                  ✅ 코드 (classify_tomatoes.py 캘리브레이션)
  - 벨트 선속도(mm/s)            ❓ 코드엔 스텝레이트만 → 위치오차는 '가정값'으로 민감도 제시

⚠️ 정직: 시간 개선율은 측정/코드값 기반. 위치오차의 mm 수치는 벨트 선속도 가정에 의존.
"""
import os, json, sys
import numpy as np
import cv2

try:
    sys.stdout.reconfigure(encoding="utf-8")   # Windows 콘솔 유니코드(≈ 등) 출력
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")

# --- 측정/코드 기반 상수 ---
T_PICK = 3.0       # 🎥 측정
T_RESTART = 1.0    # ✅ 코드
T_APPROACH = 2.0   # 🎥 측정
T_COMM = 0.3
T_LEAD = T_APPROACH + T_COMM


def section_a_throughput():
    """객체 간격별 정지 vs 무정지 처리시간·개선율. N개 ripe 객체 가정."""
    N = 10
    gaps = [0.5, 1, 2, 3, 4, 5, 6, 8, 10]  # 객체 간 벨트 진행시간(s)
    rows = []
    for g in gaps:
        # 정지 방식: 객체마다 [벨트진행 g] + [정지픽 T_PICK] + [재가동 T_RESTART]
        stop = N * (g + T_PICK + T_RESTART)
        # 무정지 예측: 벨트 안 멈춤 → 파이프라인, 객체당 max(간격, 픽시간)
        moving = N * max(g, T_PICK)
        imp = (stop - moving) / stop * 100
        rows.append((g, stop, moving, imp))
    print("\n===== A. 시간/처리량 (N=10 ripe 객체) =====")
    print(f"  T_PICK={T_PICK}s  T_RESTART={T_RESTART}s (정지 오버헤드/객체 = {T_PICK+T_RESTART}s)")
    print("  간격(s) | 정지방식(s) | 무정지예측(s) | 시간개선율")
    for g, s, m, i in rows:
        print(f"   {g:5.1f}  |  {s:7.1f}   |   {m:7.1f}    |  {i:5.1f}%")
    print("  ※ 개선율은 '객체가 분리되어 매번 정지·재가동이 발생'하는 시나리오 기준.")
    print("    객체가 연속(시야에 계속 ripe)이면 정지방식도 벨트가 계속 멈춰 둘 다 로봇 병목 → 개선 미미.")
    return [{"gap_s": g, "stop_s": s, "moving_s": m, "improve_pct": round(i, 1)} for g, s, m, i in rows]


def section_b_accuracy():
    """예측이 '움직이는 벨트' 위치오차를 제거하는 효과 (벨트 선속도는 가정)."""
    # 원본 affine (pixel→robot mm)
    pts_cam = np.float32([[375, 244], [277, 228], [487, 240]])
    pts_rob = np.float32([[204.755, -45.942], [196.154, -92.942], [198.284, -7.829]])
    M = cv2.getAffineTransform(pts_cam, pts_rob)
    M_lin = M[:, :2]
    mm_per_px = float(np.sqrt(abs(np.linalg.det(M_lin))))  # 선형 스케일(mm/px) — 실제 코드 행렬에서 도출

    print("\n===== B. 위치 정확도 (예측 효과) =====")
    print(f"  affine 선형 스케일 ≈ {mm_per_px:.3f} mm/px (코드 행렬에서 도출)")

    belt_speeds = [20, 40, 60]      # ❓ 가정: 벨트 선속도(mm/s)
    est_errors = [0.0, 0.05, 0.10, 0.20]   # 속도추정 오차율
    out = {"mm_per_px": round(mm_per_px, 4), "T_LEAD": T_LEAD, "cases": []}
    print(f"  선행시간 T_LEAD={T_LEAD}s 동안 토마토 이동 = 벨트속도 × T_LEAD")
    print("  벨트(mm/s) | 무예측 오차(mm) | 예측 오차(mm): 추정 0% / 5% / 10% / 20%")
    for v in belt_speeds:
        no_pred = v * T_LEAD                      # 예측 안 하면 통째로 빗나감
        preds = [v * e * T_LEAD for e in est_errors]
        print(f"   {v:6.0f}   |   {no_pred:7.1f}     |   " +
              " / ".join(f"{p:.1f}" for p in preds))
        out["cases"].append({"belt_mm_s": v, "no_pred_err_mm": round(no_pred, 1),
                             "pred_err_mm": {f"{int(e*100)}%": round(v*e*T_LEAD, 1) for e in est_errors}})
    print("  → 무예측은 벨트속도×2.3s 만큼 통째로 빗나감. 예측 시 '속도추정 오차분'만 남음(작음).")
    print("  ※ 벨트 mm/s 는 가정값(코드엔 스텝레이트만). 영상 광류로 실측하면 교체 가능.")
    return out


def main():
    os.makedirs(RESULTS, exist_ok=True)
    a = section_a_throughput()
    b = section_b_accuracy()
    result = {
        "params": {"T_PICK": T_PICK, "T_RESTART": T_RESTART, "T_LEAD": T_LEAD,
                   "source": "T_PICK·T_LEAD=영상측정, T_RESTART·affine=코드, 벨트mm/s=가정"},
        "A_throughput": a,
        "B_accuracy": b,
    }
    with open(os.path.join(RESULTS, "sim_result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {os.path.join(RESULTS, 'sim_result.json')}")


if __name__ == "__main__":
    main()
