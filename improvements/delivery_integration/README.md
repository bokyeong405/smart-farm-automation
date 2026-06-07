# delivery_integration — AMR 이송 연결 훅

> 발표 후 보완. 끊겨 있던 '적재 완료 → AMR 자율주행 출발'을 잇는 **연결 훅**.

## 문제
원본 파이프라인은 **검출→픽→적재(+TTS)** 까지만 자동. 그 뒤 **AMR 이송 출발이 연결 안 됨**(미통합).
SLAM 맵 주행 자체는 팀과 함께 했으나(영상 증빙), 수확 파이프라인과 **자동 연결**은 빠져 있었음.

## 해결 — 연결 훅 (nav2 goal 발행)
- `delivery_hook.py` — 적재 완료 이벤트 시 nav2 표준 `/goal_pose`(PoseStamped)로 **배달 지점 목표 발행** → TurtleBot이 SLAM 맵에서 자율주행 이송.
- 픽 노드(`classify_tomatoes_predictive.py`)의 `execute()` 완료부에 `dispatcher.dispatch()` 한 줄로 연결 (README 내 통합 지점 주석 참고).

## 검증 — sim_delivery.py
- 미통합 vs 통합(훅) 흐름을 시뮬로 비교. 통합 시 **적재→AMR 자동 출발**로 end-to-end 연결, 로봇 픽과 AMR 배달이 **병행(파이프라이닝)**.
- 실행: `python improvements/delivery_integration/sim_delivery.py`

## 정직 범위 (면접 방어선)
| 주장 | 가능? |
|---|---|
| "적재→AMR 출발 **연결 훅 구현** + 시뮬로 흐름 검증" | ✅ |
| "발표 땐 미통합이던 이송을 **이후 연결**" | ✅ |
| "실 turtlebot으로 무인 배달 **완주/성공**" | ❌ (하드웨어 없음·SLAM 코드 유실 → nav2 goal 수신은 **가정·시뮬**) |
| "SLAM을 본인이 구현" | ❌ ('팀과 맵 작성 참여'까지만) |

## 입력값 출처
- `T_PICK` = 🎥 구동영상 측정(~3s) / `T_TTS`·AMR 이동·복귀 = ❓ 가정값(라벨 표시)
- 배달 지점 좌표 `DELIVERY_POSE` = placeholder `TODO`(실제 맵 좌표 모름)
