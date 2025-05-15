from flask import Flask
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import logging
import os

# ✅ Flask 앱 생성
app = Flask(__name__)

# ✅ Firebase 초기화
db = None
try:
    if os.path.exists("firebase-key.json"):
        cred = credentials.Certificate("firebase-key.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logging.info("Firebase 초기화 성공")
    else:
        logging.warning("Firebase 키 파일이 없어 초기화를 건너뜁니다.")
except Exception as e:
    logging.error(f"Firebase 초기화 오류: {e}")

# ✅ 기본 라우트: 메인 페이지 표시
@app.route('/')
def index():
    return """
    <h1>Firebase 테스트 페이지</h1>
    <p>이 페이지는 Firebase 연결을 테스트하기 위한 페이지입니다.</p>
    <p><a href="/test">Firebase 저장 테스트 페이지로 이동</a></p>
    """

# ✅ 테스트 라우트: /test 로 접속 시 Firebase에 데이터 저장
@app.route('/test')
def test():
    if db is None:
        return "⚠️ Firebase가 초기화되지 않았습니다. Firebase 키를 설정해주세요.<br/><br/>" + \
               "Firebase 설정 방법:<br/>" + \
               "1. Firebase 콘솔에서 프로젝트 생성<br/>" + \
               "2. 서비스 계정 키(Service Account Key) 생성<br/>" + \
               "3. 키 파일을 firebase-key.json으로 저장<br/>" + \
               "4. 환경변수 FIREBASE_PROJECT_ID, FIREBASE_API_KEY, FIREBASE_APP_ID 설정"
    
    try:
        # Firebase에 테스트 데이터 저장
        doc_ref = db.collection("attendances").add({
            "student_id": "20240101",
            "name": "홍길동",
            "seat": "A1",
            "period": "1교시",
            "date": datetime.now()
        })
        return f"✅ Firebase 저장 완료! 문서 ID: {doc_ref[1].id}"
    except Exception as e:
        logging.error(f"Firebase 저장 오류: {e}")
        return f"❌ Firebase 저장 실패: {str(e)}"
if __name__ == '__main__':
    app.run(debug=True)
