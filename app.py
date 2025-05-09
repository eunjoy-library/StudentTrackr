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
    Returns (True, last_attendance_date) if already attended, (False, None) otherwise
    """
    # Skip check for students with ID starting with '3'
    if student_id.startswith('3'):
        return False, None
        
    if not os.path.exists(FILENAME):
        return False, None
        
    last_attendance_date = None
    latest_attendance_datetime = None
    
    with open(FILENAME, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        # 한국 시간 기준으로 일주일 전 계산
        one_week_ago = datetime.now(KST).replace(tzinfo=None) - timedelta(days=7)
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
                        
                    # 일주일 이내 출석 확인
                    if attend_time >= one_week_ago:
                        return True, last_attendance_date
                except ValueError:
                    continue
                    
        # 일주일 이내 출석은 없지만, 과거 출석 기록이 있는 경우
        if last_attendance_date:
            return False, last_attendance_date
            
        return False, None

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
        elif check_attendance(student_id)[0]:
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
            except ValueError:
                date_md = date
                original_date = datetime(1900, 1, 1)  # 날짜 변환 실패시 고정 날짜로
        else:
            date_md = date
            original_date = datetime(1900, 1, 1)  # 날짜 없음은 고정 날짜로
        
        # 원본 기록에 날짜 정보 추가
        record_copy = record.copy()
        record_copy['날짜_md'] = date_md
        record_copy['원본_날짜'] = original_date  # 정렬용 원본 날짜 저장
        
        # 날짜와 교시를 조합하여 키 생성 (예: "5월7일 6교시")
        period_num = int(period[0]) if period and period[0].isdigit() else 999
        
        # 교시만 키로 사용하는 것이 아니라, 날짜+교시로 새로운 키 생성
        new_period_key = f"{date_md} {period}"
        
        if new_period_key not in period_groups:
            period_groups[new_period_key] = {
                '학생_목록': [],
                '교시_번호': period_num
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
            
        # 백업 파일 생성
        with open(BACKUP_FILE, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['출석일', '교시', '학번', '이름', '공강좌석번호']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_records)
        
        # 삭제할 기록들을 파싱
        records_set = set()
        for record_str in records_to_delete:
            parts = record_str.split(',')
            if len(parts) >= 5:  # 출석일, 교시, 학번, 이름, 좌석번호
                # 출석일과 학번, 이름으로 식별 (고유 키로 사용)
                records_set.add((parts[0], parts[2], parts[3]))
        
        # 삭제되지 않을 기록만 필터링
        filtered_records = []
        for record in all_records:
            key = (record['출석일'], record['학번'], record['이름'])
            if key not in records_set:
                filtered_records.append(record)
        
        # 필터링된 기록 저장
        with open(FILENAME, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['출석일', '교시', '학번', '이름', '공강좌석번호']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(filtered_records)
        
        # Excel 호환 파일도 업데이트
        with open(EXCEL_FRIENDLY_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            fieldnames = ['출석일', '교시', '학번', '이름', '공강좌석번호']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(filtered_records)
            
        deleted_count = len(all_records) - len(filtered_records)
        return jsonify({
            'success': True, 
            'message': f'{deleted_count}개의 기록이 삭제되었습니다.',
            'deleted_count': deleted_count
        })
    
    except Exception as e:
        logging.error(f"Error deleting records: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
        already_attended, last_attendance_date = check_attendance(student_id)
        
        # 날짜를 더 읽기 쉬운 형식으로 변환 (YYYY-MM-DD -> YYYY년 MM월 DD일)
        formatted_date = None
        if last_attendance_date:
            try:
                date_obj = datetime.strptime(last_attendance_date, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%Y년 %m월 %d일')
            except:
                formatted_date = last_attendance_date
        
        return jsonify({
            'success': True, 
            'name': name, 
            'seat': seat,
            'already_attended': already_attended,
            'last_attendance_date': formatted_date
        })
    else:
        return jsonify({'success': False, 'message': '학번이 존재하지 않습니다.'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
