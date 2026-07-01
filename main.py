import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "rozgaar_production_secret_2026")
DATABASE = 'database.db'

# Pre-defined Validated Delhi-NCR Transit Zone Hubs for Sandbox Location Protection
VALID_LOCATIONS = [
    "badarpur", "sarita vihar", "jasola", "okhla", "nehru place", 
    "kashmere gate", "shastri park", "seelampur", "shahdara", 
    "dilshad garden", "connaught place", "saket", "dwarka", "rohini",
    "delhi", "new delhi", "noida", "gurugram", "ghaziabad", "faridabad"
]

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # Extended Users Table
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
                daily_rate REAL DEFAULT 0,
                rating REAL DEFAULT 5.0,
                completed_jobs INTEGER DEFAULT 0,
                available INTEGER DEFAULT 1
            )
        ''')
        # Gigs Table containing specialized Job Dates and Address details
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
                exact_address TEXT,
                job_date TEXT NOT NULL,
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
                status TEXT DEFAULT 'Pending Verification',
                ivr_confirmed INTEGER DEFAULT 0,
                FOREIGN KEY (gig_id) REFERENCES gigs (id),
                FOREIGN KEY (worker_id) REFERENCES users (id),
                UNIQUE(gig_id, worker_id)
            )
        ''')
        conn.commit()

init_db()

# --- Routes ---

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']
        name = request.form['name']
        phone = request.form['phone']
        location = request.form['location'].strip().lower()
        skills = request.form.get('skills', 'General Assembly')
        daily_rate = request.form.get('daily_rate', 450)
        
        # Location Validation Barrier Check
        is_valid = any(zone in location for zone in VALID_LOCATIONS)
        if not is_valid:
            flash("Error: Please enter a valid location within Delhi-NCR area for the system sandbox deployment.", "danger")
            return redirect(url_for('register'))
        
        try:
            with get_db() as conn:
                conn.execute('''
                    INSERT INTO users (email, password, role, name, phone, location, skills, daily_rate, rating)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 5.0)
                ''', (email, password, role, request.form['location'], skills, daily_rate))
                conn.commit()
            flash("Account registered successfully! Please sign in.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("This email address is already in use.", "danger")
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
            flash("Invalid security credentials.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    if not user:
        session.clear()
        return redirect(url_for('login'))
        
    if user['role'] == 'Contractor':
        gigs = conn.execute('SELECT * FROM gigs WHERE contractor_id = ? ORDER BY id DESC', (user['id'],)).fetchall()
        apps = conn.execute('''
            SELECT a.id as app_id, a.status as app_status, a.ivr_confirmed, g.title, g.job_date,
                   u.name as worker_name, u.phone as worker_phone, u.skills, u.rating as worker_rating, g.id as gig_id
            FROM applications a
            JOIN gigs g ON a.gig_id = g.id
            JOIN users u ON a.worker_id = u.id
            WHERE g.contractor_id = ? AND a.status = 'IVR Confirmed'
            ORDER BY u.rating DESC
        ''', (user['id'],)).fetchall()
        conn.close()
        return render_template('dashboard_contractor.html', user=user, gigs=gigs, applications=apps)
    
    else: # Worker Dashboard
        available_gigs = conn.execute('''
            SELECT g.*, u.name as contractor_name, u.phone as contractor_phone 
            FROM gigs g 
            JOIN users u ON g.contractor_id = u.id
            WHERE g.status = 'Open' AND g.id NOT IN (
                SELECT gig_id FROM applications WHERE worker_id = ?
            ) ORDER BY g.id DESC
        ''', (user['id'],)).fetchall()
        
        my_schedule = conn.execute('''
            SELECT a.status as app_status, a.ivr_confirmed, g.*, u.name as contractor_name, u.phone as contractor_phone
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
    loc = request.form['location'].strip().lower()
    exact_address = request.form['exact_address']
    job_date = request.form['job_date'] # Retains selected calendar execution date
    
    # Location Barrier Filter Validation
    is_valid = any(zone in loc for zone in VALID_LOCATIONS)
    if not is_valid:
        flash("Error: Job location must be situated within valid regional tracking bounds.", "danger")
        return redirect(url_for('dashboard'))
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO gigs (contractor_id, title, skill_required, description, wage, workers_needed, location, exact_address, job_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], title, skill, desc, wage, workers, request.form['location'], exact_address, job_date))
        conn.commit()
    flash("New task listed on the active marketplace!", "success")
    return redirect(url_for('dashboard'))

@app.route('/apply_gig/<int:gig_id>')
def apply_gig(gig_id):
    if session.get('role') != 'Worker': return redirect(url_for('dashboard'))
    
    conn = get_db()
    target_gig = conn.execute('SELECT * FROM gigs WHERE id = ?', (gig_id,)).fetchone()
    
    # --- DOUBLE BOOKING BLOCKING ENGINE MECHANICAL LAYER ---
    # Look up if this worker already has a slot locked or pending on this exact calendar target date
    conflict = conn.execute('''
        SELECT g.title, g.job_date 
        FROM applications a
        JOIN gigs g ON a.gig_id = g.id
        WHERE a.worker_id = ? AND g.job_date = ? AND a.status != 'Rejected'
    ''', (session['user_id'], target_gig['job_date'])).fetchone()
    
    if conflict:
        conn.close()
        flash(f"Aap is din pe pehle se dusre kaam par apply kar chuke hain! Ek hi date par do kaam nahi chun sakte.", "danger")
        return redirect(url_for('dashboard'))
    
    try:
        conn.execute('INSERT INTO applications (gig_id, worker_id, status, ivr_confirmed) VALUES (?, ?, "IVR Confirmed", 1)', (gig_id, session['user_id']))
        conn.commit()
        flash("Application confirmed successfully!", "success")
    except sqlite3.IntegrityError:
        flash("You have already applied for this job.", "warning")
    finally:
        conn.close()
        
    return redirect(url_for('dashboard'))

@app.route('/handle_applicant/<int:app_id>/<string:action>')
def handle_applicant(app_id, action):
    if session.get('role') != 'Contractor': return redirect(url_for('dashboard'))
    status = 'Confirmed' if action == 'accept' else 'Rejected'
    
    with get_db() as conn:
        conn.execute('UPDATE applications SET status = ? WHERE id = ?', (status, app_id))
        if status == 'Confirmed':
            conn.execute('UPDATE gigs SET workers_needed = MAX(0, workers_needed - 1) WHERE id = (SELECT gig_id FROM applications WHERE id = ?)', (app_id,))
        conn.commit()
        
    flash(f"Application choice processed successfully!", "success")
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
