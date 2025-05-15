from datetime import datetime, timedelta
import os
import time
import logging
import firebase_admin
from firebase_admin import firestore

# 시간 측정 데코레이터 (성능 모니터링)
def timing_decorator(func):
    """함수 실행 시간을 측정하는 데코레이터"""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = (end_time - start_time) * 1000  # ms로 변환
        logging.info(f"[{func.__name__}] 실행 시간: {execution_time:.2f} ms")
        return result
    return wrapper

# Firebase 데이터베이스 참조 변수 (app.py에서 설정)
db = None

# 전역 변수: Firebase 버전에 따른 FieldFilter
field_filter_support = False

# 전역 변수: Firebase FieldFilter 클래스
FieldFilter = None  # 초기값은 None으로 설정

# Firebase FieldFilter 지원 확인 및 설정 함수
def setup_firebase(firestore_db):
    """Firebase 클라이언트와 버전별 기능 지원 설정"""
    global db, field_filter_support, FieldFilter
    
    db = firestore_db
    
    # FieldFilter 지원 확인
    try:
        from firebase_admin.firestore import FieldFilter as FirebaseFieldFilter
        FieldFilter = FirebaseFieldFilter  # 전역 변수에 할당
        field_filter_support = True
        logging.info("Firebase FieldFilter 지원 확인됨")
    except ImportError:
        field_filter_support = False
        logging.info("Firebase FieldFilter 미지원 (구 버전 사용 중)")
        
    return db is not None

# ================== [유틸리티 함수] ==================

@timing_decorator
def get_document_id(collection_ref, filters=None):
    """필터 조건에 맞는 문서 ID 찾기 (Firebase 버전 호환성 개선)"""
    if filters is None or collection_ref is None:
        return None
    
    try:
        query = collection_ref
        
        # Firebase 버전에 따라 다른 쿼리 방식 사용
        if field_filter_support:
            # 신규 버전 Firebase - FieldFilter 사용 방식
            from firebase_admin.firestore import FieldFilter
            for field, op, value in filters:
                query = query.where(filter=FieldFilter(field, op, value))
        else:
            # 구 버전 Firebase - 직접 where 사용 방식
            for field, op, value in filters:
                query = query.where(field, op, value)
                
        # 결과 조회
        docs = query.limit(1).get()
        for doc in docs:
            return doc.id
        return None
    
    except Exception as e:
        logging.error(f"문서 ID 검색 오류: {e}")
        return None


def firestore_to_dict(doc):
    """Firestore 문서를 딕셔너리로 변환"""
    if doc is None:
        return None
    data = doc.to_dict()
    data['id'] = doc.id
    return data


# ================== [출석 관련 함수] ==================

def add_attendance(student_id, name, seat, period_text):
    """출석 기록 추가"""
    try:
        attendances_ref = db.collection('attendances')
        
        # 이미 오늘 같은 교시에 출석했는지 확인
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        
        # 오늘 같은 교시에 이미 출석했는지 확인
        existing_docs = attendances_ref.where(
            filter=FieldFilter("student_id", "==", student_id)
        ).where(
            filter=FieldFilter("period", "==", period_text)
        ).where(
            filter=FieldFilter("date", ">=", today_start)
        ).where(
            filter=FieldFilter("date", "<=", today_end)
        ).limit(1).get()
        
        for doc in existing_docs:
            return None  # 이미 출석한 경우 저장하지 않음
        
        # 새 출석 기록 추가
        new_record = {
            "student_id": student_id,
            "name": name,
            "seat": seat,
            "period": period_text,
            "date": datetime.now()
        }
        
        doc_ref = attendances_ref.add(new_record)
        return doc_ref[1].id  # 문서 ID 반환
    except Exception as e:
        logging.error(f"출석 기록 추가 오류: {e}")
        return None


def get_attendances_by_student(student_id):
    """학생 ID별 모든 출석 기록 조회"""
    try:
        attendances_ref = db.collection('attendances')
        docs = attendances_ref.where(
            filter=FieldFilter("student_id", "==", student_id)
        ).order_by("date", direction=firestore.Query.DESCENDING).get()
        
        return [firestore_to_dict(doc) for doc in docs]
    except Exception as e:
        logging.error(f"학생별 출석 기록 조회 오류: {e}")
        return []


def get_recent_attendance(student_id, days=7):
    """최근 특정 일수 이내의 출석 기록 조회"""
    try:
        attendances_ref = db.collection('attendances')
        recent_date = datetime.now() - timedelta(days=days)
        
        docs = attendances_ref.where(
            filter=FieldFilter("student_id", "==", student_id)
        ).where(
            filter=FieldFilter("date", ">=", recent_date)
        ).order_by("date", direction=firestore.Query.DESCENDING).limit(1).get()
        
        for doc in docs:
            return firestore_to_dict(doc)
        return None
    except Exception as e:
        logging.error(f"최근 출석 기록 조회 오류: {e}")
        return None


def get_recent_attendance_for_week(student_id, week_start_date):
    """특정 주의 출석 기록 조회 (월요일부터 금요일까지)"""
    try:
        week_end_date = week_start_date + timedelta(days=5)  # 월요일부터 금요일까지
        attendances_ref = db.collection('attendances')
        
        docs = attendances_ref.where(
            filter=FieldFilter("student_id", "==", student_id)
        ).where(
            filter=FieldFilter("date", ">=", week_start_date)
        ).where(
            filter=FieldFilter("date", "<", week_end_date)
        ).limit(1).get()
        
        for doc in docs:
            return firestore_to_dict(doc)
        return None
    except Exception as e:
        logging.error(f"주간 출석 기록 조회 오류: {e}")
        return None


def get_attendances_by_period(period, limit=50):
    """교시별 출석 기록 조회"""
    try:
        attendances_ref = db.collection('attendances')
        docs = attendances_ref.where(
            filter=FieldFilter("period", "==", period)
        ).order_by("date", direction=firestore.Query.DESCENDING).limit(limit).get()
        
        return [firestore_to_dict(doc) for doc in docs]
    except Exception as e:
        logging.error(f"교시별 출석 기록 조회 오류: {e}")
        return []


def get_today_attendances():
    """오늘의 출석 기록 조회"""
    try:
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        
        attendances_ref = db.collection('attendances')
        docs = attendances_ref.where(
            filter=FieldFilter("date", ">=", today_start)
        ).where(
            filter=FieldFilter("date", "<=", today_end)
        ).order_by("date", direction=firestore.Query.DESCENDING).get()
        
        return [firestore_to_dict(doc) for doc in docs]
    except Exception as e:
        logging.error(f"오늘의 출석 기록 조회 오류: {e}")
        return []


def delete_attendance(doc_id):
    """특정 출석 기록 삭제"""
    try:
        attendances_ref = db.collection('attendances')
        attendances_ref.document(doc_id).delete()
        return True
    except Exception as e:
        logging.error(f"출석 기록 삭제 오류: {e}")
        return False


# ================== [메모 관련 함수] ==================

def save_memo(date_str, period, memo_text):
    """교시별 메모 저장"""
    try:
        # 날짜 문자열을 날짜 객체로 변환
        if isinstance(date_str, str):
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            date_obj = date_str
            
        memos_ref = db.collection('period_memos')
        
        # 이미 존재하는 메모인지 확인
        date_str_formatted = date_obj.strftime('%Y-%m-%d')
        doc_id = get_document_id(memos_ref, [
            ("date", "==", date_str_formatted),
            ("period", "==", period)
        ])
        
        if doc_id:
            # 기존 메모 업데이트
            memos_ref.document(doc_id).update({"memo_text": memo_text})
        else:
            # 새 메모 생성
            memos_ref.add({
                "date": date_str_formatted,
                "period": period,
                "memo_text": memo_text
            })
            
        return True
    except Exception as e:
        logging.error(f"메모 저장 오류: {e}")
        return False


def get_memo(date_str, period):
    """특정 날짜와 교시의 메모 조회"""
    try:
        # 날짜 문자열을 날짜 객체로 변환
        if isinstance(date_str, str):
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            date_obj = date_str
            
        date_str_formatted = date_obj.strftime('%Y-%m-%d')
        memos_ref = db.collection('period_memos')
        
        docs = memos_ref.where(
            filter=FieldFilter("date", "==", date_str_formatted)
        ).where(
            filter=FieldFilter("period", "==", period)
        ).limit(1).get()
        
        for doc in docs:
            return doc.to_dict().get("memo_text", "")
        return ""
    except Exception as e:
        logging.error(f"메모 조회 오류: {e}")
        return ""


def get_all_memos():
    """모든 메모 조회"""
    try:
        memos_ref = db.collection('period_memos')
        docs = memos_ref.order_by("date", direction=firestore.Query.DESCENDING).get()
        
        return [
            {
                "날짜": doc.to_dict().get("date"),
                "교시": doc.to_dict().get("period"),
                "메모": doc.to_dict().get("memo_text", "")
            }
            for doc in docs
        ]
    except Exception as e:
        logging.error(f"전체 메모 조회 오류: {e}")
        return []


# ================== [경고 관련 함수] ==================

def is_student_warned(student_id):
    """학생이 현재 유효한 경고를 받았는지 확인"""
    try:
        now = datetime.now()
        warnings_ref = db.collection('warnings')
        
        docs = warnings_ref.where(
            filter=FieldFilter("student_id", "==", student_id)
        ).where(
            filter=FieldFilter("expiry_date", ">", now)
        ).where(
            filter=FieldFilter("is_active", "==", True)
        ).limit(1).get()
        
        for doc in docs:
            return True, firestore_to_dict(doc)
        return False, None
    except Exception as e:
        logging.error(f"경고 확인 오류: {e}")
        return False, None


def add_warning(student_id, student_name, days=30, reason=None):
    """학생에게 경고 추가 (기본 30일 경고)"""
    try:
        now = datetime.now()
        expiry_date = now + timedelta(days=days)
        
        warnings_ref = db.collection('warnings')
        doc_ref = warnings_ref.add({
            "student_id": student_id,
            "student_name": student_name,
            "warning_date": now,
            "expiry_date": expiry_date,
            "reason": reason,
            "is_active": True
        })
        
        return doc_ref[1].id  # 문서 ID 반환
    except Exception as e:
        logging.error(f"경고 추가 오류: {e}")
        return None


def remove_warning(warning_id):
    """경고 제거 (활성화 상태만 변경)"""
    try:
        warnings_ref = db.collection('warnings')
        warnings_ref.document(warning_id).update({"is_active": False})
        return True
    except Exception as e:
        logging.error(f"경고 비활성화 오류: {e}")
        return False


def delete_warning(warning_id):
    """경고 완전 삭제"""
    try:
        warnings_ref = db.collection('warnings')
        warnings_ref.document(warning_id).delete()
        return True
    except Exception as e:
        logging.error(f"경고 삭제 오류: {e}")
        return False


def delete_all_warnings():
    """모든 경고 삭제"""
    try:
        warnings_ref = db.collection('warnings')
        docs = warnings_ref.get()
        
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        
        batch.commit()
        return True
    except Exception as e:
        logging.error(f"모든 경고 삭제 오류: {e}")
        return False