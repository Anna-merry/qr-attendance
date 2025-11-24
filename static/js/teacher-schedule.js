
class TeacherScheduleApp {
    constructor() {
        this.currentDate = new Date(2025, 9, 1); // Октябрь 2025
        this.selectedDate = null;
        this.fullSchedule = {}; // { "2025-10-01": [...] }
        this.semesterStart = new Date(2025, 8, 1); // 1 сентября 2025 (месяцы с 0!)
        this.groups = [
            'Д-Э 301', 'Д-Э 302', 'Д-Э 303', 'Д-Э 304', 'Д-Э 305',
            'Д-Э 306', 'Д-Э 307', 'Д-Э 308', 'Д-Э 309', 'Д-Э 310'
        ];
        this.editingClassId = null;
        this.editingDateString = null;
        this.init();
    }

    async init() {
        await this.loadSchedule();
        this.renderCalendar();
        this.showClassesForDate(this.selectedDate || new Date());
    }

    async loadSchedule() {
        try {
            const res = await fetch('/api/teacher/schedule');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.fullSchedule = await res.json();
        } catch (e) {
            console.error('❌ Ошибка загрузки расписания:', e);
            // Оставляем пустой объект — интерфейс не сломается
        }
    }

    getWeekInfo(date) {
        const diff = Math.floor((date - this.semesterStart) / 86400000);
        const weekNum = Math.floor(diff / 7) + 1;
        const parity = weekNum % 2; // 1 = нечётная, 0 = чётная
        return { weekNum, parity };
    }

    // === Календарь ===
    renderCalendar() {
        const grid = document.getElementById('teacher-calendar-grid');
        const monthEl = document.getElementById('teacher-current-month');

        const monthNames = ['Январь','Февраль','Март','Апрель','Май','Июнь',
                            'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];
        monthEl.textContent = `${monthNames[this.currentDate.getMonth()]} ${this.currentDate.getFullYear()}`;
        grid.innerHTML = '';

        // Заголовки дней
        ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'].forEach(d => {
            const h = document.createElement('div');
            h.className = 'calendar-day-header';
            h.textContent = d;
            grid.appendChild(h);
        });

        const first = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth(), 1);
        const last = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth() + 1, 0);
        const startOffset = (first.getDay() + 6) % 7; // Пн = 0

        // Предыдущие дни
        for (let i = startOffset - 1; i >= 0; i--) {
            const d = new Date(first);
            d.setDate(-i);
            grid.appendChild(this.renderDay(d, true));
        }

        // Текущие дни
        for (let day = 1; day <= last.getDate(); day++) {
            const d = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth(), day);
            grid.appendChild(this.renderDay(d, false));
        }
    }

    renderDay(date, isOtherMonth) {
        const el = document.createElement('button');
        el.className = 'calendar-day';
        if (isOtherMonth) el.classList.add('other-month');

        const { parity } = this.getWeekInfo(date);
        el.classList.add(parity ? 'odd-week' : 'even-week');

        const key = this.formatDate(date);
        const events = this.fullSchedule[key] || [];
        el.innerHTML = `
            <div class="day-number">${date.getDate()}</div>
            ${events.length ? `<div class="day-events">${events.length} ${this.getClassWord(events.length)}</div>` : ''}
        `;

        if (this.selectedDate && this.isSameDay(date, this.selectedDate)) {
            el.classList.add('active');
        }

        el.onclick = () => this.selectDate(date);
        return el;
    }

    getClassWord(count) {
        if (count === 1) return 'занятие';
        if (count >= 2 && count <= 4) return 'занятия';
        return 'занятий';
    }

    selectDate(date) {
        this.selectedDate = date;
        this.renderCalendar();
        this.showClassesForDate(date);
    }

    showClassesForDate(date) {
        const container = document.getElementById('teacher-classes-container');
        const key = this.formatDate(date);
        const events = this.fullSchedule[key] || [];

        const { weekNum, parity } = this.getWeekInfo(date);
        document.getElementById('teacher-selected-date').textContent =
            `Занятия на ${date.toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'numeric' })} (неделя ${weekNum}, ${parity ? 'нечётная' : 'чётная'}):`;

        if (!events.length) {
            container.innerHTML = '<div class="no-classes">На выбранную дату занятий нет</div>';
            return;
        }

        container.innerHTML = events.map(e => `
            <div class="class-item">
                <div class="class-info">
                    <div class="class-name">${e.subject || e.name}</div>
                    <div class="class-details">
                        <span class="class-time">${e.time}</span>
                        <span class="class-group">Группа: ${e.group || e.group_name}</span>
                    </div>
                </div>
                <div class="class-actions">
                    <button class="edit-btn" onclick="app.editClass('${key}', ${e.id})">Изменить</button>
                    <button class="delete-btn" onclick="app.deleteClass('${key}', ${e.id})">Удалить</button>
                </div>
            </div>
        `).join('');
    }

    // === Навигация по месяцам ===
    prevMonth() {
        this.currentDate.setMonth(this.currentDate.getMonth() - 1);
        this.renderCalendar();
    }
    nextMonth() {
        this.currentDate.setMonth(this.currentDate.getMonth() + 1);
        this.renderCalendar();
    }

    // === Модальные окна ===
    showAddClassModal() {
        if (!this.selectedDate) {
            alert('Сначала выберите дату');
            return;
        }
        const select = document.getElementById('teacher-newClassGroup');
        select.innerHTML = '<option value="">Выберите группу</option>' +
            this.groups.map(g => `<option value="${g}">${g}</option>`).join('');
        document.getElementById('teacher-addClassModal').style.display = 'flex';
    }

    hideAddClassModal() {
        document.getElementById('teacher-addClassModal').style.display = 'none';
    }

    async addNewClass() {
        const name = document.getElementById('teacher-newClassName').value.trim();
        const time = document.getElementById('teacher-newClassTime').value.trim();
        const group = document.getElementById('teacher-newClassGroup').value;
        if (!name || !time || !group) return alert('Заполните все поля');

        const parts = time.split(/[–\-]/).map(t => t.trim());
        if (parts.length < 2) return alert('Формат времени: 9:00–10:35');

        const { parity } = this.getWeekInfo(this.selectedDate);
        const dow = this.selectedDate.getDay() || 7; // Вс → 7

        try {
            const res = await fetch('/api/teacher/schedule', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    day_of_week: dow,
                    week_parity: parity,
                    start_time: parts[0] + ':00',
                    end_time: parts[1] + ':00',
                    subject: name,
                    group_name: group
                })
            });

            if (res.ok) {
                await this.loadSchedule();
                this.renderCalendar();
                this.showClassesForDate(this.selectedDate);
                this.hideAddClassModal();

                // Сброс формы
                document.getElementById('teacher-newClassName').value = '';
                document.getElementById('teacher-newClassTime').value = '';
                document.getElementById('teacher-newClassGroup').value = '';
            } else {
                const err = await res.json();
                alert(err.error || 'Ошибка сохранения');
            }
        } catch (e) {
            alert('Сетевая ошибка');
        }
    }

    async deleteClass(dateStr, id) {
        if (!confirm('Вы уверены, что хотите удалить это занятие?')) return;

        try {
            const res = await fetch(`/api/teacher/schedule/${id}`, { method: 'DELETE' });
            if (res.ok) {
                await this.loadSchedule();
                this.renderCalendar();
                this.showClassesForDate(this.selectedDate);
            } else {
                alert('Не удалось удалить занятие');
            }
        } catch (e) {
            alert('Ошибка удаления');
        }
    }

    editClass(dateStr, id) {
        const item = (this.fullSchedule[dateStr] || []).find(e => e.id === id);
        if (!item) return;

        document.getElementById('teacher-editClassName').value = item.subject || item.name;
        document.getElementById('teacher-editClassTime').value = item.time;
        document.getElementById('teacher-editClassGroup').value = item.group || item.group_name;

        this.editingClassId = id;
        this.editingDateString = dateStr;
        this.showEditClassModal();
    }

    async saveClassChanges() {
        const name = document.getElementById('teacher-editClassName').value.trim();
        const time = document.getElementById('teacher-editClassTime').value.trim();
        const group = document.getElementById('teacher-editClassGroup').value;
        if (!name || !time || !group) return alert('Заполните все поля');

        const parts = time.split(/[–\-]/).map(t => t.trim());
        if (parts.length < 2) return alert('Формат времени: 9:00–10:35');

        try {
            const res = await fetch(`/api/teacher/schedule/${this.editingClassId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    subject: name,
                    start_time: parts[0] + ':00',
                    end_time: parts[1] + ':00',
                    group_name: group
                })
            });

            if (res.ok) {
                await this.loadSchedule();
                this.showClassesForDate(this.selectedDate);
                this.hideEditClassModal();
            } else {
                alert('Не удалось сохранить изменения');
            }
        } catch (e) {
            alert('Ошибка сохранения');
        }
    }

    showEditClassModal() {
        document.getElementById('teacher-editClassModal').style.display = 'flex';
    }

    hideEditClassModal() {
        document.getElementById('teacher-editClassModal').style.display = 'none';
        this.editingClassId = null;
        this.editingDateString = null;
    }

    // === Утилиты ===
    formatDate(d) { return d.toISOString().split('T')[0]; }
    isSameDay(a, b) { return this.formatDate(a) === this.formatDate(b); }
}

// Глобальный экземпляр
const app = new TeacherScheduleApp();

// Совместимость с onclick из 123.docx
function teacherCalendarPreviousMonth() { app.prevMonth(); }
function teacherCalendarNextMonth() { app.nextMonth(); }
function teacherCalendarShowAddClassModal() { app.showAddClassModal(); }
function teacherCalendarHideAddClassModal() { app.hideAddClassModal(); }
function teacherCalendarAddNewClass() { app.addNewClass(); }
function teacherCalendarHideEditClassModal() { app.hideEditClassModal(); }
function teacherCalendarSaveClassChanges() { app.saveClassChanges(); }

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', () => {
    // app.init() уже вызван в конструкторе
});