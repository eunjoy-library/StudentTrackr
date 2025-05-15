# 현재 워크플로우가 이 파일을 실행하고 있습니다.
# 실제 앱을 실행하도록 app.py를 임포트하여 사용합니다.

from app import app as real_app
import os
import logging

# Firebase 테스트 라우트는 /firebase-test로 이동합니다
@real_app.route('/firebase-test')
def firebase_test():
    return """
    <h1>Firebase 테스트 페이지</h1>
    <p>이 페이지는 Firebase 연결을 테스트하기 위한 페이지입니다.</p>
    <p><a href="/firebase-test/test">Firebase 저장 테스트 페이지로 이동</a></p>
    """

# ✅ 테스트 라우트: /firebase-test/test 로 접속 시 Firebase에 데이터 저장
@real_app.route('/firebase-test/test')
def firebase_test_save():
    try:
        from app import models
        # Firebase가 앱에서 초기화되지 않았으면 오류 메시지
        if models.db is None:
            return "⚠️ Firebase가 초기화되지 않았습니다. Firebase 키를 설정해주세요.<br/><br/>" + \
                   "Firebase 설정 방법:<br/>" + \
                   "1. Firebase 콘솔에서 프로젝트 생성<br/>" + \
                   "2. 서비스 계정 키(Service Account Key) 생성<br/>" + \
                   "3. 키 파일을 firebase-key.json으로 저장<br/>" + \
                   "4. 환경변수 FIREBASE_PROJECT_ID, FIREBASE_API_KEY, FIREBASE_APP_ID 설정"
        
        # Firebase에 테스트 데이터 저장 (실제 앱의 함수 사용)
        doc_id = models.add_attendance("20240101", "홍길동", "A1", "1교시")
        if doc_id:
            return f"✅ Firebase에 출석 기록이 성공적으로 저장되었습니다! 문서 ID: {doc_id}"
        else:
            return "❌ Firebase 저장 실패: 중복된 데이터 또는 알 수 없는 오류"
    except Exception as e:
        logging.error(f"Firebase 저장 오류: {e}")
        return f"❌ Firebase 저장 실패: {str(e)}"

# 실제 앱 객체 사용
app = real_app
if __name__ == '__main__':
    app.run(debug=True)
