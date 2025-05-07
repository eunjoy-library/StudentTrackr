/**
 * 테이블 정렬 기능
 */

// 현재 정렬 상태
var currentSortCol = -1;
var currentSortDir = 'asc';

/**
 * 테이블 정렬 함수
 */
function sortTable(tableId, colNum) {
    var table = document.getElementById(tableId);
    var switching = true;
    var rows, i, x, y, shouldSwitch;
    var dir = "asc";
    
    // 이전에 정렬했던 컬럼인 경우 방향 전환
    if (currentSortCol === colNum) {
        dir = currentSortDir === "asc" ? "desc" : "asc";
    }
    
    // 정렬 상태 업데이트
    currentSortCol = colNum;
    currentSortDir = dir;
    
    // 아이콘 업데이트
    updateSortIcons(table, colNum, dir);
    
    // 계속 전환이 필요한 동안 루프
    while (switching) {
        switching = false;
        rows = table.rows;
        
        // 헤더를 제외한 모든 행 순회
        for (i = 1; i < (rows.length - 1); i++) {
            shouldSwitch = false;
            
            // 현재 행과 다음 행 비교
            x = rows[i].getElementsByTagName("td")[colNum];
            y = rows[i + 1].getElementsByTagName("td")[colNum];
            
            // 셀이 없으면 건너뛰기
            if (!x || !y) continue;
            
            var xContent = x.textContent.trim();
            var yContent = y.textContent.trim();
            
            // 숫자 컬럼인 경우 (학번, 공강좌석번호)
            if (colNum === 2 || colNum === 4) {
                var xNum = parseInt(xContent.replace(/\D/g, '')) || 0;
                var yNum = parseInt(yContent.replace(/\D/g, '')) || 0;
                
                if (dir === "asc") {
                    if (xNum > yNum) {
                        shouldSwitch = true;
                        break;
                    }
                } else {
                    if (xNum < yNum) {
                        shouldSwitch = true;
                        break;
                    }
                }
            } 
            // 문자열 컬럼
            else {
                if (dir === "asc") {
                    if (xContent.localeCompare(yContent, 'ko') > 0) {
                        shouldSwitch = true;
                        break;
                    }
                } else {
                    if (xContent.localeCompare(yContent, 'ko') < 0) {
                        shouldSwitch = true;
                        break;
                    }
                }
            }
        }
        
        // 행 위치 변경
        if (shouldSwitch) {
            rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
            switching = true;
        }
    }
}

/**
 * 정렬 아이콘 업데이트
 */
function updateSortIcons(table, activeCol, direction) {
    // 모든 헤더 찾기
    var headers = table.querySelectorAll('th');
    
    // 모든 헤더 순회
    headers.forEach(function(header, index) {
        var icon = header.querySelector('i');
        if (!icon) return;
        
        // 선택된 헤더의 아이콘 업데이트
        if (index === activeCol) {
            if (direction === 'asc') {
                icon.className = 'fas fa-sort-up';
            } else {
                icon.className = 'fas fa-sort-down';
            }
        } else {
            icon.className = 'fas fa-sort';
        }
    });
}