# Firebase 테스트를 건너뛰고 실제 앱을 실행합니다.
# 메인 페이지로 자동 리디렉션을 위한 코드입니다.

from flask import Flask, redirect, Response

# 앱 생성
app = Flask(__name__)

# 루트 경로를 실제 앱으로 리디렉션
@app.route('/')
def index():
    # 캐시 방지 헤더를 포함한 리디렉션 응답
    html = """
    <html>
    <head>
        <meta http-equiv="refresh" content="0;url=/">
        <title>도서실 출석 시스템</title>
    </head>
    <body>
        <h1>도서실 출석 시스템으로 이동합니다...</h1>
        <p>자동으로 이동하지 않는 경우 <a href="/">여기</a>를 클릭하세요.</p>
        <script>
            // 캐시 무효화를 위한 타임스탬프 추가
            window.location.href = "/?nocache=" + new Date().getTime();
        </script>
    </body>
    </html>
    """
    response = Response(html)
    # 캐시 방지 헤더 추가
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# 다른 모든 경로도 실제 앱으로 위임
@app.route('/<path:path>')
def catch_all(path):
    # 실제 앱 임포트 (여기서 임포트해야 순환 참조 방지)
    from app import app as real_app
    
    # 실제 앱의 view 함수 찾기
    view_function = real_app.view_functions.get(path)
    if view_function:
        return view_function()
    else:
        # 실제 앱의 url_map에서 일치하는 경로 찾기
        for rule in real_app.url_map.iter_rules():
            if rule.endpoint == path:
                return redirect(rule.rule)
    
    # 기본적으로 출석 페이지로 리디렉션
    return redirect('/attendance')
if __name__ == '__main__':
    app.run(debug=True)
