from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from datetime import datetime, timedelta
import re, random, string
from functools import wraps
import os
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
import os
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'blood.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ── Session expires on browser close (non-permanent / session cookie) ──
# No PERMANENT_SESSION_LIFETIME needed — session.permanent is never set to True
app.config['SESSION_COOKIE_HTTPONLY'] = True   # JS cannot read the cookie
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
# Set SESSION_COOKIE_SECURE = True in production (HTTPS only)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5000').split(',')
CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGINS}})

# ─────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────

class User(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    username    = db.Column(db.String(100), unique=True, nullable=False)
    email       = db.Column(db.String(150), unique=True, nullable=False)
    phone       = db.Column(db.String(20))
    first_name  = db.Column(db.String(60))
    middle_name = db.Column(db.String(60))
    last_name   = db.Column(db.String(60))
    city        = db.Column(db.String(100))
    password    = db.Column(db.String(200), nullable=False)
    role        = db.Column(db.String(20), default="user")   # "user" | "admin"
    is_admin    = db.Column(db.Boolean, default=False)       # explicit admin flag
    created     = db.Column(db.DateTime, default=datetime.utcnow)
    login_count = db.Column(db.Integer, default=0)           # tracks total logins

class Donor(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(100), nullable=False)
    blood_group  = db.Column(db.String(5), nullable=False)
    city         = db.Column(db.String(100), nullable=False)
    phone        = db.Column(db.String(15))
    email        = db.Column(db.String(150))
    last_donated = db.Column(db.Date)
    is_available = db.Column(db.Boolean, default=True)
    donations    = db.Column(db.Integer, default=0)

class BloodInventory(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    blood_group = db.Column(db.String(5), nullable=False)
    city        = db.Column(db.String(100), nullable=False)   # per-city inventory
    bank_name   = db.Column(db.String(150))                   # blood bank name
    units       = db.Column(db.Integer, default=0)
    cost_per_bag= db.Column(db.Float, default=1500.0)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("blood_group", "city", name="uq_bg_city"),)

class EmergencyRequest(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    blood_group = db.Column(db.String(5), nullable=False)
    location    = db.Column(db.String(100), nullable=False)
    address     = db.Column(db.String(250))
    units       = db.Column(db.Integer, nullable=False)
    patient_name    = db.Column(db.String(100))
    receiver_phone  = db.Column(db.String(20))               # +91XXXXXXXXXX
    status      = db.Column(db.String(20), default="pending")  # pending|fulfilled|cancelled
    fulfillment = db.Column(db.String(20), default="none")    # stock|donor|mixed|none
    units_from_stock = db.Column(db.Integer, default=0)
    units_from_donor = db.Column(db.Integer, default=0)
    requested_at= db.Column(db.DateTime, default=datetime.utcnow)
    donor_name  = db.Column(db.String(100))

class Donation(db.Model):
    """Tracks individual donation records; status drives certificate release."""
    id          = db.Column(db.Integer, primary_key=True)
    donor_id    = db.Column(db.Integer, db.ForeignKey("donor.id"), nullable=False)
    donated_on  = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    status      = db.Column(db.String(20), default="Pending")  # Pending | Completed
    notes       = db.Column(db.String(250))
    donor       = db.relationship("Donor", backref="donation_records")

class Transaction(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    receipt_no   = db.Column(db.String(20), unique=True)
    patient_name = db.Column(db.String(100))
    blood_group  = db.Column(db.String(5))
    bags         = db.Column(db.Integer)
    cost_per_bag = db.Column(db.Float)
    delivery_fee = db.Column(db.Float, default=0)
    total        = db.Column(db.Float)
    status       = db.Column(db.String(20), default="pending")   # pending|paid|flagged
    fraud_flag   = db.Column(db.Boolean, default=False)
    rider_id     = db.Column(db.Integer, db.ForeignKey("rider.id"))  # assigned delivery partner
    rider_name   = db.Column(db.String(100))                     # denormalized for easy access
    rider_phone  = db.Column(db.String(20))                      # denormalized for easy access
    user_id      = db.Column(db.Integer, db.ForeignKey("user.id"))   # user who created this transaction
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

class OTPRecord(db.Model):
    """Stores a 6-digit OTP with a 60-second expiry for password recovery."""
    id         = db.Column(db.Integer, primary_key=True)
    identifier = db.Column(db.String(150), nullable=False)  # email or phone
    method     = db.Column(db.String(10), nullable=False)   # "email" | "phone"
    otp_code   = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used       = db.Column(db.Boolean, default=False)

    @property
    def is_expired(self):
        return (datetime.utcnow() - self.created_at).total_seconds() > 60

class Appointment(db.Model):
    """Stores donation appointment bookings."""
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    phone       = db.Column(db.String(20), nullable=False)   # stored as +91XXXXXXXXXX
    dob         = db.Column(db.Date)
    blood_group = db.Column(db.String(5))
    appt_date   = db.Column(db.Date, nullable=False)
    slot        = db.Column(db.String(50))
    centre      = db.Column(db.String(150))
    last_donated= db.Column(db.Date)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

class DeliveryRequest(db.Model):
    """Emergency Response Unit — tracks a blood delivery from bank to patient."""
    id            = db.Column(db.Integer, primary_key=True)
    eru_code      = db.Column(db.String(20), unique=True, nullable=False)
    blood_group   = db.Column(db.String(5), nullable=False)
    location      = db.Column(db.String(100), nullable=False)
    address       = db.Column(db.String(250))
    units         = db.Column(db.Integer, nullable=False)
    patient_name  = db.Column(db.String(100))
    donor_name    = db.Column(db.String(100))
    # Status: pending → in_transit → completed
    status        = db.Column(db.String(20), default="pending")
    receipt_no    = db.Column(db.String(20))          # set on completion
    # Distance-based ETA fields
    distance_km   = db.Column(db.Float, default=0.0)  # Haversine distance
    eta_seconds   = db.Column(db.Integer, default=12) # (distance × 2) + 10
    delivery_fee  = db.Column(db.Float, default=50.0) # ₹50 + ₹15/km
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    started_at    = db.Column(db.DateTime)
    completed_at  = db.Column(db.DateTime)

class Rider(db.Model):
    """Bloodhound delivery partners — emergency blood transport riders."""
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    phone      = db.Column(db.String(20), nullable=False)
    city       = db.Column(db.String(100), nullable=False)
    vehicle    = db.Column(db.String(50), default="Motorcycle")  # Motorcycle, Ambulance, etc.
    is_free    = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

BLOOD_PRICES = {"A+":1500,"B+":1500,"O+":1800,"AB+":2000,
                "A-":1500,"B-":1500,"O-":1800,"AB-":2000}

CITIES = ["Virar","Nalasopara","Vasai","Naigaon","Bhayandar",
          "Mira Road","Dahisar","Borivali","Kandivali","Malad"]

# One central blood bank per city
CITY_BANKS = {
    "Virar":      "Virar Central Blood Bank, Station Road",
    "Nalasopara": "Nalasopara Blood Centre, East",
    "Vasai":      "Vasai Central Blood Bank, Vasai Road",
    "Naigaon":    "Naigaon Blood Centre, Near Station",
    "Bhayandar":  "Bhayandar Central Blood Bank, West",
    "Mira Road":  "Mira Road Blood Centre, Sector 1",
    "Dahisar":    "Dahisar Central Blood Bank, East",
    "Borivali":   "Borivali Blood Centre, S.V. Road",
    "Kandivali":  "Kandivali Central Blood Bank, West",
    "Malad":      "Malad Blood Centre, Malad West",
}

# ── Real-world coordinates for each blood bank (lat, lon) ──────────────────
CITY_COORDS = {
    "Virar":      (19.4588, 72.8110),
    "Nalasopara": (19.4209, 72.7996),
    "Vasai":      (19.3919, 72.8397),
    "Naigaon":    (19.3636, 72.8530),
    "Bhayandar":  (19.3000, 72.8500),
    "Mira Road":  (19.2812, 72.8726),
    "Dahisar":    (19.2490, 72.8560),
    "Borivali":   (19.2307, 72.8567),
    "Kandivali":  (19.2043, 72.8490),
    "Malad":      (19.1863, 72.8484),
}

# Default delivery address coordinates (city centre — used when address is free-text)
CITY_CENTRE_COORDS = {
    "Virar":      (19.4650, 72.8050),
    "Nalasopara": (19.4250, 72.8050),
    "Vasai":      (19.3950, 72.8450),
    "Naigaon":    (19.3680, 72.8580),
    "Bhayandar":  (19.3050, 72.8550),
    "Mira Road":  (19.2850, 72.8780),
    "Dahisar":    (19.2530, 72.8600),
    "Borivali":   (19.2350, 72.8620),
    "Kandivali":  (19.2080, 72.8540),
    "Malad":      (19.1900, 72.8530),
}

def auto_capitalize(name: str) -> str:
    """Convert any name string to Title Case."""
    return name.strip().title() if name else name

def sanitize_name(name: str) -> str:
    """Remove digits and special characters; keep only letters, spaces, hyphens."""
    cleaned = re.sub(r"[^A-Za-z\s\-]", "", name)
    return auto_capitalize(cleaned)

import math

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth (km).
    Uses the Haversine formula — no external API needed.
    """
    R = 6371.0  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = math.radians(lat2 - lat1)
    dlambda    = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def calculate_delivery(city: str) -> dict:
    """
    Given a city name, compute:
      - distance_km  : Haversine distance from blood bank to city centre
      - eta_minutes  : 15 min base + (distance / 25 km/h), minimum 15 min
      - eta_seconds  : demo simulation countdown = (distance × 3) + 15
      - delivery_fee : ₹20 flat + ₹5/km, rounded to nearest integer
    """
    city_key   = city.strip().title()
    bank_coord = CITY_COORDS.get(city_key, (19.2307, 72.8567))
    dest_coord = CITY_CENTRE_COORDS.get(city_key, (19.2350, 72.8620))

    dist_km  = round(haversine_km(bank_coord[0], bank_coord[1],
                                   dest_coord[0],  dest_coord[1]), 2)
    dist_km  = max(dist_km, 0.5)

    # Realistic ETA: 15 min base + travel time at 25 km/h
    eta_mins = max(15, 15 + math.ceil((dist_km / 25) * 60))

    # Demo simulation countdown (seconds)
    eta_secs = int((dist_km * 3) + 15)

    # Integer fee: ₹20 flat + ₹5/km
    fee = int(round(20 + (dist_km * 5)))

    return {
        "distance_km":  dist_km,
        "eta_minutes":  eta_mins,
        "eta_seconds":  eta_secs,
        "delivery_fee": fee,
    }


def calculate_delivery_from_city(source_city: str, dest_city: str) -> dict:
    """
    Calculate delivery info from a specific source blood bank city to a destination city.
    Used for multi-bank cost comparison.
    """
    src_key   = source_city.strip().title()
    dst_key   = dest_city.strip().title()
    src_coord = CITY_COORDS.get(src_key, CITY_COORDS.get(dst_key, (19.2307, 72.8567)))
    dst_coord = CITY_CENTRE_COORDS.get(dst_key, CITY_CENTRE_COORDS.get(dst_key, (19.2350, 72.8620)))

    dist_km  = round(haversine_km(src_coord[0], src_coord[1],
                                   dst_coord[0],  dst_coord[1]), 2)
    dist_km  = max(dist_km, 0.5)
    eta_mins = max(15, 15 + math.ceil((dist_km / 25) * 60))
    eta_secs = int((dist_km * 3) + 15)
    fee      = int(round(20 + (dist_km * 5)))

    return {
        "source_city":  src_key,
        "distance_km":  dist_km,
        "eta_minutes":  eta_mins,
        "eta_seconds":  eta_secs,
        "delivery_fee": fee,
        "bank_name":    CITY_BANKS.get(src_key, f"{src_key} Blood Bank"),
    }

def delivery_fee_for_bags(bags: int) -> float:
    """Legacy flat-rate fee — kept for Finance page manual receipts."""
    if bags <= 3:   return 100
    if bags <= 7:   return 200
    if bags <= 12:  return 350
    return 500

def valid_password(pw):
    if len(pw) < 8:              return "Password must be at least 8 characters"
    if not re.search("[A-Z]",pw): return "Must contain at least 1 uppercase letter"
    if not re.search("[0-9]",pw): return "Must contain at least 1 number"
    if not re.search("[!@#$%^&*(),.?\":{}|<>]",pw): return "Must contain at least 1 special character"
    return None

def valid_phone(phone):
    """Strict 10-digit: no letters/symbols, starts with 9/8/7/6. Accepts +91 prefix."""
    digits = re.sub(r"^\+91", "", phone)
    return bool(re.fullmatch(r"[6987]\d{9}", digits))

def valid_username(username):
    """No spaces allowed."""
    return " " not in username and len(username) >= 3

def gen_receipt():
    return "RCP-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

def fraud_check(bags, total, blood_group):
    flags = []
    if bags > 15:
        flags.append("Exceeds maximum bag limit of 15")
    if total > 40000:
        flags.append("Transaction amount exceeds threshold")
    if blood_group in ["O-","AB-"] and bags > 5:
        flags.append("Rare blood group bulk request")
    return flags

def seed_data():
    # ── Multi-city inventory (one bank per city, all 8 blood groups) ──
    if BloodInventory.query.count() == 0:
        for city, bank in CITY_BANKS.items():
            for bg, price in BLOOD_PRICES.items():
                units = random.randint(5, 30)
                db.session.add(BloodInventory(
                    blood_group=bg, city=city, bank_name=bank,
                    units=units, cost_per_bag=price))

    # ── Donors ──
    if Donor.query.count() == 0:
        donors = [
            ("Arjun Sharma",   "A+",  "Virar",      "+919876543210", "arjun@mail.com",   30),
            ("Priya Patel",    "B+",  "Nalasopara", "+919123456780", "priya@mail.com",   45),
            ("Rahul Verma",    "O+",  "Vasai",      "+919988776655", "rahul@mail.com",   20),
            ("Sneha Iyer",     "AB+", "Naigaon",    "+919871234560", "sneha@mail.com",   60),
            ("Karan Mehta",    "A-",  "Bhayandar",  "+919765432100", "karan@mail.com",   15),
            ("Divya Nair",     "B-",  "Mira Road",  "+919654321000", "divya@mail.com",   90),
            ("Amit Singh",     "O-",  "Dahisar",    "+919543210000", "amit@mail.com",    10),
            ("Neha Gupta",     "AB-", "Borivali",   "+919432100000", "neha@mail.com",    35),
            ("Vikram Rao",     "O+",  "Kandivali",  "+919321000000", "vikram@mail.com",  25),
            ("Pooja Desai",    "A+",  "Malad",      "+919210000000", "pooja@mail.com",   50),
            ("Suresh Kumar",   "B+",  "Virar",      "+919100000001", "suresh@mail.com",  40),
            ("Anita Joshi",    "O-",  "Nalasopara", "+919000000002", "anita@mail.com",   70),
        ]
        for d in donors:
            last = datetime.utcnow().date() - timedelta(days=d[5])
            avail = d[5] >= 90
            db.session.add(Donor(name=d[0], blood_group=d[1], city=d[2],
                                 phone=d[3], email=d[4], last_donated=last,
                                 is_available=avail, donations=random.randint(1,10)))

    # ── Bloodhound Riders ──
    if Rider.query.count() == 0:
        riders = [
            ("Rajesh Kumar",    "+919876501234", "Virar",      "Motorcycle"),
            ("Sanjay Patil",    "+919876502345", "Nalasopara", "Motorcycle"),
            ("Deepak Sharma",   "+919876503456", "Vasai",      "Ambulance"),
            ("Manoj Singh",     "+919876504567", "Naigaon",    "Motorcycle"),
            ("Anil Verma",      "+919876505678", "Bhayandar",  "Motorcycle"),
            ("Sunil Yadav",     "+919876506789", "Mira Road",  "Ambulance"),
            ("Ramesh Gupta",    "+919876507890", "Dahisar",    "Motorcycle"),
            ("Vijay Desai",     "+919876508901", "Borivali",   "Motorcycle"),
            ("Prakash Mehta",   "+919876509012", "Kandivali",  "Ambulance"),
            ("Ashok Joshi",     "+919876500123", "Malad",      "Motorcycle"),
        ]
        for r in riders:
            db.session.add(Rider(name=r[0], phone=r[1], city=r[2], vehicle=r[3], is_free=True))

    # ── No hardcoded admin accounts — use /create-initial-admin on first run ──
    db.session.commit()


def hard_reset_demo_data():
    """
    Hard-deletes all test transactions and resets inventory to exactly 20 units.

    Uses raw SQL DELETE + UPDATE statements so changes are written directly to
    the physical .db file — no ORM caching, no partial commits.

    SAFE: Does NOT touch the 'user', 'donor', or 'rider' tables.
    """
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # ── 1. Hard-delete all transactional records ──
    db.session.execute(db.text("DELETE FROM emergency_request"))
    db.session.commit()   # commit immediately — force physical write

    db.session.execute(db.text('DELETE FROM "transaction"'))
    db.session.commit()

    db.session.execute(db.text("DELETE FROM delivery_request"))
    db.session.commit()

    db.session.execute(db.text("DELETE FROM appointment")) 
    db.session.commit()

    # ── 2. Overwrite every inventory row to exactly 20 units ──
    #    UPDATE (not INSERT) so existing city/blood-group rows are preserved
    db.session.execute(
        db.text("UPDATE blood_inventory SET units = 20, updated_at = :ts"),
        {"ts": now_str}
    )
    db.session.commit()   # final commit — inventory now clean

    # ── 3. Verify counts ──
    er_count  = db.session.execute(db.text("SELECT COUNT(*) FROM emergency_request")).scalar()
    txn_count = db.session.execute(db.text('SELECT COUNT(*) FROM "transaction"')).scalar()
    inv_check = db.session.execute(
        db.text("SELECT COUNT(*) FROM blood_inventory WHERE units != 20")
    ).scalar()

    print(f"[HARD RESET] emergency_request rows : {er_count}  (expected 0)")
    print(f"[HARD RESET] transaction rows        : {txn_count}  (expected 0)")
    print(f"[HARD RESET] inventory rows != 20    : {inv_check}  (expected 0)")
    print(f"[HARD RESET] Complete — DB is clean for demo.")

# ─────────────────────────────────────────
# ─────────────────────────────────────────
# PAGE ROUTES
# ─────────────────────────────────────────

# ── Login-required decorator ──────────────────────────────────
from functools import wraps

def login_required(f):
    """Redirect to /signin if no active session exists."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("signin"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    """Redirect to /admin-entry if the session is not flagged as admin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("admin_entry") + "?error=login_required")
        if not session.get("is_admin"):
            return redirect(url_for("admin_entry") + "?error=unauthorized")
        return f(*args, **kwargs)
    return decorated

@app.route("/")
def home():
    # If already logged in, send to the right dashboard
    if session.get("user_id"):
        if session.get("is_admin"):
            return redirect(url_for("admin_command_panel"))
        return redirect(url_for("user_dashboard"))
    # Otherwise show the portal choice screen (landing page)
    return redirect(url_for("signin"))

@app.route("/signup")
def signup():
    return render_template("signup.html")

@app.route("/signin")
def signin():
    return render_template("index.html")

@app.route("/admin-login")
def admin_login_page():
    """Dedicated admin login page — separate from the user login."""
    error = request.args.get("error", "")
    if session.get("user_id") and session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html", error=error)

@app.route("/admin-portal")
def admin_portal():
    """
    Secret admin portal for team registration and login.
    This is the unified entry point for admin account creation and authentication.
    Share this URL with your team: /admin-portal  or  /admin-entry
    """
    # If already logged in as admin, redirect to dashboard
    if session.get("user_id") and session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_portal.html")

@app.route("/admin-entry")
def admin_entry():
    """
    Public-facing admin entry point linked from the landing page.
    Renders the same admin portal (passphrase + login tabs).
    """
    if session.get("user_id") and session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_portal.html")

@app.route("/create-initial-admin", methods=["GET", "POST"])
def create_initial_admin():
    """
    Hidden first-run route. Only works when NO admin exists in the database.
    GET  → renders a simple form.
    POST → creates the first admin account with bcrypt-hashed password.
    Once any admin exists this route returns 403.
    """
    # Block if any admin already exists
    if User.query.filter_by(is_admin=True).first():
        return jsonify({
            "error": "An admin account already exists. "
                     "Use the Admin Dashboard to add more admins."
        }), 403

    if request.method == "GET":
        return _admin_setup_form("Create Initial Admin",
            "This page is only available when no admin account exists.")

    return _handle_admin_creation_form()


@app.route("/reset-admin", methods=["GET", "POST"])
def reset_admin():
    """
    Emergency admin reset route — works even when admins already exist.
    Requires the secret key ?key=sbdms_reset_2026 to prevent misuse.
    Use this when you've lost access to all admin accounts.
    """
    secret = request.args.get("key", "") or request.form.get("key", "")
    RESET_SECRET = os.getenv('RESET_SECRET', 'sbdms_reset_2026')
    #if secret != "sbdms_reset_2026":
    if secret != RESET_SECRET:
        return "<h3 style='color:red;font-family:sans-serif;text-align:center;padding:40px'>Access denied — invalid key.</h3>", 403

    if request.method == "GET":
        return _admin_setup_form("Reset / Create Admin",
            "This will create a new admin account. Existing accounts are not deleted.")

    return _handle_admin_creation_form()


def _admin_setup_form(title, subtitle):
    """Shared HTML form for both /create-initial-admin and /reset-admin."""
    return f"""
    <!DOCTYPE html><html><head>
      <title>{title} — SBDMS</title>
      <style>
        body{{font-family:sans-serif;display:flex;align-items:center;
             justify-content:center;min-height:100vh;background:#f1f5f9}}
        .card{{background:#fff;padding:36px 32px;border-radius:12px;
              box-shadow:0 8px 32px rgba(0,0,0,.12);width:380px}}
        h2{{color:#9b1c1c;margin-bottom:6px}}
        p{{font-size:13px;color:#64748b;margin-bottom:20px}}
        label{{font-size:12px;font-weight:700;color:#475569;
               text-transform:uppercase;letter-spacing:.5px;
               display:block;margin-bottom:4px;margin-top:12px}}
        input{{width:100%;padding:10px 12px;border:2px solid #e2e8f0;
               border-radius:8px;font-size:14px;box-sizing:border-box}}
        input:focus{{outline:none;border-color:#9b1c1c}}
        button{{width:100%;padding:12px;background:#9b1c1c;color:#fff;
                border:none;border-radius:8px;font-size:15px;
                font-weight:700;cursor:pointer;margin-top:18px}}
        .note{{font-size:11px;color:#94a3b8;margin-top:12px;text-align:center}}
        .req{{font-size:11px;color:#64748b;margin-top:6px}}
      </style>
    </head><body>
      <div class="card">
        <h2>🛡️ {title}</h2>
        <p>{subtitle}</p>
        <form method="POST">
          <input type="hidden" name="key" value="{request.args.get('key', '')}">
          <label>Username</label>
          <input type="text" name="username" placeholder="e.g. super_admin" required
                 autocomplete="off">
          <label>Password</label>
          <input type="password" name="password" required autocomplete="new-password"
                 placeholder="Min 8 chars, 1 upper, 1 number, 1 symbol">
          <p class="req">Requirements: ≥8 chars · 1 uppercase · 1 number · 1 special char</p>
          <label>Email (optional)</label>
          <input type="email" name="email" placeholder="admin@example.com">
          <button type="submit">✓ Create Admin Account</button>
        </form>
        <p class="note">Password is hashed with bcrypt before storage.</p>
      </div>
    </body></html>
    """


def _handle_admin_creation_form():
    """Shared POST handler for both admin setup routes."""
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    email    = request.form.get("email", "").strip() or f"{username}@sbdms.local"

    if not valid_username(username):
        return ("<p style='color:red;font-family:sans-serif;padding:20px'>"
                "Username must be ≥3 chars with no spaces. "
                "<a href='javascript:history.back()'>← Back</a></p>"), 400

    err = valid_password(password)
    if err:
        return (f"<p style='color:red;font-family:sans-serif;padding:20px'>"
                f"{err}. <a href='javascript:history.back()'>← Back</a></p>"), 400

    # If username already exists, update it to admin instead of creating duplicate
    existing = User.query.filter_by(username=username).first()
    if existing:
        existing.password = bcrypt.generate_password_hash(password).decode("utf-8")
        existing.role     = "admin"
        existing.is_admin = True
        db.session.commit()
        print(f"[ADMIN SETUP] Promoted existing user '{username}' to admin")
        action = "updated and promoted to admin"
    else:
        hashed = bcrypt.generate_password_hash(password).decode("utf-8")
        admin  = User(
            username=username, email=email, phone="+910000000000",
            first_name="Admin", last_name="User", city="Borivali",
            password=hashed, role="admin", is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print(f"[ADMIN SETUP] Created new admin '{username}'")
        action = "created"

    return f"""
    <html><body style="font-family:sans-serif;text-align:center;padding:60px;background:#f1f5f9">
      <div style="background:#fff;border-radius:12px;padding:40px;
                  max-width:400px;margin:auto;box-shadow:0 8px 32px rgba(0,0,0,.1)">
        <div style="font-size:48px;margin-bottom:16px">✅</div>
        <h2 style="color:#059669">Admin account '{username}' {action}!</h2>
        <p style="color:#64748b;margin:12px 0">
          You can now log in at
          <a href="/admin-login" style="color:#9b1c1c;font-weight:700">/admin-login</a>
        </p>
        <p style="color:#94a3b8;font-size:12px">
          Username: <strong>{username}</strong><br>
          Use the password you just set.
        </p>
      </div>
    </body></html>
    """

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/user-dashboard")
@login_required
def user_dashboard():
    """Alias for /dashboard — used by the new login flow."""
    return render_template("dashboard.html")

@app.route("/inventory")
def inventory():
    return render_template("inventory.html")

@app.route("/finance")
def finance():
    return render_template("finance.html")

@app.route("/book_appointment")
def book_appointment():
    # Guard: if eligibility session vars are missing, redirect to eligibility page
    if not session.get("elig_dob") or not session.get("elig_blood_group"):
        return redirect(url_for("eligibility_page"))
    return render_template(
        "book_appointment.html",
        elig_dob=session["elig_dob"],
        elig_last_date=session.get("elig_last_date", ""),
        elig_blood_group=session["elig_blood_group"]
    )

@app.route("/api/appointment", methods=["POST"])
def api_appointment():
    d = request.get_json()

    name        = sanitize_name(d.get("name", ""))
    phone_raw   = d.get("phone", "").strip()
    dob_str     = d.get("dob", "").strip()
    blood_group = d.get("blood_group", "").strip()
    date_str    = d.get("date", "").strip()
    slot        = d.get("slot", "").strip()
    centre      = d.get("centre", "").strip()
    last_str    = d.get("last_donated", "").strip()

    # ── Required fields ──
    if not all([name, phone_raw, dob_str, blood_group, date_str, slot, centre]):
        return jsonify({"success": False, "message": "All required fields must be filled"}), 400

    # ── Phone validation: strip +91 prefix, then enforce exactly 10 digits starting 9/8/7/6 ──
    digits = re.sub(r"^\+91", "", phone_raw)
    digits = re.sub(r"\D", "", digits)          # strip any remaining non-digits
    if not re.fullmatch(r"[6987]\d{9}", digits):
        return jsonify({
            "success": False,
            "message": "Phone must be exactly 10 digits and start with 9, 8, 7, or 6"
        }), 400
    phone = "+91" + digits                       # canonical E.164 format

    # ── Parse dates ──
    try:
        dob      = datetime.strptime(dob_str, "%Y-%m-%d").date()
        appt_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"success": False, "message": "Invalid date format"}), 400

    last_donated = None
    if last_str:
        try:
            last_donated = datetime.strptime(last_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"success": False, "message": "Invalid last donation date"}), 400

        # ── Age-gate: must have been ≥ 18 at time of last donation ──
        age_at_donation = (
            last_donated.year - dob.year
            - ((last_donated.month, last_donated.day) < (dob.month, dob.day))
        )
        if age_at_donation < 18:
            return jsonify({
                "success": False,
                "message": "Ineligible: You must have been at least 18 years old "
                           "at the time of your last donation."
            }), 400

        # ── 90-day cooldown ──
        days_since = (datetime.utcnow().date() - last_donated).days
        if days_since < 90:
            return jsonify({
                "success": False,
                "message": f"Only {days_since} days since last donation — minimum gap is 90 days"
            }), 400

    appt = Appointment(
        name=name, phone=phone, dob=dob,
        blood_group=blood_group, appt_date=appt_date,
        slot=slot, centre=centre, last_donated=last_donated
    )
    db.session.add(appt)
    db.session.commit()

    print(f"[APPOINTMENT] {name} | {phone} | {blood_group} | {appt_date} | {centre}")
    return jsonify({
        "success": True,
        "message": f"Appointment confirmed for {name} on {appt_date.strftime('%d %b %Y')}",
        "appointment_id": appt.id
    })

@app.route("/admin")
@admin_required
def admin_dashboard():
    return render_template("admin.html")

@app.route("/admin-command-panel")
@admin_required
def admin_command_panel():
    """Canonical admin dashboard URL — matches the new routing spec."""
    return render_template("admin.html")

@app.route("/rider")
def rider_dashboard():
    return render_template("rider.html")

# ─────────────────────────────────────────
# AUTH API
# ─────────────────────────────────────────

@app.route("/api/signup", methods=["POST"])
def api_signup():
    d = request.get_json()
    first_name  = sanitize_name(d.get("first_name",""))
    middle_name = sanitize_name(d.get("middle_name",""))
    last_name   = sanitize_name(d.get("last_name",""))
    username    = d.get("username","").strip()
    email       = d.get("email","").strip()
    phone       = d.get("phone","").strip()
    password    = d.get("password","")
    confirm     = d.get("confirm","")
    blood_group = d.get("blood_group","")
    city        = d.get("city","").strip()

    # Required fields
    if not all([first_name, last_name, username, email, phone, password, confirm, city]):
        return jsonify({"success": False, "message": "All required fields must be filled"}), 400

    # Username: no spaces
    if not valid_username(username):
        return jsonify({"success": False, "message": "Username must be at least 3 characters and contain no spaces"}), 400

    # Phone: strict 10-digit, starts with 9/8/7
    if not valid_phone(phone):
        return jsonify({"success": False, "message": "Phone must be +91 followed by 10 digits starting with 9, 8, 7, or 6"}), 400

    if password != confirm:
        return jsonify({"success": False, "message": "Passwords do not match"}), 400
    err = valid_password(password)
    if err:
        return jsonify({"success": False, "message": err}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"success": False, "message": "Username already taken"}), 409
    if User.query.filter_by(email=email).first():
        return jsonify({"success": False, "message": "Email already registered"}), 409

    full_name = f"{first_name} {middle_name} {last_name}".replace("  ", " ").strip()
    hashed = bcrypt.generate_password_hash(password).decode("utf-8")
    user = User(username=username, email=email, phone=phone,
                first_name=first_name, middle_name=middle_name, last_name=last_name,
                city=city, password=hashed, role="user", is_admin=False)
    db.session.add(user)

    # Register as donor — city from signup is the anchor
    if blood_group and city:
        db.session.add(Donor(name=full_name, blood_group=blood_group,
                             city=city, phone=phone, email=email,
                             last_donated=None, is_available=True))

    # ── First-run logic: if no admin exists, promote this user to Super Admin ──
    if not User.query.filter_by(is_admin=True).first():
        user.role     = "admin"
        user.is_admin = True
        db.session.commit()
        return jsonify({
            "success": True,
            "message": f"Welcome, {first_name}! No admin existed — you have been made Super Admin. "
                       f"Please log in via /admin-login."
        })

    db.session.commit()
    return jsonify({"success": True, "message": f"Welcome, {first_name}! Redirecting to login..."})

@app.route("/api/login", methods=["POST"])
def api_login():
    d = request.get_json()
    username = d.get("username","").strip()
    password = d.get("password","")

    err = valid_password(password)
    if err:
        return jsonify({"success": False, "message": err}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not bcrypt.check_password_hash(user.password, password):
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    # ── Admin users must use the dedicated /admin-entry portal ──
    if user.role == "admin" or user.is_admin:
        return jsonify({
            "success": False,
            "message": "Admin accounts must log in via the Admin Portal.",
            "redirect_to": "/admin-entry"
        }), 403

    # ── Session is non-permanent — expires when browser closes ──
    session.permanent   = False
    session["user_id"]  = user.id
    session["username"] = user.username
    session["role"]     = user.role
    session["is_admin"] = False
    session["city"]     = user.city or ""

    # Track login count to distinguish first vs returning logins
    user.login_count = (user.login_count or 0) + 1
    is_first_login   = user.login_count == 1
    db.session.commit()

    # Fetch linked donor record for user-specific data
    donor = Donor.query.filter_by(email=user.email).first()

    first_name = user.first_name or user.username

    return jsonify({
        "success":        True,
        "message":        f"Hi {first_name}! Redirecting..." if is_first_login
                          else f"Welcome back, {first_name}! Redirecting...",
        "role":           user.role,
        "redirect_to":    "/user-dashboard",
        "is_first_login": is_first_login,
        "user": {
            "id":             user.id,
            "username":       user.username,
            "full_name":      f"{user.first_name or ''} {user.last_name or ''}".strip(),
            "first_name":     user.first_name or user.username,
            "email":          user.email,
            "phone":          user.phone,
            "city":           user.city,
            "role":           user.role,
            "is_first_login": is_first_login,
            "donor_id":       donor.id if donor else None,
            "blood_group":    donor.blood_group if donor else None,
            "last_donated":   str(donor.last_donated) if donor and donor.last_donated else None,
            "is_available":   donor.is_available if donor else None,
            "donations":      donor.donations if donor else 0
        }
    })

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/me")
def api_me():
    """
    Returns the currently logged-in user's full profile from SQL.
    Used by the frontend to auto-restore session state without re-login.
    Returns 401 if no active session.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"authenticated": False}), 401

    user = User.query.get(user_id)
    if not user:
        session.clear()
        return jsonify({"authenticated": False}), 401

    donor = Donor.query.filter_by(email=user.email).first()

    return jsonify({
        "authenticated": True,
        "user": {
            "id":             user.id,
            "username":       user.username,
            "full_name":      f"{user.first_name or ''} {user.last_name or ''}".strip(),
            "first_name":     user.first_name or user.username,
            "email":          user.email,
            "phone":          user.phone,
            "city":           user.city,
            "role":           user.role,
            "is_first_login": (user.login_count or 0) == 1,
            "donor_id":       donor.id if donor else None,
            "blood_group":    donor.blood_group if donor else None,
            "last_donated":   str(donor.last_donated) if donor and donor.last_donated else None,
            "is_available":   donor.is_available if donor else None,
            "donations":      donor.donations if donor else 0
        }
    })

# ─────────────────────────────────────────
# PASSWORD RECOVERY API
# ─────────────────────────────────────────

@app.route("/forgot-password")
def forgot_password_page():
    return render_template("forgot_password.html")

@app.route("/api/otp/send", methods=["POST"])
def send_otp():
    """Generate a 6-digit OTP, store it with timestamp, return it (simulated send)."""
    d          = request.get_json()
    method     = d.get("method", "")       # "email" | "phone"
    identifier = d.get("identifier", "").strip()

    if method not in ("email", "phone"):
        return jsonify({"success": False, "message": "Invalid recovery method"}), 400
    if not identifier:
        return jsonify({"success": False, "message": "Please provide your email or phone"}), 400

    # Verify the identifier exists in the database
    if method == "email":
        user = User.query.filter_by(email=identifier).first()
    else:
        # Accept with or without +91 prefix
        digits = re.sub(r"^\+91", "", identifier)
        user = User.query.filter(
            (User.phone == identifier) | (User.phone == "+91" + digits)
        ).first()

    if not user:
        return jsonify({"success": False, "message": f"No account found with that {method}"}), 404

    # Invalidate any previous unused OTPs for this identifier
    OTPRecord.query.filter_by(identifier=identifier, used=False).update({"used": True})

    otp_code = "".join(random.choices(string.digits, k=6))
    record   = OTPRecord(identifier=identifier, method=method, otp_code=otp_code)
    db.session.add(record)
    db.session.commit()

    # In production: send via SMS/email. Here we return it for demo purposes.
    return jsonify({
        "success": True,
        "message": f"OTP sent to your {method}. Valid for 60 seconds.",
        "otp_demo": otp_code,          # remove in production
        "expires_in": 60,
        "record_id": record.id
    })

@app.route("/api/otp/verify", methods=["POST"])
def verify_otp():
    d          = request.get_json()
    identifier = d.get("identifier", "").strip()
    otp_code   = d.get("otp", "").strip()

    record = OTPRecord.query.filter_by(
        identifier=identifier, otp_code=otp_code, used=False
    ).order_by(OTPRecord.created_at.desc()).first()

    if not record:
        return jsonify({"success": False, "message": "Invalid OTP. Please try again."}), 400
    if record.is_expired:
        record.used = True
        db.session.commit()
        return jsonify({"success": False, "message": "OTP has expired. Please request a new one."}), 400

    # Mark OTP as used and issue a reset token stored in session
    record.used = True
    db.session.commit()
    session["reset_identifier"] = identifier
    session["reset_verified"]   = True
    return jsonify({"success": True, "message": "OTP verified. You may now reset your password."})

@app.route("/api/password/reset", methods=["POST"])
def reset_password():
    if not session.get("reset_verified"):
        return jsonify({"success": False, "message": "Session expired. Please restart recovery."}), 403

    d            = request.get_json()
    new_password = d.get("password", "")
    confirm      = d.get("confirm", "")
    identifier   = session.get("reset_identifier", "")

    if new_password != confirm:
        return jsonify({"success": False, "message": "Passwords do not match"}), 400
    err = valid_password(new_password)
    if err:
        return jsonify({"success": False, "message": err}), 400

    # Find user by email or phone
    user = User.query.filter_by(email=identifier).first()
    if not user:
        digits = re.sub(r"^\+91", "", identifier)
        user = User.query.filter(
            (User.phone == identifier) | (User.phone == "+91" + digits)
        ).first()

    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    user.password = bcrypt.generate_password_hash(new_password).decode("utf-8")
    db.session.commit()
    session.pop("reset_identifier", None)
    session.pop("reset_verified", None)
    return jsonify({"success": True, "message": "Password reset successfully! You can now log in."})

# ─────────────────────────────────────────
# DASHBOARD API
# ─────────────────────────────────────────

@app.route("/api/dashboard/stats")
def dashboard_stats():
    try:
        total_units  = db.session.query(db.func.sum(BloodInventory.units)).scalar() or 0
    except Exception:
        total_units  = 0
    try:
        total_donors = Donor.query.count()
        avail_donors = Donor.query.filter_by(is_available=True).count()
    except Exception:
        total_donors = 0
        avail_donors = 0
    try:
        active_emerg = EmergencyRequest.query.filter_by(status="pending").count()
    except Exception:
        active_emerg = 0
    try:
        total_txn   = Transaction.query.count()
        pending_txn = Transaction.query.filter_by(status="pending").count()
        revenue     = db.session.query(
            db.func.sum(Transaction.total)
        ).filter(Transaction.status == "paid").scalar() or 0
    except Exception:
        total_txn   = 0
        pending_txn = 0
        revenue     = 0
    return jsonify({
        "total_units":        total_units,
        "total_donors":       total_donors,
        "available_donors":   avail_donors,
        "active_emergencies": active_emerg,
        "total_transactions": total_txn,
        "pending_payments":   pending_txn,
        "total_revenue":      int(round(float(revenue)))
    })

@app.route("/api/dashboard/inventory_preview")
def dashboard_inventory_preview():
    """Mini blood-group gauges for the dashboard command center."""
    items = BloodInventory.query.order_by(BloodInventory.blood_group).all()
    max_units = max((i.units for i in items), default=1)
    return jsonify([{
        "blood_group": i.blood_group,
        "units": i.units,
        "cost_per_bag": i.cost_per_bag,
        "status": "critical" if i.units < 5 else "low" if i.units < 10 else "ok",
        "pct": round((i.units / max_units) * 100) if max_units else 0
    } for i in items])

@app.route("/api/dashboard/recent_orders")
def dashboard_recent_orders():
    """Last 5 transactions for the dashboard Recent Orders widget.
    Returns [] when no transactions exist so the widget stays blank."""
    txns = Transaction.query.order_by(Transaction.created_at.desc()).limit(5).all()
    return jsonify([{
        "receipt_no": t.receipt_no,
        "patient_name": t.patient_name,
        "blood_group": t.blood_group,
        "bags": t.bags,
        "total": t.total,
        "status": t.status,
        "date": t.created_at.strftime("%d %b %Y")
    } for t in txns])

# ─────────────────────────────────────────
# INVENTORY API
# ─────────────────────────────────────────

@app.route("/api/inventory")
def get_inventory():
    """Admin-only: returns full stock details, optionally filtered by city."""
    if not session.get("is_admin"):
        return jsonify({"success": False, "message": "Admin access required"}), 403

    city = request.args.get("city", "")
    q = BloodInventory.query
    if city:
        q = q.filter(BloodInventory.city.ilike(city))
    items = q.order_by(BloodInventory.city, BloodInventory.blood_group).all()
    return jsonify([{
        "id": i.id, "blood_group": i.blood_group, "city": i.city,
        "bank_name": i.bank_name, "units": i.units, "cost_per_bag": i.cost_per_bag,
        "status": "critical" if i.units < 5 else "low" if i.units < 10 else "ok"
    } for i in items])

@app.route("/api/inventory/city/<city_name>")
def get_inventory_by_city(city_name):
    """Returns inventory for a specific city.
    Both admin and regular users receive unit counts so the UI can render correctly.
    Admin users additionally receive cost_per_bag and stock-adjust actions.
    """
    is_admin = session.get("is_admin", False)

    ALL_BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]
    items = BloodInventory.query.filter(
        BloodInventory.city.ilike(city_name)
    ).order_by(BloodInventory.blood_group).all()

    item_map  = {i.blood_group: i for i in items}
    bank_name = items[0].bank_name if items else f"{city_name} Blood Bank"
    city_label = items[0].city    if items else city_name

    result = []
    for bg in ALL_BLOOD_GROUPS:
        i     = item_map.get(bg)
        units = int(i.units) if i and i.units is not None else 0
        cost  = float(i.cost_per_bag) if i and i.cost_per_bag is not None else 1500.0
        status = "critical" if units < 5 else "low" if units < 10 else "ok"
        row = {
            "blood_group": bg,
            "city":        city_label,
            "bank_name":   bank_name,
            "units":       units,          # always present so the UI never defaults to 0
            "status":      status,
            "available":   units > 0,
        }
        if is_admin:
            row["cost_per_bag"] = cost
        result.append(row)
    return jsonify(result)

@app.route("/api/inventory/public")
def get_inventory_public():
    """Public view: availability status only, no unit counts."""
    city = request.args.get("city", "")
    q = BloodInventory.query
    if city:
        q = q.filter(BloodInventory.city.ilike(city))
    items = q.all()
    return jsonify([{
        "blood_group": i.blood_group, "city": i.city,
        "bank_name": i.bank_name,
        "status": "critical" if i.units < 5 else "low" if i.units < 10 else "ok",
        "available": i.units > 0
    } for i in items])

@app.route("/api/inventory/update", methods=["POST"])
def update_inventory():
    """Admin-only: adjust stock for a specific blood group + city."""
    if not session.get("is_admin"):
        return jsonify({"success": False, "message": "Admin access required"}), 403
    d = request.get_json()
    city = d.get("city", "")
    item = BloodInventory.query.filter(
        BloodInventory.blood_group == d["blood_group"],
        BloodInventory.city.ilike(city)
    ).first()
    if not item:
        return jsonify({"success": False, "message": "Blood group / city not found"}), 404
    item.units = max(0, item.units + int(d.get("delta", 0)))
    item.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "units": item.units})

@app.route("/api/inventory/stats")
def inventory_stats():
    """Live stock totals per blood group across all cities — used for real-time refresh."""
    city = request.args.get("city", "")
    q = BloodInventory.query
    if city:
        q = q.filter(BloodInventory.city.ilike(city))
    items = q.order_by(BloodInventory.city, BloodInventory.blood_group).all()
    total_units = sum(i.units for i in items if i.units is not None)
    return jsonify({
        "total_units": total_units,
        "items": [{
            "blood_group":  i.blood_group,
            "city":         i.city,
            "bank_name":    i.bank_name,
            "units":        int(i.units) if i.units is not None else 0,
            "cost_per_bag": float(i.cost_per_bag) if i.cost_per_bag is not None else 1500.0,
            "status": "critical" if (i.units or 0) < 5 else "low" if (i.units or 0) < 10 else "ok",
            "updated_at":   i.updated_at.strftime("%d %b %Y %H:%M") if i.updated_at else ""
        } for i in items]
    })

# ─────────────────────────────────────────
# DONORS API
# ─────────────────────────────────────────

@app.route("/api/donors")
def get_donors():
    donors = Donor.query.all()
    return jsonify([{
        "id": d.id, "name": d.name, "blood_group": d.blood_group,
        "city": d.city, "phone": d.phone, "email": d.email,
        "last_donated": str(d.last_donated) if d.last_donated else None,
        "is_available": d.is_available, "donations": d.donations
    } for d in donors])

@app.route("/api/donors/search")
def search_donors():
    bg   = request.args.get("blood_group","")
    city = request.args.get("city","")
    q = Donor.query
    if bg:   q = q.filter_by(blood_group=bg)
    if city: q = q.filter(Donor.city.ilike(f"%{city}%"))
    donors = q.all()
    return jsonify([{
        "id": d.id, "name": d.name, "blood_group": d.blood_group,
        "city": d.city, "phone": d.phone, "is_available": d.is_available,
        "donations": d.donations
    } for d in donors])

# ─────────────────────────────────────────
# EMERGENCY API
# ─────────────────────────────────────────

@app.route("/api/emergency/request", methods=["POST"])
def emergency_request():
    d            = request.get_json()
    bg           = d.get("blood_group", "")
    loc          = d.get("location", "")
    address      = d.get("address", "").strip()
    units        = int(d.get("units", 1))
    patient_name = d.get("patient_name", "").strip()
    receiver_phone_raw = d.get("receiver_phone", "").strip()

    # ── Basic validation ──
    if not bg or not loc:
        return jsonify({"success": False, "message": "Blood group and location required"}), 400
    if not address:
        return jsonify({"success": False, "message": "Detailed address is required"}), 400

    # ── Patient name: alphabets and spaces only ──
    if not patient_name:
        return jsonify({"success": False, "message": "Patient name is required"}), 400
    if not re.fullmatch(r"[A-Za-z\s]{2,}", patient_name):
        return jsonify({
            "success": False,
            "message": "Patient name must contain letters only — no numbers or special characters"
        }), 400
    patient_name = patient_name.title()   # auto-capitalize

    # ── Phone: exactly 10 digits, starts with 9/8/7/6, auto-prefix +91 ──
    if not receiver_phone_raw:
        return jsonify({"success": False, "message": "Patient phone number is required"}), 400
    phone_digits = re.sub(r"^\+91", "", receiver_phone_raw)
    phone_digits = re.sub(r"\D", "", phone_digits)
    if not re.fullmatch(r"[6987]\d{9}", phone_digits):
        return jsonify({
            "success": False,
            "message": "Phone must be exactly 10 digits and start with 9, 8, 7, or 6"
        }), 400
    receiver_phone = "+91" + phone_digits   # canonical E.164

    if units > 15:
        return jsonify({"success": False, "message": "Maximum 15 units per emergency request"}), 400
    units = max(1, units)

    # ── STEP 1: Inventory Check (city-specific) ──
    inv = BloodInventory.query.filter(
        BloodInventory.blood_group == bg,
        BloodInventory.city.ilike(loc)
    ).first()

    stock_available  = inv.units if inv else 0
    units_from_stock = min(stock_available, units)
    units_needed_from_donor = units - units_from_stock

    # ── STEP 1b: Multi-bank fallback — find nearby cities with stock ──
    # If local stock is insufficient, check all other cities and rank by distance
    nearby_options = []
    if units_from_stock < units:
        all_inv = BloodInventory.query.filter(
            BloodInventory.blood_group == bg,
            BloodInventory.units > 0
        ).all()
        for alt_inv in all_inv:
            alt_city = alt_inv.city
            if alt_city.lower() == loc.lower():
                continue   # already checked
            alt_info = calculate_delivery_from_city(alt_city, loc)
            nearby_options.append({
                "city":         alt_city,
                "bank_name":    alt_info["bank_name"],
                "units":        alt_inv.units,
                "distance_km":  alt_info["distance_km"],
                "eta_minutes":  alt_info["eta_minutes"],
                "delivery_fee": alt_info["delivery_fee"],
                "can_cover":    alt_inv.units >= units,
            })
        # Sort by distance
        nearby_options.sort(key=lambda x: x["distance_km"])

    # ── STEP 2: Donor Search for shortfall (location-locked) ──
    compatible = {"O-":["O-"],"O+":["O-","O+"],"A-":["O-","A-"],
                  "A+":["O-","O+","A-","A+"],"B-":["O-","B-"],
                  "B+":["O-","O+","B-","B+"],"AB-":["O-","A-","B-","AB-"],
                  "AB+":["O-","O+","A-","A+","B-","B+","AB-","AB+"]}
    compatible_groups = compatible.get(bg, [bg])

    donors_needed = units_needed_from_donor > 0
    matched_donors = []
    if donors_needed:
        matched_donors = (Donor.query
                          .filter(Donor.blood_group.in_(compatible_groups),
                                  Donor.is_available == True,
                                  Donor.city.ilike(loc))
                          .order_by(Donor.donations.desc())
                          .all())

    exact  = [d for d in matched_donors if d.blood_group == bg]
    others = [d for d in matched_donors if d.blood_group != bg]
    ranked = exact + others
    primary = ranked[0] if ranked else None

    # ── STEP 3: Determine fulfillment case ──
    # Case A: full stock covers request
    # Case B: partial stock + donor covers shortfall
    # Case C: no stock, donor covers all
    # Case D: cannot fulfill
    if units_from_stock == units:
        fulfillment = "stock"          # Case A
        can_fulfill = True
    elif units_from_stock > 0 and primary:
        fulfillment = "mixed"          # Case B
        can_fulfill = True
    elif units_from_stock == 0 and primary:
        fulfillment = "donor"          # Case C
        can_fulfill = True
    else:
        fulfillment = "none"           # Case D
        can_fulfill = False

    req_status = "fulfilled" if can_fulfill else "pending"

    # ── IF blood not available locally but alternatives exist, DON'T create request yet ──
    # Instead, return nearby options for user to choose
    if not can_fulfill and nearby_options:
        return jsonify({
            "success": True,
            "blood_unavailable": True,
            "message": f"{bg} not available in {loc}",
            "nearby_options": nearby_options[:3],
            "patient_name": patient_name,
            "blood_group": bg,
            "units_requested": units,
            "location": loc,
            "address": address,
            "receiver_phone": receiver_phone
        })

    # ── STEP 4: Deduct inventory ──
    if units_from_stock > 0 and inv:
        inv.units = max(0, inv.units - units_from_stock)

    # ── STEP 5: Create request record ──
    req = EmergencyRequest(
        blood_group=bg, location=loc, address=address,
        units=units, patient_name=patient_name,
        receiver_phone=receiver_phone,
        status=req_status, fulfillment=fulfillment,
        units_from_stock=units_from_stock,
        units_from_donor=units_needed_from_donor if primary else 0,
        donor_name=primary.name if primary else None
    )
    db.session.add(req)
    db.session.commit()

    # ── STEP 6: Pre-calculate finance values — transaction created only when
    #            user generates the receipt on the Finance page ──
    receipt_no = None
    finance_prefill = None
    if can_fulfill:
        price    = BLOOD_PRICES.get(bg, 1500)
        delivery = delivery_fee_for_bags(units)
        total    = (units * price) + delivery
        finance_prefill = {
            "patient": patient_name,
            "blood":   bg,
            "bags":    units,
            "total":   total
        }

    donors_list = [{
        "id": d.id, "name": d.name, "blood_group": d.blood_group,
        "city": d.city, "phone": d.phone, "donations": d.donations,
        "exact_match": d.blood_group == bg
    } for d in ranked]

    # Build human-readable pipeline message
    if fulfillment == "stock":
        pipeline_msg = f"✅ All {units} unit(s) fulfilled from local inventory."
    elif fulfillment == "mixed":
        pipeline_msg = (f"⚡ {units_from_stock} unit(s) from inventory + "
                        f"{units_needed_from_donor} unit(s) from donor {primary.name}.")
    elif fulfillment == "donor":
        pipeline_msg = f"👤 All {units} unit(s) to be fulfilled by donor {primary.name}."
    else:
        pipeline_msg = f"⏳ Insufficient stock and no available donor in {loc}. Request queued."

    return jsonify({
        "success":          True,
        "request_id":       req.id,
        "status":           req_status,
        "fulfillment":      fulfillment,
        "can_fulfill":      can_fulfill,
        "units_requested":  units,
        "units_from_stock": units_from_stock,
        "units_from_donor": units_needed_from_donor if primary else 0,
        "stock_available":  stock_available,
        "stock_remaining":  inv.units if inv else 0,
        "donors":           donors_list,
        "donor":            {"id": primary.id, "name": primary.name,
                             "blood_group": primary.blood_group,
                             "city": primary.city, "phone": primary.phone,
                             "donations": primary.donations} if primary else None,
        "finance_prefill":  finance_prefill,
        "patient_name":     patient_name,
        "blood_group":      bg,
        "bags":             units,
        "pipeline_msg":     pipeline_msg,
        "message":          pipeline_msg,
        "nearby_options":   nearby_options[:3],   # top 3 nearest alternatives
    })

@app.route("/api/emergency/confirm-alternative", methods=["POST"])
def confirm_alternative():
    """User confirms they want blood from alternative city despite longer delivery"""
    d = request.get_json()
    patient_name = d.get("patient_name", "").strip()
    bg = d.get("blood_group", "")
    units = int(d.get("units", 1))
    location = d.get("location", "")  # target location
    address = d.get("address", "").strip()
    receiver_phone = d.get("receiver_phone", "")
    source_city = d.get("source_city", "")  # city to get blood FROM
    
    if not all([patient_name, bg, location, source_city]):
        return jsonify({"success": False, "message": "Missing required fields"}), 400
    
    # ── Create request with alternative city ──
    req = EmergencyRequest(
        blood_group=bg, location=location, address=address,
        units=units, patient_name=patient_name,
        receiver_phone=receiver_phone,
        status="pending", fulfillment="alternative_city",
        units_from_stock=units,
        source_city=source_city
    )
    db.session.add(req)
    db.session.commit()
    
    # ── Calculate costs with source city ──
    alt_info = calculate_delivery_from_city(source_city, location)
    price = BLOOD_PRICES.get(bg, 1500)
    delivery = alt_info["delivery_fee"]
    total = (units * price) + delivery
    
    # ── Create receipt ──
    receipt_no = gen_receipt()
    
    # ── Assign available rider from the city ──
    rider = Rider.query.filter_by(city=location, is_free=True).first()
    rider_name = rider.name if rider else "Available"
    rider_phone = rider.phone if rider else "Pending Assignment"
    rider_id = rider.id if rider else None
    
    txn = Transaction(
        receipt_no=receipt_no,
        patient_name=patient_name,
        blood_group=bg,
        bags=units,
        cost_per_bag=price,
        delivery_fee=delivery,
        total=total,
        status="pending",
        fraud_flag=False,
        rider_id=rider_id,
        rider_name=rider_name,
        rider_phone=rider_phone,
        user_id=session.get("user_id")  # Track who created this transaction
    )
    db.session.add(txn)
    req.receipt_no = receipt_no
    if rider:
        rider.is_free = False  # mark rider as busy
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": f"Request confirmed from {source_city}. Delivery in ~{alt_info['eta_minutes']} mins.",
        "receipt_no": receipt_no,
        "request_id": req.id,
        "total": total,
        "eta_minutes": alt_info["eta_minutes"],
        "source_city": source_city
    })

@app.route("/api/emergency/list")
def emergency_list():
    reqs = EmergencyRequest.query.order_by(EmergencyRequest.requested_at.desc()).limit(20).all()
    # Always return a list — empty [] when no records exist so the frontend
    # renders a blank "Recent Emergency Requests" section instead of an error
    return jsonify([{
        "id": r.id, "blood_group": r.blood_group, "location": r.location,
        "units": r.units, "status": r.status, "donor_name": r.donor_name,
        "requested_at": r.requested_at.strftime("%d %b %Y %H:%M")
    } for r in reqs])

# ─────────────────────────────────────────
# FINANCE API
# ─────────────────────────────────────────

@app.route("/api/finance/calculate", methods=["POST"])
def calculate():
    d = request.get_json()
    bg   = d.get("blood_group","A+")
    bags = int(d.get("bags", 1))

    # ── 15-bag cap ──
    bags = min(bags, 15)

    price    = BLOOD_PRICES.get(bg, 1500)
    delivery = delivery_fee_for_bags(bags)
    subtotal = bags * 50          # ₹50 per bag (processing fee component)
    total    = (bags * price) + delivery
    flags    = fraud_check(bags, total, bg)

    return jsonify({
        "blood_group": bg, "bags": bags,
        "cost_per_bag": price,
        "processing_fee": subtotal,
        "delivery_fee": delivery,
        "total": total,
        "fraud_flags": flags
    })

@app.route("/api/finance/receipt", methods=["POST"])
def generate_receipt():
    d = request.get_json()
    bg      = d.get("blood_group","A+")
    bags    = int(d.get("bags", 1))
    patient = d.get("patient_name","").strip()
    city    = d.get("city","").strip()

    # ── Mandatory patient name ──
    if not patient:
        return jsonify({"success": False, "message": "Patient name is required"}), 400

    # ── 15-bag cap ──
    bags = min(bags, 15)

    price    = BLOOD_PRICES.get(bg, 1500)
    delivery = delivery_fee_for_bags(bags)
    total    = (bags * price) + delivery
    flags    = fraud_check(bags, total, bg)
    receipt_no = gen_receipt()

    # ── Immediate inventory deduction (city-aware) ──
    inv_item = None
    if city:
        inv_item = BloodInventory.query.filter(
            BloodInventory.blood_group == bg,
            BloodInventory.city.ilike(city)
        ).first()
    if not inv_item:
        # Fallback: deduct from any city that has stock
        inv_item = BloodInventory.query.filter(
            BloodInventory.blood_group == bg,
            BloodInventory.units >= bags
        ).order_by(BloodInventory.units.desc()).first()

    deducted_from = None
    if inv_item and inv_item.units >= bags:
        inv_item.units = max(0, inv_item.units - bags)
        inv_item.updated_at = datetime.utcnow()
        deducted_from = inv_item.city

    # ── Log transaction as "pending" — receiver pays via Payment Portal ──
    # Auto-assign nearest available rider
    rider_for_txn = Rider.query.filter_by(city=city, is_free=True).first() if city else None
    if not rider_for_txn:
        rider_for_txn = Rider.query.filter_by(city=city).first() if city else None
    if not rider_for_txn:
        rider_for_txn = Rider.query.filter_by(is_free=True).first()
    if not rider_for_txn:
        rider_for_txn = Rider.query.first()

    txn = Transaction(
        receipt_no=receipt_no,
        patient_name=patient,
        blood_group=bg,
        bags=bags,
        cost_per_bag=price,
        delivery_fee=delivery,
        total=total,
        fraud_flag=bool(flags),
        status="pending",
        rider_name  = rider_for_txn.name  if rider_for_txn else "—",
        rider_phone = rider_for_txn.phone if rider_for_txn else "—",
        user_id=session.get("user_id")  # Track who created this transaction
    )
    db.session.add(txn)
    db.session.commit()

    print(f"[RECEIPT] {receipt_no} | {patient} | {bg} x{bags} | ₹{total} | "
          f"Deducted from: {deducted_from or 'N/A'} | Status: pending")

    return jsonify({
        "success": True,
        "redirect_to_payment": True,
        "payment_url": f"/payment?receipt={receipt_no}",
        "receipt": {
            "receipt_no":   receipt_no,
            "patient_name": patient,
            "blood_group":  bg,
            "bags":         bags,
            "cost_per_bag": price,
            "delivery_fee": delivery,
            "total":        total,
            "status":       txn.status,
            "fraud_flags":  flags,
            "city":         city,
            "deducted_from": deducted_from,
            "date":         txn.created_at.strftime("%d %b %Y %H:%M")
        }
    })

@app.route("/api/finance/transactions")
def transactions():
    txns = Transaction.query.order_by(Transaction.created_at.desc()).limit(20).all()
    return jsonify([{
        "id": t.id, "receipt_no": t.receipt_no, "patient_name": t.patient_name,
        "blood_group": t.blood_group, "bags": t.bags, "total": t.total,
        "status": t.status, "fraud_flag": t.fraud_flag,
        "date": t.created_at.strftime("%d %b %Y")
    } for t in txns])

# ─────────────────────────────────────────
# RECEIVER PAYMENT PORTAL
# ─────────────────────────────────────────

@app.route("/payment")
def payment_portal():
    # Pass receipt_no from URL param into template so Jinja can pre-seed it
    receipt_no = request.args.get("receipt", "")
    return render_template("payment.html", receipt_no=receipt_no)

@app.route("/api/payment/bill/<receipt_no>")
def get_bill(receipt_no):
    # Try exact match first, then case-insensitive
    txn = Transaction.query.filter_by(receipt_no=receipt_no).first()
    if not txn:
        txn = Transaction.query.filter(Transaction.receipt_no.ilike(receipt_no)).first()
    if not txn:
        return jsonify({"success": False, "message": "Failed to load a bill. Please try again."}), 404
    
    # Check if this bill belongs to the current user
    current_user_id = session.get("user_id")
    
    # AUTO-ASSIGN: If transaction has no owner and user is logged in, assign it to them
    if txn.user_id is None and current_user_id:
        txn.user_id = current_user_id
        db.session.commit()
        print(f"[PAYMENT] Auto-assigned transaction {receipt_no} to user {current_user_id}")
    
    # STRICT OWNERSHIP CHECK
    is_mine = False
    if current_user_id and txn.user_id == current_user_id:
        is_mine = True
        print(f"[PAYMENT] Transaction {receipt_no} belongs to user {current_user_id}")
    elif txn.user_id is None:
        # Still no owner after auto-assign attempt
        print(f"[PAYMENT] WARNING: Transaction {receipt_no} has no owner (user not logged in)")
    else:
        print(f"[PAYMENT] Transaction {receipt_no} belongs to user {txn.user_id}, current user is {current_user_id}")
    
    # Get associated delivery request and rider info
    rider_name = txn.rider_name or "—"
    rider_phone = txn.rider_phone or "—"
    
    # If transaction doesn't have rider info, try linking via DeliveryRequest receipt
    if rider_name == "—":
        delivery = DeliveryRequest.query.filter_by(receipt_no=receipt_no).first()
        if delivery:
            rider = Rider.query.filter_by(city=delivery.location, is_free=False).first()
            if not rider:
                rider = Rider.query.filter_by(city=delivery.location).first()
            if rider:
                rider_name  = rider.name
                rider_phone = rider.phone
    
    return jsonify({
        "success": True,
        "bill": {
            "id": txn.id,
            "receipt_no": txn.receipt_no,
            "patient_name": txn.patient_name,
            "blood_group": txn.blood_group,
            "bags": txn.bags,
            "cost_per_bag": txn.cost_per_bag,
            "delivery_fee": txn.delivery_fee,
            "total": txn.total,
            "status": txn.status,
            "fraud_flag": txn.fraud_flag,
            "date": txn.created_at.strftime("%d %b %Y %H:%M"),
            "rider_name": rider_name,
            "rider_phone": rider_phone,
            "is_mine": is_mine,  # Only true if user_id matches exactly
            "no_owner": False  # Always false now (auto-assigned)
        }
    })

@app.route("/api/payment/pay", methods=["POST"])
def pay_bill():
    d = request.get_json()
    receipt_no = d.get("receipt_no", "")
    txn = Transaction.query.filter_by(receipt_no=receipt_no).first()
    if not txn:
        return jsonify({"success": False, "message": "Receipt not found"}), 404
    if txn.status == "paid":
        return jsonify({"success": False, "message": "This bill has already been paid"}), 400

    # ── AUTHORIZATION CHECK ──
    current_user_id = session.get("user_id")
    if not current_user_id:
        return jsonify({"success": False, "message": "You must be logged in to make a payment"}), 401
    
    # AUTO-ASSIGN: If transaction has no owner, assign it to current user
    if txn.user_id is None:
        txn.user_id = current_user_id
        print(f"[PAYMENT] Auto-assigned transaction {receipt_no} to user {current_user_id}")
    
    # Check if current user is the owner
    if txn.user_id != current_user_id:
        return jsonify({
            "success": False, 
            "message": "You can only pay for your own transactions. This payment belongs to another user."
        }), 403

    # ── SQL UPDATE: pending → paid ──
    txn.status     = "paid"
    txn.fraud_flag = False

    db.session.commit()

    print(f"[PAYMENT] {receipt_no} | {txn.patient_name} | {txn.blood_group} x{txn.bags} "
          f"| ₹{txn.total:,.0f} | STATUS → PAID | USER_ID: {current_user_id}")

    # Return the full updated transaction so the UI can sync all views at once
    return jsonify({
        "success":     True,
        "message":     f"Payment of ₹{txn.total:,.0f} received successfully!",
        "receipt_no":  txn.receipt_no,
        "total":       txn.total,
        "transaction": {
            "id":           txn.id,
            "receipt_no":   txn.receipt_no,
            "patient_name": txn.patient_name,
            "blood_group":  txn.blood_group,
            "bags":         txn.bags,
            "total":        txn.total,
            "status":       txn.status,          # "paid"
            "date":         txn.created_at.strftime("%d %b %Y")
        }
    })

@app.route("/api/payment/pending")
def pending_bills():
    """Return all unpaid / flagged transactions for the receiver portal."""
    current_user_id = session.get("user_id")
    
    txns = Transaction.query.filter(
        Transaction.status.in_(["pending", "flagged"])
    ).order_by(Transaction.created_at.desc()).all()
    
    return jsonify([{
        "id": t.id, 
        "receipt_no": t.receipt_no, 
        "patient_name": t.patient_name,
        "blood_group": t.blood_group, 
        "bags": t.bags, 
        "total": t.total,
        "status": t.status, 
        "date": t.created_at.strftime("%d %b %Y"),
        # STRICT: Only true if user_id matches exactly
        "is_mine": t.user_id == current_user_id if current_user_id else False,
        "no_owner": t.user_id is None  # Flag for unassigned transactions
    } for t in txns])

@app.route("/api/payment/my-pending")
def my_pending_bills():
    """Return only the current user's unpaid transactions."""
    current_user_id = session.get("user_id")
    if not current_user_id:
        return jsonify([])
    
    txns = Transaction.query.filter(
        Transaction.user_id == current_user_id,
        Transaction.status.in_(["pending", "flagged"])
    ).order_by(Transaction.created_at.desc()).all()
    
    return jsonify([{
        "id": t.id, 
        "receipt_no": t.receipt_no, 
        "patient_name": t.patient_name,
        "blood_group": t.blood_group, 
        "bags": t.bags, 
        "total": t.total,
        "status": t.status, 
        "date": t.created_at.strftime("%d %b %Y"),
        "is_mine": True
    } for t in txns])

# ─────────────────────────────────────────
# CERTIFICATE API
# ─────────────────────────────────────────

@app.route("/api/certificate/<int:donor_id>")
def get_certificate(donor_id):
    donor = Donor.query.get_or_404(donor_id)

    # ── Certificate only available after at least one Completed donation ──
    completed = Donation.query.filter_by(donor_id=donor_id, status="Completed").first()
    if not completed:
        return jsonify({
            "success": False,
            "locked": True,
            "message": "Certificate is locked. It will be available once a donation is marked Completed by the blood bank."
        }), 403

    cert_no = "CERT-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return jsonify({
        "success": True,
        "locked": False,
        "certificate_no": cert_no,
        "donor_name": donor.name,
        "blood_group": donor.blood_group,
        "city": donor.city,
        "donations": donor.donations,
        "issued_date": datetime.utcnow().strftime("%d %b %Y"),
        "message": f"This certifies that {donor.name} has donated blood {donor.donations} time(s) and is a valued hero."
    })

@app.route("/api/donation/complete", methods=["POST"])
def complete_donation():
    """Admin endpoint to mark a donation as Completed, unlocking the certificate."""
    d = request.get_json()
    donor_id = d.get("donor_id")
    donor = Donor.query.get_or_404(donor_id)

    rec = Donation(donor_id=donor_id,
                   donated_on=datetime.utcnow().date(),
                   status="Completed",
                   notes=d.get("notes",""))
    db.session.add(rec)
    donor.donations += 1
    donor.last_donated = datetime.utcnow().date()
    # Re-evaluate availability (90-day cooldown)
    donor.is_available = False
    db.session.commit()
    return jsonify({"success": True, "message": f"Donation marked Completed for {donor.name}. Certificate unlocked."})

@app.route("/api/donation/check/<int:donor_id>")
def check_donation_status(donor_id):
    """Returns whether the donor has a Completed donation (for certificate button state)."""
    completed = Donation.query.filter_by(donor_id=donor_id, status="Completed").first()
    return jsonify({"has_completed": completed is not None})

# ─────────────────────────────────────────
# GAMIFICATION BADGES API
# ─────────────────────────────────────────

BADGES = [
    {
        "id": "life_saver",
        "name": "Life Saver",
        "tier": "bronze",
        "medal": "🥉",
        "required": 1,
        "description": "Awarded for completing your first blood donation."
    },
    {
        "id": "blood_hero",
        "name": "Blood Hero",
        "tier": "silver",
        "medal": "🥈",
        "required": 5,
        "description": "Awarded for 5 successful blood donations."
    },
    {
        "id": "guardian_angel",
        "name": "Guardian Angel",
        "tier": "gold",
        "medal": "🥇",
        "required": 10,
        "description": "Awarded for 10 or more blood donations — a true hero."
    },
]

@app.route("/profile")
def profile_page():
    return render_template("profile.html")

@app.route("/api/profile/<int:donor_id>")
def get_profile(donor_id):
    donor = Donor.query.get_or_404(donor_id)
    donations = donor.donations

    earned_badges = []
    locked_badges = []
    for b in BADGES:
        entry = {**b, "earned": donations >= b["required"]}
        if donations >= b["required"]:
            earned_badges.append(entry)
        else:
            locked_badges.append(entry)

    # Next badge to unlock
    next_badge = next((b for b in BADGES if donations < b["required"]), None)
    progress_pct = 0
    if next_badge:
        prev_req = 0
        for b in BADGES:
            if b["required"] <= donations:
                prev_req = b["required"]
        span = next_badge["required"] - prev_req
        progress_pct = min(100, round(((donations - prev_req) / span) * 100)) if span else 100
    else:
        progress_pct = 100

    return jsonify({
        "donor": {
            "id": donor.id,
            "name": donor.name,
            "blood_group": donor.blood_group,
            "city": donor.city,
            "phone": donor.phone,
            "email": donor.email,
            "donations": donations,
            "is_available": donor.is_available,
            "last_donated": str(donor.last_donated) if donor.last_donated else None
        },
        "badges": BADGES,
        "earned_badges": earned_badges,
        "locked_badges": locked_badges,
        "next_badge": next_badge,
        "progress_pct": progress_pct,
        "highest_tier": earned_badges[-1]["tier"] if earned_badges else None
    })

@app.route("/api/profile/all")
def all_profiles():
    """Return all donors with their badge status — for the profile listing."""
    donors = Donor.query.order_by(Donor.donations.desc()).all()
    result = []
    for donor in donors:
        d = donor.donations
        tier = None
        for b in reversed(BADGES):
            if d >= b["required"]:
                tier = b["tier"]
                break
        result.append({
            "id": donor.id,
            "name": donor.name,
            "blood_group": donor.blood_group,
            "city": donor.city,
            "donations": d,
            "is_available": donor.is_available,
            "badge_tier": tier,
            "badge_medal": next((b["medal"] for b in reversed(BADGES) if d >= b["required"]), "—")
        })
    return jsonify(result)

# ─────────────────────────────────────────
# HEALTH ELIGIBILITY API
# ─────────────────────────────────────────

@app.route("/api/eligibility/check", methods=["POST"])
def eligibility_check():
    d = request.get_json()
    last_donation_str = d.get("last_donation", "")   # YYYY-MM-DD or ""
    dob_str      = d.get("dob", "")                  # YYYY-MM-DD — required for age-gate
    age          = int(d.get("age", 0))
    weight_kg    = float(d.get("weight", 0))
    hemoglobin   = float(d.get("hemoglobin", 0))
    bp_systolic  = int(d.get("bp_systolic", 0))
    bp_diastolic = int(d.get("bp_diastolic", 0))
    recent_illness = d.get("recent_illness", False)
    recent_surgery = d.get("recent_surgery", False)
    on_medication  = d.get("on_medication", False)

    issues = []
    passed = []

    # Age check
    if age < 18 or age > 65:
        issues.append("Age must be between 18 and 65 years")
    else:
        passed.append(f"Age {age} is within eligible range")

    # Weight check
    if weight_kg < 50:
        issues.append("Minimum weight requirement is 50 kg")
    else:
        passed.append(f"Weight {weight_kg} kg meets requirement")

    # Hemoglobin check
    if hemoglobin < 12.5:
        issues.append("Hemoglobin level below 12.5 g/dL — not eligible")
    else:
        passed.append(f"Hemoglobin {hemoglobin} g/dL is acceptable")

    # Blood pressure check
    if bp_systolic and bp_diastolic:
        if bp_systolic < 90 or bp_systolic > 160 or bp_diastolic < 60 or bp_diastolic > 100:
            issues.append(f"Blood pressure {bp_systolic}/{bp_diastolic} mmHg is outside safe range")
        else:
            passed.append(f"Blood pressure {bp_systolic}/{bp_diastolic} mmHg is normal")

    # Last donation date checks
    days_since = None
    if last_donation_str:
        try:
            last = datetime.strptime(last_donation_str, "%Y-%m-%d").date()

            # ── Age-gate: donor must have been ≥ 18 at the time of that donation ──
            if dob_str:
                dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
                # Calculate exact age on the donation date
                age_at_donation = (
                    last.year - dob.year
                    - ((last.month, last.day) < (dob.month, dob.day))
                )
                if age_at_donation < 18:
                    issues.append(
                        "Ineligible: You must have been at least 18 years old "
                        "at the time of your last donation."
                    )
                else:
                    passed.append(
                        f"Age at last donation was {age_at_donation} years — valid"
                    )

            # ── 90-day cooldown ──
            days_since = (datetime.utcnow().date() - last).days
            if days_since < 90:
                issues.append(
                    f"Only {days_since} days since last donation — minimum gap is 90 days"
                )
            else:
                passed.append(f"{days_since} days since last donation — gap is sufficient")

        except ValueError:
            issues.append("Invalid date format for last donation date")

    # Health flags
    if recent_illness:
        issues.append("Recent illness reported — must wait at least 14 days after recovery")
    if recent_surgery:
        issues.append("Recent surgery reported — must wait at least 6 months")
    if on_medication:
        issues.append("Currently on medication — eligibility depends on medication type; consult a doctor")

    eligible = len(issues) == 0
    return jsonify({
        "eligible": eligible,
        "issues": issues,
        "passed": passed,
        "days_since_last_donation": days_since,
        "summary": "You are eligible to donate blood!" if eligible else
                   f"{len(issues)} issue(s) found. Please review before booking."
    })

@app.route("/api/eligibility/pass", methods=["POST"])
def eligibility_pass():
    """
    Called by the frontend when the eligibility check passes.
    Stores DOB, last donation date, and blood group in the Flask session
    so the Book Appointment page can pre-fill and lock those fields.
    """
    d = request.get_json()
    dob        = d.get("dob", "").strip()
    last_date  = d.get("last_donation", "").strip()
    blood_group = d.get("blood_group", "").strip()

    if not dob or not blood_group:
        return jsonify({"success": False, "message": "DOB and blood group are required"}), 400

    session["elig_dob"]        = dob
    session["elig_last_date"]  = last_date
    session["elig_blood_group"] = blood_group
    return jsonify({"success": True})

@app.route("/eligibility")
def eligibility_page():
    return render_template("eligibility.html")

# ─────────────────────────────────────────
# ADMIN API
# ─────────────────────────────────────────

def require_admin():
    if not session.get("is_admin"):
        return jsonify({"success": False, "message": "Admin access required"}), 403
    return None

@app.route("/api/admin-portal/signup", methods=["POST"])
def api_admin_portal_signup():
    """
    Admin portal signup endpoint — protected by secret passphrase.
    This allows your team to create admin accounts without exposing a public signup.
    
    Secret passphrase: techfest2026
    (Change this in production!)
    """
    d = request.get_json()
    
    secret_key = d.get("secretKey", "").strip()
    username   = d.get("username", "").strip()
    email      = d.get("email", "").strip()
    password   = d.get("password", "")
    confirm    = d.get("confirm", "")
    
    # ── Step 1: Verify secret passphrase ──
    #ADMIN_SECRET = "techfest2026"  # Change this for your presentation!
    ADMIN_SECRET = os.getenv('ADMIN_SECRET', 'techfest2026')
    
    if secret_key != ADMIN_SECRET:
        print(f"[ADMIN PORTAL] Failed signup attempt — invalid secret key")
        return jsonify({
            "success": False,
            "message": "❌ Invalid secret passphrase. Contact your system administrator."
        }), 403
    
    # ── Step 2: Validate inputs ──
    if not all([username, email, password, confirm]):
        return jsonify({
            "success": False,
            "message": "All fields are required"
        }), 400
    
    if not valid_username(username):
        return jsonify({
            "success": False,
            "message": "Username must be at least 3 characters with no spaces"
        }), 400
    
    if password != confirm:
        return jsonify({
            "success": False,
            "message": "Passwords do not match"
        }), 400
    
    err = valid_password(password)
    if err:
        return jsonify({
            "success": False,
            "message": err
        }), 400
    
    # ── Step 3: Check for duplicates ──
    if User.query.filter_by(username=username).first():
        return jsonify({
            "success": False,
            "message": "Username already taken"
        }), 409
    
    if User.query.filter_by(email=email).first():
        return jsonify({
            "success": False,
            "message": "Email already registered"
        }), 409
    
    # ── Step 4: Create admin account ──
    hashed = bcrypt.generate_password_hash(password).decode("utf-8")
    admin  = User(
        username=username,
        email=email,
        phone="+910000000000",  # Placeholder
        first_name="Admin",
        last_name="User",
        city="Borivali",  # Default city
        password=hashed,
        role="admin",
        is_admin=True
    )
    
    db.session.add(admin)
    db.session.commit()
    
    print(f"[ADMIN PORTAL] New admin created: {username} | {email}")
    
    return jsonify({
        "success": True,
        "message": f"Admin account '{username}' created successfully! You can now log in."
    })

@app.route("/api/debug/admins")
def debug_admins():
    """Temporary debug route — shows all admin users in the DB. Remove before production."""
    admins = User.query.filter(
        db.or_(User.is_admin == True, User.role == "admin")
    ).all()
    return jsonify([{
        "id":       u.id,
        "username": u.username,
        "email":    u.email,
        "role":     u.role,
        "is_admin": u.is_admin,
        "created":  str(u.created)
    } for u in admins])


@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    """
    Dedicated admin authentication endpoint.
    Checks credentials against the User table where role = 'admin'.
    Sets a clearly tagged admin session (non-permanent — expires on browser close).
    Regular user sessions are completely separate from admin sessions.
    """
    d        = request.get_json()
    username = d.get("username", "").strip()
    password = d.get("password", "")

    if not username or not password:
        return jsonify({"success": False,
                        "message": "Username and password are required"}), 400

    # ── Debug: log all admin users in DB ──
    all_admins = User.query.filter(
        db.or_(User.is_admin == True, User.role == "admin")
    ).all()
    print(f"[ADMIN LOGIN] Attempt: username='{username}' | Admins in DB: {[u.username for u in all_admins]}")

    # Look up only users with is_admin=True OR role="admin" (legacy rows)
    user = User.query.filter(
        User.username == username,
        db.or_(User.is_admin == True, User.role == "admin")
    ).first()

    if not user:
        print(f"[ADMIN LOGIN] No admin found with username='{username}'")
        return jsonify({"success": False,
                        "message": "Invalid admin credentials"}), 401

    pw_ok = bcrypt.check_password_hash(user.password, password)
    print(f"[ADMIN LOGIN] User found: id={user.id}, is_admin={user.is_admin}, role={user.role}, pw_ok={pw_ok}")

    if not pw_ok:
        return jsonify({"success": False,
                        "message": "Invalid admin credentials"}), 401

    # Ensure is_admin flag is set for legacy rows
    if not user.is_admin:
        user.is_admin = True
        db.session.commit()

    # ── Issue a non-permanent admin session ──
    session.clear()
    session.permanent    = False
    session["user_id"]   = user.id
    session["username"]  = user.username
    session["role"]      = "admin"
    session["is_admin"]  = True          # Boolean flag — primary auth check
    session["city"]      = user.city or ""

    print(f"[ADMIN LOGIN] Success — {user.username} | id={user.id}")

    return jsonify({
        "success":  True,
        "message":  "Admin access granted.",
        "username": user.username,
        "role":     "admin",
        "redirect_to": "/admin-command-panel"
    })

@app.route("/api/admin/users")
def admin_users():
    err = require_admin()
    if err: return err
    users = User.query.order_by(User.created.desc()).all()
    result = []
    for u in users:
        donor = Donor.query.filter_by(email=u.email).first()
        result.append({
            "id": u.id, "username": u.username,
            "name": f"{u.first_name or ''} {u.last_name or ''}".strip(),
            "email": u.email, "phone": u.phone, "city": u.city,
            "role": u.role,
            "created": u.created.strftime("%d %b %Y"),
            "donations": donor.donations if donor else 0,
            "donor_id": donor.id if donor else None
        })
    return jsonify(result)

@app.route("/api/admin/add-admin", methods=["POST"])
def api_admin_add_admin():
    """
    Admin CRUD: create a new admin account.
    Only callable by an authenticated admin session.
    Password is bcrypt-hashed before storage.
    """
    err = require_admin()
    if err: return err

    d        = request.get_json()
    username = d.get("username", "").strip()
    password = d.get("password", "")
    email    = d.get("email", "").strip() or f"{username}@sbdms.local"

    if not valid_username(username):
        return jsonify({"success": False,
                        "message": "Username must be ≥3 characters with no spaces"}), 400
    pw_err = valid_password(password)
    if pw_err:
        return jsonify({"success": False, "message": pw_err}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"success": False, "message": "Username already taken"}), 409

    hashed = bcrypt.generate_password_hash(password).decode("utf-8")
    new_admin = User(
        username=username, email=email, phone="+910000000000",
        first_name="Admin", last_name="User", city="Borivali",
        password=hashed, role="admin", is_admin=True
    )
    db.session.add(new_admin)
    db.session.commit()
    print(f"[ADMIN CRUD] New admin '{username}' created by '{session.get('username')}'")
    return jsonify({
        "success": True,
        "message": f"Admin account '{username}' created successfully.",
        "id": new_admin.id
    })

@app.route("/api/admin/requests")
def admin_requests():
    """
    Admin endpoint: Get all emergency requests with delivery status.
    Returns empty list if no requests exist (prevents "Failed to load" error).
    """
    err = require_admin()
    if err: return err
    
    # Get filter parameter: 'recent' (default) or 'all'
    view = request.args.get('view', 'recent')
    limit = request.args.get('limit', 5, type=int)
    
    query = EmergencyRequest.query.order_by(EmergencyRequest.requested_at.desc())
    
    # Filter by view type
    if view == 'recent':
        # Show only recent requests (last 30 days or limited count)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        query = query.filter(EmergencyRequest.requested_at >= thirty_days_ago)
        reqs = query.limit(limit).all()
    else:
        # Show all requests (full history)
        reqs = query.all()
    
    result = []
    
    for r in reqs:
        # Find associated delivery request
        # Safe access — receipt_no may not exist on older DB rows
        receipt_no = getattr(r, 'receipt_no', None)
        delivery = None
        if receipt_no:
            delivery = DeliveryRequest.query.filter_by(receipt_no=receipt_no).first()
        # Fallback: match by location + blood_group + units (most recent)
        if not delivery:
            delivery = DeliveryRequest.query.filter_by(
                location=r.location,
                blood_group=r.blood_group,
                units=r.units
            ).order_by(DeliveryRequest.created_at.desc()).first()

        # Map delivery status to display label
        if delivery:
            raw_status = delivery.status  # pending | in_transit | completed
            if raw_status == "completed":
                delivery_label = "Completed"
            elif raw_status == "in_transit":
                delivery_label = "In Transit"
            else:
                delivery_label = "Pending"
        else:
            # If no ERU record but emergency request is fulfilled, show Completed
            delivery_label = "Completed" if r.status == "fulfilled" else "Pending"

        result.append({
            "id":              r.id,
            "blood_group":     r.blood_group,
            "location":        r.location,
            "address":         r.address or "—",
            "units":           r.units,
            "status":          r.status,
            "donor_name":      r.donor_name or "—",
            "requested_at":    r.requested_at.strftime("%d %b %Y %H:%M"),
            "delivery_status": delivery_label,
            "rider":           "Bloodhound Unit" if delivery and delivery.status != "pending" else "—",
            "eta":             f"{delivery.eta_seconds // 60} min" if delivery and delivery.status == "in_transit" else "—"
        })
    
    return jsonify(result)

@app.route("/api/admin/inventory/all")
def admin_inventory_all():
    """Master inventory across all cities — admin only."""
    err = require_admin()
    if err: return err
    items = BloodInventory.query.order_by(BloodInventory.city, BloodInventory.blood_group).all()
    return jsonify([{
        "id": i.id, "blood_group": i.blood_group, "city": i.city,
        "bank_name": i.bank_name, "units": i.units, "cost_per_bag": i.cost_per_bag,
        "status": "critical" if i.units < 5 else "low" if i.units < 10 else "ok"
    } for i in items])

@app.route("/api/admin/inventory/set", methods=["POST"])
def admin_set_inventory():
    """Admin: directly set units for a blood group in a city."""
    err = require_admin()
    if err: return err
    d = request.get_json()
    item = BloodInventory.query.filter(
        BloodInventory.blood_group == d["blood_group"],
        BloodInventory.city.ilike(d.get("city",""))
    ).first()
    if not item:
        return jsonify({"success": False, "message": "Not found"}), 404
    item.units = max(0, int(d.get("units", item.units)))
    item.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "units": item.units})

@app.route("/api/rider/all")
def api_rider_all():
    """
    Get all Bloodhound delivery riders.
    Returns empty list if no riders exist (prevents "Failed to load" error).
    Public endpoint for admin panel display.
    """
    riders = Rider.query.order_by(Rider.city, Rider.name).all()
    return jsonify([{
        "id": r.id,
        "name": r.name,
        "phone": r.phone,
        "city": r.city,
        "vehicle": r.vehicle,
        "is_free": r.is_free
    } for r in riders])

# ─────────────────────────────────────────
# SYSTEM RESET & MANAGEMENT
# ─────────────────────────────────────────

@app.route("/api/demo-reset", methods=["POST"])
def api_demo_reset():
    """
    One-click demo reset — callable from the admin panel at any time.

    Actions (all via raw SQL for guaranteed physical write):
      1. DELETE FROM emergency_request
      2. DELETE FROM transaction
      3. DELETE FROM delivery_request
      4. DELETE FROM appointment
      5. UPDATE blood_inventory SET units = 20

    Does NOT touch: user, donor, rider tables.
    Clears the server-side session so the frontend fetches fresh data.
    Returns a JSON summary with verification counts.
    """
    err = require_admin()
    if err: return err

    try:
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # ── Hard-delete all transactional tables ──
        er_before  = db.session.execute(db.text("SELECT COUNT(*) FROM emergency_request")).scalar()
        txn_before = db.session.execute(db.text('SELECT COUNT(*) FROM "transaction"')).scalar()
        dr_before  = db.session.execute(db.text("SELECT COUNT(*) FROM delivery_request")).scalar()
        ap_before  = db.session.execute(db.text("SELECT COUNT(*) FROM appointment")).scalar()

        db.session.execute(db.text("DELETE FROM emergency_request"))
        db.session.commit()

        db.session.execute(db.text('DELETE FROM "transaction"'))
        db.session.commit()

        db.session.execute(db.text("DELETE FROM delivery_request"))
        db.session.commit()

        db.session.execute(db.text("DELETE FROM appointment"))
        db.session.commit()

        # ── Overwrite every inventory row to exactly 20 units ──
        inv_rows = db.session.execute(db.text("SELECT COUNT(*) FROM blood_inventory")).scalar()
        db.session.execute(
            db.text("UPDATE blood_inventory SET units = 20, updated_at = :ts"),
            {"ts": now_str}
        )
        db.session.commit()

        # ── Verify ──
        er_after  = db.session.execute(db.text("SELECT COUNT(*) FROM emergency_request")).scalar()
        txn_after = db.session.execute(db.text('SELECT COUNT(*) FROM "transaction"')).scalar()
        inv_wrong = db.session.execute(
            db.text("SELECT COUNT(*) FROM blood_inventory WHERE units != 20")
        ).scalar()

        # ── Clear server-side session cache so frontend re-fetches fresh data ──
        admin_id       = session.get("user_id")
        admin_username = session.get("username")
        session.clear()
        # Restore admin session so they stay logged in
        session.permanent  = False
        session["user_id"]  = admin_id
        session["username"] = admin_username
        session["role"]     = "admin"
        session["is_admin"] = True

        summary = {
            "emergency_requests_deleted": er_before,
            "transactions_deleted":       txn_before,
            "delivery_requests_deleted":  dr_before,
            "appointments_deleted":       ap_before,
            "inventory_rows_reset":       inv_rows,
        }
        verification = {
            "emergency_request_count": er_after,
            "transaction_count":       txn_after,
            "inventory_rows_not_20":   inv_wrong,
        }

        print(f"[DEMO RESET] Triggered by admin '{admin_username}' at {now_str}")
        print(f"[DEMO RESET] Deleted: {summary}")
        print(f"[DEMO RESET] Verification: {verification}")

        return jsonify({
            "success":      True,
            "message":      "Demo reset complete. All test data cleared, inventory set to 20 units.",
            "summary":      summary,
            "verification": verification,
            "timestamp":    now_str
        })

    except Exception as e:
        db.session.rollback()
        print(f"[DEMO RESET ERROR] {e}")
        return jsonify({"success": False, "message": f"Reset failed: {str(e)}"}), 500


@app.route("/api/admin/system-reset", methods=["POST"])
def admin_system_reset():
    """
    Admin-only system reset for demo preparation.
    Clears test data and restores inventory to default levels.
    
    SAFETY: Does NOT delete user accounts, donors, or riders.
    """
    err = require_admin()
    if err: return err
    
    d = request.get_json()
    reset_type = d.get("type", "all")  # 'all', 'requests', 'inventory', 'transactions'
    confirm = d.get("confirm", False)
    
    if not confirm:
        return jsonify({
            "success": False,
            "message": "Confirmation required. Set 'confirm': true"
        }), 400
    
    try:
        reset_summary = []
        
        # HARD DELETE Emergency Requests
        if reset_type in ["all", "requests"]:
            req_count = db.session.query(EmergencyRequest).count()
            delivery_count = db.session.query(DeliveryRequest).count()
            
            # Use .delete() for HARD DELETE (not soft delete)
            db.session.query(EmergencyRequest).delete()
            db.session.query(DeliveryRequest).delete()
            
            reset_summary.append(f"HARD DELETED {req_count} emergency requests")
            reset_summary.append(f"HARD DELETED {delivery_count} delivery requests")
        
        # HARD DELETE Transactions
        if reset_type in ["all", "transactions"]:
            txn_count = db.session.query(Transaction).count()
            db.session.query(Transaction).delete()
            reset_summary.append(f"HARD DELETED {txn_count} transactions")
        
        # HARD RESET Inventory to Default Levels (OVERWRITE, not increment)
        if reset_type in ["all", "inventory"]:
            # Custom inventory levels per blood group (more realistic)
            custom_levels = d.get("custom_levels", {})
            
            # Default levels if not specified
            default_inventory = {
                "A+":  30,
                "A-":  25,
                "B+":  35,
                "B-":  20,
                "O+":  40,  # Most common
                "O-":  15,  # Rare
                "AB+": 25,
                "AB-": 10,  # Rarest
            }
            
            # Use custom levels if provided, otherwise use defaults
            inventory_levels = custom_levels if custom_levels else default_inventory
            fallback_units = d.get("default_units", 30)
            
            inventory_items = BloodInventory.query.all()
            updated_count = 0
            
            for item in inventory_items:
                # OVERWRITE units (not add/subtract)
                old_units = item.units
                new_units = inventory_levels.get(item.blood_group, fallback_units)
                item.units = new_units
                item.updated_at = datetime.utcnow()
                updated_count += 1
            
            reset_summary.append(f"HARD RESET {updated_count} inventory items (OVERWRITTEN to default levels)")
        
        # HARD DELETE Appointments (optional)
        if reset_type in ["all", "appointments"]:
            appt_count = db.session.query(Appointment).count()
            db.session.query(Appointment).delete()
            reset_summary.append(f"HARD DELETED {appt_count} appointments")
        
        # Commit all changes
        db.session.commit()
        
        # Verification
        verification = {
            "emergency_requests": EmergencyRequest.query.count(),
            "delivery_requests": DeliveryRequest.query.count(),
            "transactions": Transaction.query.count(),
            "appointments": Appointment.query.count(),
        }
        
        print(f"[HARD RESET] Admin '{session.get('username')}' performed HARD RESET: {reset_type}")
        print(f"[HARD RESET] Summary: {', '.join(reset_summary)}")
        print(f"[HARD RESET] Verification: {verification}")
        
        return jsonify({
            "success": True,
            "message": "HARD RESET completed successfully",
            "summary": reset_summary,
            "verification": verification,
            "timestamp": datetime.utcnow().strftime("%d %b %Y %H:%M:%S")
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"[HARD RESET ERROR] {str(e)}")
        return jsonify({
            "success": False,
            "message": f"HARD RESET failed: {str(e)}"
        }), 500

@app.route("/api/admin/system-stats")
def admin_system_stats():
    """
    Get system statistics for admin dashboard.
    Shows counts of all major entities.
    """
    err = require_admin()
    if err: return err
    
    try:
        stats = {
            "users": User.query.count(),
            "admins": User.query.filter_by(is_admin=True).count(),
            "donors": Donor.query.count(),
            "riders": Rider.query.count(),
            "emergency_requests": EmergencyRequest.query.count(),
            "pending_requests": EmergencyRequest.query.filter_by(status="pending").count(),
            "fulfilled_requests": EmergencyRequest.query.filter_by(status="fulfilled").count(),
            "transactions": Transaction.query.count(),
            "appointments": Appointment.query.count(),
            "total_inventory_units": db.session.query(db.func.sum(BloodInventory.units)).scalar() or 0,
            "low_stock_items": BloodInventory.query.filter(BloodInventory.units < 10).count(),
            "critical_stock_items": BloodInventory.query.filter(BloodInventory.units < 5).count(),
        }
        
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ─────────────────────────────────────────
# EMERGENCY RESPONSE UNIT (ERU) API
# ─────────────────────────────────────────

def gen_eru_code():
    return "ERU-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

@app.route("/api/eru/initiate", methods=["POST"])
def eru_initiate():
    """
    Unified endpoint: creates the ERU record, marks it in_transit immediately.
    Calculates real distance via Haversine formula and derives:
      eta_minutes  = distance / 25 km/h  (realistic display for doctors)
      eta_seconds  = (distance × 3) + 15 (demo simulation countdown)
      delivery_fee = ₹20 + ₹5/km
    Returns eru_id, eru_code, distance_km, eta_minutes, eta_seconds, delivery_fee.
    """
    d            = request.get_json()
    blood_group  = d.get("blood_group", "")
    location     = d.get("location", "")
    address      = d.get("address", "").strip()
    units        = int(d.get("units", 1))
    patient_name = d.get("patient_name", "").strip()
    donor_name   = d.get("donor_name", "").strip()

    if not all([blood_group, location, patient_name]):
        return jsonify({"success": False,
                        "message": "Blood group, location and patient name required"}), 400

    delivery_info = calculate_delivery(location)
    dist_km   = delivery_info["distance_km"]
    eta_mins  = delivery_info["eta_minutes"]
    eta_secs  = delivery_info["eta_seconds"]
    del_fee   = delivery_info["delivery_fee"]

    eru = DeliveryRequest(
        eru_code     = gen_eru_code(),
        blood_group  = blood_group,
        location     = location,
        address      = address,
        units        = units,
        patient_name = patient_name,
        donor_name   = donor_name,
        status       = "in_transit",
        started_at   = datetime.utcnow(),
        distance_km  = dist_km,
        eta_seconds  = eta_secs,
        delivery_fee = del_fee,
    )
    db.session.add(eru)
    db.session.commit()

    print(f"[ERU] Initiated {eru.eru_code} | {blood_group} x{units} | "
          f"{location} | {dist_km}km | {eta_mins}min real | {eta_secs}s sim | Fee ₹{del_fee}")

    return jsonify({
        "success":      True,
        "eru_code":     eru.eru_code,
        "eru_id":       eru.id,
        "distance_km":  dist_km,
        "eta_minutes":  eta_mins,
        "eta_seconds":  eta_secs,
        "delivery_fee": del_fee,
        "message":      f"Delivery initiated — {dist_km}km — Estimated Arrival: {eta_mins} min"
    })

@app.route("/api/eru/create", methods=["POST"])
def eru_create():
    """Create a delivery request after donor is found via emergency search."""
    d            = request.get_json()
    blood_group  = d.get("blood_group", "")
    location     = d.get("location", "")
    address      = d.get("address", "").strip()
    units        = int(d.get("units", 1))
    patient_name = d.get("patient_name", "").strip()
    donor_name   = d.get("donor_name", "").strip()

    if not all([blood_group, location, patient_name]):
        return jsonify({"success": False, "message": "Blood group, location and patient name required"}), 400

    eru = DeliveryRequest(
        eru_code     = gen_eru_code(),
        blood_group  = blood_group,
        location     = location,
        address      = address,
        units        = units,
        patient_name = patient_name,
        donor_name   = donor_name,
        status       = "pending"
    )
    db.session.add(eru)
    db.session.commit()

    print(f"[ERU] Created {eru.eru_code} | {blood_group} x{units} | {location} | Patient: {patient_name}")

    return jsonify({
        "success":  True,
        "eru_code": eru.eru_code,
        "eru_id":   eru.id,
        "message":  f"Delivery request {eru.eru_code} created. Rider notified."
    })

@app.route("/api/eru/list")
def eru_list():
    """Return all delivery requests — used by the Rider page."""
    status_filter = request.args.get("status", "")
    q = DeliveryRequest.query
    if status_filter:
        q = q.filter_by(status=status_filter)
    requests = q.order_by(DeliveryRequest.created_at.desc()).all()

    result = []
    for r in requests:
        # Calculate remaining ETA for in_transit requests
        eta_remaining = 0
        if r.status == "in_transit" and r.started_at:
            elapsed       = int((datetime.utcnow() - r.started_at).total_seconds())
            eta_remaining = max(0, (r.eta_seconds or 12) - elapsed)

        result.append({
            "id":           r.id,
            "eru_code":     r.eru_code,
            "blood_group":  r.blood_group,
            "location":     r.location,
            "address":      r.address,
            "units":        r.units,
            "patient_name": r.patient_name,
            "donor_name":   r.donor_name,
            "status":       r.status,
            "receipt_no":   r.receipt_no,
            "distance_km":  round(float(r.distance_km or 0), 2),
            "eta_minutes":  max(5, math.ceil((float(r.distance_km or 0.5) / 25) * 60)),
            "eta_seconds":  r.eta_seconds or 12,
            "eta_remaining": eta_remaining,
            "delivery_fee": round(float(r.delivery_fee or 0), 2),
            "created_at":   r.created_at.strftime("%d %b %Y %H:%M"),
            "started_at":   r.started_at.strftime("%d %b %Y %H:%M") if r.started_at else None,
            "completed_at": r.completed_at.strftime("%d %b %Y %H:%M") if r.completed_at else None,
        })
    return jsonify(result)

@app.route("/api/eru/start", methods=["POST"])
def eru_start():
    """Rider marks delivery as In Transit."""
    d   = request.get_json()
    eru = DeliveryRequest.query.get_or_404(d.get("eru_id"))
    if eru.status != "pending":
        return jsonify({"success": False, "message": "Request is not in pending state"}), 400
    eru.status     = "in_transit"
    eru.started_at = datetime.utcnow()
    db.session.commit()
    print(f"[ERU] {eru.eru_code} → IN TRANSIT")
    return jsonify({"success": True, "status": eru.status, "eru_code": eru.eru_code})

@app.route("/api/eru/complete", methods=["POST"])
def eru_complete():
    """
    Marks delivery as Completed.
    Formula: Total = (bags × ₹50) + (distance × ₹5) + ₹20 flat fee
    Inventory is NOT deducted here — it is deducted only when payment is confirmed
    (see pay_bill). This ensures stock is only reduced after money is received.
    """
    d   = request.get_json()
    eru = DeliveryRequest.query.get_or_404(d.get("eru_id"))
    if eru.status not in ("pending", "in_transit"):
        return jsonify({"success": False, "message": "Request already completed"}), 400

    bg    = eru.blood_group
    units = eru.units

    # ── Integer pricing: (bags × ₹1500) + (dist × ₹5) + ₹20 flat fee ──
    dist_km     = round(float(eru.distance_km or 0.5), 2)
    bag_cost    = int(units * 1500)              # ₹1500 per bag — whole number
    dist_charge = int(round(dist_km * 5))        # ₹5 per km — whole number
    flat_fee    = 20                             # ₹20 service fee — whole number
    del_fee     = int(dist_charge + flat_fee)    # whole number delivery fee
    total       = int(bag_cost + del_fee)        # whole number total
    receipt_no  = gen_receipt()

    # ── Create transaction as "pending" — inventory deducted on payment ──
    # Auto-assign a rider from the Rider table for the matching city
    assigned_rider = Rider.query.filter_by(city=eru.location, is_free=True).first()
    if not assigned_rider:
        assigned_rider = Rider.query.filter_by(city=eru.location).first()
    if not assigned_rider:
        assigned_rider = Rider.query.first()   # fallback: any rider

    txn = Transaction(
        receipt_no   = receipt_no,
        patient_name = eru.patient_name,
        blood_group  = bg,
        bags         = units,
        cost_per_bag = 1500,
        delivery_fee = del_fee,
        total        = total,
        status       = "pending",
        fraud_flag   = False,
        rider_name   = assigned_rider.name  if assigned_rider else "—",
        rider_phone  = assigned_rider.phone if assigned_rider else "—",
    )
    db.session.add(txn)

    # ── Mark ERU as completed ──
    eru.status       = "completed"
    eru.completed_at = datetime.utcnow()
    eru.receipt_no   = receipt_no
    db.session.commit()

    print(f"[ERU] {eru.eru_code} → COMPLETED | Receipt: {receipt_no} | "
          f"{dist_km}km | Bags×₹1500={bag_cost} | Dist×₹5={dist_charge} | "
          f"Flat=₹20 | Total ₹{total} | Inventory pending payment")

    return jsonify({
        "success":      True,
        "status":       "completed",
        "eru_code":     eru.eru_code,
        "receipt_no":   receipt_no,
        "distance_km":  dist_km,
        "bag_cost":     bag_cost,
        "dist_charge":  dist_charge,
        "flat_fee":     flat_fee,
        "delivery_fee": del_fee,
        "total":        total,
        "bags":         units,
        "payment_url":  f"/payment?receipt={receipt_no}",
        "message":      f"Delivery completed. Receipt {receipt_no} created."
    })

@app.route("/api/eru/status/<int:eru_id>")
def eru_status(eru_id):
    """
    Returns current ERU status + remaining ETA seconds for refresh persistence.
    Frontend calls this on page reload to resume the countdown from the correct point.
    """
    eru = DeliveryRequest.query.get_or_404(eru_id)
    elapsed = 0
    if eru.started_at:
        elapsed = int((datetime.utcnow() - eru.started_at).total_seconds())

    eta_total     = eru.eta_seconds or 12
    eta_remaining = max(0, eta_total - elapsed)

    return jsonify({
        "eru_id":        eru.id,
        "eru_code":      eru.eru_code,
        "status":        eru.status,
        "distance_km":   round(float(eru.distance_km or 0), 2),
        "eta_seconds":   eta_total,
        "eta_remaining": eta_remaining,
        "delivery_fee":  round(float(eru.delivery_fee or 0), 2),
        "receipt_no":    eru.receipt_no,
        "payment_url":   f"/payment?receipt={eru.receipt_no}" if eru.receipt_no else None,
    })

# ─────────────────────────────────────────
# RUN
# ─────────────────────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()   # creates tables only if they don't exist — data is preserved
        # ── Schema migrations: add columns that may be missing from older DBs ──
        migrations = [
            ("emergency_request", "receiver_phone", "ALTER TABLE emergency_request ADD COLUMN receiver_phone VARCHAR(20)"),
            ("emergency_request", "address",        "ALTER TABLE emergency_request ADD COLUMN address VARCHAR(250)"),
            ("delivery_request",  "receipt_no",     "ALTER TABLE delivery_request ADD COLUMN receipt_no VARCHAR(20)"),
            ("delivery_request",  "distance_km",    "ALTER TABLE delivery_request ADD COLUMN distance_km FLOAT DEFAULT 0.0"),
            ("delivery_request",  "eta_seconds",    "ALTER TABLE delivery_request ADD COLUMN eta_seconds INTEGER DEFAULT 12"),
            ("delivery_request",  "delivery_fee",   "ALTER TABLE delivery_request ADD COLUMN delivery_fee FLOAT DEFAULT 50.0"),
            # is_admin column — must run before seed_data() which queries this column
            ("user",              "is_admin",        "ALTER TABLE user ADD COLUMN is_admin BOOLEAN DEFAULT 0"),
            # login_count — tracks total logins for welcome-back greeting
            ("user",              "login_count",     "ALTER TABLE user ADD COLUMN login_count INTEGER DEFAULT 0"),
        ]
        for table, col, sql in migrations:
            try:
                existing = [r[1] for r in db.session.execute(
                    db.text(f"PRAGMA table_info({table})")
                ).fetchall()]
                if col not in existing:
                    db.session.execute(db.text(sql))
                    db.session.commit()
                    print(f"[MIGRATION] Added column '{col}' to '{table}'")
            except Exception as e:
                print(f"[MIGRATION] Skipped {table}.{col}: {e}")
        seed_data()       # seeds only if tables are empty — safe to call every restart

    app.run(debug=False, host="0.0.0.0", port=5000)
