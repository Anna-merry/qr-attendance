import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
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
app.config['SECRET_KEY'] = 'dev-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:mypostgrespwd@localhost:5432/qr_attendance'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Вспомогательная функция
def get_todays_lessons(teacher_id, target_date=None):
    if target_date is None:
        target_date = date.today()
    
    semester_start = date(2025, 10, 1)
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
            return redirect(url_for('lectures' if user.role == 'teacher' else 'dashboard'))

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
    
@app.route('/lectures')
@login_required
def lectures():
    if current_user.role != 'teacher':
        return redirect(url_for('login'))
    lessons = get_todays_lessons(current_user.id)
    return render_template('teacher.html', lectures=lessons, now=datetime.now())

@app.route('/dashboard')  # студент
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
    scan_url = url_for('api_scan', item_id=item_id, date=date_str, token=token, _external=True)
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
        # 1 Проверяем подпись и срок (max_age=10 сек)
        token_data = serializer.loads(token, max_age=10)  # ← автоматически проверяет подпись и время!
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
        return jsonify({'status': 'success', 'message': '✅ Посещение засчитано!'})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': 'Неверный формат даты'}), 400
    

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
        for field in ['day_of_week', 'week_parity', 'start_time', 'end_time', 'subject', 'group_name']:
            if not data.get(field):
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
        print("❌ Ошибка:", e)
        return jsonify({'error': 'Не удалось сохранить'}), 500
    
@app.route('/api/teacher/schedule/<int:item_id>', methods=['DELETE'])
@login_required
def api_delete_schedule_item(item_id):
    if current_user.role != 'teacher':
        return jsonify({'error': 'access denied'}), 403

    item = ScheduleItem.query.filter_by(id=item_id, teacher_id=current_user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    return jsonify({'message': 'Удалено'}), 200



@app.route('/')
def home():
    return render_template('index2.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Таблицы созданы!")
    app.run(debug=True)