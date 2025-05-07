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

document.addEventListener('DOMContentLoaded', function() {
    // 모든 페이지에서 시간 표시 업데이트
    updateFixedTimeDisplay();
    setInterval(updateFixedTimeDisplay, 1000);
    
    // Auto-hide alert messages after 5 seconds
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert:not(.alert-dismissible)');
        alerts.forEach(function(alert) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
    
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
