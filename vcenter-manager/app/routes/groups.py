from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import Group, GroupVMPermission, User, VCenter, db
from app import vcenter_client
from functools import wraps

groups_bp = Blueprint('groups', __name__, url_prefix='/groups')


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin():
            flash('Administrator access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated


@groups_bp.route('/')
@login_required
@admin_required
def index():
    groups = Group.query.order_by(Group.name).all()
    return render_template('groups/index.html', groups=groups)


@groups_bp.route('/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if not name:
            flash('Group name is required.', 'danger')
            return render_template('groups/form.html', group=None)

        if Group.query.filter_by(name=name).first():
            flash(f'A group named "{name}" already exists.', 'danger')
            return render_template('groups/form.html', group=None)

        group = Group(name=name, description=description)
        db.session.add(group)
        db.session.commit()
        flash(f'Group "{name}" created.', 'success')
        return redirect(url_for('groups.members', group_id=group.id))

    return render_template('groups/form.html', group=None)


@groups_bp.route('/<int:group_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(group_id):
    group = Group.query.get_or_404(group_id)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if not name:
            flash('Group name is required.', 'danger')
            return render_template('groups/form.html', group=group)

        clash = Group.query.filter(Group.name == name, Group.id != group_id).first()
        if clash:
            flash(f'A group named "{name}" already exists.', 'danger')
            return render_template('groups/form.html', group=group)

        group.name = name
        group.description = description
        db.session.commit()
        flash('Group updated.', 'success')
        return redirect(url_for('groups.index'))

    return render_template('groups/form.html', group=group)


@groups_bp.route('/<int:group_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(group_id):
    group = Group.query.get_or_404(group_id)
    name = group.name
    db.session.delete(group)
    db.session.commit()
    flash(f'Group "{name}" deleted.', 'success')
    return redirect(url_for('groups.index'))


# ── Member management ──────────────────────────────────────────────────────

@groups_bp.route('/<int:group_id>/members', methods=['GET', 'POST'])
@login_required
@admin_required
def members(group_id):
    group = Group.query.get_or_404(group_id)

    if request.method == 'POST':
        user_id = request.form.get('user_id', type=int)
        user = User.query.get(user_id) if user_id else None
        if not user:
            flash('User not found.', 'danger')
        elif user in group.members:
            flash(f'{user.username} is already in this group.', 'warning')
        else:
            group.members.append(user)
            db.session.commit()
            flash(f'{user.username} added to group.', 'success')

    all_users = User.query.order_by(User.username).all()
    member_ids = {u.id for u in group.members}
    non_members = [u for u in all_users if u.id not in member_ids]

    return render_template(
        'groups/members.html',
        group=group,
        non_members=non_members,
    )


@groups_bp.route('/<int:group_id>/members/<int:user_id>/remove', methods=['POST'])
@login_required
@admin_required
def remove_member(group_id, user_id):
    group = Group.query.get_or_404(group_id)
    user = User.query.get_or_404(user_id)
    if user in group.members:
        group.members.remove(user)
        db.session.commit()
        flash(f'{user.username} removed from group.', 'success')
    return redirect(url_for('groups.members', group_id=group_id))


# ── VM permission management ───────────────────────────────────────────────

@groups_bp.route('/<int:group_id>/permissions', methods=['GET', 'POST'])
@login_required
@admin_required
def permissions(group_id):
    group = Group.query.get_or_404(group_id)
    vcenters = VCenter.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        vcenter_id = request.form.get('vcenter_id', type=int)
        vm_moref = request.form.get('vm_moref', '').strip()
        vm_name = request.form.get('vm_name', '').strip()
        can_power = bool(request.form.get('can_power'))
        can_snapshot = bool(request.form.get('can_snapshot'))

        if not vcenter_id or not vm_moref:
            flash('vCenter and VM are required.', 'danger')
        else:
            existing = GroupVMPermission.query.filter_by(
                group_id=group_id, vcenter_id=vcenter_id, vm_moref=vm_moref
            ).first()
            if existing:
                existing.vm_name = vm_name
                existing.can_power = can_power
                existing.can_snapshot = can_snapshot
                flash('Permission updated.', 'success')
            else:
                perm = GroupVMPermission(
                    group_id=group_id,
                    vcenter_id=vcenter_id,
                    vm_moref=vm_moref,
                    vm_name=vm_name,
                    can_power=can_power,
                    can_snapshot=can_snapshot,
                )
                db.session.add(perm)
                flash('VM permission added to group.', 'success')
            db.session.commit()

    current_perms = GroupVMPermission.query.filter_by(group_id=group_id).all()

    all_vms = {}
    for vc in vcenters:
        try:
            all_vms[vc.id] = vcenter_client.get_all_vms(vc)
        except Exception:
            all_vms[vc.id] = []

    return render_template(
        'groups/permissions.html',
        group=group,
        vcenters=vcenters,
        current_perms=current_perms,
        all_vms=all_vms,
    )


@groups_bp.route('/<int:group_id>/permissions/<int:perm_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_permission(group_id, perm_id):
    perm = GroupVMPermission.query.get_or_404(perm_id)
    if perm.group_id != group_id:
        flash('Invalid permission.', 'danger')
        return redirect(url_for('groups.permissions', group_id=group_id))
    db.session.delete(perm)
    db.session.commit()
    flash('Permission removed.', 'success')
    return redirect(url_for('groups.permissions', group_id=group_id))
