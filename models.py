from datetime import datetime, timedelta
import os
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class Attendance(db.Model):
    """학생 출석 기록 모델"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    seat = db.Column(db.String(20), nullable=True)
    period = db.Column(db.String(20), nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    @staticmethod
    def add_attendance(student_id, name, seat, period_text):
        """출석 기록 추가"""
        today = datetime.now().date()
        existing = Attendance.query.filter_by(
            student_id=student_id,
            period=period_text,
            date=today
        ).first()

        if existing:
            return  # 이미 출석한 경우 저장하지 않음

        new_record = Attendance()
        new_record.student_id = student_id
        new_record.name = name
        new_record.seat = seat
        new_record.period = period_text
        new_record.date = today
        db.session.add(new_record)
        db.session.commit()
        return new_record
    
    @staticmethod
    def get_attendances_by_student(student_id):
        """학생 ID별 모든 출석 기록 조회"""
        return Attendance.query.filter_by(student_id=student_id).order_by(Attendance.date.desc()).all()
    
    @staticmethod
    def get_recent_attendance(student_id, days=7):
        """최근 특정 일수 이내의 출석 기록 조회"""
        now = datetime.utcnow()
        recent_date = now - timedelta(days=days)
        return Attendance.query.filter(
            Attendance.student_id == student_id,
            Attendance.date >= recent_date
        ).order_by(Attendance.date.desc()).first()
    
    @staticmethod
    def get_attendances_by_period(period, limit=50):
        """교시별 출석 기록 조회"""
        return Attendance.query.filter_by(period=period).order_by(Attendance.date.desc()).limit(limit).all()
    
    @staticmethod
    def get_today_attendances():
        """오늘의 출석 기록 조회"""
        today = datetime.utcnow().date()
        tomorrow = today + timedelta(days=1)
        return Attendance.query.filter(
            Attendance.date >= today,
            Attendance.date < tomorrow
        ).order_by(Attendance.date.desc()).all()
    
    @staticmethod
    def delete_attendance(attendance_id):
        """특정 출석 기록 삭제"""
        attendance = Attendance.query.get(attendance_id)
        if attendance:
            db.session.delete(attendance)
            db.session.commit()
            return True
        return False


class PeriodMemo(db.Model):
    """교시별 메모 모델"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    period = db.Column(db.String(20), nullable=False)
    memo_text = db.Column(db.Text, nullable=True)
    
    @staticmethod
    def save_memo(date_str, period, memo_text):
        """교시별 메모 저장"""
        try:
            # 날짜 문자열을 날짜 객체로 변환
            if isinstance(date_str, str):
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            else:
                date_obj = date_str
                
            # 이미 존재하는 메모인지 확인
            existing_memo = PeriodMemo.query.filter_by(
                date=date_obj,
                period=period
            ).first()
            
            if existing_memo:
                # 기존 메모 업데이트
                existing_memo.memo_text = memo_text
            else:
                # 새 메모 생성
                new_memo = PeriodMemo()
                new_memo.date = date_obj
                new_memo.period = period
                new_memo.memo_text = memo_text
                db.session.add(new_memo)
                
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            print(f"메모 저장 오류: {e}")
            return False
    
    @staticmethod
    def get_memo(date_str, period):
        """특정 날짜와 교시의 메모 조회"""
        try:
            # 날짜 문자열을 날짜 객체로 변환
            if isinstance(date_str, str):
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            else:
                date_obj = date_str
                
            memo = PeriodMemo.query.filter_by(
                date=date_obj,
                period=period
            ).first()
            
            return memo.memo_text if memo else ""
        except Exception as e:
            print(f"메모 조회 오류: {e}")
            return ""
    
    @staticmethod
    def get_all_memos():
        """모든 메모 조회"""
        try:
            memos = PeriodMemo.query.order_by(PeriodMemo.date.desc()).all()
            return [
                {
                    "날짜": memo.date.strftime('%Y-%m-%d'),
                    "교시": memo.period,
                    "메모": memo.memo_text
                }
                for memo in memos
            ]
        except Exception as e:
            print(f"전체 메모 조회 오류: {e}")
            return []


class Warning(db.Model):
    """경고 받은 학생 정보 모델"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), nullable=False, index=True)
    student_name = db.Column(db.String(100), nullable=False)
    warning_date = db.Column(db.DateTime, default=datetime.utcnow)
    expiry_date = db.Column(db.DateTime, nullable=False)  # 경고 만료일
    reason = db.Column(db.Text, nullable=True)  # 경고 사유
    is_active = db.Column(db.Boolean, default=True)  # 경고 활성화 여부

    @staticmethod
    def is_student_warned(student_id):
        """학생이 현재 유효한 경고를 받았는지 확인"""
        now = datetime.utcnow()
        warning = Warning.query.filter(
            Warning.student_id == student_id,
            Warning.expiry_date > now,
            Warning.is_active == True
        ).first()
        return warning is not None, warning

    @staticmethod
    def add_warning(student_id, student_name, days=30, reason=None):
        """학생에게 경고 추가 (기본 30일 경고)"""
        now = datetime.utcnow()
        expiry_date = now + timedelta(days=days)
        
        warning = Warning()
        warning.student_id = student_id
        warning.student_name = student_name
        warning.warning_date = now
        warning.expiry_date = expiry_date
        warning.reason = reason
        warning.is_active = True
        
        db.session.add(warning)
        db.session.commit()
        return warning

    @staticmethod
    def remove_warning(warning_id):
        """경고 제거 (활성화 상태만 변경)"""
        warning = Warning.query.get(warning_id)
        if warning:
            warning.is_active = False
            db.session.commit()
            return True
        return False
        
    @staticmethod
    def delete_warning(warning_id):
        """경고 완전 삭제"""
        warning = Warning.query.get(warning_id)
        if warning:
            db.session.delete(warning)
            db.session.commit()
            return True
        return False
        
    @staticmethod
    def delete_all_warnings():
        """모든 경고 삭제"""
        try:
            Warning.query.delete()
            db.session.commit()
            return True
        except:
            db.session.rollback()
            return False