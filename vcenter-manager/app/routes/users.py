from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import User, VCenter, VMPermission, db
from app import vcenter_client
from functools import wraps

users_bp = Blueprint('users', __name__, url_prefix='/users')


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin():
            flash('Administrator access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated


@users_bp.route('/')
@login_required
@admin_required
def index():
    users = User.query.all()
    return render_template('users/index.html', users=users)


@users_bp.route('/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'viewer')

        if not all([username, email, password]):
            flash('All fields are required.', 'danger')
            return render_template('users/form.html', user=None, roles=User.ROLES)

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return render_template('users/form.html', user=None, roles=User.ROLES)

        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'danger')
            return render_template('users/form.html', user=None, roles=User.ROLES)

        if role not in User.ROLES:
            role = 'viewer'

        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f'User "{username}" created successfully.', 'success')
        return redirect(url_for('users.index'))

    return render_template('users/form.html', user=None, roles=User.ROLES)


@users_bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        user.email = request.form.get('email', '').strip()
        user.role = request.form.get('role', 'viewer')
        user.is_active = bool(request.form.get('is_active'))
        new_password = request.form.get('password', '')
        if new_password:
            if len(new_password) < 8:
                flash('Password must be at least 8 characters.', 'danger')
                return render_template('users/form.html', user=user, roles=User.ROLES)
            user.set_password(new_password)

        if user.role not in User.ROLES:
            user.role = 'viewer'

        db.session.commit()
        flash(f'User "{user.username}" updated.', 'success')
        return redirect(url_for('users.index'))

    return render_template('users/form.html', user=user, roles=User.ROLES)


@users_bp.route('/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('users.index'))
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{user.username}" deleted.', 'success')
    return redirect(url_for('users.index'))


@users_bp.route('/<int:user_id>/permissions', methods=['GET', 'POST'])
@login_required
@admin_required
def permissions(user_id):
    user = User.query.get_or_404(user_id)
    vcenters = VCenter.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        vcenter_id = int(request.form.get('vcenter_id', 0))
        vm_moref = request.form.get('vm_moref', '').strip()
        vm_name = request.form.get('vm_name', '').strip()
        can_power = bool(request.form.get('can_power', False))
        can_snapshot = bool(request.form.get('can_snapshot', False))

        if not all([vcenter_id, vm_moref]):
            flash('vCenter and VM are required.', 'danger')
        else:
            existing = VMPermission.query.filter_by(
                user_id=user.id, vcenter_id=vcenter_id, vm_moref=vm_moref
            ).first()
            if existing:
                existing.vm_name = vm_name
                existing.can_power = can_power
                existing.can_snapshot = can_snapshot
                flash('Permission updated.', 'success')
            else:
                perm = VMPermission(
                    user_id=user.id,
                    vcenter_id=vcenter_id,
                    vm_moref=vm_moref,
                    vm_name=vm_name,
                    can_power=can_power,
                    can_snapshot=can_snapshot,
                )
                db.session.add(perm)
                flash('Permission added.', 'success')
            db.session.commit()

    current_perms = VMPermission.query.filter_by(user_id=user.id).all()

    all_vms = {}
    for vc in vcenters:
        try:
            vms = vcenter_client.get_all_vms(vc)
            all_vms[vc.id] = vms
        except Exception:
            all_vms[vc.id] = []

    return render_template(
        'users/permissions.html',
        user=user,
        vcenters=vcenters,
        current_perms=current_perms,
        all_vms=all_vms,
    )


@users_bp.route('/<int:user_id>/permissions/<int:perm_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_permission(user_id, perm_id):
    perm = VMPermission.query.get_or_404(perm_id)
    if perm.user_id != user_id:
        flash('Invalid permission.', 'danger')
        return redirect(url_for('users.permissions', user_id=user_id))
    db.session.delete(perm)
    db.session.commit()
    flash('Permission removed.', 'success')
    return redirect(url_for('users.permissions', user_id=user_id))
