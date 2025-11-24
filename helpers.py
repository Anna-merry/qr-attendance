from datetime import datetime, timedelta
from models import ScheduleItem, db

# Генерация расписания на семестр 
def expand_schedule_to_semester(teacher_id, start_date=None, end_date=None):
   
    if start_date is None:
        start_date = datetime(2025, 9, 1).date()  # 1 сентября
    if end_date is None:
        end_date = datetime(2025, 12, 31).date()  # 31 декабря

    # Загружаем шаблон
    template = ScheduleItem.query.filter_by(teacher_id=teacher_id).all()
    if not template:
        return {}

    # Группируем по (день_недели, чётность)
    grouped = {}
    for item in template:
        key = (item.day_of_week, item.week_parity)
        grouped.setdefault(key, []).append(item)

    result = {}

    current = start_date
    week_num = 1

    while current <= end_date:
        dow = current.isoweekday()  # Пн=1, ..., Вс=7
        parity = week_num % 2       # 1=нечёт, 0=чёт

        for lesson in grouped.get((dow, parity), []):
            date_str = current.isoformat()
            if date_str not in result:
                result[date_str] = []
            result[date_str].append({
                'id': lesson.id,
                'subject': lesson.subject,
                'time': f"{lesson.start_time.strftime('%H:%M')}–{lesson.end_time.strftime('%H:%M')}",
                'group': lesson.group_name,
                'room': lesson.room or '—',
                'week_num': week_num,
                'parity_str': 'нечётная' if parity == 1 else 'чётная'
            })
        current += timedelta(days=1)
        if current.weekday() == 0 and current != start_date:
            week_num += 1

    return result

# === Токены для QR ===
def generate_token():
    return secrets.token_urlsafe(16)