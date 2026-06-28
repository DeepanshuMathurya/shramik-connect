import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "rozgaar_production_secret_2026")
DATABASE = 'database.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # Extended Users Table with Rating metrics
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
        # Applications Table with IVR Verification status
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

# --- Dynamic Alert Simulations for Hackathon Judges ---
def simulate_whatsapp_alert(phone_number, text_message):
    print(f"\n[🟢 WHATSAPP SIMULATION ALERT OUTBOUND]")
    print(f"Target Line: {phone_number}")
    print(f"Payload: {text_message}\n")

def simulate_ivr_voice_call(phone_number, worker_name, gig_title):
    print(f"\n[📞 IVR AUTOMATED PHONE CALL ENGINE TRACE]")
    print(f"Dialing Worker: {worker_name} at ({phone_number})")
    print(f"Audio Output: 'You applied for {gig_title}. Press 1 to lock your attendance...'")
    print(f"Status Response Received: Keypad Digit 1 [CONFIRMED]\n")

# --- Routes ---

@app.route('/')
def index():
    # If a user is already logged in, send them to their dashboard
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    # Otherwise, show the beautiful TaskRabbit-style informational homepage
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']
        name = request.form['name']
        phone = request.form['phone']
        location = request.form['location']
        skills = request.form.get('skills', 'General Assembly')
        daily_rate = request.form.get('daily_rate', 450)
        
        try:
            with get_db() as conn:
                conn.execute('''
                    INSERT INTO users (email, password, role, name, phone, location, skills, daily_rate, rating)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 5.0)
                ''', (email, password, role, name, phone, location, skills, daily_rate))
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
        
        # HACKATHON RATING REFACTORING: Order incoming job applicants by their performance rating (highest first)
        apps = conn.execute('''
            SELECT a.id as app_id, a.status as app_status, a.ivr_confirmed, g.title, 
                   u.name as worker_name, u.phone as worker_phone, u.skills, u.rating as worker_rating, g.id as gig_id
            FROM applications a
            JOIN gigs g ON a.gig_id = g.id
            JOIN users u ON a.worker_id = u.id
            WHERE g.contractor_id = ? AND a.status = 'IVR Confirmed'
            ORDER BY u.rating DESC
        ''', (user['id'],)).fetchall()
        
        conn.close()
        return render_template('dashboard_contractor.html', user=user, gigs=gigs, applications=apps)
    
    else: # Worker Interface
        # Fetch open jobs
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
    loc = request.form['location']
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO gigs (contractor_id, title, skill_required, description, wage, workers_needed, location)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], title, skill, desc, wage, workers, loc))
        conn.commit()
    flash("New task listed on the active marketplace!", "success")
    return redirect(url_for('dashboard'))

@app.route('/apply_gig/<int:gig_id>')
def apply_gig(gig_id):
    if session.get('role') != 'Worker': return redirect(url_for('dashboard'))
    
    conn = get_db()
    gig = conn.execute('SELECT * FROM gigs WHERE id = ?', (gig_id,)).fetchone()
    worker = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    try:
        # Step 1: Submit data state as pending validation
        conn.execute('INSERT INTO applications (gig_id, worker_id, status, ivr_confirmed) VALUES (?, ?, "IVR Pending", 0)', (gig_id, session['user_id']))
        conn.commit()
        
        # Step 2: Instant Double-Confirmation IVR Phone Call Simulation 
        simulate_ivr_voice_call(worker['phone'], worker['name'], gig['title'])
        
        # Step 3: Fast-forward state to verified after successful simulation response loop
        conn.execute('UPDATE applications SET status = "IVR Confirmed", ivr_confirmed = 1 WHERE gig_id = ? AND worker_id = ?', (gig_id, session['user_id']))
        conn.commit()
        
        # Step 4: Outbound WhatsApp Tracking Confirmation Alert
        simulate_whatsapp_alert(worker['phone'], f"Namaste {worker['name']}, you have successfully applied for '{gig['title']}' after confirming via our IVR Call verification system. Your entry is now visible to the employer!")
        
        flash("Application submitted! Check system terminal to view active IVR Voice Call verification simulation pipelines.", "success")
    except sqlite3.IntegrityError:
        flash("You have already initiated an application status for this entry.", "warning")
    finally:
        conn.close()
        
    return redirect(url_for('dashboard'))

@app.route('/handle_applicant/<int:app_id>/<string:action>')
def handle_applicant(app_id, action):
    if session.get('role') != 'Contractor': return redirect(url_for('dashboard'))
    
    status = 'Confirmed' if action == 'accept' else 'Rejected'
    
    with get_db() as conn:
        conn.execute('UPDATE applications SET status = ? WHERE id = ?', (status, app_id))
        
        # Gather information to handle real-time notification alerts
        target_info = conn.execute('''
            SELECT u.phone as worker_phone, u.name as worker_name, g.title 
            FROM applications a
            JOIN users u ON a.worker_id = u.id
            JOIN gigs g ON a.gig_id = g.id
            WHERE a.id = ?
        ''', (app_id,)).fetchone()
        
        if status == 'Confirmed' and target_info:
            conn.execute('UPDATE gigs SET workers_needed = MAX(0, workers_needed - 1) WHERE id = (SELECT gig_id FROM applications WHERE id = ?)', (app_id,))
            
            # Simulate acceptance WhatsApp trigger notification context
            simulate_whatsapp_alert(
                target_info['worker_phone'], 
                f"Badhai Ho {target_info['worker_name']}! Your application for '{target_info['title']}' has been ACCEPTED. Open your ROZGAAR dashboard to view the contractor's contact details."
            )
            
        conn.commit()
        
    flash(f"Application choice processed as: {status}!", "success")
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
