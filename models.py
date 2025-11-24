from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets

db = SQLAlchemy()

class User(UserMixin,db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='student')
    group = db.Column(db.String(50))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Lecture(db.Model):
    __tablename__ = 'lectures'
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)
    group = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    current_token = db.Column(db.String(100))
    token_expires_at = db.Column(db.DateTime)

    def generate_new_token(self):
        self.current_token = secrets.token_urlsafe(16)
        self.token_expires_at = datetime.utcnow() + timedelta(seconds=10)
        return self.current_token

    def is_token_valid(self, token):
        now = datetime.utcnow()
        return (
            self.current_token == token and
            self.token_expires_at is not None and
            self.token_expires_at > now
        )

class Attendance(db.Model):
    __tablename__ = 'attendances'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lectures.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    token_used = db.Column(db.String(100))  # ← добавлено

# === НОВАЯ МОДЕЛЬ: шаблон расписания (для двухнедельного цикла) ===
class ScheduleItem(db.Model):
    __tablename__ = 'schedule_items'
    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.Integer, nullable=False)  # 1=Пн, 7=Вс
    week_parity = db.Column(db.Integer, nullable=False)  # 1=нечёт, 0=чёт
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    subject = db.Column(db.String(150), nullable=False)
    group_name = db.Column(db.String(20), nullable=False)
    room = db.Column(db.String(20))
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)