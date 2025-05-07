from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, jsonify, after_this_request
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

# Add datetime functions to templates
@app.context_processor
def inject_now():
    # 항상 한국 시간을 사용하여 현재 시간 반환
    return {'now': lambda: datetime.now(KST).replace(tzinfo=None)}

# File configurations
FILENAME = 'attendance.csv'
BACKUP_FILE = 'attendance_backup.csv'
LOG_FILE = 'attendance_error.log'
EXCEL_FRIENDLY_FILE = 'attendance_excel.csv'
STUDENT_FILE = 'students.xlsx'
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")  # Default is "1234" if not set in environment

# Period schedule configuration
PERIOD_SCHEDULE = {
    1: (8, 0, 9, 15),
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
    
    # Excel용 파일은 UTF-8-SIG(BOM 포함)로 저장
    if not os.path.exists(EXCEL_FRIENDLY_FILE):
        try:
            with open(EXCEL_FRIENDLY_FILE, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['출석일', '교시', '학번', '이름', '공강좌석번호'])
            logging.info(f"Created Excel-friendly file: {EXCEL_FRIENDLY_FILE}")
        except Exception as e:
            logging.error(f"Error creating Excel-friendly file {EXCEL_FRIENDLY_FILE}: {e}")

initialize_files()

def get_current_period():
    """
    Determine the current class period based on current time (Korean time)
    Returns period number (1-10) or 0 if outside scheduled periods
    """
    # 한국 시간 기준으로 현재 시간 가져오기
    now = datetime.now(KST).time()
    for period, (start_h, start_m, end_h, end_m) in PERIOD_SCHEDULE.items():
        start = datetime.strptime(f"{start_h}:{start_m}", "%H:%M").time()
        end = datetime.strptime(f"{end_h}:{end_m}", "%H:%M").time()
        if start <= now < end:
            return period
    return 0  # 교시가 아닌 시간일 경우

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

def check_attendance(student_id):
    """
    Check if the student has already attended this week
    Returns True if already attended, False otherwise
    """
    # Skip check for students with ID starting with '3'
    if student_id.startswith('3'):
        return False
        
    if not os.path.exists(FILENAME):
        return False
        
    with open(FILENAME, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        # 한국 시간 기준으로 일주일 전 계산
        one_week_ago = datetime.now(KST).replace(tzinfo=None) - timedelta(days=7)
        for r in reader:
            if r['학번'] == student_id:
                try:
                    attend_time = datetime.strptime(r['출석일'], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    try:
                        attend_time = datetime.strptime(r['출석일'], '%Y-%m-%d')
                    except ValueError:
                        continue
                if attend_time >= one_week_ago:
                    return True
        return False

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
    # 한국 시간 기준으로 현재 시간 저장
    now = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
    period = get_current_period()
    period_text = f'{period}교시' if period > 0 else '시간 외'
    
    row = {
        '출석일': now, 
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

@app.route('/', methods=['GET', 'POST'])
def attendance():
    """Main attendance page and form submission handler"""
    if request.method == 'POST':
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
        elif check_attendance(student_id):
            flash("⚠️ 이번 주에 이미 출석하셨습니다. 다음 주에 다시 와주세요.", "warning")
        else:
            seat = student_info[1]
            if save_attendance(student_id, name, seat):
                flash(f"✅ 출석이 완료되었습니다. 공강좌석번호: {seat}", "success")
        return redirect(url_for('attendance'))
        
    return render_template('attendance.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/list')
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
            
        # 파일 전송 후 파일 삭제를 위한 콜백 함수
        def remove_temp_file():
            if os.path.exists(temp_file):
                os.remove(temp_file)
                
        return send_file(
            temp_file, 
            as_attachment=True, 
            download_name="attendance.csv",
            mimetype='text/csv',
            # 파일 전송 후 임시 파일 삭제
            after_this_request=remove_temp_file
        )
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
    
    # 교시별로 학생 데이터 그룹화
    period_groups = {}
    
    for record in records:
        date = record.get('출석일', '날짜 없음')
        period = record.get('교시', '시간 외')
        
        # 교시를 키로 사용
        period_key = period
        
        # 날짜 형식 변환 - 두 가지 형식 만들기
        if date != '날짜 없음':
            try:
                date_obj = datetime.strptime(date, "%Y-%m-%d")
                # MM월 DD일 형식 (카드 표시용)
                date_formatted = f"{date_obj.month}월 {date_obj.day}일"
                # YYYY/MM/DD 형식 (교시 제목용)
                date_ymd = f"{date_obj.year}/{date_obj.month}/{date_obj.day}"
            except ValueError:
                date_formatted = date
                date_ymd = date
        else:
            date_formatted = date
            date_ymd = date
        
        # 원본 기록에 날짜 정보 추가
        record_copy = record.copy()
        record_copy['날짜_표시'] = date_formatted
        record_copy['날짜_ymd'] = date_ymd
        
        if period_key not in period_groups:
            period_groups[period_key] = []
        
        period_groups[period_key].append(record_copy)
    
    # 교시 순서대로 정렬
    sorted_periods = sorted(period_groups.keys(), key=lambda p: (
        # 숫자 교시는 숫자 순서대로 정렬
        int(p[0]) if p and p[0].isdigit() else 999,
        # 나머지는 문자열 순서대로
        p
    ))
    
    # 각 교시 내에서 날짜와 이름으로 정렬
    for period in period_groups:
        period_groups[period] = sorted(period_groups[period], key=lambda r: (r.get('출석일', ''), r['이름']))
    
    return render_template('by_period.html', period_groups=period_groups, sorted_periods=sorted_periods)

@app.route('/logout')
def logout():
    """Logout from admin"""
    session.pop('admin', None)
    flash("로그아웃 되었습니다.", "success")
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
