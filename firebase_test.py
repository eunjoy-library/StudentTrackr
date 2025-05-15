from flask import Flask
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# ✅ Firebase 초기화
cred = credentials.Certificate("firebase-key.json")  # 같은 디렉토리에 있어야 함
firebase_admin.initialize_app(cred)
db = firestore.client()

# ✅ Flask 앱 생성
app = Flask(__name__)

# ✅ 테스트 라우트: /test 로 접속 시 Firebase에 데이터 저장
@app.route('/test')
def test():
    db.collection("attendances").add({
        "student_id": "20240101",
        "name": "홍길동",
        "seat": "A1",
        "period": "1교시",
        "date": datetime.now()
    })
    return "✅ Firebase 저장 완료!"
if __name__ == '__main__':
    app.run(debug=True)
