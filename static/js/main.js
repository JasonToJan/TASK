// 通用函数
function confirmAction(message) {
    return confirm(message);
}

// 初始化代码编辑器
function initCodeEditor(elementId) {
    if (document.getElementById(elementId)) {
        var editor = ace.edit(elementId);
        editor.setTheme("ace/theme/monokai");
        editor.session.setMode("ace/mode/python");
        editor.setOptions({
            fontSize: "14px",
            showPrintMargin: false,
            showGutter: true,
            highlightActiveLine: true,
            enableBasicAutocompletion: true,
            enableSnippets: true,
            enableLiveAutocompletion: true
        });
        return editor;
    }
    return null;
}

// CRON表达式验证
function validateCronExpression(expression) {
    const parts = expression.split(' ');
    if (parts.length !== 5) {
        return false;
    }

    const patterns = {
        minute: /^(\*|[0-9]|[1-5][0-9])(\/[0-9]+)?$/,
        hour: /^(\*|[0-9]|1[0-9]|2[0-3])(\/[0-9]+)?$/,
        day: /^(\*|[1-9]|[12][0-9]|3[01])(\/[0-9]+)?$/,
        month: /^(\*|[1-9]|1[0-2])(\/[0-9]+)?$/,
        weekday: /^(\*|[0-6])(\/[0-9]+)?$/
    };

    const keys = ['minute', 'hour', 'day', 'month', 'weekday'];
    return parts.every((part, index) => patterns[keys[index]].test(part));
}

// 表单验证
function validateTaskForm() {
    const name = document.getElementById('name').value;
    const cronExpression = document.getElementById('cron_expression').value;
    const scriptContent = editor.getValue();

    if (!name.trim()) {
        alert('请输入任务名称');
        return false;
    }

    if (!validateCronExpression(cronExpression)) {
        alert('无效的CRON表达式');
        return false;
    }

    if (!scriptContent.trim()) {
        alert('请输入脚本内容');
        return false;
    }

    return true;
}

// 动态加载任务日志
function loadTaskLogs(taskId, page = 1) {
    fetch(`/tasks/${taskId}/logs?page=${page}`)
        .then(response => response.json())
        .then(data => {
            updateLogsTable(data.logs);
            updatePagination(data.pagination);
        })
        .catch(error => console.error('Error loading logs:', error));
}

// 更新实时监控数据
function updateMonitorStats() {
    fetch('/tasks/monitor/stats')
        .then(response => response.json())
        .then(data => {
            Object.keys(data).forEach(key => {
                const element = document.getElementById(`stat-${key}`);
                if (element) {
                    element.textContent = data[key];
                }
            });
        })
        .catch(error => console.error('Error updating stats:', error));
}

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
    // 初始化代码编辑器
    const editor = initCodeEditor('script_content');

    // 初始化表单验证
    const taskForm = document.querySelector('form');
    if (taskForm) {
        taskForm.addEventListener('submit', function(e) {
            if (!validateTaskForm()) {
                e.preventDefault();
            }
        });
    }

    // 初始化工具提示
    const tooltipTriggerList = [].slice.call(
        document.querySelectorAll('[data-toggle="tooltip"]')
    );
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // 监控页面自动刷新
    if (document.getElementById('monitor-page')) {
        setInterval(updateMonitorStats, 30000);
    }
});
