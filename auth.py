"""
auth.py - Authentication and User Management for ForexAI Chain.

Handles:
- User registration and login using SQLite (users table in ledger.db)
- Password hashing via werkzeug.security (generate_password_hash / check_password_hash)
- Rate limiting: 5 failed attempts per email locks login for 5 minutes (300s)
- Streamlit session state management with a modern glassmorphic login card
"""

import re
import time
import sqlite3
import threading
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import streamlit as st
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# Database Configuration & Thread Safety
# ---------------------------------------------------------------------------

_PROJECT_DIR = Path(__file__).resolve().parent
_DB_PATH = _PROJECT_DIR / "ledger.db"
_auth_lock = threading.Lock()

def _get_auth_db():
    """Return a thread-safe SQLite connection and initialize auth tables."""
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    with _auth_lock:
        # Table 1: Registered users
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # Table 2: Login attempt tracker for rate limiting
        conn.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                email TEXT PRIMARY KEY,
                attempts INTEGER DEFAULT 0,
                locked_until REAL DEFAULT 0
            )
        """)
        conn.commit()
    return conn

# Initialize tables immediately on import
_get_auth_db()

# ---------------------------------------------------------------------------
# Validation Helpers
# ---------------------------------------------------------------------------

_EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}$")

def is_valid_email(email: str) -> bool:
    """Validate email format using regex."""
    if not email:
        return False
    return bool(_EMAIL_REGEX.match(email.strip()))

# ---------------------------------------------------------------------------
# Authentication Operations
# ---------------------------------------------------------------------------

def create_user(name: str, email: str, password: str, confirm_password: str) -> Tuple[bool, str]:
    """
    Validate and register a new user.
    Returns: (success: bool, message: str)
    """
    name = (name or "").strip()
    email = (email or "").strip().lower()

    if not name:
        return False, "Please enter your name."
    if not is_valid_email(email):
        return False, "Please enter a valid email address."
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if password != confirm_password:
        return False, "Passwords do not match."

    conn = _get_auth_db()
    with _auth_lock:
        cursor = conn.cursor()
        # Check if email is already taken
        cursor.execute("SELECT id FROM users WHERE lower(email) = ?", (email,))
        if cursor.fetchone() is not None:
            return False, "An account with this email already exists."

        # Hash password securely (scrypt / pbkdf2 via werkzeug)
        pwd_hash = generate_password_hash(password)
        try:
            cursor.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, pwd_hash)
            )
            conn.commit()
            return True, "Account created successfully! You can now log in."
        except sqlite3.IntegrityError:
            return False, "An account with this email already exists."
        except Exception as e:
            return False, f"Registration error: {e}"

MAX_LOGIN_ATTEMPTS = 10

def authenticate_user(email: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Authenticate an existing user with rate-limiting.
    Returns: (success: bool, user_dict or None, message: str)
    """
    email = (email or "").strip().lower()
    if not email or not password:
        return False, None, "Please provide both email and password."

    conn = _get_auth_db()
    now = time.time()

    with _auth_lock:
        cursor = conn.cursor()
        # 1. Check rate limit
        cursor.execute("SELECT attempts, locked_until FROM login_attempts WHERE email = ?", (email,))
        attempt_row = cursor.fetchone()
        attempts = 0
        locked_until = 0.0
        if attempt_row:
            attempts, locked_until = attempt_row

        if locked_until and locked_until > now:
            remaining_seconds = int(locked_until - now)
            minutes = remaining_seconds // 60
            seconds = remaining_seconds % 60
            return False, None, f"🔒 Account temporarily locked due to {MAX_LOGIN_ATTEMPTS} failed attempts. Please try again in {minutes}m {seconds}s."

        # 2. Look up user by email
        cursor.execute("SELECT id, name, email, password_hash FROM users WHERE lower(email) = ?", (email,))
        user_row = cursor.fetchone()

        # 3. Check password if user exists
        if user_row and check_password_hash(user_row[3], password):
            # Login successful: reset failed attempt counter
            cursor.execute("INSERT OR REPLACE INTO login_attempts (email, attempts, locked_until) VALUES (?, 0, 0)", (email,))
            conn.commit()
            user_data = {
                "id": user_row[0],
                "name": user_row[1],
                "email": user_row[2]
            }
            return True, user_data, "Login successful!"

        # Failed attempt: increment counter
        attempts += 1
        new_lock = 0.0
        if attempts >= MAX_LOGIN_ATTEMPTS:
            new_lock = now + 300.0  # 5 minutes block
            cursor.execute(
                "INSERT OR REPLACE INTO login_attempts (email, attempts, locked_until) VALUES (?, ?, ?)",
                (email, attempts, new_lock)
            )
            conn.commit()
            return False, None, f"🔒 Too many failed attempts ({MAX_LOGIN_ATTEMPTS}). Account locked for 5 minutes."
        else:
            cursor.execute(
                "INSERT OR REPLACE INTO login_attempts (email, attempts, locked_until) VALUES (?, ?, ?)",
                (email, attempts, 0)
            )
            conn.commit()
            remaining = MAX_LOGIN_ATTEMPTS - attempts
            return False, None, f"Invalid email or password. ({remaining} attempt{'s' if remaining != 1 else ''} remaining)"

# ---------------------------------------------------------------------------
# UI Styling & Rendering
# ---------------------------------------------------------------------------

_LOGIN_CSS = """
<style>
/* Hide standard Streamlit header, menu, footer and sidebar on login page */
#MainMenu { visibility: hidden !important; }
header { visibility: hidden !important; }
footer { visibility: hidden !important; }
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }

/* Set overall page background to dark navy-to-teal gradient */
.stApp {
    background: linear-gradient(135deg, #091224 0%, #11203b 35%, #0d3b54 75%, #0f5b66 100%) !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #f1f5f9;
}

/* Constrain main block to center the card (~420px wide) */
.block-container {
    max-width: 420px !important;
    padding-top: 3rem !important;
    padding-bottom: 2rem !important;
    margin: 0 auto !important;
}

@media (max-width: 480px) {
    .block-container {
        max-width: 92% !important;
        padding-top: 1.8rem !important;
    }
    .auth-card-header {
        padding: 1.5rem 1rem 1rem 1rem !important;
    }
}

/* Glassmorphism Card Header */
.auth-card-header {
    background: rgba(255, 255, 255, 0.06);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 16px;
    padding: 1.8rem 1.5rem 1.2rem 1.5rem;
    box-shadow: 0 20px 45px rgba(0, 0, 0, 0.45);
    text-align: center;
    margin-bottom: 1.2rem;
}

.auth-logo-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 52px;
    height: 52px;
    border-radius: 14px;
    background: linear-gradient(135deg, #10b981 0%, #0284c7 100%);
    box-shadow: 0 8px 20px rgba(16, 185, 129, 0.35);
    font-size: 24px;
    margin-bottom: 0.65rem;
}

.auth-title {
    font-size: 1.7rem;
    font-weight: 800;
    letter-spacing: -0.5px;
    margin: 0 0 0.3rem 0;
    background: linear-gradient(90deg, #ffffff 0%, #67e8f9 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.auth-subtitle {
    font-size: 0.85rem;
    color: #94a3b8;
    margin: 0;
    line-height: 1.4;
}

/* Glassmorphism styling for Form Card */
div[data-testid="stForm"] {
    background: rgba(255, 255, 255, 0.05) !important;
    backdrop-filter: blur(18px) !important;
    -webkit-backdrop-filter: blur(18px) !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    border-radius: 16px !important;
    padding: 1.4rem !important;
    box-shadow: 0 16px 36px rgba(0, 0, 0, 0.35) !important;
}

/* Rounded Input Fields */
div[data-baseweb="input"] {
    background-color: rgba(15, 23, 42, 0.65) !important;
    border: 1px solid rgba(255, 255, 255, 0.14) !important;
    border-radius: 10px !important;
    color: #f8fafc !important;
    transition: all 0.2s ease-in-out;
}

div[data-baseweb="input"]:focus-within {
    border-color: #38bdf8 !important;
    box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.25) !important;
}

/* Full-width gradient button with smooth hover effect */
div.stButton > button, div[data-testid="stForm"] div.stButton > button {
    width: 100% !important;
    border: none !important;
    border-radius: 10px !important;
    background: linear-gradient(90deg, #0284c7 0%, #0d9488 100%) !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    font-size: 0.98rem !important;
    padding: 0.65rem 1rem !important;
    box-shadow: 0 8px 18px rgba(2, 132, 199, 0.3) !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease !important;
    margin-top: 0.4rem !important;
}

div.stButton > button:hover, div[data-testid="stForm"] div.stButton > button:hover {
    transform: translateY(-1px) !important;
    filter: brightness(1.1) !important;
    box-shadow: 0 12px 24px rgba(2, 132, 199, 0.45) !important;
}

div.stButton > button:active, div[data-testid="stForm"] div.stButton > button:active {
    transform: translateY(0px) !important;
}

/* Tab labels styling */
button[data-baseweb="tab"] {
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    color: #94a3b8 !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #38bdf8 !important;
    border-bottom-color: #38bdf8 !important;
}

/* Footer disclaimer */
.auth-footer {
    text-align: center;
    font-size: 0.78rem;
    color: #64748b;
    margin-top: 1.6rem;
    padding-top: 0.8rem;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
}
</style>
"""

def render_login_gate() -> bool:
    """
    Authenticate user and control access to the main dashboard.
    Returns:
        True  -> user is logged in (dashboard code can proceed)
        False -> user is not logged in (rendered login page and called st.stop())
    """
    # Initialize session state variables
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None

    # If user is already logged in, show user info in sidebar and proceed
    if st.session_state.authenticated and st.session_state.user:
        user_name = st.session_state.user.get("name", "User")
        user_email = st.session_state.user.get("email", "")

        # Sidebar authentication status
        st.sidebar.markdown(f"### 👤 Welcome, **{user_name}**")
        st.sidebar.caption(f"Logged in as `{user_email}`")
        if st.sidebar.button("🚪 Logout", key="btn_auth_logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user = None
            st.rerun()

        st.sidebar.markdown("---")
        return True

    # -----------------------------------------------------------------------
    # User is NOT logged in: Render the Glassmorphism Auth Page
    # -----------------------------------------------------------------------
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    # Header Card with Branding
    st.markdown("""
        <div class="auth-card-header">
            <div class="auth-logo-badge">📈</div>
            <h1 class="auth-title">ForexAI Chain</h1>
            <p class="auth-subtitle">AI-powered Forex signals, verified on blockchain</p>
        </div>
    """, unsafe_allow_html=True)

    # Login and Sign up tabs
    tab_login, tab_signup = st.tabs(["🔑 Login", "📝 Sign up"])

    with tab_login:
        with st.form("login_form", clear_on_submit=False):
            login_email = st.text_input("Email address", placeholder="name@example.com", key="login_email")
            login_password = st.text_input("Password", type="password", placeholder="••••••••", key="login_password")
            submit_login = st.form_submit_button("Sign In")
            st.caption("💡 **Demo Account:** `admin@forex.com` / `Admin@1234`")

            if submit_login:
                ok, user_data, msg = authenticate_user(login_email, login_password)
                if ok and user_data:
                    st.session_state.authenticated = True
                    st.session_state.user = user_data
                    st.success(f"Welcome back, {user_data['name']}!")
                    time.sleep(0.4)
                    st.rerun()
                else:
                    st.error(msg)

    with tab_signup:
        with st.form("signup_form", clear_on_submit=False):
            signup_name = st.text_input("Full Name", placeholder="Jane Doe", key="signup_name")
            signup_email = st.text_input("Email address", placeholder="jane@example.com", key="signup_email")
            signup_password = st.text_input("Password (min 8 characters)", type="password", placeholder="••••••••", key="signup_password")
            signup_confirm = st.text_input("Confirm Password", type="password", placeholder="••••••••", key="signup_confirm")
            submit_signup = st.form_submit_button("Create Account")

            if submit_signup:
                ok, msg = create_user(signup_name, signup_email, signup_password, signup_confirm)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

    # Small footer
    st.markdown("""
        <div class="auth-footer">
            ForexAI Chain &bull; Learning platform &bull; Not financial advice
        </div>
    """, unsafe_allow_html=True)

    # Stop execution so the rest of app.py is never rendered to unauthorized visitors
    st.stop()
    return False
