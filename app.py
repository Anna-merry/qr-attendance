import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from datetime import datetime, date, timedelta
import qrcode
from io import BytesIO
import secrets
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError 

# Импортируем модели и хелперы
from models import db, User,  Attendance, ScheduleItem
from helpers import expand_schedule_to_semester, generate_token

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL') or 'postgresql://postgres:mypostgrespwd@localhost:5432/qr_attendance'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

uri = app.config['SQLALCHEMY_DATABASE_URI']
if uri.startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = uri.replace("postgres://", "postgresql://", 1)

serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
with app.app_context():
    db.create_all()
login_manager.login_view = 'login'

# Вспомогательная функция
def get_todays_lessons(teacher_id, target_date=None):
    if target_date is None:
        target_date = date.today()
    
    semester_start = date(2025, 9, 1)
    days_diff = (target_date - semester_start).days
    week_num = days_diff // 7 + 1
    parity = week_num % 2
    dow = target_date.isoweekday()  

    return ScheduleItem.query.filter_by(
        teacher_id=teacher_id,
        day_of_week=dow,
        week_parity=parity
    ).all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id)) 


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'student')

        if not username or not password:
            flash('Пожалуйста, заполните все поля', 'error')
            return render_template('auth.html', mode='login')

        user = User.query.filter_by(username=username, role=role).first()

        if not user:
            flash('Пользователь с таким логином не найден', 'error')
        elif not user.check_password(password):
            flash('Пароль введён неверно', 'error')
        else:
            login_user(user)
            return redirect(url_for('lectures' if user.role == 'teacher' else 'student_dashboard'))

    return render_template('auth.html', mode='login')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'student')  # ← исправлено
        group = request.form.get('group') if role == 'student' else None

        # Валидация обязательных полей
        if not username or not password:
            flash('Пожалуйста, заполните все поля', 'error')
            return render_template('auth.html', mode='register')

        # Проверка: студент должен указать группу
        if role == 'student' and not group:
            flash('Студенты должны указать группу', 'error')
            return render_template('auth.html', mode='register')

        try:
            user = User(username=username, role=role, group=group)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('Регистрация успешна! Теперь вы можете войти.', 'success')
            return redirect(url_for('login'))
        except IntegrityError:
            db.session.rollback()  # отменяем транзакцию
            flash(f'Пользователь с логином «{username}» уже существует', 'error')
            return render_template('auth.html', mode='register')

    return render_template('auth.html', mode='register')
    
@app.route('/teacher')
@login_required
def lectures():
    if current_user.role != 'teacher':
        return redirect(url_for('login'))
    lessons = get_todays_lessons(current_user.id)
    return render_template('teacher.html', lectures=lessons, now=datetime.now())

@app.route('/student')  # студент
@login_required
def student_dashboard():
    if current_user.role != 'student':
        return redirect(url_for('login'))
    lessons = get_todays_lessons_for_group(current_user.group)
    return render_template('student.html', lectures=lessons, now=datetime.now())

def get_todays_lessons_for_group(group_name):
    today = date.today()
    semester_start = date(2025, 9, 1)
    week_num = ((today - semester_start).days // 7) + 1
    parity = week_num % 2
    dow = today.isoweekday()
    return ScheduleItem.query.filter_by(
        group_name=group_name,
        day_of_week=dow,
        week_parity=parity
    ).all()
    
# QR-СИСТЕМА (ТОЛЬКО ДЛЯ ПРЕПОДАВАТЕЛЯ)

@app.route('/qr/full/<int:item_id>')
@login_required
def qr_fullscreen(item_id):
    if current_user.role != 'teacher':
        abort(403)
    item = ScheduleItem.query.filter_by(id=item_id, teacher_id=current_user.id).first_or_404()
    today = date.today().strftime('%Y-%m-%d')
    token_data = f"{item_id}:{today}"
    token = serializer.dumps(token_data)  # ← подписанный токен
    
    return render_template('qr_fullscreen.html', item_id=item_id, date_str=today, token=token)

@app.route('/qr-image/<int:item_id>/<date_str>/<token>')
def qr_image(item_id, date_str, token):
    # Без @login_required — студенты должны видеть QR!
    scan_url = url_for('scan', item_id=item_id, date=date_str, token=token, _external=True)
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(scan_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

# СКАНИРОВАНИЕ (ТОЛЬКО ДЛЯ СТУДЕНТОВ)

@app.route('/api/scan', methods=['POST'])
@login_required
def api_scan():
    if current_user.role != 'student':
        return jsonify({'status': 'error', 'message': 'Только для студентов'}), 403

    data = request.get_json()
    item_id = data.get('item_id')
    date_str = data.get('date') 
    token = data.get('token')

    if not all([item_id, date_str, token]):
        return jsonify({'status': 'error', 'message': 'Не хватает данных'}), 400

    try:
        # 1 Проверяем подпись и срок (max_age=5 сек)
        token_data = serializer.loads(token, max_age=5)  # ← автоматически проверяет подпись и время!
        expected_item_id, expected_date = token_data.split(':', 1)
        
        # 2 Проверяем, что данные совпадают
        if int(expected_item_id) != item_id or expected_date != date_str:
            return jsonify({'status': 'error', 'message': 'Несоответствие данных в токене'}), 400

        # 3 Проверяем, что занятие существует и для группы студента
        item = ScheduleItem.query.filter_by(
            id=item_id,
            group_name=current_user.group
        ).first()
        if not item:
            return jsonify({'status': 'error', 'message': 'Занятие не найдено'}), 404
        
        # 4 Проверяем, не отмечался ли уже
        existing = Attendance.query.filter_by(
            student_id=current_user.id,
            schedule_item_id=item_id,
            date=date.fromisoformat(date_str)
        ).first()
        if existing:
            return jsonify({'status': 'error', 'message': 'Вы уже отметились'}), 409

        # 5 Сохраняем
        attendance = Attendance(
            student_id=current_user.id,
            schedule_item_id=item_id,
            date=date.fromisoformat(date_str)
        )
        db.session.add(attendance)
        db.session.commit()
        return jsonify({'status': 'success', 'message': ' Посещение засчитано!'})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': 'Неверный формат даты'}), 400
    
@app.route('/scan')
@login_required
def scan():
    if current_user.role != 'student':
        flash('Доступно только студентам', 'error')
        return redirect(url_for('login'))
    
    item_id = request.args.get('item_id')
    date_str = request.args.get('date')
    token = request.args.get('token')
    
    #print(f"→ /scan получены параметры: item_id={item_id}, date={date_str}, token={token[:20]}...")
    
    return render_template('scan.html', item_id=item_id, date=date_str, token=token)

@app.route('/logout')
def logout():
    from flask_login import logout_user
    logout_user()
    return redirect(url_for('login'))


# КАЛЕНДАРЬ 

@app.route('/teacher/schedule')
@login_required
def teacher_schedule():
    if current_user.role != 'teacher':
        flash('Доступ разрешён только преподавателям', 'error')
        return redirect(url_for('login'))
    return render_template('teacher_schedule.html')

@app.route('/api/teacher/schedule')
@login_required
def api_teacher_schedule():
    if current_user.role != 'teacher':
        return jsonify({'error': 'access denied'}), 403
    schedule = expand_schedule_to_semester(current_user.id)
    return jsonify(schedule)

@app.route('/api/teacher/schedule', methods=['POST'])
@login_required
def api_add_schedule_item():
    if current_user.role != 'teacher':
        return jsonify({'error': 'Только для преподавателей'}), 403

    data = request.get_json()
    try:
        # Валидация
        required_fields = ['day_of_week', 'week_parity', 'start_time', 'end_time', 'subject', 'group_name']
        for field in required_fields:
            if field not in data or data[field] is None:
                return jsonify({'error': f'Поле {field} обязательно'}), 400

        item = ScheduleItem(
            day_of_week=int(data['day_of_week']),
            week_parity=int(data['week_parity']),
            start_time=data['start_time'],   # "09:00"
            end_time=data['end_time'],       # "10:35"
            subject=data['subject'].strip(),
            group_name=data['group_name'].strip(),
            room=data.get('room', '').strip() or None,
            teacher_id=current_user.id
        )
        db.session.add(item)
        db.session.commit()

        return jsonify({
            'id': item.id,
            'message': 'Занятие добавлено в шаблон'
        }), 201

    except Exception as e:
        db.session.rollback()
        print("Ошибка:", e)
        return jsonify({'error': 'Не удалось сохранить'}), 500
    
@app.route('/api/teacher/schedule/<int:item_id>', methods=['PUT'])
@login_required
def update_schedule_item(item_id):
    if current_user.role != 'teacher':
        return jsonify({'error': 'Только для преподавателей'}), 403

    data = request.get_json()
    subject = data.get('subject')
    group = data.get('group')
    start_time_str = data.get('start_time')  # "09:00:00"
    end_time_str = data.get('end_time')      # "10:35:00"

    if not subject or not group or not start_time_str or not end_time_str:
        return jsonify({'error': 'Все поля обязательны'}), 400

    item = ScheduleItem.query.get_or_404(item_id)

    if item.teacher_id != current_user.id:
        return jsonify({'error': 'Это не ваше занятие'}), 403

    try:
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()

        item.subject = subject
        item.group_name = group
        item.start_time = start_time
        item.end_time = end_time
        

        db.session.commit()

        return jsonify({
            'status': 'success',
            'message': 'Занятие в шаблоне обновлено',
            'item': {
                'id': item.id,
                'subject': item.subject,
                'group': item.group_name,
                'start_time': item.start_time.strftime('%H:%M'),
                'end_time': item.end_time.strftime('%H:%M')
            }
        })

    except ValueError as e:
        return jsonify({'error': f'Неверный формат времени: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        print("Ошибка обновления:", e)
        return jsonify({'error': 'Не удалось обновить'}), 5000

@app.route('/api/teacher/schedule/<int:item_id>', methods=['DELETE'])
@login_required
def api_delete_schedule_item(item_id):
    if current_user.role != 'teacher':
        return jsonify({'error': 'access denied'}), 403

    item = ScheduleItem.query.filter_by(id=item_id, teacher_id=current_user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    return jsonify({'message': 'Удалено'}), 200

# Статистика
@app.route('/attendance')
@login_required
def attendance():
    if current_user.role != 'student':
        flash('Статистика доступна только студентам', 'error')
        return redirect(url_for('login'))
    return render_template('attendance.html')

from sqlalchemy import func

@app.route('/api/attendance')
@login_required
def api_attendance():
    if current_user.role != 'student':
        return jsonify({'error': 'Только для студентов'}), 403

    group = current_user.group
    if not group:
        return jsonify([])

    start_date = date(2025, 9, 1)
    end_date = date(2025, 12, 20)

    items = ScheduleItem.query.filter_by(group_name=group).all()

    # Группируем по subject + group
    from collections import defaultdict
    stats_by_subject = defaultdict(lambda: {"expected": 0, "attended": 0})

    for item in items:
        attended = Attendance.query.filter(
            Attendance.student_id == current_user.id,
            Attendance.schedule_item_id == item.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        ).count()

        expected = count_expected_lectures(item, start_date, end_date)

        key = (item.subject, item.group_name)
        stats_by_subject[key]["expected"] += expected
        stats_by_subject[key]["attended"] += attended

    result = []
    for (subject, group_name), stat in stats_by_subject.items():
        percentage = round(stat["attended"] / stat["expected"] * 100, 1) if stat["expected"] else 0
        result.append({
            "subject": subject,
            "group": group_name,
            "expected": stat["expected"],
            "attended": stat["attended"],
            "percentage": percentage
        })

    return jsonify(result)

@app.route('/teacher/attendance')
@login_required
def teacher_attendance():
    if current_user.role != 'teacher':
        flash('Доступ разрешён только преподавателям', 'error')
        return redirect(url_for('login'))
    groups = db.session.query(ScheduleItem.group_name).filter_by(
        teacher_id=current_user.id
    ).distinct().all()
    groups = [g[0] for g in groups if g[0]]
    return render_template('teacher_attendance.html', groups=groups)

from datetime import datetime

@app.route('/api/teacher/attendance')
@login_required
def api_teacher_attendance():
    if current_user.role != 'teacher':
        return jsonify({'error': 'Доступ запрещён'}), 403

    group = request.args.get('group')
    date_str = request.args.get('date')
    
    if not date_str:
        return jsonify({'error': 'Параметр date обязателен'}), 400

    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': 'Неверный формат даты (YYYY-MM-DD)'}), 400

    # Получаем занятия преподавателя на эту дату
    semester_start = date(2025, 9, 1)
    week_num = ((target_date - semester_start).days // 7) + 1
    parity = week_num % 2
    dow = target_date.isoweekday()

    query = ScheduleItem.query.filter_by(
        teacher_id=current_user.id,
        day_of_week=dow,
        week_parity=parity
    )
    if group:
        query = query.filter_by(group_name=group)
    lessons = query.all()

    result = []

    for lesson in lessons:
        # Получаем студентов группы
        students = User.query.filter_by(
            role='student',
            group=lesson.group_name
        ).all()

        student_list = []
        for student in students:
            attendance = Attendance.query.filter_by(
                student_id=student.id,
                schedule_item_id=lesson.id,
                date=target_date
            ).first()

            student_list.append({
                'name': student.username,
                'attended': bool(attendance),
                'timestamp': attendance.scanned_at.isoformat() if attendance and hasattr(attendance, 'scanned_at') else None
            })

        result.append({
            'subject': lesson.subject,
            'time': f"{lesson.start_time}–{lesson.end_time}",
            'group_name': lesson.group_name,
            'students': student_list
        })

    return jsonify({
        'date': target_date.isoformat(),
        'lessons': result
    })

from flask import send_file
import pandas as pd
from io import BytesIO

@app.route('/api/teacher/attendance/export')
@login_required
def export_attendance_excel():
    if current_user.role != 'teacher':
        return jsonify({'error': 'Доступ запрещён'}), 403

    group = request.args.get('group')
    date_str = request.args.get('date')
    
    if not date_str:
        return jsonify({'error': 'date обязателен'}), 400

    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': 'Неверный формат даты'}), 400

    # Получаем данные (аналогично api_teacher_attendance)
    semester_start = date(2025, 9, 1)
    week_num = ((target_date - semester_start).days // 7) + 1
    parity = week_num % 2
    dow = target_date.isoweekday()

    query = ScheduleItem.query.filter_by(
        teacher_id=current_user.id,
        day_of_week=dow,
        week_parity=parity
    )
    if group:
        query = query.filter_by(group_name=group)
    lessons = query.all()

    rows = []
    for lesson in lessons:
        students = User.query.filter_by(role='student', group=lesson.group_name).all()
        for student in students:
            att = Attendance.query.filter_by(
                student_id=student.id,
                schedule_item_id=lesson.id,
                date=target_date
            ).first()
            rows.append({
                'Группа': lesson.group_name,
                'Предмет': lesson.subject,
                'Время': f"{lesson.start_time}–{lesson.end_time}",
                'Студент': student.username,
                'Статус': 'Присутствует' if att else 'Отсутствует',
                'Дата': target_date.isoformat(),
                'Время отметки': att.scanned_at.strftime('%H:%M:%S') if att and hasattr(att, 'createt') else ''
            })

    if not rows:
        rows = [{'Группа': group or '', 'Предмет': '', 'Время': '', 'Студент': 'Нет данных', 'Статус': '', 'Дата': date_str, 'Время отметки': ''}]

    df = pd.DataFrame(rows)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Посещаемость')
        worksheet = writer.sheets['Посещаемость']
        for column_cells in worksheet.columns:
            length = max(len(str(cell.value)) for cell in column_cells)
            worksheet.column_dimensions[column_cells[0].column_letter].width = min(length + 2, 30)

    output.seek(0)
    filename = f"Посещаемость_{group or 'все'}_{target_date}.xlsx"
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

from datetime import date, timedelta

def count_expected_lectures(schedule_item, start_date, end_date):
    """Считает, сколько раз занятие по шаблону должно быть в периоде."""
    count = 0
    current = start_date
    semester_start = date(2025, 9, 1)  # начало семестра

    while current <= end_date:
        # Совпадает ли день недели?
        if current.isoweekday() == schedule_item.day_of_week:
            # Совпадает ли чётность?
            weeks_since_start = (current - semester_start).days // 7
            current_parity = weeks_since_start % 2
            if current_parity == schedule_item.week_parity:
                count += 1
        current += timedelta(days=1)
    return count


@app.route('/')
def home():
    return render_template('index2.html')

#if __name__ == '__main__':
#    with app.app_context():
 #       db.create_all()
#        print("Таблицы созданы!")
#   app.run(debug=True)