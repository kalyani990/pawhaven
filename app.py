try:
    import eventlet
    eventlet.monkey_patch()
    ASYNC_MODE = 'eventlet'
except ImportError:
    ASYNC_MODE = 'threading'
    print("Warning: eventlet not found, using threading mode")

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

# Try to import JWT for API tokens
try:
    from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token
    JWT_AVAILABLE = True
except ImportError:
    print("Warning: flask-jwt-extended not found, installing...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask-jwt-extended"])
    from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token
    JWT_AVAILABLE = True

# Try to import SocketIO, disable chat if not available
try:
    from flask_socketio import SocketIO, join_room, emit
    SOCKETIO_AVAILABLE = True
except ImportError:
    print("Warning: flask-socketio not found, chat functionality disabled")
    SOCKETIO_AVAILABLE = False
    SocketIO = None
import mysql.connector
from mysql.connector import Error
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from threading import Timer
import time
from uuid import uuid4
from datetime import datetime
import webbrowser
from flask import jsonify 
import base64

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000/")

app = Flask(__name__)

# JWT Configuration
app.config["JWT_SECRET_KEY"] = "pawhaven-super-secret-jwt-key-2025"
if JWT_AVAILABLE:
    jwt = JWTManager(app)

# Initialize SocketIO only if available
if SOCKETIO_AVAILABLE:
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode=ASYNC_MODE, logger=True, engineio_logger=True)
else:
    socketio = None
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
success_pets = {
    1: {"id": 1, "name": "Lucky", "type": "Dog", "breed": "Indie",
        "age": "1.2 Years", "gender": "Male", "color": "Golden Brown",
        "weight": "16 kg", "size": "Medium",
        "health": "Recovering (Minor Injury)",
        "image": "success_pic1.jpg",
        "desc": "Lucky recovered well and lives peacefully near the lake."
       },
    2: {
        "id": 2, "name": "Bruno", "type": "Dog", "breed": "Mixed Breed",
        "age": "2 Years", "gender": "Male", "color": "Brown + Golden",
        "weight": "18 kg", "size": "Medium", "health": "Vaccinated",
        "image": "success_pic7.jpg",
        "desc": "A playful dog who now enjoys a happy life."
       },
    3: {
        "id": 3, "name": "Misty", "type": "Cat", "breed": "Long Hair Tabby",
        "age": "1 Year", "gender": "Female", "color": "Brown + Black",
        "weight": "3.8 kg", "size": "Medium", "health": "Healthy",
        "image": "success_pic3.jpg",
        "desc": "Misty found the perfect family to love and care for her."
       },
    4: {
        "id": 4, "name": "Ginger", "type": "Cat", "breed": "Orange Tabby",
        "age": "1.5 Years", "gender": "Male", "color": "Orange",
        "weight": "4.3 kg", "size": "Medium", "health": "Vaccinated",
        "image": "success_pic4.jpg",
        "desc": "A shy kitty who found warmth and love in a new home."
    },
    5: {
        "id": 5, "name": "Snowy", "type": "Sheep", "breed": "Merino Sheep",
        "age": "2 Years", "gender": "Female", "color": "White",
        "weight": "28 kg", "size": "Medium", "health": "Healthy",
        "image": "success_pic5.jpg",
        "desc": "Snowy was rescued from harsh conditions and now lives happily."
    },
    6: {
        "id": 6, "name": "Bunny", "type": "Rabbit", "breed": "Dutch Rabbit",
        "age": "8 Months", "gender": "Female", "color": "Light Brown",
        "weight": "1.2 kg", "size": "Small", "health": "Vaccinated, Healthy",
        "image": "success_pic6.jpg",
        "desc": "A sweet calm bunny who finally found a safe and caring home."
    },
}

app.secret_key = 'your_secret_key'
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db_config ={
    'host': 'localhost',
    'user': 'root',
    'password': 'Jesus@143',     # Set your MySQL password here
    'database': 'petportal'
}
db = mysql.connector.connect(**db_config)

cursor = db.cursor(dictionary=True)
def get_or_create_chat_room(conn, request_type, request_id, pet_id=None):
    """
    request_type: 'lost' / 'found' / 'adoption'
    request_id : int (request table id)
    pet_id     : optional pet id (mainly adoption ki)
    """
    # room id format: lost_3, found_5, adoption_7
    room_id = f"{request_type}_{request_id}"

    cur = conn.cursor(dictionary=True)

    # already room unda chudu
    cur.execute("SELECT id FROM chat_rooms WHERE room_id = %s", (room_id,))
    row = cur.fetchone()

    if not row:
        # lekapote create chey
        cur.execute(
            """
            INSERT INTO chat_rooms (room_id, pet_id, request_type)
            VALUES (%s, %s, %s)
            """,
            (room_id, pet_id, request_type),
        )
        conn.commit()

    cur.close()
    return room_id


# Quick fix: Install missing packages
# Run these commands in your terminal:
# pip install flask-socketio==5.3.6
# pip install eventlet==0.36.1

# For now, the app will run without chat functionality
print("="*50)
print("🚀 FLASK APP STARTING")
print("📦 SocketIO Available:", SOCKETIO_AVAILABLE)
print("💬 Chat Functionality:", "Enabled" if SOCKETIO_AVAILABLE else "Disabled")
print("🌐 Access your app at: http://127.0.0.1:5000")
print("="*50)

def get_db_connection():
    try:
        connection = mysql.connector.connect(**db_config)
        return connection
    except Error as e:
        print("Error connecting to database:", e)
        return None

def update_report_status(conn, report_type, new_status,
                         pet_id=None, message_prefix=None, pet_name=None):
    """
    Common helper to update reports.status.

    - Adoption: use pet_id.
    - Lost/Found: use message pattern 'Lost pet: <name>' / 'Found pet: <name>'.
    """
    cur = conn.cursor()

    if pet_id is not None:
        # Adoption case
        cur.execute("""
            UPDATE reports
            SET status = %s
            WHERE report_type = %s
              AND pet_id = %s
              AND status = 'Pending'
        """, (new_status, report_type, pet_id))

    elif message_prefix and pet_name:
        # Lost / Found case using message text
        cur.execute("""
            UPDATE reports
            SET status = %s
            WHERE report_type = %s
              AND message = %s
              AND status = 'Pending'
        """, (new_status, report_type, f"{message_prefix} {pet_name}"))

    cur.close()


# USER LOADER (IMPORTANT)
@login_manager.user_loader
def load_user(user_id):
    from user_dashboard import Users  # adjust if needed
    return Users.query.get(int(user_id))
def get_success_stories():
    conn = get_db_connection()
    if not conn:
        return []

    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            p.name       AS pet_name,
            p.age        AS age,
            p.image_url  AS image_url,
            r.message    AS short_summary,
            r.id         AS id
        FROM reports r
        LEFT JOIN pets p ON r.pet_id = p.id
        WHERE r.report_type = 'Adoption'
        AND r.status = 'Resolved'
        ORDER BY r.created_at DESC
        LIMIT 3
    """)

    stories = cursor.fetchall()

    cursor.close()
    conn.close()

    return stories


@app.route("/")
def index():
    # Landing page
    pets_list = list(success_pets.values())
    return render_template("landing.html",success_pets=pets_list)

@app.route("/success/<int:pet_id>")
def success_details(pet_id):
    pet = success_pets.get(pet_id)
    if not pet:
        abort(404)
    return render_template("success_details.html", pet=pet)

@app.route("/success-dashboard")
def success_dashboard():
    return render_template("dashboard_success.html", success_pets=success_pets)

# ---------------- Registration ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fname = request.form['first_name'].strip()
        lname = request.form['last_name'].strip()
        email = request.form['email'].strip()
        city = request.form['city'].strip()
        phone = request.form['phone'].strip()
        pincode = request.form.get('pincode', '').strip()
        dob = request.form.get('dob')
        gender = request.form.get('gender')
        password = request.form['password']

        if not (fname and lname and email and password):
            flash('Please fill in all required fields.', 'danger')
            return render_template('register.html')

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'danger')
            return render_template('register.html')

        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id FROM users WHERE email = %s', (email,))
        if cursor.fetchone():
            flash('Email already registered. Login instead.', 'warning')
            cursor.close()
            conn.close()
            return redirect(url_for('login'))

        cursor.execute("""
            INSERT INTO users
                (first_name, last_name, email, phone, city, pincode,
                 address, dob, gender, password, role)
            VALUES (%s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s)
        """, (
            fname, lname, email, phone, city, pincode,
            None, dob, gender, hashed_password, 'user'
        ))

        conn.commit()
        cursor.close()
        conn.close()

        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


# ========== API AUTHENTICATION ROUTES ==========

@app.route('/api/test', methods=['GET'])
def api_test():
    """Simple test endpoint to verify API is working"""
    return jsonify({
        "success": True,
        "message": "PawHaven API is working!",
        "timestamp": datetime.now().isoformat(),
        "endpoints": [
            "GET /api/test",
            "GET /api/docs", 
            "POST /api/auth/login",
            "POST /api/auth/register",
            "GET /api/pets",
            "GET /api/stats"
        ]
    }), 200

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """JSON-based login for mobile apps and API clients"""
    try:
        # Debug: Log the request
        print(f"🔍 API Login Request - Content-Type: {request.content_type}")
        print(f"🔍 Raw data: {request.get_data()}")
        
        data = request.get_json() or {}
        print(f"🔍 Parsed JSON: {data}")
        
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        print(f"🔍 Email: {email}, Password: {'*' * len(password) if password else 'None'}")
        
        if not email or not password:
            return jsonify({
                "success": False,
                "detail": "Email and password required"
            }), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({
                "success": False,
                "detail": "Database connection error"
            }), 500
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM users WHERE email=%s', (email,))
        user = cursor.fetchone()
        
        print(f"🔍 User found: {user is not None}")
        
        cursor.close()
        conn.close()
        
        if not user:
            return jsonify({
                "success": False,
                "detail": "Invalid credentials"
            }), 401
        
        db_pass = user['password']
        try:
            valid = check_password_hash(db_pass, password)
        except Exception as e:
            print(f"🔍 Password check exception: {e}")
            valid = (db_pass == password)
        
        print(f"🔍 Password valid: {valid}")
        
        if not valid:
            return jsonify({
                "success": False,
                "detail": "Invalid credentials"
            }), 401
        
        # Create JWT tokens
        if JWT_AVAILABLE:
            access_token = create_access_token(identity=user["id"])
            refresh_token = create_refresh_token(identity=user["id"])
        else:
            access_token = f"mock_access_token_{user['id']}"
            refresh_token = f"mock_refresh_token_{user['id']}"
        
        # Successful login response with JWT tokens
        return jsonify({
            "access": access_token,
            "refresh": refresh_token,
            "username": user["first_name"],
            "email": user["email"],
            "is_admin": (user["role"] == "admin")
        }), 200
        
    except Exception as e:
        print(f"🔍 API Login Error: {str(e)}")
        return jsonify({
            "success": False,
            "detail": f"Server error: {str(e)}"
        }), 500

@app.route('/api/auth/admin-login', methods=['POST'])
def api_admin_login():
    """JSON-based admin login"""
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        print(f"🔍 Admin Login Request: {email}")
        
        if not email or not password:
            return jsonify({"detail": "Email and password required"}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"detail": "Database error"}), 500
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email=%s AND role='admin'", (email,))
        admin = cursor.fetchone()
        cursor.close()
        conn.close()
        
        print(f"🔍 Admin found: {admin is not None}")
        
        if not admin:
            return jsonify({"detail": "Invalid admin credentials"}), 401
        
        db_pass = admin['password']
        try:
            valid = check_password_hash(db_pass, password)
        except Exception:
            valid = (db_pass == password)
        
        print(f"🔍 Admin password valid: {valid}")
        
        if not valid:
            return jsonify({"detail": "Invalid admin credentials"}), 401
        
        # Create JWT tokens for admin
        if JWT_AVAILABLE:
            access_token = create_access_token(identity=admin["id"])
            refresh_token = create_refresh_token(identity=admin["id"])
        else:
            access_token = f"mock_admin_access_token_{admin['id']}"
            refresh_token = f"mock_admin_refresh_token_{admin['id']}"
        
        # Successful admin login response with JWT tokens
        return jsonify({
            "access": access_token,
            "refresh": refresh_token,
            "username": admin["first_name"],
            "email": admin["email"],
            "is_admin": True
        }), 200
        
    except Exception as e:
        print(f"🔍 Admin Login Error: {str(e)}")
        return jsonify({"detail": f"Server error: {str(e)}"}), 500

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    """JSON-based user registration"""
    try:
        # Debug: Log the request
        print(f"🔍 API Register Request - Content-Type: {request.content_type}")
        print(f"🔍 Raw data: {request.get_data()}")
        
        data = request.get_json() or {}
        print(f"🔍 Parsed JSON: {data}")
        
        # Validate required fields
        required_fields = ['first_name', 'last_name', 'email', 'password']
        for field in required_fields:
            if not data.get(field, '').strip():
                return jsonify({"detail": f"Missing required field: {field}"}), 400
        
        fname = data['first_name'].strip()
        lname = data['last_name'].strip()
        email = data['email'].strip().lower()
        password = data['password']
        phone = data.get('phone', '').strip()
        city = data.get('city', '').strip()
        
        print(f"🔍 Registration Details: {fname} {lname}, {email}")
        
        if len(password) < 6:
            print(f"❌ Password too short: {len(password)} characters")
            return jsonify({"detail": "Password must be at least 6 characters"}), 400
        
        hashed_password = generate_password_hash(password)
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"detail": "Database error"}), 500
        
        cursor = conn.cursor(dictionary=True)
        
        # Check if email already exists
        cursor.execute('SELECT id FROM users WHERE email = %s', (email,))
        if cursor.fetchone():
            print(f"❌ Email already exists: {email}")
            cursor.close()
            conn.close()
            return jsonify({"detail": "Email already registered"}), 409
        
        # Insert new user
        cursor.execute("""
            INSERT INTO users
                (first_name, last_name, email, phone, city, password, role, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'user', NOW())
        """, (fname, lname, email, phone, city, hashed_password))
        
        user_id = cursor.lastrowid
        conn.commit()
        print(f"✅ User registered successfully: ID={user_id}, Email={email}")
        cursor.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "message": "Registration successful",
            "user": {
                "id": user_id,
                "email": email,
                "name": f"{fname} {lname}",
                "first_name": fname,
                "last_name": lname,
                "role": "user"
            }
        }), 201
        
    except Exception as e:
        return jsonify({"detail": f"Server error: {str(e)}"}), 500

@app.route('/api/auth/verify', methods=['POST'])
def api_verify_user():
    """Verify user credentials (for session validation)"""
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        email = data.get('email')
        
        if not user_id and not email:
            return jsonify({"detail": "User ID or email required"}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"detail": "Database error"}), 500
        
        cursor = conn.cursor(dictionary=True)
        
        if user_id:
            cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
        else:
            cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user:
            return jsonify({"detail": "User not found"}), 404
        
        return jsonify({
            "success": True,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "name": user["first_name"] + " " + user["last_name"],
                "first_name": user["first_name"],
                "last_name": user["last_name"],
                "role": user["role"],
                "phone": user.get("phone"),
                "city": user.get("city")
            }
        }), 200
        
    except Exception as e:
        return jsonify({"detail": f"Server error: {str(e)}"}), 500


# ---------------- Login (USER) ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']

        if not email or not password:
            flash('Please enter email and password.', 'danger')
            return render_template('login.html')

        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'danger')
            return render_template('login.html')

        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM users WHERE email=%s', (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            db_pass = user['password']
            valid = False
            try:
                valid = check_password_hash(db_pass, password)
            except Exception:
                valid = (db_pass == password)

            if valid:
                # ✅ set both keys
                session['user_id'] = user['id']
                session['userid'] = user['id']
                session['role'] = user['role']
                session['name'] = user['first_name'] + ' ' + user['last_name']
                session['email'] = user['email']

                if user['role'] == 'admin':
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('user_dashboard'))

        flash('Invalid email or password.', 'danger')
    return render_template('login.html')


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if new_password != confirm_password:
            flash("Passwords do not match. Please try again.", "danger")
            return render_template('forgot_password.html')
        # Add password update logic here
        flash("Password reset successful! Please log in.", "success")
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

# ---------------- Logout ----------------
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# ---------------- User Dashboard ----------------

@app.route('/home')
def user_dashboard():
    if 'user_id' not in session or session.get('role') not in ['user', 'admin']:
        flash('Please login to access this page.', 'warning')
        return redirect(url_for('login'))

    full_name = session.get('name', '')
    username = full_name.split(' ')[0] if full_name else ''
    email = session.get('email')

    conn = get_db_connection()
    if not conn:
        flash('Database connection error.', 'danger')
        return render_template(
            'user_dashboard.html',
            name=full_name,
            role=session.get('role'),
            username=username,
            email=email
        )

    cursor = conn.cursor(dictionary=True)
    pets = []

    # ✅ LOST – lost_requests (YOUR EXACT SCHEMA)
    cursor.execute("""
        SELECT id,
               pet_name,
               pet_type,
               breed,
               color,
               location AS place,
               pet_image AS image,
               'lost' AS kind,
               status
        FROM lost_requests
        WHERE status IN ('pending', 'found')
        ORDER BY created_at DESC 
        LIMIT 12
    """)
    pets += cursor.fetchall()

    # ✅ FOUND – found_requests (YOUR EXACT SCHEMA)
    cursor.execute("""
        SELECT id,
               pet_name,
               pet_type,
               breed,
               color,
               location AS place,
               pet_image AS image,
               'found' AS kind,
               status
        FROM found_requests
        WHERE status IN ('pending', 'matched')
        ORDER BY created_at DESC 
        LIMIT 12
    """)
    pets += cursor.fetchall()

    # ✅ ADOPT – pets (FIXED: NO location column → empty string)
    cursor.execute("""
        SELECT id,
               name AS pet_name,
               species AS pet_type,
               breed,
               color,
               '' AS place,        -- ✅ pets table lo location ledu
               image_url AS image,
               'adopt' AS kind,
               status      AS status
        FROM pets
        
        ORDER BY created_at DESC 
        LIMIT 12
    """)
    pets += cursor.fetchall()

    # Pet Care Hub stats (CORRECTED)
    # Pet Care Hub stats (SAFE - NO MISSING TABLES)
    cursor.execute("SELECT COUNT(*) AS count FROM pets WHERE status='active'")
    vaccination_centers = cursor.fetchone()['count'] or 0  # ✅ Uses existing pets table

    cursor.execute("SELECT COUNT(*) AS count FROM pets WHERE status='active'")
    shelter_pets = cursor.fetchone()['count'] or 0  # ✅ Uses existing pets table

    cursor.execute("SELECT COUNT(*) AS count FROM users WHERE role='user'")
    community_members = cursor.fetchone()['count'] or 0  # ✅ Uses existing users table

    unread = get_unread_count(session["user_id"])  # ✅ Fixed: user_id

    cursor.close()
    conn.close()

    return render_template(
        'user_dashboard.html',
        pets=pets,
        unread_count=unread,
        name=full_name,
        role=session.get('role'),
        username=username,
        email=email,
        vaccination_centers=vaccination_centers,
        shelter_pets=shelter_pets,
        community_members=community_members
    )

@app.route('/community')
def community():
    # user login ayi unte direct community
    if 'user_id' in session:
        return render_template('community.html')

    # login lekunte
    flash('Please login or sign up to join the community.', 'info')
    return redirect(url_for('login'))

# ===== ADD AFTER existing routes (~line 800-900) =====
@app.route('/submit_pet_request', methods=['POST'])
def submit_pet_request():
    if 'userid' not in session: 
        return redirect(url_for('login'))
    
    req_id = request.form.get('req_id')
    query = request.form.get('query')
    req_type = request.form.get('type', 'lost')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 🔥 YOUR UNION - PERFECT (keep as is)
    cur.execute("""
        SELECT pet_name, pet_type FROM lost_requests WHERE id=%s
        UNION ALL 
        SELECT pet_name, pet_type FROM found_requests WHERE id=%s
    """, (req_id, req_id))
    
    results = cur.fetchall()
    pet = results[0] if results else None
    
    if pet:
        room_id = f"knowpet_{req_id}_{session['userid']}"
        
        # 🔥 FIX 1: Add detail_url parameter
        detail_url = f"/admin_request_detail/{req_id}"
        send_notification(2, f'I Know This Pet #{req_id}', query, room_id)
    
    cur.close()
    conn.commit()
    conn.close()
    
    flash('request_success', 'knowpet')
    
    if req_type == 'lost':
        return redirect(url_for('lost_request_details', requestid=req_id))
    else:
        return redirect(url_for('found_request_details', request_id=req_id))

def get_user_by_id(user_id):
    conn = get_db_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash('Please login first!')
        return redirect('/login')

    user = get_user_by_id(session['user_id'])
    if not user:
        flash('User not found!')
        return redirect('/login')

    return render_template('profile.html', user=user)

@app.route('/edit_profile', methods=['GET'])
def edit_profile():
    if 'user_id' not in session:
        flash('Please login first!')
        return redirect('/login')

    user = get_user_by_id(session['user_id'])
    if not user:
        flash('User not found!')
        return redirect('/login')

    return render_template('edit_profile.html', user=user)

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect('/login')

    data = request.form

    conn = get_db_connection()
    if not conn:
        flash('Database error!', 'danger')
        return redirect('/profile')

    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET 
            first_name = %s,
            last_name  = %s,
            email      = %s,
            phone      = %s,
            city       = %s,
            pincode    = %s,
            address    = %s,
            dob        = %s,
            gender     = %s
        WHERE id = %s
    """, (
        data.get('first_name'),
        data.get('last_name'),
        data.get('email'),
        data.get('phone'),
        data.get('city'),
        data.get('pincode'),
        data.get('address'),
        data.get('dob'),
        data.get('gender'),
        session['user_id']
    ))

    conn.commit()
    cursor.close()
    conn.close()

    flash('Profile updated successfully!')
    return redirect('/profile')

def get_pending_count():
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM adoptions WHERE status='Pending'")
    n = cur.fetchone()[0]
    cur.close(); conn.close()
    return n

@app.route('/admin/users')
def admin_users():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    if not conn:
        flash('Database error.', 'danger')
        return redirect(url_for('admin_dashboard'))

    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, first_name, last_name, email, city, role, created_at
        FROM users
        ORDER BY created_at DESC
    """)
    users = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('admin_users.html', users=users)

# ---------------- Admin Dashboard ----------------
@app.route('/admin_dashboard')
def admin_dashboard():
    # Access control
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('user_dashboard'))

    admin_id = session['user_id']   # <- admin actual id from session
    conn = get_db_connection()

    if not conn:
        flash('Database connection error.', 'danger')
        return render_template(
            'admin_dashboard.html',
            admin_id=admin_id,
            pending_count=0, total_requests=0, pending=0, adoptions=0,
            total_users=0, active_reports=0, active_found=0, active_lost=0,
            reports=[], total_reports=0, resolved_reports=0,
            unread_count=0, requests=[]
        )

    cur = conn.cursor(dictionary=True)

    # ===== STATS QUERIES =====
    cur.execute("SELECT COUNT(*) AS c FROM lost_requests WHERE LOWER(status) = 'pending'")
    lost_pending = cur.fetchone()['c']

    cur.execute("SELECT COUNT(*) AS c FROM found_requests WHERE LOWER(status) = 'pending'")
    found_pending = cur.fetchone()['c']

    cur.execute("SELECT COUNT(*) AS c FROM adoption_requests WHERE LOWER(status) = 'pending'")
    adoptions_pending = cur.fetchone()['c']

    pending_count = lost_pending + found_pending + adoptions_pending
    total_requests = pending_count

    # Total users
    cur.execute("SELECT COUNT(*) AS c FROM users")
    total_users = cur.fetchone()['c']

    # Active counts
    cur.execute("SELECT COUNT(*) AS c FROM lost_requests WHERE LOWER(status) IN ('pending','found')")
    active_lost = cur.fetchone()['c']

    cur.execute("SELECT COUNT(*) AS c FROM found_requests WHERE LOWER(status) IN ('pending','matched')")
    active_found = cur.fetchone()['c']

    cur.execute("SELECT COUNT(*) AS c FROM adoption_requests WHERE LOWER(status) IN ('pending','approved')")
    active_adopt = cur.fetchone()['c']

    active_reports = active_lost + active_found + active_adopt
    total_reports = lost_pending + found_pending
    reports_pending = lost_pending + found_pending
    resolved_reports = 0

    # Pending requests list (unchanged)
    cur.execute("""
        SELECT 'lost' as request_type, l.id, l.pet_name as petname, l.status, l.created_at,
               u.email, u.first_name as firstname, 0 as unread_count
        FROM lost_requests l
        LEFT JOIN users u ON l.user_id = u.id
        WHERE LOWER(l.status) = 'pending'

        UNION ALL

        SELECT 'found' as request_type, f.id, f.pet_name as petname, f.status, f.created_at,
               u.email, u.first_name as firstname, 0 as unread_count
        FROM found_requests f
        LEFT JOIN users u ON f.user_id = u.id
        WHERE LOWER(f.status) = 'pending'

        UNION ALL

        SELECT 'adoption' as request_type, ar.id, 'Adoption Request' as petname,
               ar.status, ar.created_at,
               u.email, u.first_name as firstname, 0 as unread_count
        FROM adoption_requests ar
        LEFT JOIN users u ON ar.user_id = u.id
        WHERE LOWER(ar.status) = 'pending'

        ORDER BY created_at DESC
    """)
    requests = cur.fetchall()

    # Unread notifications for THIS admin
    unread_count = get_unread_count(admin_id)

    cur.close()
    conn.close()

    return render_template(
        'admin_dashboard.html',
        admin_id=admin_id,
        pending_count=pending_count,
        total_requests=total_requests,
        pending=reports_pending,
        adoptions=adoptions_pending,
        total_users=total_users,
        unread_count=unread_count,
        active_reports=active_reports,
        active_found=active_found,
        active_lost=active_lost,
        active_adopt=active_adopt,
        reports=[],
        total_reports=total_reports,
        resolved_reports=resolved_reports,
        requests=requests
    )


# ---------------- Admin Register ----------------
@app.route('/admin_register', methods=['GET', 'POST'])
def admin_register():
    if request.method == 'POST':
        full_name = request.form['name'].strip()
        parts = full_name.split(' ', 1)
        fname = parts[0]
        lname = parts[1] if len(parts) > 1 else ''

        email = request.form['email'].strip().lower()
        phone = request.form['phone'].strip()
        gender = request.form['gender']
        dob = request.form['dob']
        city = request.form['city'].strip()
        pincode = request.form.get('pincode', '').strip()
        address = request.form['address'].strip()
        admin_code = request.form['admin_code'].strip()
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash("Password and Confirm Password do not match.", "danger")
            return render_template("admin_register.html")

        if admin_code != "Admin@123":
            flash("Invalid Admin Authorization Code!", "danger")
            return render_template("admin_register.html")

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return render_template("admin_register.html")

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            flash("Email already registered! Please login.", "warning")
            cursor.close()
            conn.close()
            return redirect(url_for('login'))

        try:
            cursor.execute("""
                INSERT INTO users
                    (first_name, last_name, email, phone, city, pincode,
                     address, dob, gender, password, role, created_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s,
                     %s, %s, %s, %s, 'admin', NOW())
            """, (
                fname, lname, email, phone, city, pincode,
                address, dob, gender, hashed_password
            ))

            conn.commit()
            flash("Admin registered successfully! Please login.", "success")
            cursor.close()
            conn.close()
            return redirect(url_for('login'))

        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            flash("Registration failed. Try again.", "danger")
            return render_template("admin_register.html")

    return render_template("admin_register.html")

# ---------------- Admin Login ----------------
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']

        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'danger')
            return render_template('admin_login.html')

        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE email=%s AND role='admin'",
            (email,)
        )
        admin = cursor.fetchone()
        cursor.close()
        conn.close()

        if admin:
            db_pass = admin['password']
            try:
                valid = check_password_hash(db_pass, password)
            except Exception:
                valid = (db_pass == password)

            if valid:
                full_name = f"{admin['first_name']} {admin['last_name']}".strip()

                # CLEAR + SET ALL ADMIN SESSION KEYS
                session.clear()
                session['role'] = 'admin'
                session['user_id'] = admin['id']        # old key, if used elsewhere
                session['name'] = full_name
                session['email'] = admin['email']

                # NEW: explicit admin keys for chat
                session['admin_id'] = admin['id']
                session['admin_name'] = full_name

                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid admin email or password.', 'danger')
        else:
            flash('Invalid admin email or password.', 'danger')

    return render_template('admin_login.html')


# ===== ADMIN LOST REQUESTS (Pet ID Enhanced) =====
@app.route('/admin/lost_requests')
def admin_lost_requests():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    # ✅ YOUR TABLE: lost_requests
    cur.execute("""
        SELECT *
        FROM lost_requests
        WHERE status = 'pending'                  -- ⭐ only not-found
        ORDER BY id DESC
    """)
    lost_list = cur.fetchall()
    cur.close(); conn.close()
    return render_template('admin_lost_requests.html', lost_list=lost_list)
@app.route('/admin/lost/<int:lost_id>/approve', methods=['POST'])
def admin_approve_lost(lost_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Get lost request details
    cur.execute("SELECT * FROM lost_requests WHERE id=%s", (lost_id,))
    lost = cur.fetchone()
    
    if not lost:
        flash('Lost request not found!', 'error')
        cur.close(); conn.close()
        return redirect(url_for('admin_dashboard'))
    
    # Update status + Chat + Notification (SAME TRANSACTION)
    cur.execute("UPDATE lost_requests SET status='found' WHERE id=%s", (lost_id,))
    roomid = get_or_create_chat_room(conn, 'lost', lost_id)
    send_notification(lost['user_id'], "Lost Request APPROVED!", 
                     f"Your lost pet {lost['pet_name']} marked as FOUND! Chat", roomid)
    
    conn.commit()  # All 3 operations safe ga save
    
    cur.close()
    conn.close()
    
    flash(f'✅ {lost["pet_name"]} lost request approved & user notified!', 'success')
    
    # 🔥 TWO SIDE CHAT ROOM OPEN - SocketIO emit to user
    socketio.emit('chat_room_created', {
        'room_id': roomid,
        'pet_name': lost['pet_name'],
        'message': f"✅ Admin approved your lost request! Chat now open.",
        'user_id': lost['user_id']
    }, room=f'notifications_{lost["user_id"]}')
    
    # Admin side real-time notification update
    socketio.emit('admin_status_update', {
        'type': 'lost_approved',
        'pet_name': lost['pet_name'],
        'room_id': roomid,
        'req_id': lost_id
    }, room='notifications_admin')
    
    return redirect(url_for('admin_reports', status='Accepted'))


@app.route('/admin/lost/<int:lost_id>/reject', methods=['POST'])
def admin_reject_lost(lost_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE lost_requests SET status='closed' WHERE id=%s", (lost_id,))
    conn.commit()
    cur.close(); conn.close()
    flash(' Lost request rejected.', 'info')
    return redirect(url_for('admin_lost_requests'))
@app.route('/admin/lost/<int:lost_id>')
def admin_lost_detail(lost_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    # ✅ Keep 'id' as-is - template expects r.id
    cur.execute("""
        SELECT id, pet_name, pet_type, breed, age, gender, color, 
               pet_size, weight, unique_marks, collar_details, microchip_number, 
               behavior, health_conditions, lost_date, last_seen_location, 
               last_seen_datetime, nearest_landmark, location, pet_image,
               owner_name, owner_phone, contact_info, user_id, status, created_at
        FROM lost_requests WHERE id = %s
    """, (lost_id,))
    r = cur.fetchone()
    cur.close(); conn.close()

    if not r:
        flash('Lost request not found.', 'danger')
        return redirect(url_for('admin_lost_requests'))

    return render_template('admin_lost_detail.html', r=r)

# ===== ADMIN FOUND REQUESTS =====
@app.route('/admin/found_requests')
def admin_found_requests():
    # Admin auth check
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT *
        FROM found_requests
        WHERE LOWER(status) = 'pending'
        ORDER BY id DESC
    """)
    found_list = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('admin_found_requests.html', found_list=found_list)


# ---------- ADMIN: approve ----------
@app.route('/admin/found/<int:found_id>/approve', methods=['POST'])
def admin_approve_found(found_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Get found request details
    cur.execute("SELECT * FROM found_requests WHERE id=%s", (found_id,))
    found = cur.fetchone()
    
    if not found:
        flash('Found request not found!', 'error')
        cur.close(); conn.close()
        return redirect(url_for('admin_dashboard'))
    
    # Update status to 'matched'
    cur.execute("UPDATE found_requests SET status='matched' WHERE id=%s", (found_id,))
    roomid = get_or_create_chat_room(conn, 'found', found_id)
    send_notification(found['user_id'], "Found Request APPROVED!", 
                 f"Your found pet {found['pet_name']} matched! Chat with owner", roomid)
    conn.commit()

    cur.close()
    conn.close()
    
    flash(f'✅ {found["pet_name"]} found request approved (matched) & user notified!', 'success')
    
    return redirect(url_for('admin_reports', status='Accepted'))


# ---------- ADMIN: reject ----------
@app.route('/admin/found/<int:found_id>/reject', methods=['POST'])
def admin_reject_found(found_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE found_requests SET status='closed' WHERE id=%s", (found_id,))
    conn.commit()
    cur.close()
    conn.close()

    flash('Found request rejected.', 'info')
    return redirect(url_for('admin_found_requests'))


# ---------- ADMIN: detail ----------
@app.route('/admin/found/<int:found_id>')
def admin_found_detail(found_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, pet_name, pet_type, breed, age, gender, color,
               pet_size, weight, unique_marks, collar_details, microchip_number,
               behavior, health_conditions,
               found_date, found_location, found_datetime, nearest_landmark, location,
               pet_image,
               owner_name, owner_phone, contact_info,
               user_id, status, created_at
        FROM found_requests WHERE id = %s
    """, (found_id,))
    r = cur.fetchone()
    cur.close()
    conn.close()

    if not r:
        flash('Found request not found.', 'danger')
        return redirect(url_for('admin_found_requests'))

    return render_template('admin_found_detail.html', r=r)

@app.route('/admin/found/<int:found_id>/status/<string:new_status>', methods=['POST'])
def update_found_status(found_id, new_status):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    # DB lo store chese exact values ni use cheyyi
    allowed_status = ['Pending', 'Matched', 'Closed']
    if new_status not in allowed_status:
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin_found_requests'))

    conn = get_db_connection()
    cur = conn.cursor()

    # 1) found_requests table update
    cur.execute(
        "UPDATE found_requests SET status = %s WHERE id = %s",
        (new_status, found_id)
    )

    # 2) reports table lo corresponding Found report update
    cur.execute("""
        UPDATE reports
        SET status = %s
        WHERE report_type = 'Found'
          AND message = CONCAT('Found pet report', %s)
    """, (new_status, found_id))

    conn.commit()
    cur.close()
    conn.close()

    flash(f'Found request {new_status}.', 'success')
    return redirect(url_for('admin_found_requests'))


@app.route('/admin_profile')
def admin_profile():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    admin = get_user_by_id(session['user_id'])
    if not admin:
        flash('Admin not found!', 'danger')
        return redirect(url_for('admin_login'))

    return render_template('admin_profile.html', admin=admin)

@app.route('/admin_settings', methods=["GET", "POST"])
def admin_settings():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    if request.method == "POST":
        conn = get_db_connection()
        if not conn:
            flash('Database error!', 'danger')
            return redirect(url_for('admin_settings'))

        cursor = conn.cursor(dictionary=True)
        name = request.form['name']
        phone = request.form['phone']
        email = request.form['email']

        parts = name.split(' ', 1)
        fname = parts[0]
        lname = parts[1] if len(parts) > 1 else ''

        cursor.execute("""
            UPDATE users 
            SET first_name=%s, last_name=%s, phone=%s, email=%s 
            WHERE id=%s AND role='admin'
        """, (fname, lname, phone, email, session['user_id']))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Profile updated successfully!', 'success')
        return redirect(url_for('admin_profile'))

    admin = get_user_by_id(session['user_id'])
    return render_template("admin_settings.html", admin=admin)

@app.route('/admin/reports', methods=['GET'])
def admin_reports():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    if not conn:
        flash('Database error.', 'danger')
        return redirect(url_for('admin_dashboard'))

    cur = conn.cursor(dictionary=True)

    # Filters
    report_id = request.args.get('report_id', '').strip()
    requester_email = request.args.get('requester_email', '').strip()
    status_filter = request.args.get('status', 'All')

    # 🔥 BULLETPROOF: Only SAFE columns - NO description, NO user join
    cur.execute("""
        SELECT 
            id as req_id, pet_name as petname, pet_image as petimage, 
            location, contact_info as reporter_info, status, created_at,
            'Lost' as request_type
        FROM lost_requests 
        WHERE status = 'pending'
        UNION ALL
        SELECT 
            id as req_id, pet_name as petname, pet_image as petimage,
            location, contact_info as reporter_info, status, created_at,
            'Found' as request_type
        FROM found_requests 
        WHERE status = 'pending'
        ORDER BY created_at DESC 
        LIMIT 9
    """)
    pending_reqs = cur.fetchall()

    # Reports table - PERFECT (already works)
    union_sql = """
        SELECT 
            lr.id AS report_id,
            'Lost' AS report_type,
            lr.contact_info AS requester_email,
            CONCAT('Lost pet: ', lr.pet_name) AS message,
            CASE 
              WHEN lr.status = 'pending' THEN 'Pending'
              WHEN lr.status = 'found'   THEN 'Accepted'
              WHEN lr.status = 'closed'  THEN 'Resolved'
              ELSE 'Pending'
            END AS status,
            lr.created_at AS created_at
        FROM lost_requests lr
        UNION ALL
        SELECT 
            fr.id AS report_id,
            'Found' AS report_type,
            fr.contact_info AS requester_email,
            CONCAT('Found pet: ', fr.pet_name) AS message,
            CASE 
              WHEN fr.status = 'pending' THEN 'Pending'
              WHEN fr.status = 'matched' THEN 'Accepted'
              WHEN fr.status = 'closed'  THEN 'Resolved'
              ELSE 'Pending'
            END AS status,
            fr.created_at AS created_at
        FROM found_requests fr
        UNION ALL
        SELECT 
            ar.id AS report_id,
            'Adoption' AS report_type,
            ar.phone AS requester_email,
            CONCAT('Adoption request for ', ap.name) AS message,
            CASE 
              WHEN ar.status = 'Pending'  THEN 'Pending'
              WHEN ar.status = 'Approved' THEN 'Accepted'
              WHEN ar.status = 'Rejected' THEN 'Rejected'
              ELSE 'Pending'
            END AS status,
            ar.created_at AS created_at
        FROM adoption_requests ar
        JOIN adopt_pets ap ON ar.pet_id = ap.id
    """

    # Filters + execute
    sql = f"SELECT * FROM ({union_sql}) AS R WHERE 1=1"
    params = []
    if report_id:
        sql += " AND R.report_id = %s"
        params.append(report_id)
    if requester_email:
        sql += " AND R.requester_email LIKE %s"
        params.append(f"%{requester_email}%")
    if status_filter != 'All':
        sql += " AND R.status = %s"
        params.append(status_filter)
    sql += " ORDER BY R.created_at DESC"

    cur.execute(sql, tuple(params))
    reports = cur.fetchall()

    # Counts
    cur.execute(f"SELECT COUNT(*) AS c FROM ({union_sql}) AS R")
    total_reports = cur.fetchone()['c']
    cur.execute(f"SELECT COUNT(*) AS c FROM ({union_sql}) AS R WHERE R.status = 'Pending'")
    pending = cur.fetchone()['c']
    cur.execute(f"SELECT COUNT(*) AS c FROM ({union_sql}) AS R WHERE R.status = 'Accepted'")
    accepted = cur.fetchone()['c']
    cur.execute(f"SELECT COUNT(*) AS c FROM ({union_sql}) AS R WHERE R.status = 'Resolved'")
    resolved = cur.fetchone()['c']
    cur.execute(f"SELECT COUNT(*) AS c FROM ({union_sql}) AS R WHERE R.status = 'Rejected'")
    rejected = cur.fetchone()['c']
    reunited = 0

    cur.close()
    conn.close()

    return render_template(
        'admin_reports.html',
        reports=reports,
        total_reports=total_reports,
        pending=pending,
        accepted=accepted,
        resolved=resolved,
        rejected=rejected,
        reunited=reunited,
        report_id=report_id,
        requester_email=requester_email,
        status=status_filter,
        pending_reqs=pending_reqs
    )


@app.route('/admin/reports/<int:report_id>/approve', methods=['POST'])
def approve_report(report_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('user_dashboard'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE reports SET status = 'Accepted' WHERE id = %s", (report_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin_reports'))  # nee reports dashboard route name


@app.route('/admin/reports/<int:report_id>/reject', methods=['POST'])
def reject_report(report_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('user_dashboard'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE reports SET status = 'Rejected' WHERE id = %s", (report_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin_reports'))


@app.route('/admin/reports/<int:report_id>/resolve', methods=['POST'])
def resolve_report(report_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('user_dashboard'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE reports SET status = 'Resolved' WHERE id = %s", (report_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin_reports'))

# LOST REQUEST STATUS UPDATE ROUTE
@app.route('/admin/lost/<int:lost_id>/status/<string:new_status>', methods=['POST'])
def update_lost_status(lost_id, new_status):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    if new_status not in ['pending', 'found', 'closed']:
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin_dashboard'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE lost_requests SET status=%s WHERE id=%s",
                (new_status, lost_id))
    conn.commit()
    cur.close()
    conn.close()

    flash('Lost request status updated.', 'success')
    return redirect(url_for('admin_lost_requests'))

@app.route('/admin_logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

# ---------------- Rescue page ----------------
@app.route('/rescue')
def rescue():
    if 'user_id' not in session:
        flash('Please login to access this page.', 'warning')
        return redirect(url_for('login'))
    return render_template('rescue.html')

# ---------------- Lost Pet Requests ----------------
@app.route('/lost_requests', methods=['GET', 'POST'])
def lost_requests():
    if 'user_id' not in session:
        flash('Please login.', 'warning')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        # Simple form (your old lost_requests.html)
        pet_name = request.form.get('pet_name')
        breed = request.form.get('breed')
        location = request.form.get('location')
        description = request.form.get('description')
        contact = request.form.get('contact_info')
        date = request.form.get('lost_date')
        
        image_file = request.files.get('pet_image')
        filename = None
        if image_file and image_file.filename:
            filename = secure_filename(image_file.filename)
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        # YOUR TABLE: lost_requests
        cursor.execute("""
            INSERT INTO lost_requests (pet_name, pet_image, lost_date, location, 
                                     description, contact_info, user_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
        """, (pet_name, filename, date, location, description, contact, session['user_id']))
        conn.commit()
        flash('Lost pet submitted!', 'success')
        return redirect(url_for('lost_requests'))
    
    # YOUR TABLE: lost_requests
    cursor.execute("SELECT * FROM lost_requests ORDER BY lost_date DESC")
    lost_pets = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('lost_requests.html', requests=lost_pets)

# ===== FOUND REQUESTS - YOUR SCHEMA =====
@app.route('/found_requests')
def found_requests():
    if 'user_id' not in session:
        flash('Please login to report or view found pets.', 'warning')
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        flash('Database error.', 'danger')
        return redirect(url_for('user_dashboard'))

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM found_requests ORDER BY found_date DESC")
    found_pets = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('found_requests.html', requests=found_pets)

@app.route('/lost_requests/<int:requestid>')
def lost_request_details(requestid):
    if 'userid' not in session:
        flash('Please login.', 'warning')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM lost_requests WHERE id=%s", (requestid,))
    lost = cur.fetchone()
    cur.close()
    conn.close()

    if not lost:
        flash('Lost request not found.', 'danger')
        return redirect(url_for('lost_requests'))

    return render_template('lost_request_details.html', req=lost)


@app.route('/found_requests/<int:request_id>')
def found_request_details(request_id):
    if 'user_id' not in session:
        flash('Please login.', 'warning')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM found_requests WHERE id = %s", (request_id,))
    found = cur.fetchone()
    cur.close()
    conn.close()

    if not found:
        flash('Found request not found.', 'danger')
        return redirect(url_for('found_requests'))

    return render_template('found_request_details.html', req=found)


# ---------------- Lost Pet Form (separate page) ----------------
# ===== LOST FORM (Pet Name REMOVED) =====
@app.route('/lost_form', methods=['GET', 'POST'])
def lost_form():
    if 'user_id' not in session:
        flash('Please login to report a lost pet.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        pet_name = request.form.get('pet_name') or None
        pet_type   = request.form.get('pet_type')
        breed      = request.form.get('breed') or None
        age        = request.form.get('age')
        gender     = request.form.get('gender')
        color      = request.form.get('color')
        pet_size   = request.form.get('pet_size')
        weight     = request.form.get('weight')
        unique_marks      = request.form.get('unique_marks')
        collar_details    = request.form.get('collar_details')
        microchip_number  = request.form.get('microchip_number')
        behavior          = request.form.get('behavior')
        health_conditions = request.form.get('health_conditions')
        lost_date         = request.form.get('lost_date')
        last_seen_location = request.form.get('last_seen_location')
        last_seen_datetime = request.form.get('last_seen_datetime')
        nearest_landmark   = request.form.get('nearest_landmark')
        location           = request.form.get('location')
        owner_name  = request.form.get('owner_name')
        owner_phone = request.form.get('owner_phone')
        contact_info = request.form.get('contact_info')

        # Image upload
        file = request.files.get('pet_image')
        filename = None
        if file and file.filename:
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            _, ext = os.path.splitext(secure_filename(file.filename))
            filename = f"{uuid4().hex}{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        user_id = session.get('user_id')
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            # 🆕 No pet_name in INSERT
            cur.execute("""
                INSERT INTO lost_requests
                (pet_type, breed, age, gender, color, pet_size, weight,
                 unique_marks, collar_details, microchip_number, behavior,
                 health_conditions, lost_date, last_seen_location, last_seen_datetime,
                 nearest_landmark, location, pet_image,
                 owner_name, owner_phone, contact_info, user_id, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')
            """, (pet_type, breed, age, gender, color, pet_size, weight,
                  unique_marks, collar_details, microchip_number, behavior,
                  health_conditions, lost_date, last_seen_location, last_seen_datetime,
                  nearest_landmark, location, filename, owner_name, owner_phone, 
                  contact_info, user_id))
            
            # Reports entry (use pet_type instead)
            cur.execute("""
                INSERT INTO reports (report_type, status, message, reported_by_user_id)
                VALUES ('Lost', 'Pending', %s, %s)
            """, (f'Lost {pet_type}', user_id))
            
            conn.commit()
            flash('Lost pet reported successfully!', 'success')
            return redirect(url_for('lost_requests'))
        except Exception as e:
            conn.rollback()
            flash(f'Error: {str(e)}', 'danger')
        finally:
            cur.close(); conn.close()

    return render_template('lost_form.html')
# ---------------- Found Pet Form (separate page) ----------------
@app.route('/found_form', methods=['GET', 'POST'])
def found_form():
    if 'user_id' not in session:
        flash('Please login to report a found pet.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Optional name – most of the time empty
        pet_name  = request.form.get('pet_name') or None
        pet_type  = request.form.get('pet_type')
        breed     = request.form.get('breed')
        age       = request.form.get('age')
        gender    = request.form.get('gender')
        color     = request.form.get('color')
        pet_size  = request.form.get('pet_size')
        weight    = request.form.get('weight')

        unique_marks     = request.form.get('unique_marks')
        collar_details   = request.form.get('collar_details')
        microchip_number = request.form.get('microchip_number')

        behavior          = request.form.get('behavior')
        health_conditions = request.form.get('health_conditions')

        found_date      = request.form.get('found_date')
        found_location  = request.form.get('found_location')
        found_datetime  = request.form.get('found_datetime')
        nearest_landmark = request.form.get('nearest_landmark')
        location        = request.form.get('location')

        owner_name   = request.form.get('owner_name')
        owner_phone  = request.form.get('owner_phone')
        contact_info = request.form.get('contact_info')

        # Image upload
        file = request.files.get('pet_image')
        filename = None
        if file and file.filename:
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            _, ext = os.path.splitext(secure_filename(file.filename))
            filename = f"{uuid4().hex}{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        user_id = session['user_id']

        conn = get_db_connection()
        if not conn:
            flash('Database error.', 'danger')
            return redirect(url_for('user_dashboard'))

        cur = conn.cursor()
        cur.execute("""
            INSERT INTO found_requests (
                pet_name, pet_type, breed, age, gender, color,
                pet_size, weight,
                unique_marks, collar_details, microchip_number,
                behavior, health_conditions,
                found_date, found_location, found_datetime, nearest_landmark, location,
                pet_image,
                owner_name, owner_phone, contact_info,
                user_id, status
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s,
                %s,
                %s, %s, %s,
                %s, 'pending'
            )
        """, (
            pet_name, pet_type, breed, age, gender, color,
            pet_size, weight,
            unique_marks, collar_details, microchip_number,
            behavior, health_conditions,
            found_date, found_location, found_datetime, nearest_landmark, location,
            filename,
            owner_name, owner_phone, contact_info,
            user_id
        ))
        conn.commit()
        cur.close()
        conn.close()

        flash('Found pet report submitted successfully.', 'success')
        return redirect(url_for('found_requests'))

    return render_template('found_form.html')


@app.route('/grooming')
def grooming():
    return render_template('grooming_cards.html')

# ---------------- adopt Pet Requests ----------------
@app.route('/browse_pets')
def browse_pets():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1) All available pets + search filter
    search = request.args.get('search')
    query = """
        SELECT *
        FROM adopt_pets
        WHERE availability = 'Available'
    """
    params = []
    if search:
        query += " AND (name LIKE %s OR breed LIKE %s OR CAST(id AS CHAR) = %s)"
        like = f"%{search}%"
        params.extend([like, like, search])

    cursor.execute(query, params)
    pets = cursor.fetchall()

    # 2) My requests - hard‑coded phone (later session lo nundi teesuko)
    cursor.execute("""
        SELECT ar.*, 
               ap.name  AS petname, 
               ap.photo AS petmainphoto,
               ap.species, 
               ap.breed
        FROM adoption_requests ar
        JOIN adopt_pets ap ON ar.pet_id = ap.id
        WHERE ar.phone = '9123456789'
        ORDER BY ar.id DESC
        LIMIT 10
    """)
    myadoptions = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('adopt_pets.html', pets=pets, myadoptions=myadoptions)


@app.route('/pet/<int:pet_id>')
def pet_details(pet_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM adopt_pets WHERE id = %s", (pet_id,))
    pet = cursor.fetchone()
    cursor.close(); conn.close()

    if not pet:
        flash('Pet not found', 'warning')
        return redirect(url_for('browse_pets'))
    
    return render_template('pet_detail.html', pet=pet)



@app.route('/adopt/<int:pet_id>')
def adopt_pet(pet_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM adopt_pets WHERE id = %s AND availability = 'Available'", (pet_id,))
    pet = cursor.fetchone()
    cursor.close(); conn.close()
    if not pet:
        flash('Pet not found or not available!', 'warning')
        return redirect(url_for('browse_pets'))
    return render_template('adoption_form.html', pet=pet)

@app.route('/adopt_request/<int:pet_id>', methods=['POST'])
def adopt_request(pet_id):
    if 'user_id' not in session:
        flash('Please login to submit adoption request.', 'warning')
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        flash('Database error.', 'danger')
        return redirect(url_for('browse_pets'))

    cursor = conn.cursor()

    # Insert into adoption_requests
    cursor.execute("""
        INSERT INTO adoption_requests (pet_id, name, phone, reason, status)
        VALUES (%s, %s, %s, %s, 'Pending')
    """, (
        pet_id,
        session.get('name', 'User'),
        request.form.get('phone', ''),
        request.form.get('reason', '')
    ))

    # Get pet name for reports
    cursor.execute("SELECT name FROM adopt_pets WHERE id=%s", (pet_id,))
    pet_result = cursor.fetchone()
    pet_name = pet_result[0] if pet_result else f'Pet ID {pet_id}'

    # Optional: create report entry (no FK to pets)
    cursor.execute("""
        INSERT INTO reports (report_type, pet_id, reported_by_user_id, message, status)
        VALUES ('Adoption', NULL, %s, %s, 'Pending')
    """, (
        session['user_id'],
        f"Adoption request for {pet_name}"
    ))

    conn.commit()
    cursor.close()
    conn.close()
    flash(' Adoption request submitted successfully!', 'success')
    return redirect(url_for('browse_pets'))

# ===== COMPLETE ADMIN ADOPTIONS (Lines 1500+) =====
@app.route('/admin/adoptions')
def admin_adoptions():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT 
            ar.id   AS adoptionid,
            ar.status,
            ar.name AS username,
            ar.phone,
            ar.reason,
            ar.pet_id,
            ap.name    AS pet_name,
            ap.species,
            ap.breed,
            ap.photo
        FROM adoption_requests ar 
        JOIN adopt_pets ap ON ar.pet_id = ap.id
        WHERE ar.status = 'Pending' 
        ORDER BY ar.id DESC
    """)
    requests = cur.fetchall()
    cur.close(); conn.close()
    return render_template('admin_adoptions.html', requests=requests)

@app.route('/admin/adoptions/<int:adoption_id>/approve', methods=['POST'])
def approve_adoption(adoption_id):
    # 0. Admin auth
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # 1) Get adoption request + pet details
    cur.execute("""
        SELECT ar.*, ap.name as pet_name, u.email, u.username 
        FROM adoption_requests ar 
        JOIN adopt_pets ap ON ar.pet_id = ap.id
        LEFT JOIN users u ON ar.user_id = u.id
        WHERE ar.id = %s
    """, (adoption_id,))
    adoption = cur.fetchone()
    
    if not adoption:
        flash('Adoption request not found!', 'danger')
        cur.close(); conn.close()
        return redirect(url_for('admin_adoptions'))

    pet_id = adoption['pet_id']
    pet_name = adoption['pet_name']
    user_id = adoption['user_id']

    # 2) Approve this adoption request
    cur.execute("UPDATE adoption_requests SET status = 'Approved' WHERE id = %s", (adoption_id,))

    # 3) Mark pet as Adopted
    cur.execute("UPDATE adopt_pets SET availability = 'Adopted' WHERE id = %s", (pet_id,))
    # After UPDATE adoptionrequests & adoptpets:
    room_id = get_or_create_chat_room(conn, 'adoption', adoption_id)
    send_notification(adoption['user_id'], "✅ Adoption APPROVED!", 
                 f"Chat: {room_id}", room_id)
    conn.commit()

    # 4) Reject all other pending requests for same pet
    cur.execute("""
        UPDATE adoption_requests
        SET status = 'Rejected'
        WHERE pet_id = %s AND id <> %s AND LOWER(status) = 'pending'
    """, (pet_id, adoption_id))

    return redirect(url_for('admin_reports', status='Accepted'))

@app.route('/admin/adoptions/<int:adoption_id>/reject', methods=['POST'])
def reject_adoption(adoption_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE adoption_requests SET status='Rejected' WHERE id=%s", (adoption_id,))
    conn.commit()
    cur.close(); conn.close()
    flash('Adoption rejected.', 'info')
    return redirect(url_for('admin_adoptions'))
@app.route('/admin/adoptions/<int:adoption_id>/view')
def admin_view_adoption(adoption_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT 
            ar.id          AS adoptionid,
            ar.status,
            ar.name        AS requestername,
            ar.phone       AS requesterphone,
            ar.reason,
            ap.id          AS petid,
            ap.name        AS petname,
            ap.photo       AS petimage,
            ap.species     AS petspecies,
            ap.breed       AS petbreed,
            ap.age         AS petage,
            ap.gender      AS petgender,
            ap.description AS petdescription
        FROM adoption_requests ar
        JOIN adopt_pets ap ON ar.pet_id = ap.id
        WHERE ar.id = %s
    """, (adoption_id,))
    details = cur.fetchone()
    cur.close(); conn.close()

    if not details:
        abort(404)

    return render_template('admin_adoption_detail.html', details=details)


@app.route('/pet/<int:pet_id>')
@login_required
def pet_profile(pet_id):
    conn = get_db_connection()
    if not conn:
        flash('Database error!', 'danger')
        return redirect(url_for('browse_pets'))

    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.*, u.first_name, u.last_name 
        FROM pets p 
        LEFT JOIN users u ON p.owner_id = u.id 
        WHERE p.id = %s
    """, (pet_id,))
    pet = cursor.fetchone()
    cursor.close()
    conn.close()

    if not pet:
        abort(404)

    return render_template('pet_profile.html', pet=pet)


@app.route('/admin/all_pets')
def admin_all_pets():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # Lost requests: images already static/uploads/lost/... la unte
    cur.execute("""
        SELECT 
            'Lost'      AS req_type,
            lr.id       AS req_id,
            lr.pet_name AS pet_name,
            lr.pet_type AS pet_type,
            lr.breed    AS breed,
            lr.status   AS status,
            lr.pet_image AS pet_image      -- relative path like 'uploads/lost1.jpg'
        FROM lost_requests lr
        WHERE lr.status = 'Pending'
    """)
    lost_rows = cur.fetchall()

    # Found requests
    cur.execute("""
        SELECT 
            'Found'      AS req_type,
            fr.id        AS req_id,
            fr.pet_name  AS pet_name,
            fr.pet_type  AS pet_type,
            fr.breed     AS breed,
            fr.status    AS status,
            fr.pet_image AS pet_image      -- e.g. 'uploads/found1.jpg'
        FROM found_requests fr
        WHERE fr.status = 'Pending'
    """)
    found_rows = cur.fetchall()

    # Adoption requests (adopt_pets.photo already 'img/dog1.jpg' la unte)
    cur.execute("""
        SELECT 
            'Adoption'   AS req_type,
            ar.id        AS req_id,
            ap.name      AS pet_name,
            ap.species   AS pet_type,
            ap.breed     AS breed,
            ar.status    AS status,
            ap.photo     AS pet_image      -- e.g. 'img/dog1.jpg'
        FROM adoption_requests ar
        JOIN adopt_pets ap ON ar.pet_id = ap.id
        WHERE ar.status = 'Pending'
    """)
    adopt_rows = cur.fetchall()

    all_requests = lost_rows + found_rows + adopt_rows

    cur.close(); conn.close()
    return render_template('admin_all_pets.html', all_requests=all_requests)


@app.route('/admin/all_requests')
def admin_all_requests():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
    SELECT lr.id AS req_id, 'Lost' AS req_type,
           lr.pet_name AS pet_name, lr.pet_type, lr.breed,
           lr.pet_image AS pet_image, lr.status
    FROM lost_requests lr
    WHERE lr.status = 'Pending'
    UNION ALL
    SELECT fr.id AS req_id, 'Found' AS req_type,
           fr.pet_name AS pet_name, fr.pet_type, fr.breed,
           fr.pet_image AS pet_image, fr.status
    FROM found_requests fr
    WHERE fr.status = 'Pending'
    UNION ALL
    SELECT ar.id AS req_id, 'Adoption' AS req_type,
           ap.name AS pet_name, ap.species AS pet_type,
           ap.breed AS breed, ap.photo AS pet_image,
           ar.status
    FROM adoption_requests ar
    JOIN adopt_pets ap ON ar.pet_id = ap.id
    WHERE ar.status = 'Pending'
""")
    all_requests = cur.fetchall()
    return render_template('admin_all_requests.html', all_requests=all_requests)
@app.route('/admin_filter_section')
def admin_filter_section():
    category = request.args.get('category', 'All')   # Dog / Cat / Sheep / All
    status   = request.args.get('status', 'All')     # Pending / Active / Accepted / All

    conn = get_db_connection()
    cur  = conn.cursor(dictionary=True)

    # 1) Base SQL for status
    if status == 'Pending':
        sql = """
        SELECT id, pet_name as name, pet_type as species, pet_image as image_url, status, created_at, 'Lost'  as type
        FROM lost_requests  WHERE status = 'pending'
        UNION ALL
        SELECT id, pet_name as name, pet_type as species, pet_image as image_url, status, created_at, 'Found' as type
        FROM found_requests WHERE status = 'pending'
        UNION ALL
        SELECT ar.id, ap.name as name, ap.species as species, ap.photo as image_url, ar.status, ar.created_at, 'Adopt' as type
        FROM adoption_requests ar 
        JOIN adopt_pets ap ON ar.pet_id = ap.id
        WHERE ar.status = 'Pending'
        """

    elif status == 'Active':
        sql = """
        SELECT id, name as name, species, image_url, status, created_at, 'Pet' as type
        FROM pets WHERE status = 'active'
        """

    elif status == 'Accepted':
        sql = """
        SELECT id, pet_name as name, pet_type as species, pet_image as image_url, status, created_at, 'Lost'  as type
        FROM lost_requests  WHERE status = 'found'
        UNION ALL
        SELECT id, pet_name as name, pet_type as species, pet_image as image_url, status, created_at, 'Found' as type
        FROM found_requests WHERE status = 'matched'
        UNION ALL
        SELECT ar.id, ap.name as name, ap.species as species, ap.photo as image_url, ar.status, ar.created_at, 'Adopt' as type
        FROM adoption_requests ar 
        JOIN adopt_pets ap ON ar.pet_id = ap.id
        WHERE ar.status = 'Approved'
        """

    else:  # All
        sql = """
        SELECT id, pet_name as name, pet_type as species, pet_image as image_url, status, created_at, 'Lost'  as type
        FROM lost_requests  WHERE status = 'pending'
        UNION ALL
        SELECT id, pet_name as name, pet_type as species, pet_image as image_url, status, created_at, 'Found' as type
        FROM found_requests WHERE status = 'pending'
        UNION ALL
        SELECT ar.id, ap.name as name, ap.species as species, ap.photo as image_url, ar.status, ar.created_at, 'Adopt' as type
        FROM adoption_requests ar 
        JOIN adopt_pets ap ON ar.pet_id = ap.id
        WHERE ar.status = 'Pending'
        UNION ALL
        SELECT id, name as name, species, image_url, status, created_at, 'Pet' as type
        FROM pets WHERE status = 'active'
        """

    # 2) Category filter (Dog/Cat/Sheep) on top of UNION result
    params = []
    if category != 'All':
        sql = f"SELECT * FROM ({sql}) AS X WHERE X.species = %s ORDER BY X.created_at DESC"
        params.append(category)
    else:
        sql = f"SELECT * FROM ({sql}) AS X ORDER BY X.created_at DESC"

    cur.execute(sql, params)
    items = cur.fetchall()
    conn.close()

    return render_template('filter_cards.html', items=items)

@app.route('/admin/approve_pet/<int:pet_id>')
def approve_pet(pet_id):
    cursor = mysql.connection.cursor()
    cursor.execute(
        "UPDATE pets SET status = 'active' WHERE id = %s",
        (pet_id,)
    )
    mysql.connection.commit()
    cursor.close()
    return redirect(url_for('admin_active_pets'))
@app.route('/admin/active_pets')
def admin_active_pets():
    cursor = mysql.connection.cursor()
    cursor.execute("""
        SELECT id, name, species, breed, age, color, owner_id, image_url, status, created_at
        FROM pets
        WHERE LOWER(status) = 'active'
        ORDER BY created_at DESC
    """)
    pets = cursor.fetchall()
    cursor.close()
    return render_template('active_pets.html', pets=pets)

@app.route('/admin_active_requests')
def admin_active_requests():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    sql = """
        SELECT 
            'Adoption'      AS req_type,
            ar.id           AS request_id,
            ar.pet_id       AS pet_ref,
            NULL            AS pet_name,
            NULL            AS pet_image
        FROM adoption_requests ar
        WHERE ar.status = 'Pending'

        UNION ALL

        SELECT
            'Lost'          AS req_type,
            lr.id           AS request_id,
            NULL            AS pet_ref,
            lr.pet_name     AS pet_name,
            lr.pet_image    AS pet_image
        FROM lost_requests lr
        WHERE lr.status = 'pending'

        UNION ALL

        SELECT
            'Found'         AS req_type,
            fr.id           AS request_id,
            NULL            AS pet_ref,
            fr.pet_name     AS pet_name,
            fr.pet_image    AS pet_image
        FROM found_requests fr
        WHERE fr.status = 'pending'
    """

    cur.execute(sql)
    requests = cur.fetchall()
    conn.close()

    return render_template('admin_active_requests.html', requests=requests)

@app.route('/admin/lost/accept/<int:req_id>', methods=['POST'])
def admin_accept_lost(req_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("UPDATE lost_requests SET status='found' WHERE id=%s", (req_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin_reports'))  # or admin_lost_requests

@app.route('/admin/found/accept/<int:req_id>', methods=['POST'])
def admin_accept_found(req_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("UPDATE found_requests SET status='matched' WHERE id=%s", (req_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin_reports'))

@app.route('/admin/adoption/accept/<int:req_id>', methods=['POST'])
def admin_accept_adoption(req_id):
    conn = get_db_connection()
    cur  = conn.cursor()
    cur.execute("UPDATE adoption_requests SET status='Approved' WHERE id=%s", (req_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('admin_reports'))



# ✅ Session keys: userid (nī existing), admin_id
# @socketio.on('join_chat')  # COMMENTED OUT - HANDLED IN CONDITIONAL BLOCK
def on_join(data):
    room_id = data.get('room_id')
    print(f"🔗 JOIN_CHAT request: {data}")  # Debug
    if room_id:
        join_room(room_id)
        print(f"✅ {request.sid} joined room: {room_id}")
        
        # History load
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT id as message_id, room_id, sender_role as role, sender_role, username, 
                   message, created_at as timestamp, file_path, file_name
            FROM messages WHERE room_id = %s ORDER BY created_at ASC LIMIT 50
        """, (room_id,))
        history = cur.fetchall()
        cur.close()
        conn.close()
        
        # Convert datetime objects to strings for JSON serialization
        for msg in history:
            if msg.get('timestamp'):
                msg['timestamp'] = msg['timestamp'].isoformat() if hasattr(msg['timestamp'], 'isoformat') else str(msg['timestamp'])
        
        if SOCKETIO_AVAILABLE and socketio:
            emit('load_history', {'messages': history})
        print(f"📥 Sent {len(history)} history messages to room {room_id}")


# ✅ User ID extraction from room_id - fetches from database
def get_user_id_from_room(room_id):
    """
    Extract user_id from room_id by querying the appropriate request table.
    Room formats: lost_3, found_5, adoption_7, support_10
    """
    parts = room_id.split('_')
    if len(parts) < 2:
        return None
    
    request_type = parts[0]
    try:
        request_id = int(parts[-1])
    except ValueError:
        return None
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    user_id = None
    
    if request_type == 'lost':
        cur.execute("SELECT user_id FROM lost_requests WHERE id = %s", (request_id,))
        row = cur.fetchone()
        if row:
            user_id = row['user_id']
    elif request_type == 'found':
        cur.execute("SELECT user_id FROM found_requests WHERE id = %s", (request_id,))
        row = cur.fetchone()
        if row:
            user_id = row['user_id']
    elif request_type == 'adoption':
        cur.execute("SELECT user_id FROM adoption_requests WHERE id = %s", (request_id,))
        row = cur.fetchone()
        if row:
            user_id = row['user_id']
    elif request_type == 'support':
        cur.execute("SELECT user_id FROM support_requests WHERE id = %s", (request_id,))
        row = cur.fetchone()
        if row:
            user_id = row['user_id']
    
    cur.close()
    conn.close()
    
    return user_id

# ✅ Message handler (nī session keys)

# @socketio.on('send_message')  # COMMENTED OUT - HANDLED IN CONDITIONAL BLOCK
def handle_message(data):
    try:
        print(f"📨 RECEIVED MESSAGE DATA: {data}")  # Debug
        
        room_id = data.get('room_id')
        message = data.get('message', '')[:500]
        
        if not room_id or not message.strip():
            print(f"❌ INVALID: room_id={room_id}, message={message}")
            if SOCKETIO_AVAILABLE and socketio:
                emit('error', {'message': 'Invalid room_id or message'})
            return
        
        # ✅ Session optional - use data or defaults
        sender_role = data.get('sender_role', session.get('role', 'user'))
        sender_id = data.get('sender_id', session.get('userid') or session.get('admin_id'))
        username = data.get('username', session.get('username') or session.get('admin_name', 'User'))
        admin_id = data.get('admin_id', session.get('admin_id'))
        
        print(f"📤 SAVING: room={room_id}, role={sender_role}, user={username}")  # Debug
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO messages (room_id, sender_role, sender_id, username, message)
            VALUES (%s, %s, %s, %s, %s)
        """, (room_id, sender_role, sender_id, username, message))
        conn.commit()
        message_id = cur.lastrowid
        
        print(f"✅ SAVED: message_id={message_id}")  # Debug
        
        # Admin reply → notification (if user_id extract cheyyagalam)
        if sender_role == 'admin':
            user_id = get_user_id_from_room(room_id)
            if user_id:
                cur.execute("""
                    INSERT INTO notifications (user_id, title, message, type, room_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (user_id, 'Admin replied', message[:100], 'success', room_id))
                conn.commit()
        
        cur.close()
        conn.close()
        
        emit_data = {
            'message_id': message_id,
            'room_id': room_id,
            'role': sender_role,
            'sender_role': sender_role,
            'sender_name': username,
            'username': username,
            'message': message,
            'admin_id': admin_id,
            'timestamp': datetime.now().isoformat()
        }
        print(f"📡 EMITTING to room {room_id}: {emit_data}")  # Debug
        
        # Emit to the room AND broadcast to ensure sender receives it
        if SOCKETIO_AVAILABLE and socketio:
            emit('new_message', emit_data, to=room_id)
        print(f"✅ EMIT COMPLETE")
        
    except Exception as e:
        print(f"❌ ERROR in send_message: {e}")
        import traceback
        traceback.print_exc()
        if SOCKETIO_AVAILABLE and socketio:
            emit('error', {'message': str(e)})

# ✅ File handler (session optional)
# @socketio.on('send_file')  # COMMENTED OUT - HANDLED IN CONDITIONAL BLOCK
def handle_file(data):
    room_id = data['room_id']
    file_name = data['file_name']
    file_data = data['file_data'].split(',')[1]
    sender_role = data.get('sender_role', 'user')
    username = data.get('username', 'User')
    
    upload_dir = 'static/uploads/chat_files'
    os.makedirs(upload_dir, exist_ok=True)
    filename = secure_filename(file_name)[:50]
    if '.' not in filename: filename += '.bin'
    filepath = os.path.join(upload_dir, f"{room_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}")
    
    with open(filepath, 'wb') as f:
        f.write(base64.b64decode(file_data))
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO messages (room_id, sender_role, username, file_path, file_name)
        VALUES (%s, %s, %s, %s, %s)
    """, (room_id, sender_role, username, filepath, file_name))
    conn.commit()
    cur.close()
    conn.close()
    
    if SOCKETIO_AVAILABLE and socketio:
        emit('new_file', {
            'room_id': room_id,
            'file_name': file_name,
        'file_path': filepath,
        'role': sender_role,
        'username': username,
        'timestamp': datetime.now().isoformat()
    }, room=room_id)

def create_notification(user_id, text, room_id=None):
    """Create notification for user when admin replies"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO notifications (user_id, message, room_id, is_read, created_at)
            VALUES (%s, %s, %s, 0, NOW())
        """, (user_id, text, room_id))
        
        conn.commit()
        cur.close()
        conn.close()
        print(f"🔔 NOTIFICATION: {text} for user {user_id}")
        
        # Real-time notification
        socketio.emit('notification_update', {
            'user_id': user_id,
            'message': text,
            'room_id': room_id
        }, room=f"notifications_{user_id}")
        
    except Exception as e:
        print(f"❌ NOTIFICATION ERROR: {e}")

# @socketio.on('join_notifications')  # COMMENTED OUT - HANDLED IN CONDITIONAL BLOCK
def on_join_notifications(data):
    user_id = data.get('user_id') or session.get('userid')
    if user_id:
        join_room(f'notifications_{user_id}')



# ✅ NO @login_required  
@app.route('/chat/<room_id>')
def user_chat_room(room_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT m.*, COALESCE(u.first_name, m.username, 'Unknown') AS sender_name,
               m.id as message_id
        FROM messages m
        LEFT JOIN users u ON m.sender_id = u.id
        WHERE m.room_id = %s 
        ORDER BY m.created_at ASC
    """, (room_id,))
    messages = cur.fetchall()
    
    # Get user role and username from session
    user_role = session.get('role', 'user')
    user_id = session.get('userid')
    username = session.get('username', 'User')
    
    # If user is logged in, get their name from database
    if user_id:
        cur.execute("SELECT first_name, last_name FROM users WHERE id = %s", (user_id,))
        user_data = cur.fetchone()
        if user_data:
            username = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or 'User'
    
    cur.close()
    conn.close()
    
    return render_template('chat.html', 
                         room_id=room_id, 
                         messages=messages,
                         user_role=user_role,
                         username=username,
                         user_id=user_id)


def get_unread_count(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM notifications
        WHERE user_id = %s AND is_read = FALSE
    """, (user_id,))
    count = cur.fetchone()[0]
    cur.close(); conn.close()
    return count
# If you want real unread counts later:
def get_unread_count_for_request(user_id, room_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id=%s AND room_id=%s AND is_read=FALSE", (user_id, room_id))
    count = cur.fetchone()[0]
    cur.close(); conn.close()
    return count

def send_notification(user_id, title, message_text, room_id=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO notifications (user_id, title, message, room_id, type) 
        VALUES (%s, %s, %s, %s, 'success')
    """, (user_id, title, message_text, room_id))
    conn.commit()
    cur.close()
    conn.close()
    socketio.emit(
        'notification_update',
        {
            'user_id': user_id,
            'title': title,
            'message': message_text,
            'room_id': room_id
        },
        room=f'notifications_{user_id}'
    )

@app.route('/admin/notifications')
def admin_notifications():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    # 🔥 FIX 1: Correct session key
    admin_id = session.get('user_id')  # ✅ user_id (not userid)
    status = request.args.get('status', 'all')
    
    conn = get_db_connection()
    if not conn:
        flash('Database error.', 'danger')
        return redirect(url_for('admin_dashboard'))
        
    cur = conn.cursor(dictionary=True)
    
    # Filter based on status
    if status == 'unread':
        cur.execute("""
            SELECT id, title, message, room_id, is_read, created_at
            FROM notifications
            WHERE user_id = %s AND is_read = FALSE
            ORDER BY created_at DESC
        """, (admin_id,))
    elif status == 'read':
        cur.execute("""
            SELECT id, title, message, room_id, is_read, created_at
            FROM notifications
            WHERE user_id = %s AND is_read = TRUE
            ORDER BY created_at DESC
        """, (admin_id,))
    else:  # all
        cur.execute("""
            SELECT id, title, message, room_id, is_read, created_at
            FROM notifications
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (admin_id,))
    
    notifications = cur.fetchall()
    
    #  FIX 2: Simple unread count (separate query)
    cur.execute("SELECT COUNT(*) as count FROM notifications WHERE user_id = %s AND is_read = FALSE", (admin_id,))
    unread_result = cur.fetchone()
    unread_count = unread_result['count'] if unread_result else 0
    
    cur.close()
    conn.close()
    
    return render_template('admin_notifications.html',
                          notifications=notifications,
                          status=status,
                          unread_count=unread_count,
                          admin_id=admin_id)  # ✅ Pass admin_id

@app.route('/admin/mark_all_read', methods=['POST'])
def mark_all_read():
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False})
    
    admin_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE notifications SET is_read = TRUE WHERE user_id = %s", (admin_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})



@app.route("/user_notifications")
def user_notifications():
    if "userid" not in session:
        return redirect(url_for("login"))

    status = request.args.get("status", "all")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # ✅ ADD THIS LINE - Unread count
    cur.execute("SELECT COUNT(*) as unread_count FROM notifications WHERE user_id=%s AND is_read=0", (session["userid"],))
    unread_count = cur.fetchone()['unread_count']

    base_sql = (
        "SELECT id, user_id, title, message, type, room_id, is_read, created_at "
        "FROM notifications WHERE user_id=%s "
    )
    params = [session["userid"]]

    if status == "unread":
        base_sql += "AND is_read = 0 "
    elif status == "read":
        base_sql += "AND is_read = 1 "

    base_sql += "ORDER BY created_at DESC"

    cur.execute(base_sql, params)
    notes = cur.fetchall()

    cur.execute(
        "UPDATE notifications SET is_read=1 WHERE user_id=%s AND is_read=0",
        (session["userid"],)
    )
    conn.commit()

    cur.close()
    conn.close()

    return render_template(
        "user_notifications.html",
        notifications=notes,
        status=status,
        unread_count=unread_count  # ✅ PASS TO TEMPLATE
    )



@app.route("/chats")
def user_chats():
    if "userid" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
    SELECT m.room_id,
           MAX(m.created_at) AS last_time
    FROM messages m
    WHERE m.sender_id = %s
       OR m.room_id IN (
           SELECT room_id FROM messages WHERE sender_id = %s
       )
    GROUP BY m.room_id
    ORDER BY last_time DESC
""", (session["userid"], session["userid"]))

    
    rooms = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("chat_list.html", rooms=rooms)


@app.route('/support', methods=['GET', 'POST'])
def support():
    if 'userid' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        description = request.form.get('description')

        conn = get_db_connection()
        cur = conn.cursor()

        # 1) support_requests lo save
        cur.execute("""
            INSERT INTO support_requests (user_id, description)
            VALUES (%s, %s)
        """, (session['userid'], description))
        conn.commit()
        request_id = cur.lastrowid

        # 2) chat_rooms lo room create
        room_id = get_or_create_chat_room(conn, 'support', request_id)

        cur.close()
        conn.close()

        # 3) direct chat ki velthav
        return redirect(url_for('user_chat_room', room_id=room_id))

    # GET request – form chupinchadam
    return render_template('support.html')

# ========== ADMIN DELETE ROUTES ==========
@app.route('/admin/message/<int:message_id>/delete_me', methods=['POST'])
def admin_delete_message_me(message_id):
    if 'admin_id' not in session:
        return jsonify({'success': False}), 403
    return jsonify({'success': True})

@app.route('/admin/message/<int:message_id>/delete_all', methods=['POST'])
def admin_delete_message_all(message_id):
    if 'admin_id' not in session:
        return jsonify({'success': False}), 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE messages SET is_deleted=1 WHERE id=%s", (message_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

# ========== USER DELETE ROUTES ==========
@app.route('/message/<int:message_id>/delete_me', methods=['POST'])
def user_delete_message_me(message_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    return jsonify({'success': True})

@app.route('/message/<int:message_id>/delete_all', methods=['POST'])
def user_delete_message_all(message_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE messages SET is_deleted=1 
        WHERE id=%s AND sender_role='user' AND sender_id=%s
    """, (message_id, session['user_id']))
    
    affected = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'success': affected > 0})

# ========== SOCKETIO (Keep only these) ==========
# @socketio.on('delete_message')  # COMMENTED OUT - HANDLED IN CONDITIONAL BLOCK
def handle_delete_message(data):
    room_id = data['room_id']
    message_id = data['message_id']
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if 'admin_id' in session:
        cur.execute("UPDATE messages SET is_deleted=1 WHERE id=%s", (message_id,))
    elif 'user_id' in session:
        cur.execute("UPDATE messages SET is_deleted=1 WHERE id=%s AND sender_id=%s", 
                   (message_id, session['user_id']))
    
    conn.commit()
    cur.close()
    conn.close()
    
    if SOCKETIO_AVAILABLE and socketio:
        emit('message_deleted', {'message_id': message_id, 'room_id': room_id}, 
             room=room_id, include_self=False)

# @socketio.on('connect')  # COMMENTED OUT - HANDLED IN CONDITIONAL BLOCK
def handle_connect():
    if SOCKETIO_AVAILABLE and socketio:
        emit('user_status', {'online': True}, broadcast=True)

# @socketio.on('disconnect')  # COMMENTED OUT - HANDLED IN CONDITIONAL BLOCK
def handle_disconnect():
    if SOCKETIO_AVAILABLE and socketio:
        emit('user_status', {'online': False}, broadcast=True)


# @socketio.on('load_history')  # COMMENTED OUT - HANDLED IN CONDITIONAL BLOCK
def handle_load_history(data):
    room_id = data['room_id']
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    cur.execute("""
        SELECT id, room_id, sender_id, sender_role, username, message, 
               file_path, file_name, timestamp 
        FROM messages 
        WHERE room_id=%s AND is_deleted=0
        ORDER BY timestamp ASC
    """, (room_id,))
    messages = cur.fetchall()
    
    conn.close()
    if SOCKETIO_AVAILABLE and socketio:
        emit('history_loaded', {'messages': messages}, room=room_id)



@app.route('/pet/<int:pet_id>/request-chat', methods=['POST'])
@login_required
def request_chat_for_pet(pet_id):
    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO chat_room_requests (requester_id, pet_id, type, status)
        VALUES (%s, %s, 'adopt', 'pending')
    """, (current_user.id, pet_id))
    mysql.connection.commit()
    cur.close()
    flash('Chat request sent to admin.')
    return redirect(url_for('pet_details', pet_id=pet_id))



@app.route('/admin_switch_user/<int:user_id>')
def admin_switch_user(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin access required!', 'error')
        return redirect(url_for('admin_dashboard'))
    
    # Target admin fetch chey
    conn = get_db_connection()
    cur = conn.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT id, first_name, email, name FROM users WHERE id=%s AND role='admin'", (user_id,))
    target_admin = cur.fetchone()
    cur.close()
    conn.close()
    
    if target_admin:
        # Session update
        session['user_id'] = target_admin['id']
        session['first_name'] = target_admin['first_name'] or target_admin['name'] or 'Admin'
        session['email'] = target_admin['email']
        session['name'] = target_admin['name'] or 'Admin'
        
        flash(f'Switched to {target_admin["name"] or target_admin["email"]} (ID: {target_admin["id"]})', 'success')
    else:
        flash('Admin not found!', 'error')
    
    return redirect(url_for('admin_dashboard'))




@app.route('/vaccination')
def vaccination():
    # vaccination centers list fetch chesi template ki pass chey
    return render_template('vaccination.html')

# 🔥 ROUTE 1: Pet Detail Page

# APPROVE + REJECT - PERFECT (no change needed)
@app.route('/admin_request_detail/<int:req_id>')
def admin_request_detail(req_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Admin login required.', 'warning')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # LOST + FOUND requests lo unna full columns select cheyyi
    cur.execute("""
        SELECT 
            'Lost' AS type,
            id,
            pet_name,
            pet_type,
            breed,
            age,
            gender,
            color,
            location,
            contact_info,
            owner_name,
            owner_phone,
            pet_image,
            status,
            created_at,
            user_id
        FROM lost_requests
        WHERE id = %s

        UNION ALL

        SELECT 
            'Found' AS type,
            id,
            pet_name,
            pet_type,
            breed,
            age,
            gender,
            color,
            location,
            contact_info,
            owner_name,
            owner_phone,
            pet_image,
            status,
            created_at,
            user_id
        FROM found_requests
        WHERE id = %s
    """, (req_id, req_id))

    pet = cur.fetchone()
    cur.fetchall()
    while cur.nextset():
        pass

    user = None
    if pet and pet['user_id']:
        cur.execute("""
            SELECT id, first_name, last_name, email, phone, city
            FROM users
            WHERE id = %s
        """, (pet['user_id'],))
        user = cur.fetchone()
        cur.fetchall()
        while cur.nextset():
            pass

    cur.close()
    conn.close()

    if not pet:
        flash('Pet request not found!', 'warning')
        return redirect(url_for('admin_notifications'))

    return render_template('admin_request_detail.html',
                           pet=pet,
                           user=user,
                           req_id=req_id)

# 🔥 ROUTE 2: APPROVE

@app.route('/admin_approve_request/<int:req_id>', methods=['POST'])
def admin_approve_request(req_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # 1) Lost or Found request fetch (for user_id etc. kavalsina appudu)
    cur.execute("""
        SELECT 'lost'  AS type, id, user_id, pet_type as pet_name
        FROM lost_requests WHERE id = %s
        UNION ALL
        SELECT 'found' AS type, id, user_id, pet_type as pet_name
        FROM found_requests WHERE id = %s
        LIMIT 1
    """, (req_id, req_id))
    req = cur.fetchone()

    if not req:
        flash('Request not found!', 'warning')
        cur.close(); conn.close()
        return redirect(url_for('admin_notifications'))

    # 2) Status update - only update the relevant table
    if req['type'] == 'lost':
        cur.execute("UPDATE lost_requests SET status='found' WHERE id=%s", (req_id,))
    elif req['type'] == 'found':
        cur.execute("UPDATE found_requests SET status='matched' WHERE id=%s", (req_id,))
    
    # 3) Chat room (existing helper)
    room_id = get_or_create_chat_room(conn, req['type'], req_id)

    conn.commit()
    cur.close(); conn.close()

    flash('✅ APPROVED! Chat opened.', 'success')
    # 🔥 direct ga chat page ki
    return redirect(url_for('admin_chat_room', room_id=room_id))

# 🔥 ROUTE 3: REJECT
@app.route('/admin_reject_request/<int:req_id>', methods=['POST'])
def admin_reject_request(req_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("UPDATE lost_requests  SET status='closed' WHERE id=%s", (req_id,))
    cur.execute("UPDATE found_requests SET status='closed' WHERE id=%s", (req_id,))

    conn.commit()
    cur.close()
    conn.close()

    flash('❌ REJECTED!', 'info')
    return redirect(url_for('admin_request_detail', req_id=req_id))

@app.route('/admin/chats')
def admin_chats():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Get all chat rooms with user/case info and actual user names
    cur.execute("""
        SELECT cr.*, 
               COALESCE(msg_stats.message_count, 0) as message_count,
               msg_stats.last_message,
               msg_stats.last_sender,
               CASE 
                   WHEN cr.request_type = 'lost' THEN 
                       (SELECT CONCAT(COALESCE(u.first_name, ''), ' ', COALESCE(u.last_name, '')) 
                        FROM lost_requests lr 
                        JOIN users u ON lr.user_id = u.id 
                        WHERE lr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'found' THEN 
                       (SELECT CONCAT(COALESCE(u.first_name, ''), ' ', COALESCE(u.last_name, '')) 
                        FROM found_requests fr 
                        JOIN users u ON fr.user_id = u.id 
                        WHERE fr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'adoption' THEN 
                       (SELECT CONCAT(COALESCE(u.first_name, ''), ' ', COALESCE(u.last_name, '')) 
                        FROM adoption_requests ar 
                        JOIN users u ON ar.user_id = u.id 
                        WHERE ar.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'support' THEN 
                       (SELECT CONCAT(COALESCE(u.first_name, ''), ' ', COALESCE(u.last_name, '')) 
                        FROM support_requests sr 
                        JOIN users u ON sr.user_id = u.id 
                        WHERE sr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   ELSE 'Unknown User'
               END as user_name,
               CASE 
                   WHEN cr.request_type = 'lost' THEN 
                       (SELECT u.email 
                        FROM lost_requests lr 
                        JOIN users u ON lr.user_id = u.id 
                        WHERE lr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'found' THEN 
                       (SELECT u.email 
                        FROM found_requests fr 
                        JOIN users u ON fr.user_id = u.id 
                        WHERE fr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'adoption' THEN 
                       (SELECT u.email 
                        FROM adoption_requests ar 
                        JOIN users u ON ar.user_id = u.id 
                        WHERE ar.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'support' THEN 
                       (SELECT u.email 
                        FROM support_requests sr 
                        JOIN users u ON sr.user_id = u.id 
                        WHERE sr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   ELSE NULL
               END as email
        FROM chat_rooms cr 
        LEFT JOIN (
            SELECT room_id,
                   COUNT(id) as message_count,
                   MAX(created_at) as last_message,
                   (SELECT username FROM messages m2 
                    WHERE m2.room_id = m1.room_id 
                    ORDER BY m2.created_at DESC LIMIT 1) as last_sender
            FROM messages m1
            GROUP BY room_id
        ) msg_stats ON cr.room_id = msg_stats.room_id
        ORDER BY cr.created_at DESC
    """)
    chats = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('admin_chats.html', chat_rooms=chats)
@app.route('/admin/chat/<room_id>')
def admin_chat_room(room_id):
    # Admin only access
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Chat room details (user info + case details)
    cur.execute("""
        SELECT cr.*, 
               CASE 
                   WHEN cr.request_type = 'lost' THEN 
                       (SELECT CONCAT(COALESCE(u.first_name, ''), ' ', COALESCE(u.last_name, '')) 
                        FROM lost_requests lr 
                        JOIN users u ON lr.user_id = u.id 
                        WHERE lr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'found' THEN 
                       (SELECT CONCAT(COALESCE(u.first_name, ''), ' ', COALESCE(u.last_name, '')) 
                        FROM found_requests fr 
                        JOIN users u ON fr.user_id = u.id 
                        WHERE fr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'adoption' THEN 
                       (SELECT CONCAT(COALESCE(u.first_name, ''), ' ', COALESCE(u.last_name, '')) 
                        FROM adoption_requests ar 
                        JOIN users u ON ar.user_id = u.id 
                        WHERE ar.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'support' THEN 
                       (SELECT CONCAT(COALESCE(u.first_name, ''), ' ', COALESCE(u.last_name, '')) 
                        FROM support_requests sr 
                        JOIN users u ON sr.user_id = u.id 
                        WHERE sr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   ELSE 'Unknown User'
               END as user_name,
               CASE 
                   WHEN cr.request_type = 'lost' THEN 
                       (SELECT u.email 
                        FROM lost_requests lr 
                        JOIN users u ON lr.user_id = u.id 
                        WHERE lr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'found' THEN 
                       (SELECT u.email 
                        FROM found_requests fr 
                        JOIN users u ON fr.user_id = u.id 
                        WHERE fr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'adoption' THEN 
                       (SELECT u.email 
                        FROM adoption_requests ar 
                        JOIN users u ON ar.user_id = u.id 
                        WHERE ar.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'support' THEN 
                       (SELECT u.email 
                        FROM support_requests sr 
                        JOIN users u ON sr.user_id = u.id 
                        WHERE sr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   ELSE NULL
               END as email,
               CASE 
                   WHEN cr.request_type = 'lost' THEN 
                       (SELECT u.phone 
                        FROM lost_requests lr 
                        JOIN users u ON lr.user_id = u.id 
                        WHERE lr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'found' THEN 
                       (SELECT u.phone 
                        FROM found_requests fr 
                        JOIN users u ON fr.user_id = u.id 
                        WHERE fr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'adoption' THEN 
                       (SELECT u.phone 
                        FROM adoption_requests ar 
                        JOIN users u ON ar.user_id = u.id 
                        WHERE ar.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   WHEN cr.request_type = 'support' THEN 
                       (SELECT u.phone 
                        FROM support_requests sr 
                        JOIN users u ON sr.user_id = u.id 
                        WHERE sr.id = CAST(SUBSTRING_INDEX(cr.room_id, '_', -1) AS UNSIGNED))
                   ELSE NULL
               END as phone
        FROM chat_rooms cr 
        WHERE cr.room_id = %s
    """, (room_id,))
    chatroom = cur.fetchone()
    
    if not chatroom:
        flash('Chat room not found!', 'warning')
        cur.close()
        conn.close()
        return redirect(url_for('admin_chats'))
    
    # All messages with sender names
    cur.execute("""
        SELECT m.*, 
               CASE 
                   WHEN m.sender_role = 'admin' THEN 
                       CASE m.sender_id 
                           WHEN 2 THEN 'Admin 1'
                           WHEN 7 THEN 'Admin 2'
                           ELSE CONCAT('Admin ', m.sender_id)
                       END
                   ELSE COALESCE(u.first_name, m.username, 'User')
               END as sender_name
        FROM messages m
        LEFT JOIN users u ON m.sender_id = u.id
        WHERE m.room_id = %s
        ORDER BY m.created_at ASC
    """, (room_id,))
    messages = cur.fetchall()
    
    # Get founder user info (for found pet cases - the person who found the pet)
    founder_user = None
    reporter_user = None
    if chatroom and chatroom.get('request_type') == 'found':
        # Extract request_id from room_id (format: found_123)
        try:
            request_id = int(room_id.split('_')[-1])
            
            # Get founder info (owner_name from found_requests)
            cur.execute("""
                SELECT fr.owner_name as name, fr.owner_phone as phone
                FROM found_requests fr
                WHERE fr.id = %s
            """, (request_id,))
            founder_data = cur.fetchone()
            if founder_data and founder_data.get('name'):
                founder_user = {
                    'name': founder_data.get('name'),
                    'phone': founder_data.get('phone')
                }
            
            # Get reporter info (user who reported the found pet)
            cur.execute("""
                SELECT u.first_name, u.last_name, u.email, u.phone
                FROM found_requests fr
                JOIN users u ON fr.user_id = u.id
                WHERE fr.id = %s
            """, (request_id,))
            reporter_data = cur.fetchone()
            if reporter_data:
                reporter_name = f"{reporter_data.get('first_name', '')} {reporter_data.get('last_name', '')}".strip()
                reporter_user = {
                    'name': reporter_name or 'Reporter',
                    'email': reporter_data.get('email'),
                    'phone': reporter_data.get('phone')
                }
        except Exception as e:
            print(f"Error fetching founder/reporter info: {e}")
            pass
    
    # Set admin session for template/JS
    admin_id = session.get('admin_id', 2)  # Default Admin1 (Primary)
    admin_name = 'Admin 1' if admin_id == 2 else 'Admin 2'
    session['admin_id'] = admin_id
    session['admin_name'] = admin_name
    
    cur.close()
    conn.close()
    
    # Use existing chat_room.html template with correct variable names
    return render_template('chat_room.html', 
                         room_id=room_id,
                         chats=messages,
                         chatroom=chatroom,
                         active_user_name=chatroom.get('user_name', 'User') if chatroom else 'User',
                         founder_user=founder_user,
                         reporter_user=reporter_user,
                         case_title=f"{chatroom.get('request_type', 'Chat').title()} Request" if chatroom else 'Chat',
                         case_subtitle=f"Chat with {chatroom.get('user_name', 'User')}" if chatroom else 'Chat with user',
                         case_created_at=chatroom.get('created_at') if chatroom else None,
                         admin_id=admin_id,
                         admin_name=admin_name)

# ========== CHAT MANAGEMENT ROUTES ==========

@app.route('/admin/chat/<room_id>/clear', methods=['POST'])
def clear_chat(room_id):
    """Clear all messages in a chat room (keep the room)"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM messages WHERE room_id = %s", (room_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Chat cleared successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/chat/<room_id>/delete', methods=['POST'])
def delete_chat_room(room_id):
    """Delete entire chat room and all messages"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Delete messages first
        cur.execute("DELETE FROM messages WHERE room_id = %s", (room_id,))
        # Delete the chat room
        cur.execute("DELETE FROM chat_rooms WHERE room_id = %s", (room_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Chat room deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/chat/<room_id>/export')
def export_chat(room_id):
    """Export chat messages as text file"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Get all messages
    cur.execute("""
        SELECT m.*, u.first_name, u.last_name
        FROM messages m
        LEFT JOIN users u ON m.sender_id = u.id
        WHERE m.room_id = %s
        ORDER BY m.created_at ASC
    """, (room_id,))
    messages = cur.fetchall()
    
    cur.close()
    conn.close()
    
    # Create text content
    content = f"Chat Export - Room: {room_id}\n"
    content += "=" * 50 + "\n\n"
    
    for msg in messages:
        timestamp = msg['created_at'].strftime('%Y-%m-%d %H:%M:%S') if msg['created_at'] else 'Unknown'
        sender = msg.get('username', 'Unknown')
        if msg['sender_role'] == 'admin':
            sender = f"Admin {msg.get('sender_id', '?')}"
        
        content += f"[{timestamp}] {sender}: {msg['message']}\n"
    
    # Return as downloadable file
    from flask import Response
    return Response(
        content,
        mimetype='text/plain',
        headers={'Content-Disposition': f'attachment; filename=chat_{room_id}.txt'}
    )

# Test route to add Founded User data
@app.route('/test/add-founder-data')
def test_add_founder_data():
    """Test route to add founder data to found_requests"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Update found_requests with test founder data
    cur.execute("""
        UPDATE found_requests 
        SET owner_name = 'lohith ss', owner_phone = '9876543210'
        WHERE id = 5 AND (owner_name IS NULL OR owner_name = '')
    """)
    
    conn.commit()
    cur.close()
    conn.close()
    
    flash('Test founder data added to found_5! Now check the chat room.', 'success')
    return redirect(url_for('admin_chat_room', room_id='found_5'))
    """Export chat messages as text file"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT m.*, COALESCE(u.first_name, m.username, 'Unknown') as sender_name
        FROM messages m
        LEFT JOIN users u ON m.sender_id = u.id
        WHERE m.room_id = %s
        ORDER BY m.created_at ASC
    """, (room_id,))
    messages = cur.fetchall()
    cur.close()
    conn.close()
    
    # Generate text content
    content = f"Chat Export - Room: {room_id}\n"
    content += f"Exported on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    content += "=" * 50 + "\n\n"
    
    for msg in messages:
        timestamp = msg['created_at'].strftime('%Y-%m-%d %H:%M') if msg.get('created_at') else ''
        sender = msg.get('sender_name', 'Unknown')
        role = msg.get('sender_role', 'user').title()
        message = msg.get('message', '[File]') if not msg.get('file_name') else f"[File: {msg['file_name']}]"
        content += f"[{timestamp}] {sender} ({role}):\n{message}\n\n"
    
    from flask import Response
    return Response(
        content,
        mimetype='text/plain',
        headers={'Content-Disposition': f'attachment; filename=chat_{room_id}_{datetime.now().strftime("%Y%m%d")}.txt'}
    )

@app.route('/admin/chat/<room_id>/add-user', methods=['POST'])
def add_user_to_chat(room_id):
    """Add a user to the chat room"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({'success': False, 'error': 'User ID required'})
    
    # For now, just add a system message that user was added
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        
        # Get user name
        cur.execute("SELECT first_name, last_name FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() if user else 'User'
        
        # Add system message
        cur.execute("""
            INSERT INTO messages (room_id, sender_role, username, message)
            VALUES (%s, 'system', 'System', %s)
        """, (room_id, f"{user_name} was added to the chat by Admin"))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': f'{user_name} added to chat'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/chat/<room_id>/remove-user', methods=['POST'])
def remove_user_from_chat(room_id):
    """Remove a user from the chat room"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    # Add system message that user was removed
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO messages (room_id, sender_role, username, message)
            VALUES (%s, 'system', 'System', 'User was removed from the chat by Admin')
        """, (room_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'message': 'User removed from chat'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/search-users')
def search_users():
    """Search users for adding to chat"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify([])
    
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, first_name, last_name, email
        FROM users
        WHERE (first_name LIKE %s OR last_name LIKE %s OR email LIKE %s)
        AND role = 'user'
        LIMIT 10
    """, (f'%{query}%', f'%{query}%', f'%{query}%'))
    users = cur.fetchall()
    cur.close()
    conn.close()
    
    return jsonify([{
        'id': u['id'],
        'name': f"{u.get('first_name', '')} {u.get('last_name', '')}".strip(),
        'email': u.get('email', '')
    } for u in users])

@app.route('/admin/search-founders')
def search_founders():
    """Search found pet reports for adding founder to chat"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify([])
    
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, owner_name, pet_type, location, owner_phone
        FROM found_requests
        WHERE (owner_name LIKE %s OR pet_type LIKE %s OR location LIKE %s)
        AND status IN ('pending', 'matched')
        LIMIT 10
    """, (f'%{query}%', f'%{query}%', f'%{query}%'))
    founders = cur.fetchall()
    cur.close()
    conn.close()
    
    return jsonify([{
        'id': f['id'],
        'name': f.get('owner_name', 'Unknown'),
        'pet_type': f.get('pet_type', 'Pet'),
        'location': f.get('location', 'Unknown'),
        'phone': f.get('owner_phone', '')
    } for f in founders])

@app.route('/admin/chat/<room_id>/add-founder', methods=['POST'])
def add_founder_to_chat(room_id):
    """Add a found pet reporter to the chat room"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    founder_id = data.get('founder_id')
    
    if not founder_id:
        return jsonify({'success': False, 'error': 'Founder ID required'})
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        
        # Get founder name
        cur.execute("SELECT owner_name FROM found_requests WHERE id = %s", (founder_id,))
        founder = cur.fetchone()
        founder_name = founder.get('owner_name', 'Founder') if founder else 'Founder'
        
        # Add system message
        cur.execute("""
            INSERT INTO messages (room_id, sender_role, username, message)
            VALUES (%s, 'system', 'System', %s)
        """, (room_id, f"{founder_name} (Found Pet Reporter) was added to the chat by Admin"))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': f'{founder_name} added to chat'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/chat/<room_id>/add-admin', methods=['POST'])
def add_admin_to_chat(room_id):
    """Add an admin to the chat room"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    admin_id = data.get('admin_id')
    
    if not admin_id:
        return jsonify({'success': False, 'error': 'Admin ID required'})
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        admin_name = f"Admin {admin_id}"
        
        # Add system message
        cur.execute("""
            INSERT INTO messages (room_id, sender_role, username, message)
            VALUES (%s, 'system', 'System', %s)
        """, (room_id, f"{admin_name} was added to the chat"))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': f'{admin_name} added to chat'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/search-reporters')
def search_reporters():
    """Search users who have reported found pets"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify([])
    
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT u.id, u.first_name, u.last_name, u.email, COUNT(fr.id) as report_count
        FROM users u
        JOIN found_requests fr ON u.id = fr.user_id
        WHERE (u.first_name LIKE %s OR u.last_name LIKE %s OR u.email LIKE %s)
        AND u.role = 'user'
        GROUP BY u.id, u.first_name, u.last_name, u.email
        HAVING report_count > 0
        LIMIT 10
    """, (f'%{query}%', f'%{query}%', f'%{query}%'))
    reporters = cur.fetchall()
    cur.close()
    conn.close()
    
    return jsonify([{
        'id': r['id'],
        'name': f"{r.get('first_name', '')} {r.get('last_name', '')}".strip(),
        'email': r.get('email', ''),
        'report_count': r.get('report_count', 0)
    } for r in reporters])

@app.route('/admin/chat/<room_id>/add-reporter', methods=['POST'])
def add_reporter_to_chat(room_id):
    """Add a reporter user to the chat room"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    reporter_id = data.get('reporter_id')
    
    if not reporter_id:
        return jsonify({'success': False, 'error': 'Reporter ID required'})
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        
        # Get reporter name
        cur.execute("SELECT first_name, last_name FROM users WHERE id = %s", (reporter_id,))
        reporter = cur.fetchone()
        reporter_name = f"{reporter.get('first_name', '')} {reporter.get('last_name', '')}".strip() if reporter else 'Reporter'
        
        # Add system message
        cur.execute("""
            INSERT INTO messages (room_id, sender_role, username, message)
            VALUES (%s, 'system', 'System', %s)
        """, (room_id, f"{reporter_name} (Reporter) was added to the chat by Admin"))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True, 'message': f'{reporter_name} added to chat'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== SOCKETIO EVENT HANDLERS ==========
# Only register SocketIO handlers if SocketIO is available
if SOCKETIO_AVAILABLE and socketio:
    
    @socketio.on('join_chat')
    def on_join_safe(data):
        room_id = data.get('room_id')
        print(f"🔗 JOIN_CHAT request: {data}")
        if room_id:
            join_room(room_id)
            print(f"✅ {request.sid} joined room: {room_id}")
            
            # Load history
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT id as message_id, room_id, sender_role as role, sender_role, username, 
                       message, created_at as timestamp, file_path, file_name
                FROM messages WHERE room_id = %s ORDER BY created_at ASC LIMIT 50
            """, (room_id,))
            history = cur.fetchall()
            cur.close()
            conn.close()
            
            # Convert datetime objects to strings
            for msg in history:
                if msg.get('timestamp'):
                    msg['timestamp'] = msg['timestamp'].isoformat() if hasattr(msg['timestamp'], 'isoformat') else str(msg['timestamp'])
            
            emit('load_history', {'messages': history})
            print(f"📥 Sent {len(history)} history messages to room {room_id}")

    @socketio.on('send_message')
    def handle_message_safe(data):
        try:
            room_id = data['room_id']
            message = data['message']
            sender_role = data.get('sender_role', 'user')
            username = data.get('username', 'User')
            admin_id = data.get('admin_id')
            sender_id = data.get('sender_id')
            
            # Save to database
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO messages (room_id, sender_role, sender_id, username, message, admin_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (room_id, sender_role, sender_id, username, message, admin_id))
            
            message_id = cur.lastrowid
            conn.commit()
            cur.close()
            conn.close()
            
            # Broadcast to room
            socketio.emit('new_message', {
                'message_id': message_id,
                'room_id': room_id,
                'message': message,
                'sender_role': sender_role,
                'username': username,
                'admin_id': admin_id,
                'timestamp': datetime.now().isoformat()
            }, room=room_id)
            
            print(f"✅ MESSAGE SENT: {message[:50]}... to room {room_id}")
            
        except Exception as e:
            print(f"❌ MESSAGE ERROR: {e}")
            emit('error', {'message': 'Failed to send message'})

    @socketio.on('send_file')
    def handle_file_safe(data):
        try:
            room_id = data['room_id']
            file_name = data['file_name']
            file_data = data['file_data']
            sender_role = data.get('sender_role', 'user')
            username = data.get('username', 'User')
            
            # Save file
            import base64
            import os
            
            file_dir = os.path.join(app.static_folder, 'uploads', 'chat_files')
            os.makedirs(file_dir, exist_ok=True)
            
            # Decode and save file
            file_content = base64.b64decode(file_data.split(',')[1])
            file_path = os.path.join(file_dir, file_name)
            
            with open(file_path, 'wb') as f:
                f.write(file_content)
            
            # Save to database
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO messages (room_id, sender_role, username, message, file_name, file_path, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (room_id, sender_role, username, f"Sent file: {file_name}", file_name, file_name))
            
            message_id = cur.lastrowid
            conn.commit()
            cur.close()
            conn.close()
            
            # Broadcast to room
            socketio.emit('new_file', {
                'message_id': message_id,
                'room_id': room_id,
                'file_name': file_name,
                'file_path': file_name,
                'sender_role': sender_role,
                'username': username,
                'timestamp': datetime.now().isoformat()
            }, room=room_id)
            
            print(f"✅ FILE SENT: {file_name} to room {room_id}")
            
        except Exception as e:
            print(f"❌ FILE ERROR: {e}")
            emit('error', {'message': 'Failed to send file'})

    @socketio.on('delete_message')
    def handle_delete_message_safe(data):
        try:
            room_id = data['room_id']
            message_id = data['message_id']
            
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM messages WHERE id = %s AND room_id = %s", (message_id, room_id))
            conn.commit()
            cur.close()
            conn.close()
            
            socketio.emit('message_deleted', {
                'message_id': message_id,
                'room_id': room_id
            }, room=room_id, include_self=False)
            
            print(f"✅ MESSAGE DELETED: {message_id} from room {room_id}")
            
        except Exception as e:
            print(f"❌ DELETE ERROR: {e}")

    @socketio.on('connect')
    def handle_connect_safe():
        print("✅ Client connected")

    @socketio.on('disconnect')
    def handle_disconnect_safe():
        print("👋 Client disconnected")

    @socketio.on('join_notifications')
    def on_join_notifications_safe(data):
        user_id = data.get('user_id') or session.get('userid')
        if user_id:
            join_room(f'user_{user_id}')
            print(f"✅ User {user_id} joined notifications")

    print("✅ SocketIO event handlers registered")
else:
    print("⚠️  SocketIO not available - chat functionality disabled")

# ========== RUN APPLICATION ==========
# Main execution handled above - duplicate removed

# ========== API ROUTES ==========
# RESTful API endpoints for mobile app or external integrations

@app.route('/api/pets', methods=['GET'])
def api_get_pets():
    """Get all available pets for adoption"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        
        # Get query parameters
        pet_type = request.args.get('type')
        status = request.args.get('status', 'active')
        limit = request.args.get('limit', 10, type=int)
        
        # Build query
        query = "SELECT * FROM pets WHERE status = %s"
        params = [status]
        
        if pet_type:
            query += " AND species = %s"
            params.append(pet_type)
            
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        
        cur.execute(query, params)
        pets = cur.fetchall()
        
        # Convert datetime objects to strings
        for pet in pets:
            if pet.get('created_at'):
                pet['created_at'] = pet['created_at'].isoformat()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': pets,
            'count': len(pets)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/pets/<int:pet_id>', methods=['GET'])
def api_get_pet(pet_id):
    """Get specific pet details"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        
        cur.execute("SELECT * FROM pets WHERE id = %s", (pet_id,))
        pet = cur.fetchone()
        
        if not pet:
            return jsonify({
                'success': False,
                'error': 'Pet not found'
            }), 404
            
        # Convert datetime to string
        if pet.get('created_at'):
            pet['created_at'] = pet['created_at'].isoformat()
            
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': pet
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/lost-pets', methods=['GET'])
def api_get_lost_pets():
    """Get all lost pet reports"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        
        status = request.args.get('status', 'pending')
        limit = request.args.get('limit', 20, type=int)
        
        cur.execute("""
            SELECT lr.*, u.first_name, u.last_name, u.email, u.phone
            FROM lost_requests lr
            LEFT JOIN users u ON lr.user_id = u.id
            WHERE lr.status = %s
            ORDER BY lr.created_at DESC
            LIMIT %s
        """, (status, limit))
        
        lost_pets = cur.fetchall()
        
        # Convert datetime objects
        for pet in lost_pets:
            if pet.get('created_at'):
                pet['created_at'] = pet['created_at'].isoformat()
            if pet.get('lost_date'):
                pet['lost_date'] = pet['lost_date'].isoformat() if hasattr(pet['lost_date'], 'isoformat') else str(pet['lost_date'])
                
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': lost_pets,
            'count': len(lost_pets)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/found-pets', methods=['GET'])
def api_get_found_pets():
    """Get all found pet reports"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        
        status = request.args.get('status', 'pending')
        limit = request.args.get('limit', 20, type=int)
        
        cur.execute("""
            SELECT fr.*, u.first_name, u.last_name, u.email, u.phone
            FROM found_requests fr
            LEFT JOIN users u ON fr.user_id = u.id
            WHERE fr.status = %s
            ORDER BY fr.created_at DESC
            LIMIT %s
        """, (status, limit))
        
        found_pets = cur.fetchall()
        
        # Convert datetime objects
        for pet in found_pets:
            if pet.get('created_at'):
                pet['created_at'] = pet['created_at'].isoformat()
            if pet.get('found_date'):
                pet['found_date'] = pet['found_date'].isoformat() if hasattr(pet['found_date'], 'isoformat') else str(pet['found_date'])
                
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': found_pets,
            'count': len(found_pets)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/adoption-requests', methods=['POST'])
def api_create_adoption_request():
    """Create new adoption request via API"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['pet_id', 'user_name', 'user_email', 'user_phone']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if pet exists
        cur.execute("SELECT id FROM pets WHERE id = %s AND status = 'active'", (data['pet_id'],))
        if not cur.fetchone():
            return jsonify({
                'success': False,
                'error': 'Pet not found or not available'
            }), 404
        
        # Create adoption request
        cur.execute("""
            INSERT INTO adoption_requests 
            (pet_id, user_name, user_email, user_phone, message, status, created_at)
            VALUES (%s, %s, %s, %s, %s, 'pending', NOW())
        """, (
            data['pet_id'],
            data['user_name'],
            data['user_email'],
            data['user_phone'],
            data.get('message', '')
        ))
        
        request_id = cur.lastrowid
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Adoption request submitted successfully',
            'request_id': request_id
        }), 201
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/lost-pets', methods=['POST'])
def api_report_lost_pet():
    """Report a lost pet via API"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['pet_name', 'pet_type', 'owner_name', 'owner_phone', 'location']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Insert lost pet report
        cur.execute("""
            INSERT INTO lost_requests 
            (pet_name, pet_type, breed, age, gender, color, pet_size, weight,
             owner_name, owner_phone, location, contact_info, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', NOW())
        """, (
            data['pet_name'],
            data['pet_type'],
            data.get('breed', ''),
            data.get('age', ''),
            data.get('gender', ''),
            data.get('color', ''),
            data.get('pet_size', ''),
            data.get('weight', ''),
            data['owner_name'],
            data['owner_phone'],
            data['location'],
            data.get('contact_info', '')
        ))
        
        report_id = cur.lastrowid
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Lost pet report submitted successfully',
            'report_id': report_id
        }), 201
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/found-pets', methods=['POST'])
def api_report_found_pet():
    """Report a found pet via API"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['pet_name', 'pet_type', 'location', 'owner_name', 'owner_phone']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Insert found pet report
        cur.execute("""
            INSERT INTO found_requests 
            (pet_name, pet_type, breed, age, gender, color, pet_size, weight,
             location, owner_name, owner_phone, contact_info, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', NOW())
        """, (
            data['pet_name'],
            data['pet_type'],
            data.get('breed', ''),
            data.get('age', ''),
            data.get('gender', ''),
            data.get('color', ''),
            data.get('pet_size', ''),
            data.get('weight', ''),
            data['location'],
            data['owner_name'],
            data['owner_phone'],
            data.get('contact_info', '')
        ))
        
        report_id = cur.lastrowid
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Found pet report submitted successfully',
            'report_id': report_id
        }), 201
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/users', methods=['POST'])
def api_register_user():
    """Register new user via API"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['first_name', 'last_name', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        
        # Check if email already exists
        cur.execute('SELECT id FROM users WHERE email = %s', (data['email'],))
        if cur.fetchone():
            return jsonify({
                'success': False,
                'error': 'Email already registered'
            }), 409
        
        # Hash password
        hashed_password = generate_password_hash(data['password'])
        
        # Insert new user
        cur.execute("""
            INSERT INTO users 
            (first_name, last_name, email, phone, city, password, role, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'user', NOW())
        """, (
            data['first_name'],
            data['last_name'],
            data['email'],
            data.get('phone', ''),
            data.get('city', ''),
            hashed_password
        ))
        
        user_id = cur.lastrowid
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'User registered successfully',
            'user_id': user_id
        }), 201
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/stats', methods=['GET'])
def api_get_stats():
    """Get platform statistics"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        
        # Get various counts
        stats = {}
        
        # Total pets
        cur.execute("SELECT COUNT(*) as count FROM pets WHERE status = 'active'")
        stats['total_pets'] = cur.fetchone()['count']
        
        # Total users
        cur.execute("SELECT COUNT(*) as count FROM users WHERE role = 'user'")
        stats['total_users'] = cur.fetchone()['count']
        
        # Lost pets
        cur.execute("SELECT COUNT(*) as count FROM lost_requests WHERE status = 'pending'")
        stats['lost_pets'] = cur.fetchone()['count']
        
        # Found pets
        cur.execute("SELECT COUNT(*) as count FROM found_requests WHERE status = 'pending'")
        stats['found_pets'] = cur.fetchone()['count']
        
        # Adoption requests
        cur.execute("SELECT COUNT(*) as count FROM adoption_requests WHERE status = 'pending'")
        stats['adoption_requests'] = cur.fetchone()['count']
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': stats
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API Documentation endpoint
@app.route('/api/docs', methods=['GET'])
def api_documentation():
    """API Documentation"""
    docs = {
        'title': 'PawHaven API Documentation',
        'version': '1.0.0',
        'base_url': request.host_url + 'api',
        'endpoints': {
            'GET /api/pets': {
                'description': 'Get all available pets',
                'parameters': {
                    'type': 'Filter by pet type (optional)',
                    'status': 'Filter by status (default: active)',
                    'limit': 'Limit results (default: 10)'
                }
            },
            'GET /api/pets/{id}': {
                'description': 'Get specific pet details'
            },
            'GET /api/lost-pets': {
                'description': 'Get lost pet reports',
                'parameters': {
                    'status': 'Filter by status (default: pending)',
                    'limit': 'Limit results (default: 20)'
                }
            },
            'GET /api/found-pets': {
                'description': 'Get found pet reports',
                'parameters': {
                    'status': 'Filter by status (default: pending)',
                    'limit': 'Limit results (default: 20)'
                }
            },
            'POST /api/adoption-requests': {
                'description': 'Create adoption request',
                'required_fields': ['pet_id', 'user_name', 'user_email', 'user_phone']
            },
            'POST /api/lost-pets': {
                'description': 'Report lost pet',
                'required_fields': ['pet_name', 'pet_type', 'owner_name', 'owner_phone', 'location']
            },
            'POST /api/found-pets': {
                'description': 'Report found pet',
                'required_fields': ['pet_name', 'pet_type', 'location', 'owner_name', 'owner_phone']
            },
            'POST /api/users': {
                'description': 'Register new user',
                'required_fields': ['first_name', 'last_name', 'email', 'password']
            },
            'GET /api/stats': {
                'description': 'Get platform statistics'
            }
        }
    }
    
    return jsonify(docs)


# ========== RUN APPLICATION ==========
if __name__ == "__main__":
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    # Timer(1, open_browser).start()  # Disabled browser auto-open
    
    # Run app with or without SocketIO
    if SOCKETIO_AVAILABLE and socketio:
        socketio.run(app, debug=True, host='127.0.0.1', port=5000)
    else:
        app.run(debug=True, host='127.0.0.1', port=5000)
