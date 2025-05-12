from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, jsonify, after_this_request, send_from_directory
from datetime import datetime, timedelta
import pandas as pd
import csv
import os
import logging
import pytz
from collections import Counter

# 한국 시간대 설정
KST = pytz.timezone('Asia/Seoul')

# Set up logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "fallback_secret_key_for_development")

# 데이터베이스 설정
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///attendance.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# 데이터베이스 초기화 (models.py에서 db 객체 가져오기)
from models import db, Warning

# 데이터베이스 초기화
db.init_app(app)

# 데이터베이스 테이블 생성
with app.app_context():
    db.create_all()

# Add datetime functions to templates
@app.context_processor
def inject_now():
    # 항상 한국 시간을 사용하여 현재 시간 및 연도 반환
    now = datetime.now(KST).replace(tzinfo=None)
    return {
        'now': lambda: now,
        'current_year': now.year
    }

# File configurations
FILENAME = 'attendance.csv'
BACKUP_FILE = 'attendance_backup.csv'
LOG_FILE = 'attendance_error.log'
EXCEL_FRIENDLY_FILE = 'attendance_excel.csv'
STUDENT_FILE = 'students.xlsx'
MEMO_FILE = 'period_memos.csv'
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

# Initialize the files if they don't exist
def initialize_files():
    # 기본 파일과 백업 파일은 UTF-8로 저장
    for file in [FILENAME, BACKUP_FILE]:
        if not os.path.exists(file):
            try:
                with open(file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['출석일', '교시', '학번', '이름', '공강좌석번호'])
                logging.info(f"Created file: {file}")
            except Exception as e:
                logging.error(f"Error creating file {file}: {e}")
    
    # 기본 파일이 있고 Excel 호환 파일이 없으면 Excel 호환 파일 생성
    if os.path.exists(FILENAME) and not os.path.exists(EXCEL_FRIENDLY_FILE):
        try:
            # 기존 기록 읽기
            with open(FILENAME, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                all_records = list(reader)
                
            # Excel용 파일 생성 (UTF-8-SIG/BOM 포함)
            with open(EXCEL_FRIENDLY_FILE, 'w', newline='', encoding='utf-8-sig') as f:
                fieldnames = ['출석일', '교시', '학번', '이름', '공강좌석번호']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_records)
            logging.info(f"Created Excel-friendly file with {len(all_records)} records: {EXCEL_FRIENDLY_FILE}")
        except Exception as e:
            logging.error(f"Error creating Excel-friendly file from existing records {EXCEL_FRIENDLY_FILE}: {e}")
    # Excel 파일이 있는데 기본 파일이 없으면 기본 파일 생성
    elif not os.path.exists(FILENAME) and os.path.exists(EXCEL_FRIENDLY_FILE):
        try:
            # 엑셀 파일 읽기
            with open(EXCEL_FRIENDLY_FILE, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                all_records = list(reader)
                
            # 기본 파일 생성
            with open(FILENAME, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['출석일', '교시', '학번', '이름', '공강좌석번호']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_records)
            logging.info(f"Created main attendance file from Excel file with {len(all_records)} records: {FILENAME}")
        except Exception as e:
            logging.error(f"Error creating main file from Excel records {FILENAME}: {e}")
    # 둘 다 있으면 일관성 체크 및 동기화
    elif os.path.exists(FILENAME) and os.path.exists(EXCEL_FRIENDLY_FILE):
        try:
            # 두 파일 모두 읽기
            with open(FILENAME, 'r', newline='', encoding='utf-8') as f1:
                reader1 = csv.DictReader(f1)
                main_records = list(reader1)
                
            with open(EXCEL_FRIENDLY_FILE, 'r', newline='', encoding='utf-8-sig') as f2:
                reader2 = csv.DictReader(f2)
                excel_records = list(reader2)
                
            # 레코드 수가 다르면 기본 파일 기준으로 Excel 파일 업데이트
            if len(main_records) != len(excel_records):
                logging.warning(f"Record count mismatch: main={len(main_records)}, excel={len(excel_records)}. Syncing...")
                with open(EXCEL_FRIENDLY_FILE, 'w', newline='', encoding='utf-8-sig') as f:
                    fieldnames = ['출석일', '교시', '학번', '이름', '공강좌석번호']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(main_records)
                logging.info(f"Updated Excel-friendly file with {len(main_records)} records")
        except Exception as e:
            logging.error(f"Error checking file consistency: {e}")
    # 둘 다 없으면 빈 파일 생성
    else:
        try:
            # Excel용 파일 생성 (UTF-8-SIG/BOM 포함)
            with open(EXCEL_FRIENDLY_FILE, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['출석일', '교시', '학번', '이름', '공강좌석번호'])
            logging.info(f"Created empty Excel-friendly file: {EXCEL_FRIENDLY_FILE}")
        except Exception as e:
            logging.error(f"Error creating Excel-friendly file {EXCEL_FRIENDLY_FILE}: {e}")
            
    # 교시별 메모 파일 초기화
    if not os.path.exists(MEMO_FILE):
        try:
            with open(MEMO_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['날짜', '교시', '메모'])
            logging.info(f"Created memo file: {MEMO_FILE}")
        except Exception as e:
            logging.error(f"Error creating memo file {MEMO_FILE}: {e}")

# 교시별 메모 저장 함수
def save_period_memo(date, period, memo_text):
    """
    교시별 메모를 저장하는 함수
    """
    file_exists = os.path.exists(MEMO_FILE)
    fieldnames = ['날짜', '교시', '메모']
    
    # 이미 존재하는 같은 날짜/교시의 메모가 있는지 확인
    existing_memos = load_period_memos()
    updated = False
    
    # 파일이 이미 있는 경우, 기존 메모를 업데이트하고 새 파일로 저장
    if file_exists:
        with open(MEMO_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        for row in rows:
            if row['날짜'] == date and row['교시'] == period:
                row['메모'] = memo_text
                updated = True
                break
                
        if not updated:
            rows.append({'날짜': date, '교시': period, '메모': memo_text})
            
        # 메모 파일 덮어쓰기
        with open(MEMO_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        # 파일이 없는 경우, 새로 생성하고 메모 추가
        with open(MEMO_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow({'날짜': date, '교시': period, '메모': memo_text})
    
    return True

# 모든 교시별 메모 로드 함수
def load_period_memos():
    """
    모든 교시별 메모를 로드하는 함수
    """
    if not os.path.exists(MEMO_FILE):
        return []
        
    try:
        with open(MEMO_FILE, newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))
    except Exception as e:
        logging.error(f"메모 파일 로드 중 오류 발생: {e}")
        return []

# 특정 교시의 메모 조회 함수
def get_period_memo(date, period):
    """
    특정 날짜와 교시에 해당하는 메모를 반환하는 함수
    """
    memos = load_period_memos()
    for memo in memos:
        if memo['날짜'] == date and memo['교시'] == period:
            return memo['메모']
    return ""

initialize_files()

def get_current_period():
    """
    Determine the current class period based on current time (Korean time)
    Returns period number (1-10) or 0 if outside scheduled periods or during 4th period
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
    return 0  # 교시가 아닌 시간일 경우
    
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
    now = datetime.now(KST)
    today = now.strftime('%Y-%m-%d')
    
    if not os.path.exists(FILENAME):
        return 0
        
    count = 0
    with open(FILENAME, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            attendance_date = row['출석일'].split(' ')[0]  # 날짜 부분만 가져오기
            if attendance_date == today and row['교시'] == period_text:
                count += 1
                
    return count

def load_student_data():
    """
    Load student data from Excel file
    Returns a dictionary with student_id as key and (name, seat) as value
    """
    try:
        df = pd.read_excel(STUDENT_FILE, dtype={'학번': str})
        return {row['학번'].strip(): (row['이름'].strip(), row['공강좌석번호']) for _, row in df.iterrows()}
    except Exception as e:
        logging.error(f"[오류] 학생 정보를 불러올 수 없습니다: {e}")
        flash(f"학생 정보를 불러올 수 없습니다. 관리자에게 문의하세요: {e}", "danger")
        return {}

def check_attendance(student_id, admin_override=False):
    """
    Check if the student has already attended this week or has an active warning
    Returns tuple:
      (already_attended, last_attendance_date, is_warned, warning_info)
      
    이미 출석했거나 경고를 받은 학생은 출석을 제한함
    
    admin_override: 관리자 수동 추가 시 체크를 건너뛰는 옵션
    """
    # 경고 여부 확인
    is_warned, warning_info = Warning.is_student_warned(student_id)
    
    # 관리자 수동 추가인 경우 체크 건너뛰기 (경고도 무시)
    if admin_override:
        return False, None, False, None
        
    # '3'으로 시작하는 학번은 항상 출석 가능 (경고도 무시)
    if student_id.startswith('3'):
        return False, None, False, None
        
    # 경고 받은 경우 출석 차단
    if is_warned and not admin_override:
        return False, None, True, warning_info
        
    if not os.path.exists(FILENAME):
        return False, None, False, None
        
    last_attendance_date = None
    latest_attendance_datetime = None
    weekly_attendance_count = 0
    
    with open(FILENAME, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        # 현재 한국 시간
        now = datetime.now(KST).replace(tzinfo=None)
        
        # 현재 요일 (0: 월요일, 1: 화요일, ..., 6: 일요일)
        # datetime에서 weekday()는 0이 월요일, 6이 일요일
        current_weekday = now.weekday()
        
        # 이번 주 월요일 계산 (현재가 월요일이면 오늘, 아니면 지난 월요일)
        days_since_monday = current_weekday
        this_week_monday = now - timedelta(days=days_since_monday)
        this_week_monday = this_week_monday.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # '이번 주'를 월요일부터 금요일까지로 정의
        for r in reader:
            if r['학번'] == student_id:
                try:
                    # 날짜에 시간 정보 포함 여부 확인 및 처리
                    attendance_date = r['출석일']
                    if ' ' in attendance_date:
                        # 날짜와 시간 부분을 분리
                        date_part = attendance_date.split(' ')[0]  # 날짜 부분만 추출
                    else:
                        date_part = attendance_date
                        
                    # 날짜만 파싱
                    attend_time = datetime.strptime(date_part, '%Y-%m-%d')
                    
                    # 가장 최근 출석 날짜 업데이트
                    if latest_attendance_datetime is None or attend_time > latest_attendance_datetime:
                        latest_attendance_datetime = attend_time
                        last_attendance_date = date_part
                        
                    # 이번 주(월~금) 출석 체크
                    # 출석날짜가 이번 주 월요일 이후이고, 금요일(weekday=4) 이하인 경우만 카운트
                    if attend_time >= this_week_monday and attend_time.weekday() <= 4:
                        weekly_attendance_count += 1
                            
                except ValueError:
                    continue
        
        # 모든 출석 기록을 확인한 후 주간 출석 횟수에 따라 출석 제한 여부 결정
        # 이번 주에 이미 한 번 출석한 경우 (관리자는 제한 없음)
        if weekly_attendance_count >= 1 and not session.get('admin'):
            return True, last_attendance_date, False, None
        # 일주일 이내 출석은 없지만, 과거 출석 기록이 있는 경우
        if last_attendance_date:
            return False, last_attendance_date, False, None
            
        # 출석 기록이 없는 경우    
        return False, None, False, None

def load_attendance():
    """
    Load all attendance records
    Returns a list of dictionaries containing attendance records
    """
    if not os.path.exists(FILENAME):
        return []
    with open(FILENAME, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def save_attendance(student_id, name, seat):
    """
    Save attendance record to CSV files (with Korean time)
    """
    file_exists = os.path.exists(FILENAME)
    # 한국 시간 기준으로 현재 날짜와 시간 저장
    now = datetime.now(KST)
    # 출석일 형식: n월n일n시n분n초 (예: 5월7일14시30분22초)
    now_date_time = now.strftime('%Y-%m-%d %H:%M:%S')  # 저장용 ISO 형식 (DB 호환성)
    period = get_current_period()
    period_text = f'{period}교시' if period > 0 else '시간 외'
    
    row = {
        '출석일': now_date_time, 
        '교시': period_text,
        '학번': student_id, 
        '이름': name, 
        '공강좌석번호': seat
    }

    try:
        # Define fields in the proper order
        fieldnames = ['출석일', '교시', '학번', '이름', '공강좌석번호']
        
        # Main attendance file
        with open(FILENAME, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

        # Backup file
        with open(BACKUP_FILE, 'a', newline='', encoding='utf-8') as backup:
            backup_writer = csv.DictWriter(backup, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            if not os.path.exists(BACKUP_FILE) or os.path.getsize(BACKUP_FILE) == 0:
                backup_writer.writeheader()
            backup_writer.writerow(row)

        # Excel-friendly file (UTF-8-SIG encoding with BOM)
        try:
            # 파일이 존재하는지 확인
            file_exists = os.path.exists(EXCEL_FRIENDLY_FILE) and os.path.getsize(EXCEL_FRIENDLY_FILE) > 0
            
            # 파일이 없으면 헤더와 함께 새로 생성
            if not file_exists:
                with open(EXCEL_FRIENDLY_FILE, 'w', newline='', encoding='utf-8-sig') as excel_file:
                    excel_writer = csv.DictWriter(excel_file, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
                    excel_writer.writeheader()
            
            # 기존 파일에 행 추가
            with open(EXCEL_FRIENDLY_FILE, 'a', newline='', encoding='utf-8-sig') as excel_file:
                excel_writer = csv.DictWriter(excel_file, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
                excel_writer.writerow(row)
        except Exception as e:
            logging.error(f"Excel-friendly 파일 저장 중 오류 발생: {e}")
            
        return True

    except PermissionError:
        error_msg = f"[{datetime.now(KST)}] PermissionError: Could not write to {FILENAME}\n"
        with open(LOG_FILE, 'a', encoding='utf-8') as log:
            log.write(error_msg)
        flash("⚠️ 출석 파일이 열려 있어 저장할 수 없습니다. Excel 파일을 닫고 다시 시도해주세요.", "danger")
        return False
    except Exception as e:
        error_msg = f"[{datetime.now(KST)}] Error: {str(e)}\n"
        with open(LOG_FILE, 'a', encoding='utf-8') as log:
            log.write(error_msg)
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
        elif check_attendance(student_id)[0]:
            # 메인 출석 페이지에서는 관리자 여부와 관계없이 중복 출석을 금지
            # 관리자는 별도의 추가 출석 페이지를 통해서만 추가 출석 처리 가능
            if session.get('admin'):
                flash("⚠️ 이번 주에 이미 출석했습니다. 추가 출석은 관리자 메뉴의 '추가 출석하기'에서 진행해주세요.", "warning")
            else:
                flash("⚠️ 이번 주에 이미 출석하셨습니다. 다음 주에 다시 와주세요.", "warning")
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
        
    # Excel용 CSV 파일 생성 (UTF-8 with BOM)
    temp_file = 'temp_export.csv'
    try:
        # 원본 데이터 읽기
        with open(FILENAME, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            data = list(reader)
            
        # UTF-8 with BOM으로 새 파일 작성
        with open(temp_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            writer.writerows(data)
            
        # 파일 전송
        response = send_file(
            temp_file, 
            as_attachment=True, 
            download_name="attendance.csv",
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
                # 메모 검색을 위한 원본 날짜 문자열
                original_date_str = date
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
        
        # 파일 읽기
        if not os.path.exists(FILENAME):
            return jsonify({'success': False, 'error': '출석 기록 파일이 존재하지 않습니다.'}), 404
        
        # 기존 기록 읽기
        with open(FILENAME, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            all_records = list(reader)
            
        # 백업 파일 생성 (로깅 추가)
        logging.info(f"Backing up {len(all_records)} records to {BACKUP_FILE} before deletion")
        with open(BACKUP_FILE, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['출석일', '교시', '학번', '이름', '공강좌석번호']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_records)
        
        # 삭제할 기록들을 파싱 (새로운 JSON 형식으로)
        records_set = set()
        for record in records_to_delete:
            # 새로운 JSON 형식 - 학번, 날짜, 교시 정보를 가지고 있음
            student_id = record.get('student_id')
            date = record.get('date')
            period = record.get('period')
            
            if student_id and date:
                # 학번과 날짜로 식별
                records_set.add((date, student_id, period))
                logging.info(f"Marking for deletion: 학번={student_id}, 날짜={date}, 교시={period}")
            
        # 삭제되지 않을 기록만 필터링
        filtered_records = []
        for record in all_records:
            key = (record['출석일'], record['학번'], record['교시'])
            if key not in records_set:
                filtered_records.append(record)
        
        # 필터링된 기록 저장 (기존 파일 삭제 후 저장)
        logging.info(f"Saving {len(filtered_records)} records after deletion (removed {len(all_records) - len(filtered_records)} records)")
        
        # 기존 파일 삭제 후 새로 생성 (기록 충돌 방지)
        if os.path.exists(FILENAME):
            os.remove(FILENAME)
            
        with open(FILENAME, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['출석일', '교시', '학번', '이름', '공강좌석번호']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(filtered_records)
        
        # Excel 호환 파일도 업데이트 (기존 파일 삭제 후 새로 생성)
        if os.path.exists(EXCEL_FRIENDLY_FILE):
            os.remove(EXCEL_FRIENDLY_FILE)
            
        with open(EXCEL_FRIENDLY_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            fieldnames = ['출석일', '교시', '학번', '이름', '공강좌석번호']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(filtered_records)
        
        # 파일이 제대로 저장되었는지 확인
        with open(FILENAME, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            check_records = list(reader)
        
        if len(check_records) != len(filtered_records):
            logging.error(f"Record count mismatch after deletion: expected {len(filtered_records)}, got {len(check_records)}")
            return jsonify({'success': False, 'error': '삭제 후 기록 수가 일치하지 않습니다.'}), 500
            
        deleted_count = len(all_records) - len(filtered_records)
        logging.info(f"Successfully deleted {deleted_count} records")
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
    already_attended, last_attendance_date, is_warned, warning_info = check_attendance(student_id)
    
    # 경고 받은 학생 정보 표시 (관리자는 등록 허용)
    if is_warned:
        if warning_info:
            expiry_date = warning_info.expiry_date.strftime('%Y년 %m월 %d일')
            reason = warning_info.reason or "도서실 이용 규정 위반"
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
        
    # 모든 경고 목록 조회
    warnings = Warning.query.order_by(Warning.warning_date.desc()).all()
    
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
    warning = Warning.add_warning(student_id, student_name, days, reason)
    
    if warning:
        flash(f"{student_name}({student_id}) 학생에게 {days}일간의 도서실 이용 제한이 추가되었습니다.", "success")
    else:
        flash("경고 추가 중 오류가 발생했습니다.", "danger")
        
    return redirect('/admin/warnings')

@app.route('/admin/warnings/remove/<int:warning_id>', methods=['POST'])
def remove_warning(warning_id):
    """학생 경고 해제 처리"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
        
    # 경고 해제
    if Warning.remove_warning(warning_id):
        flash("경고가 해제되었습니다.", "success")
    else:
        flash("경고 해제 중 오류가 발생했습니다.", "danger")
        
    return redirect('/admin/warnings')

@app.route('/admin/warnings/delete/<int:warning_id>', methods=['POST'])
def delete_warning(warning_id):
    """학생 경고 완전 삭제 처리"""
    if not session.get('admin'):
        flash("관리자 로그인이 필요합니다.", "danger")
        return redirect('/admin')
        
    # 경고 완전 삭제
    if Warning.delete_warning(warning_id):
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
    if Warning.delete_all_warnings():
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
    student_id = request.args.get('student_id')
    student_data = load_student_data()
    student_info = student_data.get(student_id)

    if student_info:
        name = student_info[0]
        seat = student_info[1] if len(student_info) > 1 else None
        
        # 관리자 여부 확인
        is_admin = session.get('admin', False)
        
        # 출석 여부 확인 (경고 정보 포함) - 관리자 권한 전달
        already_attended, last_attendance_date, is_warned, warning_info = check_attendance(student_id, admin_override=is_admin)
        
        # 날짜를 더 읽기 쉬운 형식으로 변환 (YYYY-MM-DD -> YYYY년 MM월 DD일)
        formatted_date = None
        if last_attendance_date:
            try:
                date_obj = datetime.strptime(last_attendance_date, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%Y년 %m월 %d일')
            except:
                formatted_date = last_attendance_date
        
        # 경고 정보 처리
        warning_message = None
        warning_expiry = None
        if is_warned and warning_info:
            # 경고 만료일 포맷팅
            warning_expiry = warning_info.expiry_date.strftime('%Y년 %m월 %d일')
            warning_message = warning_info.reason or "도서실 이용 규정 위반"
        
        # 현재 교시 출석 인원 수 확인 (최대 35명)
        MAX_CAPACITY = 35
        current_period = get_current_period()
        capacity_exceeded = False
        
        # 현재 교시가 유효한 경우에만 확인
        if current_period > 0:
            current_count = get_current_period_attendance_count()
            capacity_exceeded = current_count >= MAX_CAPACITY
        
        return jsonify({
            'success': True, 
            'name': name, 
            'seat': seat,
            'already_attended': already_attended,
            'last_attendance_date': formatted_date,
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
            # 기준 날짜 파싱
            cutoff_date = datetime.strptime(date_str, '%Y-%m-%d')
            
            # 모든 출석 데이터 불러오기
            all_records = load_attendance()
            
            # 백업 파일에 이미 데이터가 있는지 확인
            backup_exists = os.path.exists(BACKUP_FILE) and os.path.getsize(BACKUP_FILE) > 0
            
            # 백업 파일 모드 결정 (새 파일 또는 추가)
            backup_mode = 'a' if backup_exists else 'w'
            
            # 삭제 대상 레코드와 유지할 레코드 분류
            records_to_delete = []
            records_to_keep = []
            
            for record in all_records:
                date_str = record.get('출석일', '')
                if ' ' in date_str:  # 날짜와 시간 있는 형식 (2025-05-09 10:57:36)
                    attendance_date = datetime.strptime(date_str.split(' ')[0], '%Y-%m-%d')
                else:  # 날짜만 있는 형식 (2025-05-09)
                    try:
                        attendance_date = datetime.strptime(date_str, '%Y-%m-%d')
                    except ValueError:
                        # 날짜 파싱 실패 시 현재 날짜로 처리 (= 유지)
                        records_to_keep.append(record)
                        continue
                
                # 기준 날짜 이전인지 확인
                if attendance_date < cutoff_date:
                    records_to_delete.append(record)
                else:
                    records_to_keep.append(record)
            
            # 백업 파일에 삭제 대상 레코드 저장
            with open(BACKUP_FILE, backup_mode, newline='', encoding='utf-8') as backup_file:
                fieldnames = ['출석일', '교시', '학번', '이름', '공강좌석번호']
                backup_writer = csv.DictWriter(backup_file, fieldnames=fieldnames)
                
                # 새 파일인 경우 헤더 작성
                if not backup_exists:
                    backup_writer.writeheader()
                
                # 삭제할 레코드 백업
                for record in records_to_delete:
                    backup_writer.writerow(record)
                    logging.info(f"Marking for deletion: 학번={record.get('학번')}, 날짜={record.get('출석일')}, 교시={record.get('교시')}")
            
            logging.info(f"Backing up {len(records_to_delete)} records to {BACKUP_FILE} before deletion")
            
            # 원본 파일 업데이트 (삭제 후 유지할 레코드만 저장)
            with open(FILENAME, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['출석일', '교시', '학번', '이름', '공강좌석번호']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(records_to_keep)
                
            # Excel 호환 파일도 업데이트
            with open(EXCEL_FRIENDLY_FILE, 'w', newline='', encoding='utf-8-sig') as excel_file:
                excel_writer = csv.DictWriter(excel_file, fieldnames=fieldnames)
                excel_writer.writeheader()
                excel_writer.writerows(records_to_keep)
                
            logging.info(f"Saving {len(records_to_keep)} records after deletion (removed {len(records_to_delete)} records)")
            
            if records_to_delete:
                flash(f"✅ {date_str} 이전의 {len(records_to_delete)}개 출석 기록이 삭제되었습니다.", "success")
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
