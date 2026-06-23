import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "shramik_connect_secret_123")
DATABASE = 'database.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # Users Table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                location TEXT NOT NULL,
                skills TEXT,
                daily_rate REAL,
                available INTEGER DEFAULT 1
            )
        ''')
        # Gigs Table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS gigs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contractor_id INTEGER,
                title TEXT NOT NULL,
                skill_required TEXT NOT NULL,
                description TEXT,
                wage REAL NOT NULL,
                workers_needed INTEGER NOT NULL,
                location TEXT NOT NULL,
                status TEXT DEFAULT 'Open',
                FOREIGN KEY (contractor_id) REFERENCES users (id)
            )
        ''')
        # Applications Table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gig_id INTEGER,
                worker_id INTEGER,
                status TEXT DEFAULT 'Pending',
                FOREIGN KEY (gig_id) REFERENCES gigs (id),
                FOREIGN KEY (worker_id) REFERENCES users (id),
                UNIQUE(gig_id, worker_id)
            )
        ''')
        conn.commit()

# Initialize DB on startup
init_db()

# --- Authentication Routes ---

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']
        name = request.form['name']
        phone = request.form['phone']
        location = request.form['location']
        
        # Worker specific fields
        skills = request.form.get('skills', '')
        daily_rate = request.form.get('daily_rate', 0)
        
        try:
            with get_db() as conn:
                conn.execute('''
                    INSERT INTO users (email, password, role, name, phone, location, skills, daily_rate)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (email, password, role, name, phone, location, skills, daily_rate))
                conn.commit()
            flash("Registration successful! Please login.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Email already registered.", "danger")
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['name'] = user['name']
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials.", "danger")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- Dashboard & Core Logic ---

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    if user['role'] == 'Contractor':
        gigs = conn.execute('SELECT * FROM gigs WHERE contractor_id = ? ORDER BY id DESC', (user['id'],)).fetchall()
        # Fetch applications for contractor's gigs
        apps = conn.execute('''
            SELECT a.id as app_id, a.status as app_status, g.title, u.name as worker_name, u.phone as worker_phone, u.skills, g.id as gig_id
            FROM applications a
            JOIN gigs g ON a.gig_id = g.id
            JOIN users u ON a.worker_id = u.id
            WHERE g.contractor_id = ? AND a.status = 'Pending'
        ''', (user['id'],)).fetchall()
        conn.close()
        return render_template('dashboard_contractor.html', user=user, gigs=gigs, applications=apps)
    
    else: # Worker Layout
        # Toggle availability status if passed via GET
        toggle = request.args.get('toggle_avail')
        if toggle is not None:
            new_status = 0 if user['available'] == 1 else 1
            conn.execute('UPDATE users SET available = ? WHERE id = ?', (new_status, user['id']))
            conn.commit()
            return redirect(url_for('dashboard'))

        # Fetch available matching gigs
        available_gigs = conn.execute('''
            SELECT g.*, u.name as contractor_name, u.phone as contractor_phone 
            FROM gigs g 
            JOIN users u ON g.contractor_id = u.id
            WHERE g.status = 'Open' AND g.id NOT IN (
                SELECT gig_id FROM applications WHERE worker_id = ?
            ) ORDER BY g.id DESC
        ''', (user['id'],)).fetchall()
        
        # Fetch worker schedule
        my_schedule = conn.execute('''
            SELECT a.status as app_status, g.*, u.name as contractor_name, u.phone as contractor_phone
            FROM applications a
            JOIN gigs g ON a.gig_id = g.id
            JOIN users u ON g.contractor_id = u.id
            WHERE a.worker_id = ? ORDER BY g.id DESC
        ''', (user['id'],)).fetchall()
        
        conn.close()
        return render_template('dashboard_worker.html', user=user, gigs=available_gigs, schedule=my_schedule)

@app.route('/post_gig', methods=['POST'])
def post_gig():
    if session.get('role') != 'Contractor': return redirect(url_for('dashboard'))
    
    title = request.form['title']
    skill = request.form['skill_required']
    desc = request.form['description']
    wage = request.form['wage']
    workers = request.form['workers_needed']
    loc = request.form['location']
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO gigs (contractor_id, title, skill_required, description, wage, workers_needed, location)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], title, skill, desc, wage, workers, loc))
        conn.commit()
    flash("Gig posted successfully!", "success")
    return redirect(url_for('dashboard'))

@app.route('/apply_gig/<int:gig_id>')
def apply_gig(gig_id):
    if session.get('role') != 'Worker': return redirect(url_for('dashboard'))
    
    try:
        with get_db() as conn:
            conn.execute('INSERT INTO applications (gig_id, worker_id) VALUES (?, ?)', (gig_id, session['user_id']))
            conn.commit()
        flash("Applied successfully!", "success")
    except sqlite3.IntegrityError:
        flash("Already applied to this gig.", "warning")
    return redirect(url_for('dashboard'))

@app.route('/handle_applicant/<int:app_id>/<string:action>')
def handle_applicant(app_id, action):
    if session.get('role') != 'Contractor': return redirect(url_for('dashboard'))
    
    status = 'Confirmed' if action == 'accept' else 'Rejected'
    
    with get_db() as conn:
        conn.execute('UPDATE applications SET status = ? WHERE id = ?', (status, app_id))
        
        # If accepted, deduct workers needed count
        if status == 'Confirmed':
            app_details = conn.execute('SELECT gig_id FROM applications WHERE id = ?', (app_id,)).fetchone()
            if app_details:
                conn.execute('UPDATE gigs SET workers_needed = MAX(0, workers_needed - 1) WHERE id = ?', (app_details['gig_id'],))
                # Auto-close gig if filled
                conn.execute("UPDATE gigs SET status = 'Filled' WHERE id = ? AND workers_needed = 0", (app_details['gig_id'],))
        conn.commit()
        
    flash(f"Application {status}!", "success")
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    # Render sets an environment variable named PORT. This code reads it.
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)