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

# 캐싱 시스템 - 성능 최적화를 위한 메모리 캐시
_cache = {
    'student_attendance': {},  # 학생별 출석 기록 캐시
    'warnings': {},           # 경고 기록 캐시
    'recent_lookups': set(),  # 최근 조회된 학생 ID 모음 (자주 조회되는 항목 파악)
    'cache_ttl': 60,          # 캐시 유효 시간 (초)
    'last_updated': {}        # 각 캐시별 마지막 업데이트 시간
}

def clear_cache(cache_key=None):
    """캐시 데이터 초기화 함수"""
    global _cache
    if cache_key:
        if cache_key in _cache:
            _cache[cache_key] = {} if isinstance(_cache[cache_key], dict) else type(_cache[cache_key])()
            _cache['last_updated'][cache_key] = time.time()
    else:
        _cache = {
            'student_attendance': {},
            'warnings': {},
            'recent_lookups': set(),
            'cache_ttl': 60,
            'last_updated': {}
        }

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

@timing_decorator
def add_attendance(student_id, name, seat, period_text, custom_fields=None):
    """
    출석 기록 추가
    
    Args:
        student_id: 학생 ID
        name: 학생 이름
        seat: 좌석 번호 
        period_text: 교시 텍스트
        custom_fields: 추가 필드 (선택적)
    """
    try:
        attendances_ref = db.collection('attendances')
        
        # 이미 오늘 같은 교시에 출석했는지 확인
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        
        # 타임존 처리
        if hasattr(today_start, 'tzinfo') and today_start.tzinfo:
            today_start = today_start.replace(tzinfo=None)
        if hasattr(today_end, 'tzinfo') and today_end.tzinfo:
            today_end = today_end.replace(tzinfo=None)
        
        # 단일 필드만 쿼리 (복합 인덱스 문제 해결)
        existing_docs = attendances_ref.where(
            filter=FieldFilter("student_id", "==", student_id)
        ).get()
        
        # 클라이언트 측에서 필터링
        for doc in existing_docs:
            data = doc.to_dict()
            doc_period = data.get("period")
            doc_date = data.get("date")
            
            # 타임존 처리
            if doc_date:
                if hasattr(doc_date, 'tzinfo') and doc_date.tzinfo:
                    doc_date = doc_date.replace(tzinfo=None)
            
                # 오늘 같은 교시에 이미 출석했는지 확인
                if (doc_period == period_text and 
                    doc_date.date() == today):
                    return None  # 이미 출석한 경우 저장하지 않음
        
        # 새 출석 기록 추가
        # datetime 객체 생성
        now = datetime.now()
        # 타임존 제거
        if hasattr(now, 'tzinfo') and now.tzinfo:
            now = now.replace(tzinfo=None)
        
        # 한국시간으로 보정 (시간 정확도 향상)
        try:
            import pytz
            # 한국 시간대 적용
            korea_timezone = pytz.timezone('Asia/Seoul')
            now_korea = pytz.utc.localize(now).astimezone(korea_timezone)
            # 타임존 정보 제거 (일관성 유지)
            now_korea = now_korea.replace(tzinfo=None)
            logging.info(f"한국 시간 변환: {now_korea}")
        except ImportError:
            now_korea = now
            logging.warning("pytz 모듈을 찾을 수 없어 한국 시간 적용 불가")
        
        # 기본 레코드 생성
        # 타임스탬프 문자열 명확하게 생성 (HH:MM:SS 포맷)
        time_str = now_korea.strftime('%H:%M:%S')
        full_date_str = now_korea.strftime('%Y-%m-%d %H:%M:%S')
            
        new_record = {
            "student_id": student_id,
            "name": name,
            "seat": seat,
            "period": period_text,
            "date": now_korea,  # 한국 시간 사용
            "local_time": now,  # 시스템 로컬 시간 (백업용)
            "created_at": full_date_str,  # 문자열 시간도 항상 저장
            "time_only": time_str,  # 시:분:초만 문자열로 저장
            "display_time": time_str  # 출력용 시간 값
        }
        
        # 추가 필드가 있는 경우 병합
        if custom_fields and isinstance(custom_fields, dict):
            new_record.update(custom_fields)
        
        doc_ref = attendances_ref.add(new_record)
        logging.info(f"출석 기록 추가 성공: {student_id} ({name}), 교시: {period_text}")
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


@timing_decorator
def get_recent_attendance(student_id, days=7):
    """최근 특정 일수 이내의 출석 기록 조회"""
    try:
        attendances_ref = db.collection('attendances')
        recent_date = datetime.now() - timedelta(days=days)
        
        # 타임존 처리
        if hasattr(recent_date, 'tzinfo') and recent_date.tzinfo:
            recent_date = recent_date.replace(tzinfo=None)
        
        # 단일 필드만 쿼리 (복합 인덱스 문제 해결)
        docs = attendances_ref.where(
            filter=FieldFilter("student_id", "==", student_id)
        ).get()
        
        # 클라이언트 측에서 필터링
        most_recent = None
        most_recent_date = None
        
        for doc in docs:
            data = doc.to_dict()
            doc_date = data.get("date")
            
            # 타임존 처리
            if doc_date:
                if hasattr(doc_date, 'tzinfo') and doc_date.tzinfo:
                    doc_date = doc_date.replace(tzinfo=None)
                
                # 최근 일수 이내 기록만 확인
                if doc_date >= recent_date:
                    # 가장 최근 기록 찾기
                    if most_recent_date is None or doc_date > most_recent_date:
                        most_recent = doc
                        most_recent_date = doc_date
        
        if most_recent:
            return firestore_to_dict(most_recent)
        return None
    except Exception as e:
        logging.error(f"최근 출석 기록 조회 오류: {e}")
        return None


@timing_decorator
def get_recent_attendance_for_week(student_id, week_start_date):
    """특정 주의 출석 기록 조회 (월요일부터 금요일까지)"""
    try:
        # 캐시에서 확인 (성능 최적화)
        global _cache
        
        # 캐시 키 생성 (학생 ID + 주 시작일)
        week_key = week_start_date.strftime('%Y-%m-%d')
        cache_key = f'week_attendance_{student_id}_{week_key}'
        
        # 캐시 확인 (30초간 유효)
        if 'student_attendance' in _cache and cache_key in _cache.get('last_updated', {}):
            last_update = _cache['last_updated'].get(cache_key, 0)
            # 캐시가 유효하면 캐싱된 결과 반환
            if time.time() - last_update < 30:  # 30초 캐시
                logging.info(f"주간 출석 캐시 적중: {student_id} ({week_key})")
                if cache_key in _cache.get('student_attendance', {}):
                    return _cache['student_attendance'][cache_key]
                    
        week_end_date = week_start_date + timedelta(days=5)  # 월요일부터 금요일까지
        
        # 타임존 처리
        if hasattr(week_start_date, 'tzinfo') and week_start_date.tzinfo:
            week_start_date = week_start_date.replace(tzinfo=None)
        if hasattr(week_end_date, 'tzinfo') and week_end_date.tzinfo:
            week_end_date = week_end_date.replace(tzinfo=None)
            
        attendances_ref = db.collection('attendances')
        
        # 단일 필드만 쿼리 (복합 인덱스 문제 해결)
        docs = attendances_ref.where(
            filter=FieldFilter("student_id", "==", student_id)
        ).get()
        
        # 클라이언트 측에서 필터링
        for doc in docs:
            data = doc.to_dict()
            doc_date = data.get("date")
            
            # 타임존 처리
            if doc_date:
                if hasattr(doc_date, 'tzinfo') and doc_date.tzinfo:
                    doc_date = doc_date.replace(tzinfo=None)
                
                # 특정 주의 기록만 확인
                if doc_date >= week_start_date and doc_date < week_end_date:
                    result = firestore_to_dict(doc)
                    
                    # 결과 캐싱
                    if 'student_attendance' not in _cache:
                        _cache['student_attendance'] = {}
                    if 'last_updated' not in _cache:
                        _cache['last_updated'] = {}
                        
                    _cache['student_attendance'][cache_key] = result
                    _cache['last_updated'][cache_key] = time.time()
                    
                    return result
                
        # 결과 없음 상태도 캐싱
        if 'student_attendance' not in _cache:
            _cache['student_attendance'] = {}
        if 'last_updated' not in _cache:
            _cache['last_updated'] = {}
            
        _cache['student_attendance'][cache_key] = None
        _cache['last_updated'][cache_key] = time.time()
        
        return None
    except Exception as e:
        logging.error(f"주간 출석 기록 조회 오류: {e}")
        return None


@timing_decorator
def get_attendances_by_period(period, limit=50):
    """교시별 출석 기록 조회"""
    try:
        attendances_ref = db.collection('attendances')
        # 단일 필드만 쿼리 (복합 인덱스 문제 해결)
        docs = attendances_ref.where(
            filter=FieldFilter("period", "==", period)
        ).get()
        
        # 클라이언트 측에서 정렬
        records = [firestore_to_dict(doc) for doc in docs]
        
        # 날짜 기준 내림차순 정렬
        records.sort(key=lambda x: x.get('date', datetime.min), reverse=True)
        
        # 요청된 개수만큼 반환
        return records[:limit]
    except Exception as e:
        logging.error(f"교시별 출석 기록 조회 오류: {e}")
        return []


@timing_decorator
def get_today_attendances():
    """오늘의 출석 기록 조회"""
    try:
        # 타임존 관련 문제 해결
        today = datetime.now().date()
        
        # Firebase의 복합 인덱스 문제 해결을 위한 코드
        attendances_ref = db.collection('attendances')
        
        # 모든 출석 기록 가져오기 (오늘 날짜로 필터링 없이)
        all_docs = attendances_ref.get()
        
        # 클라이언트에서 오늘 기록만 필터링
        today_records = []
        for doc in all_docs:
            data = doc.to_dict()
            doc_date = data.get("date")
            
            # 날짜만 비교 (타임존 문제 해결)
            if doc_date:
                # 타임존 정보가 있는 경우 제거
                if hasattr(doc_date, 'tzinfo') and doc_date.tzinfo:
                    doc_date = doc_date.replace(tzinfo=None)
                
                # 날짜만 비교 (시간 제외)
                if doc_date.date() == today:
                    today_records.append(firestore_to_dict(doc))
        
        # 날짜 기준 내림차순 정렬
        today_records.sort(key=lambda x: x.get('date', datetime.min), reverse=True)
        
        return today_records
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

@timing_decorator
def is_student_warned(student_id):
    """학생이 현재 유효한 경고를 받았는지 확인"""
    try:
        # 캐시에서 확인 (성능 최적화)
        global _cache
        
        # 캐시 유효 시간 (10초로 설정 - 빠른 응답이 필요한 경우)
        cache_ttl = 10
        cache_key = f'warnings_{student_id}'
        
        # 캐시 확인
        if student_id in _cache.get('warnings', {}):
            last_update = _cache.get('last_updated', {}).get(cache_key, 0)
            # 캐시가 유효하면 캐싱된 결과 반환
            if time.time() - last_update < cache_ttl:
                logging.info(f"경고 캐시 적중: {student_id}")
                return _cache['warnings'][student_id]
        
        # 캐시에 없으면 DB에서 조회
        now = datetime.now()
        warnings_ref = db.collection('warnings')
        
        # 단일 필드만 쿼리 (복합 인덱스 문제 해결)
        docs = warnings_ref.where(
            filter=FieldFilter("student_id", "==", student_id)
        ).get()
        
        # 클라이언트 측에서 필터링
        for doc in docs:
            warning_data = doc.to_dict()
            is_active = warning_data.get('is_active', False)
            expiry_date = warning_data.get('expiry_date')
            
            # 활성화되었고 만료되지 않은 경고만 반환
            if is_active and expiry_date and expiry_date > now:
                result = (True, firestore_to_dict(doc))
                # 결과 캐싱
                if 'warnings' not in _cache:
                    _cache['warnings'] = {}
                if 'last_updated' not in _cache:
                    _cache['last_updated'] = {}
                _cache['warnings'][student_id] = result
                _cache['last_updated'][cache_key] = time.time()
                return result
                
        # 경고 없음 상태 캐싱
        result = (False, None)
        if 'warnings' not in _cache:
            _cache['warnings'] = {}
        if 'last_updated' not in _cache:
            _cache['last_updated'] = {}
        _cache['warnings'][student_id] = result
        _cache['last_updated'][cache_key] = time.time()
        return result
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