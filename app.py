# ================== [IMPORTS] ==================
# 표준 라이브러리
import os
import csv
import json
import logging
from datetime import datetime, timedelta
from collections import Counter

# 외부 라이브러리
import pandas as pd
import pytz
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, jsonify, after_this_request, send_from_directory
from dotenv import load_dotenv

# Firebase 관련 라이브러리
import firebase_admin
from firebase_admin import credentials, firestore

# 내부 모듈 가져오기
import models

# ================== [환경 변수 로드] ==================
# .env 파일에서 환경 변수 명시적으로 읽어오기
load_dotenv(override=True)  # 기존 환경 변수 덮어쓰기

# 환경 변수 값 확인 및 로그 출력
firebase_api_key = os.environ.get("FIREBASE_API_KEY")
firebase_project_id = os.environ.get("FIREBASE_PROJECT_ID")
firebase_app_id = os.environ.get("FIREBASE_APP_ID")

if firebase_api_key and firebase_project_id and firebase_app_id:
    logging.info(f"Firebase 환경 변수 로드 성공: 프로젝트 ID = {firebase_project_id}")
else:
    logging.warning("Firebase 환경 변수 로드 실패. .env 파일을 확인하세요.")
    logging.warning(f"API Key: {'설정됨' if firebase_api_key else '설정되지 않음'}")
    logging.warning(f"Project ID: {'설정됨' if firebase_project_id else '설정되지 않음'}")
    logging.warning(f"App ID: {'설정됨' if firebase_app_id else '설정되지 않음'}")

# ================== [Firebase 초기화] ==================
db = None

try:
    # ✅ 정확한 파일명 사용
    cred = credentials.Certificate("firebase-key.json")
    
    # ✅ Firebase 앱 초기화
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
        logging.info("Firebase 앱 초기화 성공")
    else:
        logging.info("Firebase 앱 이미 초기화됨")
    
    # ✅ Firestore 객체 가져오기
    db = firestore.client()
    logging.info("✅ Firebase Firestore 클라이언트 생성 성공")
    
    # DB 연결 테스트
    try:
        test_ref = db.collection('test').document('connection')
        test_ref.set({'timestamp': datetime.now()})
        logging.info("Firebase 연결 테스트 성공")
    except Exception as test_error:
        logging.error(f"Firebase 연결 테스트 실패: {test_error}")
except Exception as e:
    logging.error(f"❌ Firebase 초기화 오류: {e}")

# models.py 초기화 - db 인스턴스 전달
try:
    import models
    if models.setup_firebase(db):
        logging.info("models.py Firebase 설정 완료")
    else:
        logging.error("models.py Firebase 설정 실패")
except Exception as setup_error:
    logging.error(f"models.py 설정 오류: {setup_error}")

# ================== [Flask 객체 생성] ==================
app = Flask(__name__)

# ================== [앱 설정] ==================
app.secret_key = os.environ.get("SESSION_SECRET", "fallback")

# ✅ 테스트 라우트: Firebase 저장 테스트
@app.route('/test')
def test():
    if db is None:
        return "⚠️ Firebase가 초기화되지 않았습니다. Firebase 키를 설정해주세요."
    
    try:
        # Firebase에 테스트 데이터 저장
        db.collection("attendances").add({
            "student_id": "20240101",
            "name": "홍길동",
            "seat": "A1",
            "period": "1교시",
            "date": datetime.now()
        })
        return "✅ Firebase 저장 완료!"
    except Exception as e:
        logging.error(f"Firebase 저장 테스트 오류: {e}")
        return f"❌ Firebase 저장 실패: {str(e)}"

# ================== [한국 시간대 설정 및 로그 설정] ==================

KST = pytz.timezone('Asia/Seoul')
logging.basicConfig(level=logging.DEBUG)

# ================== [템플릿 전역 함수 주입] ==================

@app.context_processor
def inject_now():
    now = datetime.now(KST).replace(tzinfo=None)
    return {
        'now': lambda: now,
        'current_year': now.year
    }


# File configurations
# 데이터베이스 기반으로 전환 완료 - CSV 파일 참조 제거
# FILENAME = 'attendance.csv'
# BACKUP_FILE = 'attendance_backup.csv'
LOG_FILE = 'attendance_error.log'
# EXCEL_FRIENDLY_FILE = 'attendance_excel.csv'
STUDENT_FILE = 'students.xlsx'  # 학생 정보는 여전히 Excel 파일에서 관리
# MEMO_FILE = 'period_memos.csv'  # 메모는 데이터베이스로 이동
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")  # Default is "1234" if not set in environment

# Period schedule configuration
PERIOD_SCHEDULE = {
    1: (7, 50, 9, 15),  # 1교시 시간 변경: 7:50-9:15
    2: (9, 15, 10, 40),
    3: (10, 40, 12, 5),
    4: (12, 5, 12, 30),
    5: (12, 30, 14, 25),
    6: (14, 25, 15, 50)
}

# 데이터베이스 초기화는 앱 초기화 단계에서 실행

# 교시별 메모 저장 함수
def save_period_memo(date, period, memo_text):
    """
    교시별 메모를 저장하는 함수 (Firebase 사용)
    """
    try:
        # Firebase에 메모 저장
        result = models.save_memo(date, period, memo_text)
        return result
    except Exception as e:
        logging.error(f"메모 저장 중 오류 발생: {e}")
        return False

# 모든 교시별 메모 로드 함수
def load_period_memos():
    """
    모든 교시별 메모를 로드하는 함수 (Firebase 사용)
    """
    try:
        # Firebase에서 모든 메모 조회
        return models.get_all_memos()
    except Exception as e:
        logging.error(f"메모 로드 중 오류 발생: {e}")
        return []

# 특정 교시의 메모 조회 함수
def get_period_memo(date, period):
    """
    특정 날짜와 교시에 해당하는 메모를 반환하는 함수 (Firebase 사용)
    """
    try:
        # Firebase에서 특정 날짜/교시의 메모 조회
        return models.get_memo(date, period)
    except Exception as e:
        logging.error(f"메모 조회 중 오류 발생: {e}")
        return ""

# 데이터베이스 초기화는 app_context 내에서 실행해야 함
# 초기화 작업은 앱 실행 시 별도로 수행

def get_current_period():
    """
    Determine the current class period based on current time (Korean time)
    Returns period number (1-10), -1 for time outside scheduled periods, or 0 for 4th period
    
    -1 = 시간 외 (모든 시간대에 출석 허용)
    0  = 4교시 (출석 불가)
    1~10 = 해당 교시
    """
    # 한국 시간 기준으로 현재 시간 가져오기
    now = datetime.now(KST).time()
    for period, (start_h, start_m, end_h, end_m) in PERIOD_SCHEDULE.items():
        start = datetime.strptime(f"{start_h}:{start_m}", "%H:%M").time()
        end = datetime.strptime(f"{end_h}:{end_m}", "%H:%M").time()
        if start <= now < end:
            # 4교시는 도서실 이용 불가능 시간으로 설정
            if period == 4:
                return 0  # 4교시는 이용 불가
            return period
    return -1  # 교시가 아닌 시간일 경우 (-1로 변경하여 시간 외 구분)
    
def get_current_period_attendance_count():
    """
    현재 교시의 출석 인원 수를 반환하는 함수
    - 현재 교시에 출석한 사람들의 수를 계산
    - 최대 인원 초과 여부 확인에 사용됨
    """
    current_period = get_current_period()
    if current_period == 0:
        return 0
        
    period_text = f"{current_period}교시"
    
    # Firebase에서 오늘의 현재 교시 출석 수 확인
    count = 0
    try:
        # Firebase에서 오늘 데이터 가져오기
        today_attendances = models.get_today_attendances()
        
        # 현재 교시에 해당하는 출석 데이터 필터링
        count = sum(1 for attendance in today_attendances if attendance.get('period') == period_text)
        
    except Exception as e:
        logging.error(f"현재 교시 출석 인원 Firebase 조회 오류: {e}")
                
    return count

# 전역 변수로 학생 데이터 캐시 저장 (속도 향상을 위해)
_student_data_cache = None
_last_student_data_load_time = None

def load_student_data():
    """
    Load student data from Excel file with caching
    Returns a dictionary with student_id as key and (name, seat) as value
    """
    global _student_data_cache, _last_student_data_load_time
    
    # 캐시가 있고 마지막 로드 시간이 30분 이내인 경우 캐시 사용
    current_time = datetime.now()
    if _student_data_cache and _last_student_data_load_time and \
       (current_time - _last_student_data_load_time).seconds < 1800:  # 30분 = 1800초
        return _student_data_cache
    
    try:
        # Excel 파일에서 학생 데이터 로드 (학번은 문자열로 처리)
        df = pd.read_excel(STUDENT_FILE, dtype={'학번': str})
        
        # 딕셔너리 생성 (오류 처리 포함)
        student_data = {}
        for _, row in df.iterrows():
            # 필요한 열이 있는지 확인
            if '학번' not in row or '이름' not in row:
                continue
                
            student_id = str(row['학번'])
            
            # NaN 값이나 빈 값은 건너뛰기 (빠른 검사)
            if not student_id or student_id == 'nan' or not row['이름'] or str(row['이름']) == 'nan':
                continue
                
            # 문자열로 변환 및 공백 제거
            student_id = str(student_id).strip()
            name = str(row['이름']).strip()
            
            # 유효하지 않은 데이터 건너뛰기
            if not student_id or not name:
                continue
            
            # 공강좌석번호 확인 (간소화된 방식)
            seat = ''
            if '공강좌석번호' in row and row['공강좌석번호'] and str(row['공강좌석번호']) != 'nan':
                seat = str(row['공강좌석번호']).strip()
            
            # 딕셔너리에 추가
            student_data[student_id] = (name, seat)
        
        # 캐시 업데이트
        _student_data_cache = student_data
        _last_student_data_load_time = current_time
            
        return student_data
    except Exception as e:
        logging.error(f"[오류] 학생 정보를 불러올 수 없습니다: {e}")
        # 캐시가 있으면 오류 발생해도 캐시 반환
        if _student_data_cache:
            return _student_data_cache
        # 캐시가 없으면 빈 딕셔너리 반환
        return {}

def check_attendance(student_id, admin_override=False):
    """
    Check if the student has already attended this week or has an active warning
    Returns tuple:
      (already_attended, last_attendance_date, is_warned, warning_info)
      
    이미 출석했거나 경고를 받은 학생은 출석을 제한함
    
    admin_override: 관리자 수동 추가 시 체크를 건너뛰는 옵션
    """
    import time
    # 빠른 경로 처리: 관리자 옵션이나 교사 학번이면 즉시 통과
    
    # 관리자 수동 추가인 경우 체크 건너뛰기 (경고도 무시)
    if admin_override:
        return False, None, False, None
        
    # '3'으로 시작하는 학번은 항상 출석 가능 (경고도 무시)
    if student_id.startswith('3'):
        return False, None, False, None
    
    # 경고 여부 확인 (빠른 경로 확인 후에만 수행)
    start_time = time.time()  # 실행 시작 시간 기록
    is_warned, warning_info = models.is_student_warned(student_id)
    end_time = time.time()
    print(f"[is_student_warned] 실행 시간: {(end_time - start_time)*1000:.2f} ms")
        
    # 경고 받은 경우 출석 차단
    if is_warned:
        return False, None, True, warning_info
    
    # 현재 한국 시간
    now = datetime.now(KST).replace(tzinfo=None)
    
    # 현재 요일 (0: 월요일, 1: 화요일, ..., 6: 일요일)
    current_weekday = now.weekday()
    
    # 이번 주 월요일 계산 (현재가 월요일이면 오늘, 아니면 지난 월요일)
    days_since_monday = current_weekday
    this_week_monday = now - timedelta(days=days_since_monday)
    this_week_monday = this_week_monday.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 이번 주 출석 기록 확인 (단일 쿼리로 처리)
    start_time = time.time()  # 실행 시작 시간 기록
    week_attendance = models.get_recent_attendance_for_week(student_id, this_week_monday)
    end_time = time.time()
    print(f"[get_recent_attendance_for_week] 실행 시간: {(end_time - start_time)*1000:.2f} ms")
    
    # 이번 주 출석 여부
    weekly_attendance_exists = week_attendance is not None
    
    # 최신 출석 날짜 (없으면 최근 7일 기준으로 확인)
    last_attendance = None
    if weekly_attendance_exists:
        last_attendance = week_attendance
    else:
        # 이번 주에 출석하지 않은 경우 최근 출석 기록만 확인
        start_time = time.time()  # 실행 시작 시간 기록
        last_attendance = models.get_recent_attendance(student_id, days=365)
        end_time = time.time()
        print(f"[get_recent_attendance] 실행 시간: {(end_time - start_time)*1000:.2f} ms")
    
    # 날짜를 문자열로 변환
    if last_attendance:
        # Firebase는 datetime 객체를 반환하므로 직접 포맷팅
        date_obj = last_attendance.get('date')
        if isinstance(date_obj, datetime):
            last_date_str = date_obj.strftime('%Y-%m-%d')
        else:
            # 문자열이거나 타임스탬프인 경우
            try:
                if isinstance(date_obj, str):
                    date_obj = datetime.fromisoformat(date_obj)
                last_date_str = date_obj.strftime('%Y-%m-%d')
            except Exception as e:
                logging.error(f"날짜 변환 오류: {e}")
                last_date_str = str(date_obj)
    else:
        last_date_str = None
    
    # 결과 반환 (이번 주 출석 여부, 마지막 출석일, 경고 여부, 경고 정보)
    return weekly_attendance_exists, last_date_str, False, None

# 날짜/시간 처리 헬퍼 함수
def parse_datetime(date_obj):
    """
    여러 형식의 날짜/시간 데이터를 일관된 datetime 객체로 변환
    """
    from datetime import datetime
    
    # 이미 datetime 객체인 경우
    if isinstance(date_obj, datetime):
        result = date_obj
    # 문자열인 경우 
    elif isinstance(date_obj, str):
        try:
            result = datetime.fromisoformat(date_obj)
        except Exception as e:
            logging.error(f"문자열 날짜 변환 실패: {e}")
            return None
    # Firestore 타임스탬프인 경우
    elif hasattr(date_obj, 'timestamp'):
        try:
            result = datetime.fromtimestamp(date_obj.timestamp())
        except Exception as e:
            logging.error(f"타임스탬프 변환 실패: {e}")
            return None
    else:
        logging.error(f"지원되지 않는 날짜 형식: {type(date_obj)}")
        return None
    
    # 타임존 제거 (일관성 유지)
    if result and result.tzinfo:
        result = result.replace(tzinfo=None)
        
    return result

def load_attendance():
    """
    Load all attendance records from Firebase
    Returns a list of dictionaries containing attendance records
    """
    # Firebase에서 출석 정보 로드
    attendances_list = []
    try:
        # 모든 출석 기록 가져오기 (models.py에 별도 함수 추가 필요)
        attendances = []
        
        # Firebase 컬렉션에서 모든 출석 문서 조회
        if models.db:
            attendances_ref = models.db.collection('attendances').order_by('date', direction=models.firestore.Query.DESCENDING).limit(1000).get()
            attendances = [models.firestore_to_dict(doc) for doc in attendances_ref]
        
        for attendance in attendances:
            # 날짜 관련 정보를 모두 가져옴
            # 1. 직접 저장된 시간 문자열
            created_at_str = attendance.get('created_at')
            timestamp_str = attendance.get('timestamp_str')
            
            # 2. 직접 저장된 시간 구성 요소
            time_only = attendance.get('time_only')
            hour = attendance.get('hour')
            minute = attendance.get('minute')
            second = attendance.get('second')
            
            # 3. datetime 객체
            date_obj = attendance.get('date')
            
            # 여러 방법으로 시간 정보 구성 시도 (우선순위 순서대로)
            
            # 케이스 1: 직접 저장된 시간 문자열 사용 (가장 선호)
            if timestamp_str and isinstance(timestamp_str, str):
                date_str = timestamp_str.split()[0]  # YYYY-MM-DD 부분만 추출
                date_time_str = timestamp_str  # 전체 시간 문자열 사용
                logging.info(f"문자열 시간 사용 (timestamp_str): {date_time_str}")
            
            # 케이스 2: created_at 문자열 사용
            elif created_at_str and isinstance(created_at_str, str):
                date_str = created_at_str.split()[0]  # YYYY-MM-DD 부분만 추출
                date_time_str = created_at_str  # 전체 시간 문자열 사용
                logging.info(f"문자열 시간 사용 (created_at): {date_time_str}")
            
            # 케이스 3: 개별 시간 구성 요소로 시간 재구성
            elif date_obj and hour is not None and minute is not None:
                # datetime 객체 우선 확인
                if isinstance(date_obj, datetime):
                    # 기존 date와 저장된 시간 구성요소 조합
                    date_str = date_obj.strftime('%Y-%m-%d')
                    
                    # 초가 있으면 포함, 없으면 00 사용
                    sec = second if second is not None else 0
                    date_time_str = f"{date_str} {hour:02d}:{minute:02d}:{sec:02d}"
                    logging.info(f"구성요소로 시간 재구성: {date_time_str}")
                else:
                    # date가 datetime이 아닌 경우: 하드코딩된 시간 사용
                    date_str = datetime.now().strftime('%Y-%m-%d')
                    date_time_str = f"{date_str} {hour:02d}:{minute:02d}:{second or 0:02d}"
                    logging.info(f"현재 날짜와 저장된 시간 사용: {date_time_str}")
                    
            # 케이스 4: 기존 datetime 객체 사용 (백업)
            else:
                parsed_date = parse_datetime(date_obj)
                
                if parsed_date:
                    date_str = parsed_date.strftime('%Y-%m-%d')
                    
                    # 시간은 현재 시간 사용 (마지막 방안)
                    now = datetime.now()
                    date_time_str = f"{date_str} {now.hour:02d}:{now.minute:02d}:{now.second:02d}"
                    logging.info(f"날짜와 현재 시간 조합: {date_time_str}")
                else:
                    # 최종 방안: 현재 시간 사용
                    now = datetime.now()
                    date_str = now.strftime('%Y-%m-%d')
                    date_time_str = now.strftime('%Y-%m-%d %H:%M:%S')
                    logging.warning(f"기본값으로 현재 시간 사용: {date_time_str}")
            
            # 새 필드 우선 사용
            record = {
                '출석일': date_str,
                '출석일_표시': date_time_str,  # 시간과 초까지 표시 (YYYY-MM-DD HH:MM:SS)
                '교시': attendance.get('period', ''),
                '학번': attendance.get('student_id', ''),
                '이름': attendance.get('name', ''),
                '공강좌석번호': attendance.get('seat', '')
            }
            
            # 디스플레이용 시간 필드가 있으면 추가
            if 'display_time' in attendance:
                record['display_time'] = attendance['display_time']
                
            # 시간만 필드가 있으면 추가
            if 'time_only' in attendance:
                record['time_only'] = attendance['time_only']
                
            attendances_list.append(record)
    except Exception as e:
        logging.error(f"Firebase 출석 기록 로드 오류: {e}")
    
    return attendances_list

def save_attendance(student_id, name, seat):
    """
    Save attendance record to Firebase (with Korean time)
    """
    try:
        # 한국 시간 기준으로 현재 날짜와 시간 저장
        now = datetime.now(KST)
        
        # 현재 시간 직접 기록 (형식화된 문자열)
        current_time_str = now.strftime('%Y-%m-%d %H:%M:%S')
        
        # 시간 저장을 위한 간소화된 접근법 - 직접 문자열로 사용
        hour = now.hour
        minute = now.minute
        second = now.second
        formatted_time = f"{hour:02d}:{minute:02d}:{second:02d}"
        
        # 로그 기록
        logging.info(f"저장할 출석 시간: {current_time_str}")
        
        period = get_current_period()
        period_text = f'{period}교시' if period > 0 else '시간 외'
        
        # 추가 필드를 포함하여 Firebase에 출석 기록 저장
        custom_fields = {
            # 다양한 형식의 시간 저장
            "timestamp_str": current_time_str,
            "time_only": formatted_time,  # 시:분:초만 저장
            "hour": hour,                # 시간만 숫자로 저장 
            "minute": minute,            # 분만 숫자로 저장
            "second": second             # 초만 숫자로 저장
        }
        
        # Firebase에 출석 기록 저장
        doc_id = models.add_attendance(student_id, name, seat, period_text, custom_fields)
        
        if doc_id:
            logging.info(f"출석 기록 성공: {current_time_str}")
            return True
        else:
            # 이미 있는 경우 (중복 출석 등) - 경고 메시지 없이 성공으로 처리
            return True
    except Exception as e:
        logging.error(f"출석 기록 저장 중 오류 발생: {e}")
        flash(f"⚠️ 오류가 발생했습니다: {str(e)}", "danger")
        return False

@app.route('/favicon.ico')
def favicon():
    """Serve favicon.ico"""
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/', methods=['GET', 'POST'])
def attendance():
    """Main attendance page and form submission handler"""
    if request.method == 'POST':
        # 현재 교시 확인
        current_period = get_current_period()
        
        # 출석 가능 시간이 아닌 경우
        if current_period == 0:
            flash("⚠️ 지금은 도서실 이용 시간이 아닙니다.", "danger")
            return redirect('/')
            
        # 현재 교시 출석 인원 확인 (최대 35명)
        MAX_CAPACITY = 35
        current_count = get_current_period_attendance_count()
        
        # 수용 인원 초과 시 출석 불가
        if current_count >= MAX_CAPACITY:
            flash("⚠️ 도서실 수용인원이 초과되었습니다(30명). 4층 공강실로 올라가주세요!", "danger")
            return redirect('/')
            
        student_id = request.form['student_id'].strip()
        name = request.form['name'].strip()

        # Load student data
        student_data = load_student_data()
        student_info = student_data.get(student_id)

        # Validate student information
        if student_info is None:
            flash("❌ 학번이 올바르지 않습니다. 다시 확인해주세요.", "danger")
        elif student_info[0].replace(' ', '') != name.replace(' ', ''):
            flash("❌ 입력한 이름이 학번과 일치하지 않습니다.", "danger")
        elif check_attendance(student_id, admin_override=False)[0]:  # 메인 페이지에선 항상 admin_override=False로 체크
            # 메인 출석 페이지에서는 관리자 여부와 관계없이 중복 출석을 금지
            # 관리자는 별도의 추가 출석 페이지를 통해서만 추가 출석 처리 가능
            if session.get('admin'):
                flash("⚠️ 이번 주에 이미 출석했습니다. 일주일에 한 번만 출석 가능합니다. 4층 공강실로 올라가주세요!", "warning")
            else:
                flash("⚠️ 이번 주에 이미 출석하셨습니다. 4층 공강실로 올라가주세요!", "warning")
            # 출석 거부 강화 - 바로 리다이렉트
            return redirect(url_for('attendance'))
        else:
            seat = student_info[1]
            if save_attendance(student_id, name, seat):
                flash(f"✅ 출석이 완료되었습니다. 공강좌석번호: {seat}", "success")
        return redirect(url_for('attendance'))
        
    return render_template('attendance.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    # 이미 로그인 되어 있으면 교시별 출석현황 페이지로 바로 리다이렉트
    if session.get('admin'):
        return redirect('/by_period')
        
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/by_period')
        else:
            flash('❌ 비밀번호가 틀렸습니다.', "danger")
    return render_template('admin_login.html')

@app.route('/list')
def list_attendance():
    """List all attendance records (admin only)"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
    records = load_attendance()
    
    # 출석일 날짜를 ISO 형식 (YYYY-MM-DD HH:MM:SS)으로 표시
    for record in records:
        date_str = record.get('출석일', '')
        if date_str:
            try:
                # 이미 ISO 형식이면 그대로 사용
                if ' ' in date_str and len(date_str.split(' ')[1].split(':')) == 3:
                    record['출석일_표시'] = date_str
                    # 날짜 객체도 저장 (정렬용)
                    record['_출석일_객체'] = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                else:
                    # 날짜만 있는 경우 (YYYY-MM-DD)
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        record['출석일_표시'] = date_obj.strftime('%Y-%m-%d %H:%M:%S')
                        record['_출석일_객체'] = date_obj
                    except ValueError:
                        # 파싱 실패 시 원본 그대로 사용
                        record['출석일_표시'] = date_str
                        record['_출석일_객체'] = datetime.now() - timedelta(days=365)  # 1년 전 날짜로 설정
            except Exception:
                # 모든 처리 실패 시 원본 그대로 사용
                record['출석일_표시'] = date_str
                record['_출석일_객체'] = datetime.now() - timedelta(days=365)  # 1년 전 날짜로 설정
        else:
            record['출석일_표시'] = ''
            record['_출석일_객체'] = datetime.now() - timedelta(days=365)  # 1년 전 날짜로 설정
    
    # 출석일 내림차순으로 정렬 (최신 출석이 맨 위로)
    records.sort(key=lambda x: x['_출석일_객체'], reverse=True)
    
    return render_template('list.html', records=records)

@app.route('/export')
def export_csv():
    """Export attendance records as CSV (admin only) with proper UTF-8 encoding"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
        
    # 임시 CSV 파일 생성 (UTF-8 with BOM 인코딩)
    temp_file = 'temp_export.csv'
    try:
        # 데이터베이스에서 모든 출석 기록 가져오기
        attendances = load_attendance()
        
        # 데이터가 없는 경우 처리
        if not attendances:
            flash("내보낼 출석 기록이 없습니다.", "warning")
            return redirect(url_for('list_attendance'))
            
        # 헤더 설정
        fieldnames = ['출석일', '교시', '학번', '이름', '공강좌석번호']
        
        # 데이터 준비
        data = [fieldnames]  # 헤더 행
        for record in attendances:
            row = [record['출석일'], record['교시'], record['학번'], record['이름'], record['공강좌석번호']]
            data.append(row)
            
        # UTF-8 with BOM으로 임시 파일 작성
        with open(temp_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            writer.writerows(data)
            
        # 파일 전송 (한글 파일명 사용)
        response = send_file(
            temp_file, 
            as_attachment=True, 
            download_name="도서실_출석기록.csv",
            mimetype='text/csv'
        )
        
        # 파일 전송 후 임시 파일 삭제 (함수를 응답 콜백에 등록)
        @after_this_request
        def remove_temp_file(response):
            if os.path.exists(temp_file):
                os.remove(temp_file)
            return response
        
        return response
    except Exception as e:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        logging.error(f"CSV 내보내기 중 오류 발생: {e}")
        flash(f"CSV 파일 생성 중 오류가 발생했습니다: {e}", "danger")
        return redirect('/list')

@app.route('/print')
def print_view():
    """Printable view of attendance records (admin only)"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
    records = load_attendance()
    
    # 출석일 날짜를 ISO 형식 (YYYY-MM-DD HH:MM:SS)으로 표시
    for record in records:
        date_str = record.get('출석일', '')
        if date_str:
            try:
                # 이미 ISO 형식이면 그대로 사용
                if ' ' in date_str and len(date_str.split(' ')[1].split(':')) == 3:
                    record['출석일_표시'] = date_str
                else:
                    # 날짜만 있는 경우 (YYYY-MM-DD)
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        record['출석일_표시'] = date_obj.strftime('%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        # 파싱 실패 시 원본 그대로 사용
                        record['출석일_표시'] = date_str
            except Exception:
                # 모든 처리 실패 시 원본 그대로 사용
                record['출석일_표시'] = date_str
        else:
            record['출석일_표시'] = ''
    
    return render_template('print.html', records=records)

@app.route('/stats')
def stats():
    """Show attendance statistics (admin only)"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
    records = load_attendance()
    counts = Counter(r['이름'] for r in records)
    sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return render_template('stats.html', attendance_counts=sorted_counts)
    
@app.route('/by_period')
def by_period():
    """교시별 출석 현황 보기 (admin only)"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
        
    records = load_attendance()
    memos = load_period_memos()  # 모든 메모 로드
    
    # 교시별로만 학생 데이터 그룹화 (날짜는 개별 학생 카드에만 표시)
    period_groups = {}
    
    for record in records:
        period = record.get('교시', '시간 외')
        date = record.get('출석일', '날짜 없음')
        
        # 날짜 형식 변환 (YYYY-MM-DD -> n월n일) - 시, 분, 초 제거
        if date != '날짜 없음':
            try:
                # 날짜 형식에 시간이 포함되어 있으면 제거
                if 'T' in date or ' ' in date:
                    # 날짜가 ISO 형식 (예: 2023-05-01T12:30:00) 또는 일반 형식 (예: 2023-05-01 12:30:00)인 경우
                    date_parts = date.split('T') if 'T' in date else date.split(' ')
                    date = date_parts[0]  # 날짜 부분만 유지 (YYYY-MM-DD)
                
                # 날짜 객체로 변환
                date_obj = datetime.strptime(date, "%Y-%m-%d")
                # 월, 일만 표시 (n월n일 형식)
                date_md = f"{date_obj.month}월{date_obj.day}일"
                # 원래 날짜도 저장 (정렬용)
                original_date = date_obj
                # 메모 검색을 위한 원본 날짜 문자열 - 시간 정보 없이 YYYY-MM-DD 형식으로 저장
                original_date_str = date_obj.strftime('%Y-%m-%d')
            except ValueError:
                date_md = date
                original_date = datetime(1900, 1, 1)  # 날짜 변환 실패시 고정 날짜로
                original_date_str = date
        else:
            date_md = date
            original_date = datetime(1900, 1, 1)  # 날짜 없음은 고정 날짜로
            original_date_str = date
        
        # 원본 기록에 날짜 정보 추가
        record_copy = record.copy()
        record_copy['날짜_md'] = date_md
        record_copy['원본_날짜'] = original_date  # 정렬용 원본 날짜 저장
        record_copy['원본_날짜_문자열'] = original_date_str  # 메모 검색용 원본 날짜 문자열
        
        # 날짜와 교시를 조합하여 키 생성 (예: "5월7일 6교시")
        period_num = int(period[0]) if period and period[0].isdigit() else 999
        
        # 교시만 키로 사용하는 것이 아니라, 날짜+교시로 새로운 키 생성
        new_period_key = f"{date_md} {period}"
        
        if new_period_key not in period_groups:
            # 이 교시에 대한 메모 찾기
            memo_text = ""
            for memo in memos:
                if memo['날짜'] == original_date_str and memo['교시'] == period:
                    memo_text = memo['메모']
                    break
                    
            period_groups[new_period_key] = {
                '학생_목록': [],
                '교시_번호': period_num,
                '메모': memo_text,
                '날짜': original_date_str,
                '교시': period
            }
        
        period_groups[new_period_key]['학생_목록'].append(record_copy)
    
    # 최근 날짜가 먼저 나오도록 정렬하고, 같은 날짜 내에서는 교시 번호가 큰 순서대로 정렬
    sorted_periods = sorted(
        period_groups.keys(), 
        key=lambda p: (
            # 날짜 추출 (기본 형식: "n월n일 m교시")
            # 각 교시에 속한 가장 최근 날짜를 기준으로 정렬 (내림차순)
            -1 * max([r['원본_날짜'].timestamp() for r in period_groups[p]['학생_목록']]) if period_groups[p]['학생_목록'] else 0,
            # 같은 날짜면 교시 번호 내림차순 (큰 교시 먼저)
            -period_groups[p]['교시_번호']
        )
    )
    
    # 각 교시 내에서 학생을 날짜 최신순, 이름으로 정렬
    for period in period_groups:
        period_groups[period]['학생_목록'] = sorted(
            period_groups[period]['학생_목록'], 
            key=lambda r: (-1 * r['원본_날짜'].timestamp(), r['이름'])
        )
    
    return render_template('by_period.html', period_groups=period_groups, sorted_periods=sorted_periods)
    
@app.route('/save_memo', methods=['POST'])
def save_memo():
    """교시별 메모 저장 API"""
    if not session.get('admin'):
        return jsonify({'success': False, 'error': '관리자 권한이 필요합니다.'}), 403
        
    try:
        data = request.get_json()
        date = data.get('date')
        period = data.get('period')
        memo_text = data.get('memo', '')
        
        if not date or not period:
            return jsonify({'success': False, 'error': '날짜와 교시 정보가 필요합니다.'}), 400
            
        # 메모 저장
        if save_period_memo(date, period, memo_text):
            return jsonify({'success': True, 'message': '메모가 저장되었습니다.'})
        else:
            return jsonify({'success': False, 'error': '메모 저장 중 오류가 발생했습니다.'}), 500
            
    except Exception as e:
        logging.error(f"메모 저장 중 오류 발생: {e}")
        return jsonify({'success': False, 'error': f'오류: {str(e)}'}), 500

@app.route('/delete_records', methods=['POST'])
def delete_records():
    """Delete selected attendance records (admin only)"""
    if not session.get('admin'):
        return jsonify({'success': False, 'error': '관리자 권한이 필요합니다.'}), 403
    
    try:
        # 삭제할 기록 받기
        data = request.get_json()
        records_to_delete = data.get('records', [])
        
        if not records_to_delete:
            return jsonify({'success': False, 'error': '삭제할 기록이 선택되지 않았습니다.'}), 400
        
        # 데이터베이스에서 학생 기록 삭제 처리
        deleted_count = 0
        
        for record in records_to_delete:
            # JSON 형식으로 받은 경우 (교시별 보기 페이지에서 삭제 시)
            student_id = record.get('student_id')
            date_str = record.get('date')
            
            if student_id and date_str:
                # 해당 학생의 해당 날짜 출석 기록 찾기
                try:
                    # 날짜 형식이 다양할 수 있으므로 여러 형식 시도
                    try:
                        # 기본 날짜 형식 (YYYY-MM-DD)
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    except ValueError:
                        try:
                            # 시간 정보가 포함된 형식 (YYYY-MM-DD HH:MM:SS)
                            date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            # ISO 형식 (YYYY-MM-DDT00:00:00)
                            date_parts = date_str.split('T')[0] if 'T' in date_str else date_str.split()[0]
                            date_obj = datetime.strptime(date_parts, '%Y-%m-%d')
                    
                    # 날짜만 추출하여 당일 00:00:00부터 다음날 00:00:00 사이의 기록 조회
                    start_of_day = datetime(date_obj.year, date_obj.month, date_obj.day, 0, 0, 0)
                    next_day = start_of_day + timedelta(days=1)
                    
                    # Firebase에서 해당 날짜의 해당 학생 기록 조회
                    # 이를 위해 models에 새 함수를 사용하거나 직접 구현
                    try:
                        # Firebase에서 모든 출석 문서 가져오기
                        if models.db:
                            attendances_ref = models.db.collection('attendances')
                            
                            # 필터링: 해당 학생 ID + 해당 날짜 범위 (FieldFilter 사용)
                            query = attendances_ref.where(
                                filter=models.firestore.FieldFilter("student_id", "==", student_id)
                            ).where(
                                filter=models.firestore.FieldFilter("date", ">=", start_of_day)
                            ).where(
                                filter=models.firestore.FieldFilter("date", "<", next_day)
                            ).get()
                            
                            # 각 결과 문서에 대해 삭제 처리
                            for doc in query:
                                # 문서 ID로 삭제
                                models.delete_attendance(doc.id)
                                deleted_count += 1
                                logging.info(f"Firebase에서 기록 삭제됨: 학번={student_id}, 문서ID={doc.id}, 날짜={date_str}")
                    except Exception as fb_error:
                        logging.error(f"Firebase 조회/삭제 중 오류: {fb_error}")
                except Exception as db_error:
                    logging.error(f"특정 기록 삭제 중 오류: {db_error}")
        
        # 삭제 결과 반환
        logging.info(f"총 {deleted_count}개의 기록이 삭제되었습니다.")
        return jsonify({
            'success': True, 
            'message': f'{deleted_count}개의 기록이 삭제되었습니다.',
            'deleted_count': deleted_count
        })
    
    except Exception as e:
        logging.error(f"Error deleting records: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin_add_attendance', methods=['GET', 'POST'])
def admin_add_attendance():
    """관리자용 추가 출석 페이지"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
        
    student_info = None
    attended = False
    last_attendance_date = None
    override = False
    
    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        override = 'override_check' in request.form
        
        if student_id:
            # 학생 데이터 로드
            student_data = load_student_data()
            student = student_data.get(student_id)
            
            if student:
                # 출석 여부 확인 (경고 정보 포함)
                already_attended, attendance_date, is_warned, warning_info = check_attendance(student_id)
                
                student_info = {
                    'id': student_id,
                    'name': student[0],
                    'seat': student[1],
                    'is_warned': is_warned,
                    'warning_info': warning_info
                }
                
                attended = already_attended
                last_attendance_date = attendance_date
            else:
                flash("❌ 입력한 학번을 찾을 수 없습니다.", "danger")
        else:
            flash("❌ 학번을 입력해주세요.", "danger")
    
    return render_template(
        'admin_add_attendance.html', 
        student_info=student_info, 
        attended=attended, 
        last_attendance_date=last_attendance_date,
        override=override
    )

@app.route('/admin_add_attendance/confirm', methods=['POST'])
def admin_add_attendance_confirm():
    """관리자용 추가 출석 확인 처리"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
        
    student_id = request.form.get('student_id', '').strip()
    name = request.form.get('name', '').strip()
    seat = request.form.get('seat', '').strip()
    override = request.form.get('override') == '1'
    
    # 학생 데이터 로드 및 검증
    student_data = load_student_data()
    student = student_data.get(student_id)
    
    if not student:
        flash("❌ 입력한 학번을 찾을 수 없습니다.", "danger")
        return redirect('/admin_add_attendance')
        
    if student[0].replace(' ', '') != name.replace(' ', ''):
        flash("❌ 입력한 이름이 학번과 일치하지 않습니다.", "danger")
        return redirect('/admin_add_attendance')
    
    # 출석 여부 확인 (경고 정보 포함)
    # override 체크 여부에 따라 admin_override 파라미터 결정
    already_attended, last_attendance_date, is_warned, warning_info = check_attendance(student_id, admin_override=override)
    
    # 경고 받은 학생 정보 표시 (관리자는 등록 허용)
    if is_warned:
        if warning_info:
            # Firebase에서 가져온 데이터는 딕셔너리 형태
            expiry_date_obj = warning_info.get('expiry_date')
            
            # datetime 객체로 변환하여 포맷팅
            if isinstance(expiry_date_obj, datetime):
                expiry_date = expiry_date_obj.strftime('%Y년 %m월 %d일')
            else:
                # 문자열이나 타임스탬프인 경우
                try:
                    if isinstance(expiry_date_obj, str):
                        expiry_date_obj = datetime.fromisoformat(expiry_date_obj)
                    expiry_date = expiry_date_obj.strftime('%Y년 %m월 %d일')
                except Exception as e:
                    logging.error(f"경고일자 변환 오류: {e}")
                    expiry_date = str(expiry_date_obj)
                    
            reason = warning_info.get('reason') or "도서실 이용 규정 위반"
            flash(f"⚠️ 이 학생은 도서실 이용이 제한된 상태입니다. (사유: {reason}, 해제일: {expiry_date}) 관리자 권한으로 출석이 가능합니다.", "warning")
        else:
            flash("⚠️ 이 학생은 도서실 이용이 제한된 상태입니다. 관리자 권한으로 출석이 가능합니다.", "warning")
    
    # 이미 출석했고 override 체크가 안 되어 있으면 중복 출석 방지
    if already_attended and not override:
        flash("⚠️ 이 학생은 이번 주에 이미 출석했습니다. 중복 출석을 허용하려면 '중복 출석 허용' 체크박스를 선택해주세요.", "warning")
        return redirect('/admin_add_attendance')
    
    # 출석 저장
    if save_attendance(student_id, name, seat):
        # 중복 출석인 경우 추가 메시지
        if already_attended:
            flash(f"✅ 관리자 권한으로 추가 출석이 완료되었습니다. 학번: {student_id}, 이름: {name}", "success")
        else:
            flash(f"✅ 출석이 완료되었습니다. 학번: {student_id}, 이름: {name}", "success")
    else:
        flash("❌ 출석 저장 중 오류가 발생했습니다.", "danger")
    
    return redirect('/admin_add_attendance')

@app.route('/admin/warnings')
def admin_warnings():
    """경고 학생 관리 페이지 (관리자만 접근 가능)"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
        
    # Firebase에서 모든 경고 목록 조회
    warnings = []
    try:
        # models.py에서 warnings 컬렉션 쿼리
        if models.db:
            warnings_ref = models.db.collection('warnings').order_by('warning_date', direction=models.firestore.Query.DESCENDING).get()
            warnings = [models.firestore_to_dict(doc) for doc in warnings_ref]
            
            # 문서 ID도 포함시키기
            for i, warning in enumerate(warnings):
                warnings[i]['id'] = warnings_ref[i].id
    except Exception as e:
        logging.error(f"경고 목록 조회 중 오류 발생: {e}")
    
    return render_template(
        'admin_warnings.html',
        warnings=warnings,
        now_datetime=datetime.utcnow()  # 현재 시간 전달 (만료 여부 확인용)
    )

@app.route('/admin/warnings/add', methods=['POST'])
def add_warning():
    """학생 경고 추가 처리"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
        
    student_id = request.form.get('student_id', '').strip()
    student_name = request.form.get('student_name', '').strip()
    days = int(request.form.get('days', 30))
    reason = request.form.get('reason', '').strip()
    
    if not student_id or not student_name:
        flash("학번과 이름을 모두 입력해주세요.", "danger")
        return redirect('/admin/warnings')
        
    # 유효한 학생인지 확인
    student_data = load_student_data()
    if student_id not in student_data:
        flash("존재하지 않는 학번입니다.", "danger")
        return redirect('/admin/warnings')
        
    # 경고 추가
    warning_id = models.add_warning(student_id, student_name, days, reason)
    
    if warning_id:
        flash(f"{student_name}({student_id}) 학생에게 {days}일간의 도서실 이용 제한이 추가되었습니다.", "success")
    else:
        flash("경고 추가 중 오류가 발생했습니다.", "danger")
        
    return redirect('/admin/warnings')

@app.route('/admin/warnings/remove/<warning_id>', methods=['POST'])
def remove_warning(warning_id):
    """학생 경고 해제 처리"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
        
    # 경고 해제
    if models.remove_warning(warning_id):
        flash("경고가 해제되었습니다.", "success")
    else:
        flash("경고 해제 중 오류가 발생했습니다.", "danger")
        
    return redirect('/admin/warnings')

@app.route('/admin/warnings/delete/<warning_id>', methods=['POST'])
def delete_warning(warning_id):
    """학생 경고 완전 삭제 처리"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
        
    # 경고 완전 삭제
    if models.delete_warning(warning_id):
        flash("경고가 완전히 삭제되었습니다.", "success")
    else:
        flash("경고 삭제 중 오류가 발생했습니다.", "danger")
        
    return redirect('/admin/warnings')

@app.route('/admin/warnings/delete-all', methods=['POST'])
def delete_all_warnings():
    """모든 경고 삭제 처리"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
        
    # 모든 경고 삭제
    if models.delete_all_warnings():
        flash("모든 경고가 삭제되었습니다.", "success")
    else:
        flash("경고 삭제 중 오류가 발생했습니다.", "danger")
        
    return redirect('/admin/warnings')

@app.route('/logout')
def logout():
    """Logout from admin"""
    session.pop('admin', None)
    flash("로그아웃 되었습니다.", "success")
    return redirect('/')
@app.route('/lookup_name')
def lookup_name():
    """
    학생 정보 조회 API - 최적화 버전
    """
    # 학생 ID를 가져오고 캐싱된 학생 데이터에서 정보 검색
    student_id = request.args.get('student_id')
    
    # 빠른 경로: 학생 ID가 없거나 유효하지 않은 경우 즉시 오류 반환
    if not student_id:
        return jsonify({'success': False, 'message': '유효한 학번을 입력해주세요.'})
    
    # 학생 정보 가져오기 (캐싱된 데이터)
    student_data = load_student_data()
    student_info = student_data.get(student_id)

    # 학생 정보가 있는 경우
    if student_info:
        name = student_info[0]
        seat = student_info[1] if len(student_info) > 1 else None
        
        # 빠른 경로 처리: 교사 학번
        if student_id.startswith('3'):
            return jsonify({
                'success': True, 
                'name': name, 
                'seat': seat,
                'already_attended': False,
                'last_attendance_date': None,
                'capacity_exceeded': False,
                'is_warned': False,
                'warning_expiry': None,
                'warning_message': None
            })
            
        # 초기값 설정
        already_attended = False
        last_attendance_date_str = None
        is_warned = False
        warning_info = None
        current_period = get_current_period()
        capacity_exceeded = False
        
        # 병렬 처리를 위한 멀티스레딩 사용 없이 최적화
        # 필요한 정보만 쿼리 (불필요한 처리 제거)
        
        # 1. 경고 정보 확인 (가장 빠른 쿼리)
        is_warned, warning_info = models.is_student_warned(student_id)
        
        # 2. 경고가 없는 경우에만 출석 정보 확인
        if not is_warned:
            # 현재 한국 시간
            now = datetime.now(KST).replace(tzinfo=None)
            current_weekday = now.weekday()
            
            # 이번 주 월요일 계산
            days_since_monday = current_weekday
            this_week_monday = now - timedelta(days=days_since_monday)
            this_week_monday = this_week_monday.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # 이번 주 출석 여부 확인 (단일 쿼리)
            week_attendance = models.get_recent_attendance_for_week(student_id, this_week_monday)
            already_attended = week_attendance is not None
            
            # 출석 기록이 있는 경우
            if already_attended and week_attendance:
                # Firebase는 딕셔너리로 데이터 반환
                date_obj = week_attendance.get('date')
                if isinstance(date_obj, datetime):
                    last_attendance_date_str = date_obj.strftime('%Y년 %m월 %d일')
                else:
                    # 문자열이나 타임스탬프인 경우 변환
                    try:
                        if isinstance(date_obj, str):
                            date_obj = datetime.fromisoformat(date_obj)
                        last_attendance_date_str = date_obj.strftime('%Y년 %m월 %d일')
                    except Exception as e:
                        logging.error(f"날짜 변환 오류: {e}")
                        last_attendance_date_str = str(date_obj)
            else:
                # 최근 출석 정보 확인 (없을 수도 있음)
                last_attendance = models.get_recent_attendance(student_id, days=365)
                if last_attendance:
                    # Firebase는 딕셔너리로 데이터 반환
                    date_obj = last_attendance.get('date')
                    if isinstance(date_obj, datetime):
                        last_attendance_date_str = date_obj.strftime('%Y년 %m월 %d일')
                    else:
                        # 문자열이나 타임스탬프인 경우 변환
                        try:
                            if isinstance(date_obj, str):
                                date_obj = datetime.fromisoformat(date_obj)
                            last_attendance_date_str = date_obj.strftime('%Y년 %m월 %d일')
                        except Exception as e:
                            logging.error(f"날짜 변환 오류: {e}")
                            last_attendance_date_str = str(date_obj)
            
            # 3. 수용 인원 확인 (다른 조건 확인 후에만)
            if current_period > 0 and not already_attended:
                # 출석 가능한 경우에만 인원 확인
                MAX_CAPACITY = 35
                current_count = get_current_period_attendance_count()
                capacity_exceeded = current_count >= MAX_CAPACITY
        
        # 경고 정보 처리
        warning_message = None
        warning_expiry = None
        if is_warned and warning_info:
            # Firebase는 딕셔너리로 데이터 반환
            expiry_date_obj = warning_info.get('expiry_date')
            
            # datetime 객체로 변환하여 포맷팅
            if isinstance(expiry_date_obj, datetime):
                warning_expiry = expiry_date_obj.strftime('%Y년 %m월 %d일')
            else:
                # 문자열이나 타임스탬프인 경우
                try:
                    if isinstance(expiry_date_obj, str):
                        expiry_date_obj = datetime.fromisoformat(expiry_date_obj)
                    warning_expiry = expiry_date_obj.strftime('%Y년 %m월 %d일')
                except Exception as e:
                    logging.error(f"경고일자 변환 오류: {e}")
                    warning_expiry = str(expiry_date_obj)
                    
            warning_message = warning_info.get('reason') or "도서실 이용 규정 위반"
        
        # 최종 결과 반환
        return jsonify({
            'success': True,
            'name': name,
            'seat': seat,
            'already_attended': already_attended,
            'last_attendance_date': last_attendance_date_str,
            'capacity_exceeded': capacity_exceeded,
            'is_warned': is_warned,
            'warning_expiry': warning_expiry,
            'warning_message': warning_message
        })
    else:
        return jsonify({'success': False, 'message': '학번이 존재하지 않습니다.'})

@app.route('/delete_before_date', methods=['GET', 'POST'])
def delete_before_date():
    """특정 날짜 이전의 모든 출석 기록 삭제 (관리자 전용)"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
    
    if request.method == 'POST':
        date_str = request.form.get('delete_date')
        if not date_str:
            flash("삭제할 기준 날짜를 입력해주세요.", "warning")
            return redirect('/by_period')
            
        try:
            # 기준 날짜 파싱 - 입력 날짜는 ISO 형식(YYYY-MM-DD)이어야 함
            cutoff_date = datetime.strptime(date_str, '%Y-%m-%d')
            
            # 자정(00:00:00)으로 시간 설정
            cutoff_date = datetime(cutoff_date.year, cutoff_date.month, cutoff_date.day, 0, 0, 0)
            
            # Firebase에서 기준 날짜 이전의 출석 레코드 조회
            delete_count = 0
            
            try:
                # Firebase에서 모든 출석 레코드 가져오기
                if models.db:
                    attendances_ref = models.db.collection('attendances')
                    
                    # 날짜로 필터링 (Firebase는 완전히 동일한 방식으로 필터링이 어려움)
                    # 모든 레코드를 가져와 Python에서 필터링
                    all_records = attendances_ref.get()
                    
                    # 문서 ID 리스트와 로그용 정보 생성
                    to_delete_ids = []
                    
                    for doc in all_records:
                        record = doc.to_dict()
                        date_val = record.get('date')
                        
                        # 날짜 객체 검증 및 변환
                        if date_val and isinstance(date_val, datetime):
                            if date_val < cutoff_date:
                                to_delete_ids.append(doc.id)
                                logging.info(f"Marking for deletion: 학번={record.get('student_id')}, 날짜={date_val}, 문서ID={doc.id}")
                    
                    # 삭제할 레코드 개수 확인
                    delete_count = len(to_delete_ids)
                    
                    # 배치로 삭제 처리 (많은 양의 데이터 효율적 처리)
                    if delete_count > 0:
                        # 배치 크기 제한 (500개씩)
                        batch_size = 500
                        for i in range(0, delete_count, batch_size):
                            batch = models.db.batch()
                            batch_ids = to_delete_ids[i:i+batch_size]
                            
                            for doc_id in batch_ids:
                                doc_ref = attendances_ref.document(doc_id)
                                batch.delete(doc_ref)
                                
                            # 배치 커밋
                            batch.commit()
                            logging.info(f"Batch delete completed: {len(batch_ids)} records")
            except Exception as e:
                logging.error(f"Firebase 대량 삭제 오류: {e}")
                flash(f"삭제 중 오류가 발생했습니다: {str(e)}", "danger")
                return redirect('/by_period')
                
                logging.info(f"Deleted {delete_count} records before {date_str}")
                flash(f"✅ {date_str} 이전의 {delete_count}개 출석 기록이 삭제되었습니다.", "success")
            else:
                flash(f"⚠️ {date_str} 이전의 출석 기록이 없습니다.", "warning")
                
        except ValueError as e:
            flash(f"❌ 날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식으로 입력해주세요: {e}", "danger")
        except Exception as e:
            logging.error(f"Error deleting records before date: {e}")
            flash(f"❌ 출석 기록 삭제 중 오류가 발생했습니다: {e}", "danger")
            
    # GET 요청 시 또는 POST 처리 후 페이지로 리다이렉트
    return redirect('/by_period')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
