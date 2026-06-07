import os
import socket
import time
from robodk.robolink import * # RoboDK API
from robodk.robomath import * # Robot Math

# --- .env 에서 설정 로드 (GitHub 공개용) ---
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

# [필수] 같은 폴더에 tomato_alarm.py가 있어야 합니다.
import tomato_alarm 

# -----------------------------------------------------
# [설정 1] 내 PC(Windows)의 IP와 포트
# -----------------------------------------------------
PC_IP = os.environ.get("PC_IP", "127.0.0.1")  # 윈도우 PC IP (.env)
PORT = 9999                # 통신 포트

# -----------------------------------------------------
# [설정 2] 실행할 RoboDK 프로그램 이름
# -----------------------------------------------------
# RoboDK 좌측 트리 메뉴에 있는 '프로그램 아이콘'의 이름과 정확히 같아야 합니다.
# (예: 'Prog1', 'Main', 'PickAndPlace' 등)
ROBODK_PROGRAM_NAME = 'Prog1' 

def run_robodk_simulation():
    """ RoboDK에 저장된 프로그램을 실행하고 완료될 때까지 대기 """
    print("🤖 [RoboDK] RoboDK 연결 중...")
    RDK = Robolink()
    
    # 1. 실행할 프로그램 찾기
    prog = RDK.Item(ROBODK_PROGRAM_NAME, ITEM_TYPE_PROGRAM)
    
    if not prog.Valid():
        print(f"⚠️ 오류: RoboDK에서 프로그램 '{ROBODK_PROGRAM_NAME}'을 찾을 수 없습니다.")
        print("   -> RoboDK 좌측 트리에 해당 이름의 프로그램이 있는지 확인해주세요.")
        return False

    print(f"🚀 [RoboDK] 시나리오 실행: {ROBODK_PROGRAM_NAME}")
    
    # 2. 프로그램 실행
    prog.RunProgram()
    
    # 3. 프로그램이 끝날 때까지 대기 (중요: 그래야 알림이 제때 울림)
    #    RoboDK가 동작 중인 동안 계속 기다립니다.
    while prog.Busy() == 1:
        time.sleep(0.1)
        
    print("✅ [RoboDK] 시나리오 동작 완료")
    return True

def main():
    # 소켓 서버 생성
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((PC_IP, PORT))
        server_socket.listen(1)
        print(f"=========================================")
        print(f"📡 [Server] 시뮬레이션 제어 서버 시작")
        print(f"👉 IP: {PC_IP} / Port: {PORT}")
        print(f"👉 Target Program: {ROBODK_PROGRAM_NAME}")
        print(f"=========================================")

        while True:
            print("⏳ 연결 대기 중...")
            conn, addr = server_socket.accept()
            print(f"🔗 클라이언트 연결됨: {addr}")
            
            data = conn.recv(1024)
            if not data:
                conn.close()
                continue
                
            msg = data.decode('utf-8')
            
            if msg == "DONE":
                print("\n📩 [수신] 작업 시작 신호('DONE') 도착!")
                
                # 1. RoboDK 시나리오 실행
                success = run_robodk_simulation()
                
                # 2. 동작이 성공적으로 끝났다면 알림 실행
                if success:
                    print("🔊 [Alarm] 알림 모듈 호출...")
                    try:
                        tomato_alarm.announce_loading("방울토마토가 적재되었습니다.")
                    except Exception as e:
                        print(f"❌ 알림 실행 중 오류 발생: {e}")
                
                print("------------- 사이클 종료 -------------\n")
            
            conn.close()

    except KeyboardInterrupt:
        print("\n🛑 사용자에 의해 서버를 종료합니다.")
    finally:
        server_socket.close()

if __name__ == '__main__':
    main()