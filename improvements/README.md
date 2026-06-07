# improvements — 발표 후 개선·검증

> 발표 시점에 "향후 개선"으로 남겼던 항목들을, **원본 코드(`../src/`)는 그대로 두고** 이 폴더에서 별도로 구현·측정한 작업입니다.
> 목적: ① 분류 정확도를 **신뢰 가능하게 측정** ② 무정지 예측 포착을 **실제 구현** ③ 끊겼던 적재→AMR 흐름을 **연결**.

## 전체 파이프라인 & 개선 위치

```
① 수확 [RoboDK 시뮬]            ② 선별 [실기]                                   ③ 이송 [AMR]
CAD 모델링 토마토 환경       컨베이어 → 검출(YOLOv5) → 숙성도 분류(MobileNetV3)     TurtleBot SLAM
→ 로봇팔 이동·수확        →  → 흡착 픽앤플레이스 → 적재 → TTS 음성알림        →   자율주행 저장창고 배달

                            ▲ eval_classifier       ▲ predictive_pick               ▲ delivery_integration
```

> 각 시뮬은 효과를 **격리 측정**하기 위한 것이며, 연결은 코드 레벨에서 이루어집니다(ROS2/HW가 없어 '한 번에 실행'만 못 함).

---

## 1. eval_classifier — 분류 정확도 재현 평가 ✅
- **왜**: 원본 학습 스크립트는 970장 전체로 학습 → 저장모델 수치가 '학습 정확도'라 과대평가. 검증 가능한 **홀드아웃 수치**가 필요.
- **방법**: 동일 설정(MobileNetV3-small · Adam lr=0.001 · 10 epochs · batch16)으로 **80/20 층화분할 재학습 → 20% 홀드아웃 평가**.
- **결과**: 홀드아웃 193장 **정확도 91.2%** (`ripe` F1=0.96 / `unripe` F1=0.93 / **`semi_ripe` F1=0.58, recall=0.41**). → [`results/accuracy.json`](eval_classifier/results/accuracy.json)
- **정직 라벨**: "재현 평가(홀드아웃 20%)" — 제출 당시 모델 인스턴스와는 다른 재학습 인스턴스.

## 2. predictive_pick — 무정지 예측 포착 ✅
- **무엇**: 벨트를 멈추지 않고 토마토 **속도 벡터를 추정** → 예측 위치로 픽. 원본 `classify_tomatoes.py`(정지·정적 affine)를 `classify_tomatoes_predictive.py`(속도벡터·무정지)로 확장.
- **결과(sim)**: 객체 분리 시나리오에서 **처리 시간 30~57% 단축**(N=9), 위치오차 무예측 92mm → 예측 시 ~9mm(벨트 40mm/s·추정 10% 가정). → [`results/sim_result.json`](predictive_pick/results/sim_result.json)
- **검증**: `sim_test.py`로 예측 수학을 검증(가상 벨트 속도·지연 입력 → 예측 좌표 오차 측정). 로직 구현 + 시뮬 검증, **실로봇 미실행**.
- 상세 → [`predictive_pick/README.md`](predictive_pick/README.md)

## 3. delivery_integration — 적재→AMR 연결 훅 ✅
- **무엇**: 끊겨있던 '적재 완료 → AMR 자율주행 출발'을 잇는 **연결 훅**(nav2 `/goal_pose` 발행) + 전체 사이클 시뮬.
- **결과(sim)**: 적재→AMR 자동 출발 end-to-end 연결, 로봇 픽과 AMR 배달 병행(파이프라이닝). AMR 1대면 배달이 병목.
- **정직 라벨**: 연결 훅 + 시뮬 검증, **실 TurtleBot 미구동**(SLAM 코드 유실, 맵 작성은 팀 협업).
- 상세 → [`delivery_integration/README.md`](delivery_integration/README.md)
