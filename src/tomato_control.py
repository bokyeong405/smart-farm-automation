# -*- coding: utf-8 -*-
import os
import gpiod
import time
import threading
import roslibpy

# --- .env 에서 설정 로드 (GitHub 공개용) ---
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

# ==========================================
# [설정] PC IP 주소
# ==========================================
PC_IP = os.environ.get("PC_IP", "127.0.0.1")
TOPIC_NAME = '/tomato_results'
TOPIC_TYPE = 'std_msgs/String'

# ==========================================
# [설정] GPIO 핀 설정
# ==========================================
dir_pin = 17
step_pin = 27
enable_pin = 22
chip = gpiod.Chip('gpiochip0')
dir_line = chip.get_line(dir_pin)
step_line = chip.get_line(step_pin)
enable_line = chip.get_line(enable_pin)
dir_line.request(consumer="dir", type=gpiod.LINE_REQ_DIR_OUT)
step_line.request(consumer="step", type=gpiod.LINE_REQ_DIR_OUT)
enable_line.request(consumer="enable", type=gpiod.LINE_REQ_DIR_OUT)

# ==========================================
# [상태 변수]
# ==========================================
motor_running = False
motor_direction = 1
motor_thread = None

is_ripe_detected = False
last_msg_time = 0   # [추가] 마지막으로 메시지 받은 시간

# [카운트 변수]
wait_count = 0      
TARGET_COUNT = 1000 

# ... (모터 함수들은 기존과 동일) ...
def step_motor_loop():
    dir_line.set_value(motor_direction)
    while motor_running:
        step_line.set_value(1)
        time.sleep(0.0004)
        step_line.set_value(0)
        time.sleep(0.0004)

def start_motor():
    global motor_running, motor_thread
    if not motor_running:
        motor_running = True
        enable_line.set_value(0)
        if motor_thread is None or not motor_thread.is_alive():
            motor_thread = threading.Thread(target=step_motor_loop)
            motor_thread.start()
        print("✅ [이동] 레일 가동")

def stop_motor():
    global motor_running
    if motor_running:
        motor_running = False
        enable_line.set_value(1)
        print("🛑 [정지] RIPE 감지됨")

def callback(message):
    global is_ripe_detected, last_msg_time
    
    # [중요] 메시지가 들어올 때마다 시간 갱신
    last_msg_time = time.time()
    
    try:
        raw_data = message['data']
        found = False
        if raw_data:
            objects = raw_data.split(' | ')
            for obj_str in objects:
                parts = obj_str.split(',')
                if len(parts) >= 1 and parts[0].strip() == 'ripe':
                    found = True
                    break
        is_ripe_detected = found
    except Exception:
        pass

# ==========================================
# [메인] 실행 로직
# ==========================================
try:
    print(f"🚀 시스템 시작 (목표 카운트: {TARGET_COUNT})")
    start_motor()

    client = roslibpy.Ros(host=PC_IP, port=9090)
    client.run()
    listener = roslibpy.Topic(client, TOPIC_NAME, TOPIC_TYPE)
    listener.subscribe(callback)
    
    # 초기 시간 설정
    last_msg_time = time.time()
    print("👀 감시 시작!")

    while True:
        current_time = time.time()

        # ---------------------------------------------------------
        # [추가된 안전장치] 데이터 끊김 확인 (Watchdog)
        # 0.5초 이상 카메라에서 소식이 없으면 -> "화면에 아무것도 없다"로 간주
        # ---------------------------------------------------------
        if current_time - last_msg_time > 0.5:
            # 마지막 데이터가 'ripe'였더라도, 지금 데이터가 안 들어오면 사라진 것으로 처리
            if is_ripe_detected:
                # print("📡 데이터 끊김 -> 탐지 해제 처리") # 디버깅 필요시 주석 해제
                is_ripe_detected = False

        # ---------------------------------------------------------
        # 로직 A: Ripe 발견됨 -> 무조건 멈춤 & 카운트 리셋
        # ---------------------------------------------------------
        if is_ripe_detected:
            if motor_running:
                stop_motor()
            wait_count = 0 
            
        # ---------------------------------------------------------
        # 로직 B: Ripe 없음 -> 멈춰있으면 숫자 세기 시작
        # ---------------------------------------------------------
        else:
            if not motor_running:
                wait_count += 1
                
                # 진행 상황 로그 (선택사항, 너무 빠르면 주석 처리)
                if wait_count % 200 == 0:
                    print(f"⏳ 대기 중... {wait_count}/{TARGET_COUNT}")

                if wait_count >= TARGET_COUNT:
                    print(f"⏩ 재가동! ({TARGET_COUNT} 달성)")
                    start_motor()
                    wait_count = 0

        time.sleep(0.001)

except KeyboardInterrupt:
    print("\n강제 종료")
finally:
    motor_running = False
    enable_line.set_value(1)
    dir_line.release()
    step_line.release()
    enable_line.release()
    if client.is_connected:
        client.terminate()