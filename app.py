from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
from hijri_converter import Gregorian
import locale
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'daywise-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///daywise.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Set locale for date formatting
locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')

# Define constants
PRIORITIES = {'low': 'Low', 'medium': 'Medium', 'high': 'High'}
TIME_BLOCKS = {'any': 'Any', 'morning': 'Morning', 'afternoon': 'Afternoon', 'evening': 'Evening'}

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    dark_mode = db.Column(db.Boolean, default=True)
    tasks = db.relationship('Task', backref='user', lazy='dynamic')
    categories = db.relationship('Category', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(20), default='blue')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tasks = db.relationship('Task', backref='category', lazy='dynamic')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'color': self.color
        }

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    estimated_time = db.Column(db.Integer, nullable=False)  # in minutes
    is_completed = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(20), default='medium')
    time_block = db.Column(db.String(20), default='any')
    order_index = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    subtasks = db.relationship('Subtask', backref='parent_task', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'description': self.description,
            'estimatedTime': self.estimated_time,
            'isCompleted': self.is_completed,
            'priority': self.priority,
            'timeBlock': self.time_block,
            'orderIndex': self.order_index,
            'categoryId': self.category_id
        }
    
    @property
    def subtask_count(self):
        return self.subtasks.count()
    
    @property
    def completed_subtask_count(self):
        return self.subtasks.filter_by(is_completed=True).count()
        
    @property
    def has_subtasks(self):
        return self.subtask_count > 0

class Subtask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    order_index = db.Column(db.Integer, default=0)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    
    def to_dict(self):
        return {
            'id': self.id,
            'description': self.description,
            'isCompleted': self.is_completed,
            'orderIndex': self.order_index,
            'taskId': self.task_id
        }

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Helper functions
def get_dates():
    today = datetime.now()
    gregorian_date = today.strftime("%A, %B %d, %Y")
    
    hijri_date_obj = Gregorian(today.year, today.month, today.day).to_hijri()
    
    hijri_months = ["Muharram", "Safar", "Rabi' al-Awwal", "Rabi' al-Thani", 
                    "Jumada al-Awwal", "Jumada al-Thani", "Rajab", "Sha'ban",
                    "Ramadan", "Shawwal", "Dhu al-Qi'dah", "Dhu al-Hijjah"]
    hijri_date = f"{hijri_date_obj.day} {hijri_months[hijri_date_obj.month-1]}, {hijri_date_obj.year} AH"
    
    return gregorian_date, hijri_date

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('register'))
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        new_user = User(username=username)
        new_user.set_password(password)
        
        # Add default categories
        default_categories = [
            Category(name="Work", color="blue", user=new_user),
            Category(name="Personal", color="green", user=new_user),
            Category(name="Health", color="red", user=new_user),
            Category(name="Learning", color="purple", user=new_user)
        ]
        
        # Add sample tasks for new users
        work_category = default_categories[0]
        personal_category = default_categories[1]
        health_category = default_categories[2]
        learning_category = default_categories[3]
        
        sample_tasks = [
            Task(description='Morning workout', estimated_time=45, is_completed=False, priority='medium', time_block='morning', user=new_user, category=health_category, order_index=1),
            Task(description='Team meeting', estimated_time=60, is_completed=False, priority='high', time_block='morning', user=new_user, category=work_category, order_index=2),
            Task(description='Work on Project X', estimated_time=120, is_completed=True, priority='high', time_block='afternoon', user=new_user, category=work_category, order_index=3),
            Task(description='Read documentation', estimated_time=30, is_completed=False, priority='low', time_block='any', user=new_user, category=learning_category, order_index=4)
        ]
        
        db.session.add(new_user)
        for category in default_categories:
            db.session.add(category)
        for task in sample_tasks:
            db.session.add(task)
            
        # We need to commit first to get task IDs assigned
        db.session.commit()
        
        # Now add the sample subtasks with correct task IDs
        team_meeting_task = Task.query.filter_by(description='Team meeting', user_id=new_user.id).first()
        project_task = Task.query.filter_by(description='Work on Project X', user_id=new_user.id).first()
        
        if team_meeting_task and project_task:
            sample_subtasks = [
                Subtask(description='Prepare meeting agenda', is_completed=False, order_index=1, task_id=team_meeting_task.id),
                Subtask(description='Send meeting invites', is_completed=True, order_index=2, task_id=team_meeting_task.id),
                Subtask(description='Setup frontend components', is_completed=True, order_index=1, task_id=project_task.id)
            ]
            
            for subtask in sample_subtasks:
                db.session.add(subtask)
            db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    gregorian_date, hijri_date = get_dates()
    
    # Get filter parameters
    category_id = request.args.get('category', 'all')
    
    # Get all tasks for the user
    if category_id == 'all' or category_id is None:
        tasks = Task.query.filter_by(user_id=current_user.id).all()
    else:
        tasks = Task.query.filter_by(user_id=current_user.id, category_id=category_id).all()
    
    # Get all categories for the user
    categories = Category.query.filter_by(user_id=current_user.id).all()
    
    # Calculate progress
    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task.is_completed)
    in_progress_tasks = total_tasks - completed_tasks
    percentage = round((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    
    # Sort tasks
    sorted_tasks = sort_tasks(tasks)
    
    # For each task, sort its subtasks by order_index
    for task in sorted_tasks:
        # Convert lazy-loaded subtasks to a sorted list
        subtasks_incomplete = Subtask.query.filter_by(task_id=task.id, is_completed=False).order_by(Subtask.order_index).all()
        subtasks_complete = Subtask.query.filter_by(task_id=task.id, is_completed=True).order_by(Subtask.order_index).all()
        # Replace the lazy-loaded relationship with our sorted list
        task._sorted_subtasks = subtasks_incomplete + subtasks_complete
    
    return render_template(
        'dashboard.html', 
        tasks=sorted_tasks,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        in_progress_tasks=in_progress_tasks,
        percentage=percentage,
        gregorian_date=gregorian_date,
        hijri_date=hijri_date,
        PRIORITIES=PRIORITIES,
        TIME_BLOCKS=TIME_BLOCKS,
        categories=categories,
        current_category=category_id,
        dark_mode=current_user.dark_mode
    )

def sort_tasks(tasks):
    priority_order = {'high': 1, 'medium': 2, 'low': 3}
    time_block_order = {'morning': 1, 'afternoon': 2, 'evening': 3, 'any': 4}
    
    def task_sort_key(task):
        # First by completion status (incomplete first)
        completion_key = 1 if task.is_completed else 0
        # Then by custom order index if set (lower index first)
        order_key = task.order_index if task.order_index is not None else 999
        # Then by time block
        block_key = time_block_order.get(task.time_block, 99)
        # Then by priority
        priority_key = priority_order.get(task.priority, 99)
        # Finally alphabetically
        name_key = task.description.lower()
        
        return (completion_key, order_key, block_key, priority_key, name_key)
    
    return sorted(tasks, key=task_sort_key)

@app.route('/toggle_dark_mode', methods=['POST'])
@login_required
def toggle_dark_mode():
    current_user.dark_mode = not current_user.dark_mode
    db.session.commit()
    return jsonify({'success': True, 'dark_mode': current_user.dark_mode})

@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    description = request.form.get('description')
    estimated_time = request.form.get('estimated_time')
    priority = request.form.get('priority')
    time_block = request.form.get('time_block')
    category_id = request.form.get('category_id')
    order_index = request.form.get('order_index', 0)
    
    if not description or not estimated_time or int(estimated_time) <= 0:
        flash('Please enter a valid task description and estimated time.')
        return redirect(url_for('dashboard'))
    
    # Validate category belongs to user
    if category_id and category_id != 'none':
        category = Category.query.filter_by(id=category_id, user_id=current_user.id).first()
        if not category:
            category_id = None
    else:
        category_id = None
    
    # Get the highest order_index for the user's tasks
    highest_order = db.session.query(db.func.max(Task.order_index)).filter_by(user_id=current_user.id).scalar() or 0
    
    new_task = Task(
        description=description,
        estimated_time=int(estimated_time),
        priority=priority,
        time_block=time_block,
        category_id=category_id,
        user_id=current_user.id,
        order_index=highest_order + 1  # Set new task to be at the end of the list
    )
    
    db.session.add(new_task)
    db.session.commit()
    
    return redirect(url_for('dashboard'))

@app.route('/toggle_task/<int:task_id>', methods=['POST'])
@login_required
def toggle_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    task.is_completed = not task.is_completed
    
    # If marking task as complete, also mark all subtasks as complete
    if task.is_completed and task.has_subtasks:
        for subtask in task.subtasks:
            subtask.is_completed = True
    
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/add_subtask/<int:task_id>', methods=['POST'])
@login_required
def add_subtask(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    description = request.form.get('subtask_description')
    
    if not description:
        flash('Please enter a valid subtask description.')
        return redirect(url_for('dashboard'))
    
    # Get the highest order_index for the task's subtasks
    highest_order = db.session.query(db.func.max(Subtask.order_index)).filter_by(task_id=task_id).scalar() or 0
    
    new_subtask = Subtask(
        description=description,
        task_id=task_id,
        order_index=highest_order + 1
    )
    
    db.session.add(new_subtask)
    
    # If parent task is marked complete, mark it incomplete since we added a new subtask
    if task.is_completed:
        task.is_completed = False
    
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/toggle_subtask/<int:subtask_id>', methods=['POST'])
@login_required
def toggle_subtask(subtask_id):
    subtask = Subtask.query.join(Task).filter(Subtask.id == subtask_id, Task.user_id == current_user.id).first_or_404()
    subtask.is_completed = not subtask.is_completed
    
    # Update parent task completion status based on subtasks
    parent_task = subtask.parent_task
    
    # If all subtasks are complete, mark parent as complete
    if parent_task.subtask_count == parent_task.completed_subtask_count:
        parent_task.is_completed = True
    else:
        parent_task.is_completed = False
    
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/edit_subtask/<int:subtask_id>', methods=['POST'])
@login_required
def edit_subtask(subtask_id):
    subtask = Subtask.query.join(Task).filter(Subtask.id == subtask_id, Task.user_id == current_user.id).first_or_404()
    description = request.form.get('description')
    
    if not description:
        flash('Please enter a valid subtask description.')
        return redirect(url_for('dashboard'))
    
    subtask.description = description
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/move_subtask_up/<int:subtask_id>', methods=['POST'])
@login_required
def move_subtask_up(subtask_id):
    subtask = Subtask.query.join(Task).filter(Subtask.id == subtask_id, Task.user_id == current_user.id).first_or_404()
    
    # Find the subtask with the next lower order_index (the subtask above this one)
    prev_subtask = Subtask.query.filter(
        Subtask.task_id == subtask.task_id,
        Subtask.order_index < subtask.order_index,
        Subtask.is_completed == subtask.is_completed  # Only swap with subtasks of same completion status
    ).order_by(Subtask.order_index.desc()).first()
    
    if prev_subtask:
        # Swap order_index values
        subtask.order_index, prev_subtask.order_index = prev_subtask.order_index, subtask.order_index
        db.session.commit()
    
    return redirect(url_for('dashboard'))

@app.route('/move_subtask_down/<int:subtask_id>', methods=['POST'])
@login_required
def move_subtask_down(subtask_id):
    subtask = Subtask.query.join(Task).filter(Subtask.id == subtask_id, Task.user_id == current_user.id).first_or_404()
    
    # Find the subtask with the next higher order_index (the subtask below this one)
    next_subtask = Subtask.query.filter(
        Subtask.task_id == subtask.task_id,
        Subtask.order_index > subtask.order_index,
        Subtask.is_completed == subtask.is_completed  # Only swap with subtasks of same completion status
    ).order_by(Subtask.order_index).first()
    
    if next_subtask:
        # Swap order_index values
        subtask.order_index, next_subtask.order_index = next_subtask.order_index, subtask.order_index
        db.session.commit()
    
    return redirect(url_for('dashboard'))


@app.route('/delete_subtask/<int:subtask_id>', methods=['POST'])
@login_required
def delete_subtask(subtask_id):
    subtask = Subtask.query.join(Task).filter(Subtask.id == subtask_id, Task.user_id == current_user.id).first_or_404()
    
    # Store parent task reference before deleting subtask
    parent_task = subtask.parent_task
    
    db.session.delete(subtask)
    db.session.commit()
    
    # After deleting, check if all remaining subtasks are complete to update parent task status
    if parent_task.subtask_count > 0 and parent_task.subtask_count == parent_task.completed_subtask_count:
        parent_task.is_completed = True
        db.session.commit()
    
    return redirect(url_for('dashboard'))

@app.route('/edit_task/<int:task_id>', methods=['POST'])
@login_required
def edit_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    
    description = request.form.get('description')
    estimated_time = request.form.get('estimated_time')
    priority = request.form.get('priority')
    time_block = request.form.get('time_block')
    category_id = request.form.get('category_id')
    
    if not description or not estimated_time or int(estimated_time) <= 0:
        flash('Please enter a valid task description and estimated time.')
        return redirect(url_for('dashboard'))
    
    # Validate category belongs to user
    if category_id and category_id != 'none':
        category = Category.query.filter_by(id=category_id, user_id=current_user.id).first()
        if not category:
            category_id = None
    else:
        category_id = None
    
    task.description = description
    task.estimated_time = int(estimated_time)
    task.priority = priority
    task.time_block = time_block
    task.category_id = category_id
    
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete_task/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/reset_all_tasks', methods=['POST'])
@login_required
def reset_all_tasks():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    for task in tasks:
        task.is_completed = False
        # Also reset all subtasks
        for subtask in task.subtasks:
            subtask.is_completed = False
    db.session.commit()
    return redirect(url_for('dashboard'))

# Category management routes
@app.route('/add_category', methods=['POST'])
@login_required
def add_category():
    name = request.form.get('name')
    color = request.form.get('color', 'blue')
    
    if not name:
        flash('Please enter a valid category name.')
        return redirect(url_for('dashboard'))
    
    # Check if category with same name already exists
    if Category.query.filter_by(name=name, user_id=current_user.id).first():
        flash('A category with this name already exists.')
        return redirect(url_for('dashboard'))
    
    new_category = Category(
        name=name,
        color=color,
        user_id=current_user.id
    )
    
    db.session.add(new_category)
    db.session.commit()
    
    return redirect(url_for('dashboard'))

@app.route('/edit_category/<int:category_id>', methods=['POST'])
@login_required
def edit_category(category_id):
    category = Category.query.filter_by(id=category_id, user_id=current_user.id).first_or_404()
    
    name = request.form.get('name')
    color = request.form.get('color')
    
    if not name:
        flash('Please enter a valid category name.')
        return redirect(url_for('dashboard'))
    
    # Check if another category with same name already exists
    existing = Category.query.filter_by(name=name, user_id=current_user.id).first()
    if existing and existing.id != category_id:
        flash('A category with this name already exists.')
        return redirect(url_for('dashboard'))
    
    category.name = name
    category.color = color
    
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete_category/<int:category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
    category = Category.query.filter_by(id=category_id, user_id=current_user.id).first_or_404()
    
    # Update tasks that use this category
    tasks = Task.query.filter_by(category_id=category_id).all()
    for task in tasks:
        task.category_id = None
    
    db.session.delete(category)
    db.session.commit()
    return redirect(url_for('dashboard'))

# Routes for task ordering
@app.route('/move_task_up/<int:task_id>', methods=['POST'])
@login_required
def move_task_up(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    
    # Find the task with the next lower order_index (the task above this one)
    prev_task = Task.query.filter(
        Task.user_id == current_user.id,
        Task.order_index < task.order_index,
        Task.is_completed == task.is_completed  # Only swap with tasks of same completion status
    ).order_by(Task.order_index.desc()).first()
    
    if prev_task:
        # Swap order_index values
        task.order_index, prev_task.order_index = prev_task.order_index, task.order_index
        db.session.commit()
    
    return redirect(url_for('dashboard'))

@app.route('/move_task_down/<int:task_id>', methods=['POST'])
@login_required
def move_task_down(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    
    # Find the task with the next higher order_index (the task below this one)
    next_task = Task.query.filter(
        Task.user_id == current_user.id,
        Task.order_index > task.order_index,
        Task.is_completed == task.is_completed  # Only swap with tasks of same completion status
    ).order_by(Task.order_index).first()
    
    if next_task:
        # Swap order_index values
        task.order_index, next_task.order_index = next_task.order_index, task.order_index
        db.session.commit()
    
    return redirect(url_for('dashboard'))

# Create the database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)