from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///habits.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your-secret-key-change-this'

db = SQLAlchemy(app)

# ─── MODELS ───────────────────────────────────────────────
class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    frequency = db.Column(db.String(20), default='daily')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    streak = db.Column(db.Integer, default=0)
    longest_streak = db.Column(db.Integer, default=0)
    completions = db.relationship('HabitCompletion', backref='habit', lazy=True, cascade='all, delete-orphan')

class HabitCompletion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'), nullable=False)
    completed_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.String(200))

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500))
    priority = db.Column(db.String(10), default='medium')  # low, medium, high, urgent
    due_date = db.Column(db.Date)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(50), default='general')

# ─── ROUTES ───────────────────────────────────────────────
@app.route('/')
def index():
    today = date.today()
    habits = Habit.query.all()
    tasks_due_today = Task.query.filter_by(due_date=today, completed=False).all()
    overdue_tasks = Task.query.filter(
        Task.due_date < today, Task.completed == False
    ).all()
    
    # Which habits completed today
    completed_today_ids = {
        c.habit_id for c in HabitCompletion.query.filter_by(completed_date=today).all()
    }
    
    return render_template('index.html',
        habits=habits,
        tasks_due_today=tasks_due_today,
        overdue_tasks=overdue_tasks,
        completed_today_ids=completed_today_ids,
        today=today
    )

# ── HABIT ROUTES ──
@app.route('/habits')
def habits():
    habits = Habit.query.all()
    today = date.today()
    completed_today_ids = {
        c.habit_id for c in HabitCompletion.query.filter_by(completed_date=today).all()
    }
    return render_template('habits.html', habits=habits, completed_today_ids=completed_today_ids, today=today)

@app.route('/habit/add', methods=['GET', 'POST'])
def add_habit():
    if request.method == 'POST':
        habit = Habit(
            name=request.form['name'],
            description=request.form.get('description', ''),
            frequency=request.form.get('frequency', 'daily')
        )
        db.session.add(habit)
        db.session.commit()
        return redirect(url_for('habits'))
    return render_template('add_habit.html')

@app.route('/habit/complete/<int:habit_id>', methods=['POST'])
def complete_habit(habit_id):
    today = date.today()
    habit = Habit.query.get_or_404(habit_id)
    existing = HabitCompletion.query.filter_by(habit_id=habit_id, completed_date=today).first()
    
    if existing:
        db.session.delete(existing)
        recalculate_streak(habit)
    else:
        completion = HabitCompletion(habit_id=habit_id, completed_date=today)
        db.session.add(completion)
        recalculate_streak(habit)
    
    db.session.commit()
    return redirect(request.referrer or url_for('habits'))

def recalculate_streak(habit):
    completions = sorted(
        [c.completed_date for c in habit.completions],
        reverse=True
    )
    if not completions:
        habit.streak = 0
        return
    
    streak = 0
    check_date = date.today()
    for comp_date in completions:
        if comp_date == check_date or comp_date == check_date - timedelta(days=1):
            streak += 1
            check_date = comp_date - timedelta(days=1)
        else:
            break
    
    habit.streak = streak
    if streak > habit.longest_streak:
        habit.longest_streak = streak

@app.route('/habit/delete/<int:habit_id>', methods=['POST'])
def delete_habit(habit_id):
    habit = Habit.query.get_or_404(habit_id)
    db.session.delete(habit)
    db.session.commit()
    return redirect(url_for('habits'))

# ── TASK ROUTES ──
@app.route('/tasks')
def tasks():
    priority_order = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}
    all_tasks = Task.query.filter_by(completed=False).all()
    all_tasks.sort(key=lambda t: (priority_order.get(t.priority, 2), t.due_date or date.max))
    completed_tasks = Task.query.filter_by(completed=True).order_by(Task.completed_at.desc()).limit(20).all()
    return render_template('tasks.html', tasks=all_tasks, completed_tasks=completed_tasks, today=date.today())

@app.route('/task/add', methods=['GET', 'POST'])
def add_task():
    if request.method == 'POST':
        due_date_str = request.form.get('due_date')
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None
        task = Task(
            title=request.form['title'],
            description=request.form.get('description', ''),
            priority=request.form.get('priority', 'medium'),
            due_date=due_date,
            category=request.form.get('category', 'general')
        )
        db.session.add(task)
        db.session.commit()
        return redirect(url_for('tasks'))
    return render_template('add_task.html', today=date.today())

@app.route('/task/complete/<int:task_id>', methods=['POST'])
def complete_task(task_id):
    task = Task.query.get_or_404(task_id)
    task.completed = not task.completed
    task.completed_at = datetime.utcnow() if task.completed else None
    db.session.commit()
    return redirect(request.referrer or url_for('tasks'))

@app.route('/task/delete/<int:task_id>', methods=['POST'])
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for('tasks'))

# ── CALENDAR ROUTE ──
@app.route('/calendar')
def calendar_view():
    today = date.today()
    year = int(request.args.get('year', today.year))
    month = int(request.args.get('month', today.month))
    
    import calendar
    cal = calendar.monthcalendar(year, month)
    month_name = calendar.month_name[month]
    
    # Get all completions and tasks for this month
    month_start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)
    
    completions = HabitCompletion.query.filter(
        HabitCompletion.completed_date >= month_start,
        HabitCompletion.completed_date <= month_end
    ).all()
    
    tasks_month = Task.query.filter(
        Task.due_date >= month_start,
        Task.due_date <= month_end
    ).all()
    
    completion_map = {}
    for c in completions:
        d = c.completed_date.day
        completion_map[d] = completion_map.get(d, 0) + 1
    
    task_map = {}
    for t in tasks_month:
        d = t.due_date.day
        if d not in task_map:
            task_map[d] = []
        task_map[d].append(t)
    
    # Prev/Next month
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year
    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year
    
    return render_template('calendar.html',
        cal=cal, month_name=month_name, year=year, month=month,
        today=today, completion_map=completion_map, task_map=task_map,
        prev_month=prev_month, prev_year=prev_year,
        next_month=next_month, next_year=next_year
    )

# ── WEEKLY SUMMARY ROUTE ──
@app.route('/summary')
def weekly_summary():
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    habits = Habit.query.all()
    habit_data = []
    for habit in habits:
        completions = HabitCompletion.query.filter(
            HabitCompletion.habit_id == habit.id,
            HabitCompletion.completed_date >= week_start,
            HabitCompletion.completed_date <= week_end
        ).all()
        completed_days = {c.completed_date for c in completions}
        habit_data.append({
            'habit': habit,
            'completions': len(completions),
            'rate': round(len(completions) / 7 * 100),
            'completed_days': completed_days
        })
    
    tasks_completed = Task.query.filter(
        Task.completed == True,
        Task.completed_at >= datetime.combine(week_start, datetime.min.time()),
        Task.completed_at <= datetime.combine(week_end, datetime.max.time())
    ).all()
    
    tasks_pending = Task.query.filter_by(completed=False).filter(
        Task.due_date <= week_end
    ).all()
    
    overdue = Task.query.filter(
        Task.due_date < today, Task.completed == False
    ).count()
    
    week_days = [week_start + timedelta(days=i) for i in range(7)]
    
    return render_template('summary.html',
        habit_data=habit_data,
        tasks_completed=tasks_completed,
        tasks_pending=tasks_pending,
        overdue=overdue,
        week_start=week_start,
        week_end=week_end,
        week_days=week_days,
        today=today
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
