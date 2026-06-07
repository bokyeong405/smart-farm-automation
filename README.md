# 🍅 Smart Farm Automation — AI 비전 + 협동로봇 토마토 자동 수확

> **SSAFY 1학기 관통 프로젝트 · 최우수상(광주 3반 1등)** · 2인 팀
>
> 카메라로 토마토 숙성도(`ripe` / `semi_ripe` / `unripe`)를 분류하고, 협동로봇이 흡착식으로 픽앤플레이스해 **수확·선별·적재**하는 자동화 시스템입니다.

---

## 1. 한눈에 보기

비전(YOLOv5 검출) → 숙성도 분류(MobileNetV3) → **비전→로봇 좌표 변환(affine)** → ROS2 협동로봇 흡착 픽앤플레이스 → 적재 → TTS 음성 알림까지를 하나의 워크플로로 통합했습니다.

```
① 수확 [RoboDK 시뮬]            ② 선별 [실기]                                       ③ 이송 [AMR]
CAD 모델링 방울토마토 환경    컨베이어 → 검출(YOLOv5) → 숙성도 분류(MobileNetV3)         TurtleBot SLAM
→ AMR 위 로봇팔 이동·수확  →  → 협동로봇 흡착 픽앤플레이스 → 적재 → TTS 음성알림   →   자율주행 저장창고 배달

                              ▲ eval_classifier        ▲ predictive_pick           ▲ delivery_integration
개선(improvements/)             (재현 정확도 91.2%)       (무정지 예측, 시간 30~57%↓·sim)  (적재→AMR 연결 훅·sim)
```

> ⚙️ **본인 핵심 담당 = ② 선별** (AI 학습/튜닝 · 에지 · 통신 · ROS2 픽앤플레이스 · 비전→로봇 좌표 변환의 end-to-end 통합).

---

## 2. 담당 역할 (팀 vs 본인)

| 구분 | 내용 |
|---|---|
| **본인 (단독)** | AI 검출/분류 모델 학습·튜닝, 에지(라즈베리파이+카메라), 소켓/ROS2 통신, 협동로봇 픽앤플레이스, **비전→로봇 좌표 변환(affine)** — 모델→실제 하드웨어 구동의 end-to-end 1인 통합 |
| **본인 (공동)** | ① 수확 시뮬의 방울토마토 CAD 모델링 / 팀과 함께 SLAM **맵 작성**에 참여 |
| **팀** | 환경 구축(Onshape) 협업, 표준 nav 스택 기반 rviz 실행·촬영 |

> 🔎 **정직 범위**: 수확→AMR 이송은 발표 시점엔 파이프라인에 **미통합**(적재까지가 동작 범위)이었고, SLAM 코드는 라즈베리파이에 있다가 유실되었습니다. 발표 후 끊겨있던 '적재→AMR 출발'을 **연결 훅으로 직접 구현하고 시뮬로 검증**했습니다(실 TurtleBot 미구동). → [`improvements/delivery_integration/`](improvements/delivery_integration/)

---

## 3. 기술 스택

| 영역 | 기술 | 선택 이유 |
|---|---|---|
| AI 검출 | **YOLOv5** (단일 클래스 "tomato") | 위치 검출 전담 |
| AI 분류 | **MobileNetV3-small** 전이학습 (3클래스) | 경량·에지 적합. 검출과 **분리(2-stage)**해 단계별 독립 튜닝 |
| 데이터 | **Roboflow 증강** (Flip·Crop·Rotation±15°·Brightness±25°·Blur·Noise) | 다양한 촬영 조건에서 검출 강건성 확보 |
| 좌표 변환 | `cv2.getAffineTransform` (캘리브레이션 3점) | 픽셀(u,v)→로봇 mm(x,y) 매핑 (스케일 ≈0.54mm/px) |
| 로보틱스 | **ROS2** (rclpy · Action+Service+Topic · `MultiThreadedExecutor`+`ReentrantCallbackGroup` · QoS BEST_EFFORT) | 이동·그리퍼·검출 동시 처리, 카메라 스트림은 최신성 우선 |
| 그리퍼 | **흡착식** | 과육 접촉 면적을 줄여 손상 최소화 |
| 통신 | Python socket(TCP) · ROS2 Topic(`/tomato_results`) · RoboDK API | 에지(라파)↔윈도우PC(시뮬)↔로봇 이기종 연동 |
| 알림 | **Naver Clova Voice (TTS)** | 적재 완료 시 음성 안내 (현장 HMI 편의) |

---

## 4. 결과

- 🏆 **SSAFY 1학기 관통 프로젝트 최우수상** (광주 3반 1등)
- 📊 **숙성도 분류 정확도 91.2%** — *재현 평가(80/20 층화분할 홀드아웃 193장)* 기준. `ripe` F1 0.96 / `unripe` F1 0.93 / `semi_ripe` F1 0.58(recall 0.41) → 중간 숙성 약점. ([`improvements/eval_classifier/`](improvements/eval_classifier/))
- ⚡ **무정지 예측 포착으로 처리 시간 30~57% 단축** — *시뮬레이션 검증* (위치오차: 무예측 92mm → 예측 ~9mm, 벨트 40mm/s·속도추정 10% 오차 가정). ([`improvements/predictive_pick/`](improvements/predictive_pick/))

> ⚠️ **수치 표기 원칙**: 위 정확도는 *재현 평가*(제출 당시 모델 인스턴스와 다름), 처리시간 단축은 *시뮬레이션*입니다. 실하드웨어 실측이 아닌 항목은 본문에 명시했습니다.

---

## 5. 트러블슈팅 하이라이트

### 움직이는 벨트 위 "무정지 예측 포착"
- **문제**: 인식 후 로봇이 도달하는 사이 컨베이어가 계속 움직여 카메라가 본 위치와 로봇 도달 시점 위치가 어긋남.
- **1차 해법(한계)**: ripe 감지 시 벨트를 정지→픽→재가동 → 객체당 벨트 약 4초 정지(처리량 손실).
- **개선**: 연속 검출로 토마토 **속도 벡터를 추정** → affine 선형부로 로봇 속도(mm/s) 변환 → **예측 위치 = 현재 + 속도 × 선행시간** 으로 벨트를 멈추지 않고 픽. → 로직 구현 + 시뮬 검증(실로봇 미통합).

### 숙성도 분류와 라벨 모호성 (데이터 회고)
- `semi_ripe`가 약했던 원인을 ① 클래스 불균형 ② **주관적 라벨 기준**(색상값 같은 객관 지표 대신 사람 판단으로 '중간' 경계 분류)으로 분석.
- 개선 방향: HSV 색공간 임계값·다중 라벨러 합의로 라벨 기준 객관화 + 리샘플링.

---

## 6. 폴더 구조

```
smart-farm-automation/
├── src/                       ② 선별: 실기 런타임 (에지 + 협동로봇)
│   ├── tomato_detect.py         YOLOv5 검출 (ROS2 노드, 라즈베리파이)
│   ├── classify_tomatoes.py     숙성도 분류 + 픽앤플레이스 (affine 좌표변환)
│   ├── tomato_control.py        로봇/그리퍼 제어
│   ├── client.py                RoboDK·소켓 통신
│   ├── tomato_alarm.py          TTS 음성 알림 (Naver Clova)
│   └── web.html                 모니터링 웹
├── training/                  AI 학습 파이프라인
│   ├── step1_auto_crop.py       YOLO로 토마토 영역 자동 크롭(배경 제거)
│   ├── step2_train.py           MobileNetV3 숙성도 분류기 학습
│   ├── step3_run.py             검출+분류 실시간 실행
│   └── step4_validate.py        검증
├── improvements/              발표 후 개선·검증 (정직 라벨)
│   ├── eval_classifier/         분류 91.2% 재현 평가(홀드아웃)
│   ├── predictive_pick/         무정지 예측 포착(시간 30~57%↓, sim)
│   └── delivery_integration/    적재→AMR 연결 훅(sim)
├── docs/Smart Farm Automation.pdf   발표자료
└── .env.example               환경변수 템플릿
```

---

## 7. 실행 / 재현

> ⚠️ **모델 가중치(`*.pt`/`*.pth`)와 데이터셋은 용량 문제로 repo에 포함하지 않았습니다.**
> 데이터셋은 **Roboflow 공개 데이터셋** 기반(증강 적용)이며, 모델은 아래 학습 파이프라인으로 재생성합니다.

### 환경변수
```bash
cp .env.example .env   # 후 실제 값 입력 (Naver Clova 키, PC LAN IP)
```

### AI 학습 파이프라인 (`training/`)
```bash
python training/step1_auto_crop.py   # YOLO로 토마토 영역 크롭 → cropped_dataset/
python training/step2_train.py       # MobileNetV3 분류기 학습 → classifier_model.pth
python training/step3_run.py         # 웹캠 실시간 검출+분류 시연
```

### 개선 모듈 검증 (`improvements/`)
하드웨어 없이도 평가·시뮬을 돌릴 수 있습니다. 각 폴더 README 참고.
```bash
python improvements/eval_classifier/eval_classifier.py        # 홀드아웃 정확도 재현
python improvements/predictive_pick/sim_test.py               # 무정지 예측 수학 검증
python improvements/delivery_integration/sim_delivery.py      # 적재→AMR 연결 시뮬
```

> 실기 런타임(`src/`)은 라즈베리파이·RealSense·협동로봇·ROS2(`dobot_msgs` 등) 환경을 전제로 합니다. 코드는 환경 구성의 참조용입니다.

---

## 8. 회고 / 다음 단계
- 라벨 기준 객관화로 `semi_ripe` 정확도 개선
- 무정지 예측 포착을 실로봇에 통합 + 하강 중 재예측(비주얼 서보잉)
- 벨트 선속도(영상 광류) 실측으로 시뮬 가정값 대체
