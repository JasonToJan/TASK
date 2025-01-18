import re
import ast
from functools import wraps
from flask import abort
from flask_login import current_user


def admin_required(f):
    """检查管理员权限的装饰器"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


def validate_cron_expression(expression):
    """验证cron表达式"""
    if not expression:
        return False

    parts = expression.split()
    if len(parts) != 5:
        return False

    patterns = [
        r'^(\*|[0-9]|[1-5][0-9])(\/[0-9]+)?$',  # 分钟
        r'^(\*|[0-9]|1[0-9]|2[0-3])(\/[0-9]+)?$',  # 小时
        r'^(\*|[1-9]|[12][0-9]|3[01])(\/[0-9]+)?$',  # 日期
        r'^(\*|[1-9]|1[0-2])(\/[0-9]+)?$',  # 月份
        r'^(\*|[0-6])(\/[0-9]+)?$',  # 星期
    ]

    try:
        for part, pattern in zip(parts, patterns):
            if not re.match(pattern, part):
                return False
        return True
    except:
        return False


def validate_script(script_content):
    """验证Python脚本的基本语法"""
    try:
        # 仅做基本的语法检查
        ast.parse(script_content)
        return True, "脚本验证通过"
    except SyntaxError as e:
        # 只返回语法错误
        return False, f"语法错误: {str(e)}"
    except Exception as e:
        return False, f"验证失败: {str(e)}"


def format_datetime(dt):
    """格式化日期时间"""
    if dt is None:
        return ''
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def format_duration(seconds):
    """格式化持续时间"""
    if seconds is None:
        return ''

    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    parts = []
    if hours > 0:
        parts.append(f"{int(hours)}小时")
    if minutes > 0:
        parts.append(f"{int(minutes)}分钟")
    if seconds > 0 or not parts:
        parts.append(f"{seconds:.2f}秒")

    return ''.join(parts)
