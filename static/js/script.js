// Main script.js file for the attendance system

// 고정된 시간 표시 업데이트 함수
function updateFixedTimeDisplay() {
    const now = new Date();
    const month = now.getMonth() + 1;
    const day = now.getDate();
    const hour = now.getHours().toString().padStart(2, '0');
    const minute = now.getMinutes().toString().padStart(2, '0');
    const second = now.getSeconds().toString().padStart(2, '0');
    const dayOfWeekNames = ['일', '월', '화', '수', '목', '금', '토'];
    const dayOfWeek = dayOfWeekNames[now.getDay()];
    
    const fixedTimeEl = document.getElementById("fixedTimeDisplay");
    if (fixedTimeEl) {
        fixedTimeEl.innerHTML = `
            <i class="fas fa-clock me-1"></i>
            ${month}/${day}(${dayOfWeek}) 
            <span class="fw-bold">${hour}:<span class="time-blink">${minute}</span>:<span class="seconds-blink">${second}</span></span>
        `;
    }
}

// 관리자 페이지 접근을 위한 키 조합 처리
let secretClickCount = 0;
const secretClickReset = () => setTimeout(() => { secretClickCount = 0; }, 2000);

// 특수 키 조합 감지 함수
function handleKeyboardShortcuts(e) {
    // Ctrl+Shift+A 키 조합 감지 (관리자 페이지)
    if (e.ctrlKey && e.shiftKey && e.key === 'A') {
        e.preventDefault();
        window.location.href = '/admin';
    }
    
    // Ctrl+F 키 조합 감지 (메인 페이지)
    if (e.ctrlKey && !e.shiftKey && e.key === 'f') {
        e.preventDefault();
        window.location.href = '/';
    }
}

document.addEventListener('DOMContentLoaded', function() {
    // 모든 페이지에서 시간 표시 업데이트
    updateFixedTimeDisplay();
    setInterval(updateFixedTimeDisplay, 1000);
    
    // 키보드 단축키 등록
    document.addEventListener('keydown', handleKeyboardShortcuts);
    
    // 숨겨진 관리자 링크 설정
    const hiddenAdminLink = document.getElementById('hiddenAdminLink');
    if (hiddenAdminLink) {
        // 클릭 이벤트 등록 (3번 빠르게 클릭해야 관리자 페이지로 이동)
        hiddenAdminLink.addEventListener('click', function(e) {
            e.preventDefault();
            secretClickCount++;
            
            if (secretClickCount >= 3) { // 3번으로 변경
                window.location.href = '/admin';
                secretClickCount = 0;
            } else {
                secretClickReset();
            }
        });
        
        // 시계를 통한 접근은 삭제
    }
    
    // 자동 숨김 코드 제거 (시간 표시가 사라지지 않도록)
    
    // Form validation enhancement
    const forms = document.querySelectorAll('.needs-validation');
    
    Array.from(forms).forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            
            form.classList.add('was-validated');
        }, false);
    });
    
    // Auto-focus for first input in forms
    const firstInput = document.querySelector('form input:first-of-type');
    if (firstInput) {
        firstInput.focus();
    }
    
    // Add student ID input formatting
    const studentIdInput = document.getElementById('student_id');
    if (studentIdInput) {
        studentIdInput.addEventListener('input', function() {
            this.value = this.value.replace(/[^0-9]/g, '');
        });
    }
    
    // Activate all tooltips
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
    
    // Add current year to the footer
    const yearSpan = document.querySelector('.current-year');
    if (yearSpan) {
        yearSpan.textContent = new Date().getFullYear();
    }
});
