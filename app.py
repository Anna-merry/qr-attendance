import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask import render_template, request, redirect, url_for, flash, send_file
from flask_login import UserMixin, LoginManager,login_required, current_user
import qrcode
from io import BytesIO


from datetime import date


app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:mypostgrespwd@localhost:5432/qr_attendance'

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id)) 

# Модели
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='student')  # 'student' или 'teacher'
    group = db.Column(db.String(50))  #  (может быть NULL для преподавателей)
    def set_password(self, password):
     self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    def check_password(self, password):
     return check_password_hash(self.password_hash, password)
class Lecture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)
    group = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lecture.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())


from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import login_user

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

import qrcode
from io import BytesIO
from flask import send_file

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

    # Генерируем URL для сканирования (на реальном сайте — с доменом)
    # Пока — локальный URL
    qr_data = f"http://localhost:5000/scan?lecture_id={lecture_id}"

    # Создаём QR-код
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # Отправляем как изображение
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

# Создание БД
with app.app_context():
    db.create_all()
    print(" Таблицы созданы!")



@app.route('/')
def home():
    return render_template('index2.html')

if __name__ == '__main__':
    app.run(debug=True)