import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from datetime import datetime, date
import qrcode
from io import BytesIO

# Импортируем модели и хелперы
from models import db, User, Lecture, Attendance, ScheduleItem
from helpers import expand_schedule_to_semester, generate_token

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:mypostgrespwd@localhost:5432/qr_attendance'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

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
    

@app.route('/dashboard')
def dashboard():
    from flask_login import current_user
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return render_template('student.html')

@app.route('/scan')
@login_required
def scan_page():
    if current_user.role != 'student':
        return "Только для студентов", 403
    return render_template('scan.html')  # ← новый шаблон

@app.route('/api/scan', methods=['POST'])
@login_required
def scan_qr():
    if current_user.role != 'student':
        return jsonify({'status': 'error', 'message': 'Только для студентов'}), 403

    data = request.get_json()
    token = data.get('token')
    lecture_id = data.get('lecture_id')

    if not token or not lecture_id:
        return jsonify({'status': 'error', 'message': 'Нет токена или ID занятия'}), 400

    lecture = Lecture.query.get(lecture_id)
    if not lecture:
        return jsonify({'status': 'error', 'message': 'Занятие не найдено'}), 404

    # Проверяем токен
    if not lecture.is_token_valid(token):
        return jsonify({'status': 'error', 'message': 'Токен недействителен или просрочен'}), 400

    # Проверяем, не сканировал ли уже этот студент
    existing = Attendance.query.filter_by(
        student_id=current_user.id,
        lecture_id=lecture_id
    ).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Вы уже отметились'}), 409

    # Записываем посещение
    attendance = Attendance(
        student_id=current_user.id,
        lecture_id=lecture_id,
        token_used=token
    )
    db.session.add(attendance)
    db.session.commit()

    return jsonify({'status': 'success', 'message': '✅ Посещение засчитано!'})

@app.route('/logout')
def logout():
    from flask_login import logout_user
    logout_user()
    return redirect(url_for('login'))

@app.route('/lectures')
@login_required
def lectures():
    if current_user.role == 'teacher':
        lecture_list = Lecture.query.filter_by(teacher_id=current_user.id).all()
    else:
        lecture_list = []  # студенты пока не видят занятия
    return render_template('teacher.html', lectures=lecture_list)

@app.route('/create_lecture', methods=['GET', 'POST'])
@login_required
def create_lecture():
    if current_user.role != 'teacher':
        return "Доступ запрещён", 403

    if request.method == 'POST':
        lecture = Lecture(
            subject=request.form['subject'],
            group=request.form['group'],
            date=request.form['date'],
            time = request.form['time'],
            teacher_id=current_user.id
        )
        db.session.add(lecture)
        db.session.commit()
        return redirect(url_for('lectures'))

    return render_template('create_lecture.html', today=date.today())

@app.route('/qr/full/<int:lecture_id>')
@login_required
def qr_fullscreen(lecture_id):
    if current_user.role != 'teacher':
        return "Только для преподавателей", 403
    return render_template('qr_fullscreen.html', lecture_id=lecture_id)

@app.route('/lecture/<int:lecture_id>')
@login_required
def lecture_qr(lecture_id):
    # Только для преподавателя
    if current_user.role != 'teacher':
        return "Доступ запрещён", 403

    # Проверяем, что занятие принадлежит текущему преподавателю
    lecture = Lecture.query.filter_by(
        id=lecture_id,
        teacher_id=current_user.id
    ).first_or_404()

    # Обновляем токен, если прошло ≥10 сек или его нет
    now = datetime.utcnow()
    if not lecture.current_token or lecture.token_expires_at <= now:
        lecture.generate_new_token()
        db.session.commit()

    # Возвращаем токен и время истечения (для фронтенда)
    return jsonify({
        'token': lecture.current_token,
        'expires_at': lecture.token_expires_at.isoformat(),
        'seconds_left': (lecture.token_expires_at - now).total_seconds()
    })

@app.route('/qr-image/<int:lecture_id>')
@login_required
def qr_image(lecture_id):
    lecture = Lecture.query.get_or_404(lecture_id)
    if not lecture.current_token:
        lecture.generate_new_token()
        db.session.commit()

    # URL для сканирования (на реальном сервере замените localhost на домен)
    qr_data = f"http://localhost:5000/scan?token={lecture.current_token}&lecture_id={lecture_id}"

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


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