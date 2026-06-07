import os
import sys
import urllib.request
import urllib.parse
from playsound import playsound  # 소리 재생 라이브러리

# --- .env 에서 키 로드 (GitHub 공개용: 키는 .env 로 분리, 하드코딩 금지) ---
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

# --- 알림 함수 정의 ---
def announce_loading(text_content):
    # API 인증 정보 (.env 에서 로드)
    client_id = os.environ.get("NAVER_CLOVA_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_CLOVA_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("[설정 오류] .env 에 NAVER_CLOVA_CLIENT_ID / NAVER_CLOVA_CLIENT_SECRET 를 설정하세요.")
        return

    # API 설정
    speaker = "nsabina"
    speed = "0"
    volume = "0"
    pitch = "0"
    fmt = "mp3"

    val = {
        "speaker": speaker,
        "volume": volume,
        "speed": speed,
        "pitch": pitch,
        "text": text_content,
        "format": fmt
    }

    # 데이터 인코딩 및 URL 설정
    data = urllib.parse.urlencode(val).encode('utf-8')
    url = "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts"

    header = {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret
    }

    # 요청 생성 및 전송
    request = urllib.request.Request(url, data, header)

    try:
        response = urllib.request.urlopen(request)
        rescode = response.getcode()

        if rescode == 200:
            print(f"[TTS] 생성 성공: '{text_content}'")
            response_body = response.read()

            # 파일 저장
            file_name = 'alert_voice.mp3'
            with open(file_name, 'wb') as f:
                f.write(response_body)

            # 재생
            print("[Player] 음성 재생 중...")
            try:
                playsound(file_name)
                # os.remove(file_name) # 필요시 주석 해제하여 파일 삭제
            except Exception as e:
                print(f"[Player Error] 재생 중 오류 발생: {e}")

        else:
            print("Error Code:" + rescode)

    except Exception as e:
        print("Error:", e)

# ==========================================
# 메인 실행부
# ==========================================
if __name__ == "__main__":
    # 이 파일만 단독으로 실행했을 때 테스트용
    announce_loading("방울토마토가 적재되었습니다.")
