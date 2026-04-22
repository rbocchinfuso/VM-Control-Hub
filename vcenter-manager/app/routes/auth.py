from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User, db
from datetime import datetime
import pyotp
import qrcode
import io
import base64

auth_bp = Blueprint('auth', __name__)

MFA_PENDING_KEY = 'mfa_pending_user_id'
MFA_REMEMBER_KEY = 'mfa_pending_remember'
MFA_NEXT_KEY = 'mfa_pending_next'


# ── Login / Logout ─────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember', False))

        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            if user.mfa_enabled:
                # Stash state in session and redirect to TOTP challenge
                session[MFA_PENDING_KEY] = user.id
                session[MFA_REMEMBER_KEY] = remember
                session[MFA_NEXT_KEY] = request.args.get('next', '')
                return redirect(url_for('auth.mfa_verify'))
            # No MFA — log in directly
            _complete_login(user, remember)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


def _complete_login(user, remember):
    user.last_login = datetime.utcnow()
    db.session.commit()
    login_user(user, remember=remember)
    flash(f'Welcome back, {user.username}!', 'success')


# ── MFA verify (login challenge) ───────────────────────────────────────────

@auth_bp.route('/mfa/verify', methods=['GET', 'POST'])
def mfa_verify():
    user_id = session.get(MFA_PENDING_KEY)
    if not user_id:
        return redirect(url_for('auth.login'))

    user = User.query.get(user_id)
    if not user or not user.mfa_enabled:
        session.pop(MFA_PENDING_KEY, None)
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        code = request.form.get('code', '').strip().replace(' ', '')
        totp = pyotp.TOTP(user.mfa_secret)
        if totp.verify(code, valid_window=1):
            remember = session.pop(MFA_REMEMBER_KEY, False)
            next_page = session.pop(MFA_NEXT_KEY, '') or url_for('main.dashboard')
            session.pop(MFA_PENDING_KEY, None)
            _complete_login(user, remember)
            return redirect(next_page)
        else:
            flash('Incorrect authentication code. Please try again.', 'danger')

    return render_template('auth/mfa_verify.html', username=user.username)


# ── Profile & password ─────────────────────────────────────────────────────

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'danger')
        elif new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
        elif len(new_password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash('Password updated successfully.', 'success')

    return render_template('auth/profile.html')


# ── MFA setup ──────────────────────────────────────────────────────────────

@auth_bp.route('/mfa/setup', methods=['GET', 'POST'])
@login_required
def mfa_setup():
    # Always generate a fresh secret for setup (shown in session until confirmed)
    if 'mfa_setup_secret' not in session:
        session['mfa_setup_secret'] = pyotp.random_base32()

    secret = session['mfa_setup_secret']
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=current_user.email,
        issuer_name='Virtual Infra Manager'
    )

    if request.method == 'POST':
        code = request.form.get('code', '').strip().replace(' ', '')
        if totp.verify(code, valid_window=1):
            current_user.mfa_secret = secret
            current_user.mfa_enabled = True
            db.session.commit()
            session.pop('mfa_setup_secret', None)
            flash('Two-factor authentication has been enabled on your account.', 'success')
            return redirect(url_for('auth.profile'))
        else:
            flash('Incorrect code — please try again. Make sure your device clock is accurate.', 'danger')

    qr_data_uri = _qr_data_uri(provisioning_uri)
    return render_template(
        'auth/mfa_setup.html',
        secret=secret,
        qr_data_uri=qr_data_uri,
    )


@auth_bp.route('/mfa/disable', methods=['POST'])
@login_required
def mfa_disable():
    password = request.form.get('password', '')
    if not current_user.check_password(password):
        flash('Incorrect password — two-factor authentication has NOT been disabled.', 'danger')
    else:
        current_user.mfa_enabled = False
        current_user.mfa_secret = None
        db.session.commit()
        flash('Two-factor authentication has been disabled.', 'warning')
    return redirect(url_for('auth.profile'))


# ── Helpers ────────────────────────────────────────────────────────────────

def _qr_data_uri(data: str) -> str:
    """Return a base64-encoded PNG data URI for the given QR code payload."""
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    encoded = base64.b64encode(buf.getvalue()).decode('ascii')
    return f'data:image/png;base64,{encoded}'
