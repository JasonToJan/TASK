from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Task, TaskLog
from app.utils import admin_required, validate_cron_expression, validate_script
from app.scheduler import TaskScheduler, get_scheduler
from datetime import datetime

bp = Blueprint('tasks', __name__)


@bp.route('/')
@bp.route('/tasks')
@login_required
def list_tasks():
    """任务列表页面"""
    page = request.args.get('page', 1, type=int)

    # 管理员可以看到所有任务，普通用户只能看到自己的任务
    if current_user.is_admin:
        query = Task.query
    else:
        query = Task.query.filter_by(user_id=current_user.id)

    tasks = query.order_by(Task.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False)

    return render_template('tasks/list.html', tasks=tasks)


@bp.route('/tasks/create', methods=['GET', 'POST'])
@login_required
def create_task():
    """创建新任务"""
    if request.method == 'POST':
        try:
            # 获取基本信息
            name = request.form['name']
            description = request.form['description']
            timeout = int(request.form.get('timeout', 3600))
            max_retries = int(request.form.get('max_retries', 0))

            # 处理脚本内容
            script_content = None
            script_source = 'editor'
            original_filename = None

            if 'script_file' in request.files and request.files['script_file'].filename:
                file = request.files['script_file']
                if not file.filename.endswith('.py'):
                    flash('只支持.py文件格式', 'danger')
                    return redirect(url_for('tasks.create_task'))

                script_content = file.read().decode('utf-8')
                script_source = 'file'
                original_filename = file.filename
            else:
                script_content = request.form.get('script_content')

            if not script_content:
                flash('请提供Python脚本', 'danger')
                return redirect(url_for('tasks.create_task'))

            # 验证脚本安全性
            is_safe, message = validate_script(script_content)
            if not is_safe:
                flash(f'脚本验证失败: {message}', 'danger')
                return redirect(url_for('tasks.create_task'))

            # 处理调度设置
            schedule_type = request.form.get('schedule_type', 'custom')
            schedule_config = {}

            try:
                if schedule_type == 'once':
                    once_datetime = request.form.get('once_datetime')
                    if not once_datetime:
                        raise ValueError('请选择执行时间')
                    schedule_config = {'datetime': once_datetime}

                elif schedule_type == 'minutes':
                    minutes = request.form.get('minutes_value', '5')
                    if not minutes.isdigit() or int(minutes) < 1:
                        raise ValueError('无效的分钟间隔')
                    schedule_config = {'value': minutes}

                elif schedule_type == 'hourly':
                    hours = request.form.get('hours_value', '1')
                    if not hours.isdigit() or int(hours) < 1:
                        raise ValueError('无效的小时间隔')
                    schedule_config = {'value': hours}

                elif schedule_type == 'daily':
                    time = request.form.get('daily_time')
                    if not time:
                        raise ValueError('请选择每日执行时间')
                    schedule_config = {'time': time}

                elif schedule_type == 'weekly':
                    day = request.form.get('week_day')
                    time = request.form.get('weekly_time')
                    if not all([day, time]):
                        raise ValueError('请选择周几和执行时间')
                    schedule_config = {'day': day, 'time': time}

                elif schedule_type == 'monthly':
                    day = request.form.get('month_day')
                    time = request.form.get('monthly_time')
                    if not all([day, time]) or not day.isdigit() or not (1 <= int(day) <= 31):
                        raise ValueError('请选择有效的日期和执行时间')
                    schedule_config = {'day': day, 'time': time}

                elif schedule_type == 'custom':
                    cron_expression = request.form.get('cron_expression')
                    if not cron_expression:
                        raise ValueError('请提供Cron表达式')
                    schedule_config = {'expression': cron_expression}

                else:
                    raise ValueError('无效的调度类型')

            except ValueError as e:
                flash(str(e), 'danger')
                return redirect(url_for('tasks.create_task'))

            # 创建任务
            task = Task(
                name=name,
                description=description,
                script_content=script_content,
                script_source=script_source,
                original_filename=original_filename,
                timeout=timeout,
                max_retries=max_retries,
                user_id=current_user.id,
                schedule_type=schedule_type,
                schedule_config=schedule_config
            )

            # 根据调度配置生成cron表达式
            try:
                task.update_schedule(schedule_type, schedule_config)
            except Exception as e:
                flash(f'调度配置错误: {str(e)}', 'danger')
                return redirect(url_for('tasks.create_task'))

            # 保存到数据库
            try:
                db.session.add(task)
                db.session.commit()

                # 添加调试日志
                current_app.logger.info("Getting scheduler instance...")
                scheduler = get_scheduler()
                current_app.logger.info(f"Scheduler instance: {scheduler}")

                if scheduler is None:
                    current_app.logger.error("Scheduler is None - not properly initialized")
                    flash('任务创建成功，但调度器未初始化', 'warning')
                    return redirect(url_for('tasks.list_tasks'))

                if scheduler.add_job(task):
                    flash('任务创建成功', 'success')
                else:
                    flash('任务创建成功，但调度失败', 'warning')

                return redirect(url_for('tasks.list_tasks'))

            except Exception as e:
                db.session.rollback()
                flash(f'保存任务失败: {str(e)}', 'danger')
                return redirect(url_for('tasks.create_task'))

        except Exception as e:
            flash(f'创建任务失败: {str(e)}', 'danger')
            return redirect(url_for('tasks.create_task'))

    # GET 请求返回创建页面
    return render_template('tasks/create.html')


@bp.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    """编辑任务"""
    task = Task.query.get_or_404(task_id)

    # 检查权限
    if not current_user.is_admin and task.user_id != current_user.id:
        flash('没有权限编辑此任务', 'danger')
        return redirect(url_for('tasks.list_tasks'))

    if request.method == 'POST':
        try:
            # 更新基本信息
            task.name = request.form['name']
            task.description = request.form['description']
            task.timeout = int(request.form.get('timeout', 3600))
            task.max_retries = int(request.form.get('max_retries', 0))

            # 处理脚本内容
            if 'script_file' in request.files and request.files['script_file'].filename:
                file = request.files['script_file']
                if not file.filename.endswith('.py'):
                    flash('只支持.py文件格式', 'danger')
                    return redirect(url_for('tasks.edit_task', task_id=task_id))

                task.script_content = file.read().decode('utf-8')
                task.script_source = 'file'
                task.original_filename = file.filename
            else:
                new_script_content = request.form.get('script_content')
                if new_script_content:
                    task.script_content = new_script_content
                    if task.script_source == 'file':
                        task.script_source = 'editor'
                        task.original_filename = None

            # 验证脚本语法
            is_safe, message = validate_script(task.script_content)
            if not is_safe:
                flash(f'脚本验证失败: {message}', 'danger')
                return redirect(url_for('tasks.edit_task', task_id=task_id))

            # 处理调度设置
            schedule_type = request.form.get('schedule_type', 'custom')
            schedule_config = {}

            try:
                if schedule_type == 'once':
                    once_datetime = request.form.get('once_datetime')
                    if not once_datetime:
                        raise ValueError('请选择执行时间')
                    schedule_config = {'datetime': once_datetime}

                elif schedule_type == 'minutes':
                    minutes = request.form.get('minutes_value', '5')
                    if not minutes.isdigit() or int(minutes) < 1:
                        raise ValueError('无效的分钟间隔')
                    schedule_config = {'value': minutes}

                elif schedule_type == 'hourly':
                    hours = request.form.get('hours_value', '1')
                    if not hours.isdigit() or int(hours) < 1:
                        raise ValueError('无效的小时间隔')
                    schedule_config = {'value': hours}

                elif schedule_type == 'daily':
                    time = request.form.get('daily_time')
                    if not time:
                        raise ValueError('请选择每日执行时间')
                    schedule_config = {'time': time}

                elif schedule_type == 'weekly':
                    day = request.form.get('week_day')
                    time = request.form.get('weekly_time')
                    if not all([day, time]):
                        raise ValueError('请选择周几和执行时间')
                    schedule_config = {'day': day, 'time': time}

                elif schedule_type == 'monthly':
                    day = request.form.get('month_day')
                    time = request.form.get('monthly_time')
                    if not all([day, time]) or not day.isdigit() or not (1 <= int(day) <= 31):
                        raise ValueError('请选择有效的日期和执行时间')
                    schedule_config = {'day': day, 'time': time}

                elif schedule_type == 'custom':
                    cron_expression = request.form.get('cron_expression')
                    if not cron_expression:
                        raise ValueError('请提供Cron表达式')
                    schedule_config = {'expression': cron_expression}

                else:
                    raise ValueError('无效的调度类型')

                # 更新调度配置
                task.update_schedule(schedule_type, schedule_config)

            except ValueError as e:
                flash(str(e), 'danger')
                return redirect(url_for('tasks.edit_task', task_id=task_id))

            # 更新任务
            task.updated_at = datetime.utcnow()
            db.session.commit()

            scheduler = get_scheduler()
            current_app.logger.info(f"Scheduler instance: {scheduler}")
            # 更新调度器
            if task.is_active:
                if scheduler.update_job(task):
                    flash('任务更新成功', 'success')
                else:
                    flash('任务更新成功，但调度更新失败', 'warning')
            else:
                flash('任务更新成功', 'success')

            return redirect(url_for('tasks.list_tasks'))

        except Exception as e:
            db.session.rollback()
            flash(f'更新任务失败: {str(e)}', 'danger')

    return render_template('tasks/edit.html', task=task)


@bp.route('/tasks/<int:task_id>/toggle', methods=['POST'])
@login_required
def toggle_task(task_id):
    """启用/禁用任务"""
    task = Task.query.get_or_404(task_id)

    if not current_user.is_admin and task.user_id != current_user.id:
        flash('没有权限操作此任务', 'danger')
        return redirect(url_for('tasks.list_tasks'))

    scheduler = get_scheduler()
    current_app.logger.info(f"Scheduler instance: {scheduler}")
    try:
        task.is_active = not task.is_active
        db.session.commit()

        if task.is_active:
            if scheduler.add_job(task):
                flash('任务已启用', 'success')
            else:
                flash('任务状态更新失败', 'danger')
        else:
            if scheduler.remove_job(task.id):
                flash('任务已禁用', 'success')
            else:
                flash('任务状态更新失败', 'danger')

    except Exception as e:
        db.session.rollback()
        flash(f'操作失败: {str(e)}', 'danger')

    return redirect(url_for('tasks.list_tasks'))


@bp.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    """删除任务"""
    task = Task.query.get_or_404(task_id)

    if not current_user.is_admin and task.user_id != current_user.id:
        flash('没有权限删除此任务', 'danger')
        return redirect(url_for('tasks.list_tasks'))

    scheduler = get_scheduler()
    current_app.logger.info(f"Scheduler instance: {scheduler}")
    try:
        # 从调度器中移除
        scheduler.remove_job(task.id)

        # 删除相关日志
        TaskLog.query.filter_by(task_id=task.id).delete()

        # 删除任务
        db.session.delete(task)
        db.session.commit()

        flash('任务删除成功', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'删除任务失败: {str(e)}', 'danger')

    return redirect(url_for('tasks.list_tasks'))


@bp.route('/tasks/<int:task_id>/logs')
@login_required
def task_logs(task_id):
    """任务执行日志"""
    task = Task.query.get_or_404(task_id)

    if not current_user.is_admin and task.user_id != current_user.id:
        flash('没有权限查看此任务的日志', 'danger')
        return redirect(url_for('tasks.list_tasks'))

    page = request.args.get('page', 1, type=int)
    logs = TaskLog.query.filter_by(task_id=task_id) \
        .order_by(TaskLog.start_time.desc()) \
        .paginate(page=page, per_page=20, error_out=False)

    return render_template('tasks/logs.html', task=task, logs=logs)


@bp.route('/monitor')
@login_required
def monitor():
    """任务监控页面"""
    # 获取最近的任务执行情况
    recent_logs = TaskLog.query.order_by(TaskLog.start_time.desc()).limit(10).all()

    # 统计信息
    stats = {
        'total_tasks': Task.query.count(),
        'active_tasks': Task.query.filter_by(is_active=True).count(),
        'total_executions': TaskLog.query.count(),
        'failed_executions': TaskLog.query.filter_by(status='FAILED').count()
    }

    if stats['total_executions'] > 0:
        stats['success_rate'] = (
                (stats['total_executions'] - stats['failed_executions'])
                / stats['total_executions'] * 100
        )
    else:
        stats['success_rate'] = 0

    return render_template('tasks/monitor.html',
                           recent_logs=recent_logs,
                           stats=stats)
