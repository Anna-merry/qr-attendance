
class TeacherTodayView {
    constructor() {
        this.fullSchedule = {};
    }

    async loadSchedule() {
        try {
            const res = await fetch('/api/teacher/schedule', {
            credentials: 'include'  // ← ЭТО КЛЮЧЕВОЙ МОМЕНТ!
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.fullSchedule = await res.json();
            console.log('✅ Расписание загружено:', this.fullSchedule);
            return this.fullSchedule;
        } catch (e) {
            console.error('❌ Ошибка загрузки расписания:', e);
            this.fullSchedule = {};
            throw e;
        }
    }

    formatDate(d) {
        return d.toISOString().split('T')[0];
    }
}

// Глобальный экземпляр для teacher.html
const todayView = new TeacherTodayView();

// Формат: "чт, 26.11"
function formatShortDate(date) {
    const days = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
    return `${days[date.getDay()]}, ${String(date.getDate()).padStart(2, '0')}.${String(date.getMonth() + 1).padStart(2, '0')}`;
}

// Открытие QR — строго по твоему маршруту: /qr/full/<id>
function openQR(lectureId) {
    const w = screen.width, h = screen.height;
    const url = `/qr/full/${lectureId}`;
    window.open(url, '_blank', `width=${w},height=${h},left=0,top=0,fullscreen=yes,location=no,menubar=no,toolbar=no`);
}

// Рендер занятий на сегодня
function renderTodayLessons() {
    const today = new Date();
    const key = todayView.formatDate(today);
    console.log('📅 Сегодня:', key);

    const container = document.getElementById('teacher-classes-container');
    if (!container) {
        console.warn('❌ Контейнер не найден');
        return;
    }

    // ✅ Без ?. в присваивании
    const dateEl = document.getElementById('current-date');
    if (dateEl) {
        dateEl.textContent = formatShortDate(today);
    }

    const lessons = todayView.fullSchedule[key] || [];
    console.log('📚 Занятия:', lessons);

    container.innerHTML = lessons.length
        ? lessons.map(l => `
            <div class="class-card">
                <h4>${l.subject || '—'}</h4>
                <div class="class-time">
                    <span class="time-slot">${l.time || '—'}</span>
                    <span class="group-name">${l.group_name || '—'}</span>
                    <button class="mark-btn" onclick="openQR(${l.id})">Отметиться</button>
                </div>
            </div>
        `).join('')
        : '<div class="no-classes">Сегодня занятий нет</div>';
}

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOMContentLoaded сработал!');

    const dateEl = document.getElementById('current-date');
    const containerEl = document.getElementById('teacher-classes-container');

    console.log('🔍 Элементы:', { dateEl, containerEl });

    if (!dateEl || !containerEl) {
        console.error('❌ Один из элементов не найден!');
        return;
    }

    // ✅ Без ?. в присваивании
    dateEl.textContent = formatShortDate(new Date());

    todayView.loadSchedule()
        .then(() => {
            console.log('🎉 Расписание загружено, рендерим...');
            renderTodayLessons();
        })
        .catch(err => {
            console.error('💥 Ошибка:', err);
            containerEl.innerHTML = '<div class="error">❌ Не удалось загрузить расписание</div>';
        });
});