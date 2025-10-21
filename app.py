import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from werkzeug.security import generate_password_hash, check_password_hash
from flask import render_template, request, redirect, url_for, flash
from flask_login import UserMixin

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
    def set_password(self, password):
     self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    def check_password(self, password):
     return check_password_hash(self.password_hash, password)
class Lecture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)
    group = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lecture.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form.get('role', 'student')

        if User.query.filter_by(username=username).first():
            flash('Пользователь уже существует')
            return redirect(url_for('register'))

        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Регистрация успешна!')
        return redirect(url_for('login'))
    return '''
    <form method="post">
        Логин: <input name="username"><br>
        Пароль: <input name="password" type="password"><br>
        Роль: <select name="role">
            <option value="student">Студент</option>
            <option value="teacher">Преподаватель</option>
        </select><br>
        <button>Зарегистрироваться</button>
    </form>
    '''

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            from flask_login import login_user
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Неверный логин или пароль')
    return '''
    <form method="post">
        Логин: <input name="username"><br>
        Пароль: <input name="password" type="password"><br>
        <button>Войти</button>
    </form>
    '''

@app.route('/dashboard')
def dashboard():
    from flask_login import current_user
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return f"<h1>Привет, {current_user.username} ({current_user.role})!</h1><a href='/logout'>Выйти</a>"

@app.route('/logout')
def logout():
    from flask_login import logout_user
    logout_user()
    return redirect(url_for('login'))

# Создание БД
with app.app_context():
    db.create_all()
    print("✅ Таблицы созданы!")



@app.route('/')
def home():
    return "<h1>Система посещаемости запущена!</h1><p><a href='/register'>Регистрация</a> | <a href='/login'>Вход</a></p>"

if __name__ == '__main__':
    app.run(debug=True)