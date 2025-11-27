from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets
from sqlalchemy.exc import IntegrityError 

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='student')
    group = db.Column(db.String(50))

    # Отношения (для обратной связи)
    schedule_items = db.relationship('ScheduleItem', backref='teacher', lazy=True)
    attendances = db.relationship('Attendance', foreign_keys='Attendance.student_id', backref='student', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


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

    def __repr__(self):
        return f"<ScheduleItem {self.subject} ({self.group_name})>"


class Attendance(db.Model):
    __tablename__ = 'attendance'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    schedule_item_id = db.Column(db.Integer, db.ForeignKey('schedule_items.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)  # дата занятия, например: 2025-11-26
    scanned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Отношения
    schedule_item = db.relationship('ScheduleItem', backref='attendances')

    # Уникальность: один студент — одна отметка на одно занятие в день
    __table_args__ = (
        db.UniqueConstraint('student_id', 'schedule_item_id', 'date', name='uq_student_item_date'),
    )

    def __repr__(self):
        return f"<Attendance {self.student.username} → {self.schedule_item.subject} on {self.date}>"
