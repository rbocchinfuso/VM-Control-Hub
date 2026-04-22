from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import VCenter, db
from app import vcenter_client
from functools import wraps
from datetime import datetime

vcenters_bp = Blueprint('vcenters', __name__, url_prefix='/vcenters')


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin():
            flash('Administrator access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated


@vcenters_bp.route('/')
@login_required
def index():
    if current_user.is_admin():
        # Admins see every vCenter (active or not) for management
        vcenters = VCenter.query.order_by(VCenter.name).all()
    else:
        # Operators and viewers only see active vCenters they have access to
        accessible_ids = current_user.accessible_vcenter_ids()
        if accessible_ids:
            vcenters = VCenter.query.filter(
                VCenter.id.in_(accessible_ids),
                VCenter.is_active == True,
            ).order_by(VCenter.name).all()
        else:
            vcenters = []

    return render_template(
        'vcenters/index.html',
        vcenters=vcenters,
        is_admin=current_user.is_admin(),
    )


@vcenters_bp.route('/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        host = request.form.get('host', '').strip()
        port = int(request.form.get('port', 443))
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        verify_ssl = bool(request.form.get('verify_ssl'))

        if not all([name, host, username, password]):
            flash('All fields are required.', 'danger')
            return render_template('vcenters/form.html', vcenter=None)

        vc = VCenter(
            name=name,
            host=host,
            port=port,
            username=username,
            password=password,
            verify_ssl=verify_ssl
        )

        success, msg = vcenter_client.test_connection(vc)
        if success:
            vc.connection_status = 'connected'
            vc.last_connected = datetime.utcnow()
            flash(f'vCenter "{name}" added and connected successfully.', 'success')
        else:
            vc.connection_status = 'error'
            flash(f'vCenter added but connection failed: {msg}', 'warning')

        db.session.add(vc)
        db.session.commit()
        return redirect(url_for('vcenters.index'))

    return render_template('vcenters/form.html', vcenter=None)


@vcenters_bp.route('/<int:vc_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(vc_id):
    vc = VCenter.query.get_or_404(vc_id)

    if request.method == 'POST':
        vc.name = request.form.get('name', '').strip()
        vc.host = request.form.get('host', '').strip()
        vc.port = int(request.form.get('port', 443))
        vc.username = request.form.get('username', '').strip()
        new_password = request.form.get('password', '')
        if new_password:
            vc.password = new_password
        vc.verify_ssl = bool(request.form.get('verify_ssl'))

        vcenter_client.disconnect_vcenter(vc.id)

        success, msg = vcenter_client.test_connection(vc)
        if success:
            vc.connection_status = 'connected'
            vc.last_connected = datetime.utcnow()
            flash(f'vCenter "{vc.name}" updated and connected.', 'success')
        else:
            vc.connection_status = 'error'
            flash(f'vCenter updated but connection failed: {msg}', 'warning')

        db.session.commit()
        return redirect(url_for('vcenters.index'))

    return render_template('vcenters/form.html', vcenter=vc)


@vcenters_bp.route('/<int:vc_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(vc_id):
    vc = VCenter.query.get_or_404(vc_id)
    vcenter_client.disconnect_vcenter(vc.id)
    db.session.delete(vc)
    db.session.commit()
    flash(f'vCenter "{vc.name}" deleted.', 'success')
    return redirect(url_for('vcenters.index'))


@vcenters_bp.route('/<int:vc_id>/test')
@login_required
@admin_required
def test(vc_id):
    vc = VCenter.query.get_or_404(vc_id)
    vcenter_client.disconnect_vcenter(vc.id)
    success, msg = vcenter_client.test_connection(vc)
    if success:
        vc.connection_status = 'connected'
        vc.last_connected = datetime.utcnow()
        db.session.commit()
        return jsonify({'status': 'connected', 'message': msg})
    else:
        vc.connection_status = 'error'
        db.session.commit()
        return jsonify({'status': 'error', 'message': msg}), 400
