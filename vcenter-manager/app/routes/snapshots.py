from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import VCenter, AuditLog, db
from app import vcenter_client

snapshots_bp = Blueprint('snapshots', __name__, url_prefix='/vms')


def log_action(user_id, action, vcenter_id=None, vm_moref=None, vm_name=None, result='success', details=None):
    log = AuditLog(
        user_id=user_id,
        action=action,
        vcenter_id=vcenter_id,
        vm_moref=vm_moref,
        vm_name=vm_name,
        result=result,
        details=details,
        target=vm_name
    )
    db.session.add(log)
    db.session.commit()


def _deny(is_json, vc_id, moref):
    if is_json:
        return jsonify({'error': 'Permission denied — snapshot operations require Admin access.'}), 403
    flash('Permission denied — snapshot operations require Admin access.', 'danger')
    return redirect(url_for('vms.detail', vc_id=vc_id, moref=moref))


@snapshots_bp.route('/<int:vc_id>/<moref>/snapshots/create', methods=['POST'])
@login_required
def create_snapshot(vc_id, moref):
    if not current_user.can_snapshot_vm(moref, vc_id):
        return _deny(request.is_json, vc_id, moref)

    vc = VCenter.query.get_or_404(vc_id)
    data = request.json if request.is_json else request.form

    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()
    memory = bool(data.get('memory', False))
    quiesce = bool(data.get('quiesce', False))
    vm_name = data.get('vm_name', moref)

    if not name:
        if request.is_json:
            return jsonify({'error': 'Snapshot name is required'}), 400
        flash('Snapshot name is required.', 'danger')
        return redirect(url_for('vms.detail', vc_id=vc_id, moref=moref))

    try:
        vcenter_client.create_snapshot(vc, moref, name, description, memory, quiesce)
        log_action(current_user.id, 'create_snapshot', vc_id, moref, vm_name, 'success', f'Snapshot: {name}')
        if request.is_json:
            return jsonify({'message': f'Snapshot "{name}" created successfully'})
        flash(f'Snapshot "{name}" created successfully.', 'success')
    except Exception as e:
        log_action(current_user.id, 'create_snapshot', vc_id, moref, vm_name, 'error', str(e))
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Failed to create snapshot: {str(e)}', 'danger')

    return redirect(url_for('vms.detail', vc_id=vc_id, moref=moref))


@snapshots_bp.route('/<int:vc_id>/<moref>/snapshots/<snap_moref>/revert', methods=['POST'])
@login_required
def revert_snapshot(vc_id, moref, snap_moref):
    if not current_user.can_snapshot_vm(moref, vc_id):
        return _deny(request.is_json, vc_id, moref)

    vc = VCenter.query.get_or_404(vc_id)
    vm_name = request.json.get('vm_name', moref) if request.is_json else request.form.get('vm_name', moref)

    try:
        vcenter_client.revert_to_snapshot(vc, snap_moref)
        log_action(current_user.id, 'revert_snapshot', vc_id, moref, vm_name, 'success', f'Snap moref: {snap_moref}')
        if request.is_json:
            return jsonify({'message': 'Reverted to snapshot successfully'})
        flash('Reverted to snapshot successfully.', 'success')
    except Exception as e:
        log_action(current_user.id, 'revert_snapshot', vc_id, moref, vm_name, 'error', str(e))
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Failed to revert snapshot: {str(e)}', 'danger')

    return redirect(url_for('vms.detail', vc_id=vc_id, moref=moref))


@snapshots_bp.route('/<int:vc_id>/<moref>/snapshots/<snap_moref>/delete', methods=['POST'])
@login_required
def delete_snapshot(vc_id, moref, snap_moref):
    if not current_user.can_snapshot_vm(moref, vc_id):
        return _deny(request.is_json, vc_id, moref)

    vc = VCenter.query.get_or_404(vc_id)
    vm_name = request.json.get('vm_name', moref) if request.is_json else request.form.get('vm_name', moref)
    remove_children = bool(request.json.get('remove_children', False) if request.is_json else request.form.get('remove_children', False))

    try:
        vcenter_client.delete_snapshot(vc, snap_moref, remove_children)
        log_action(current_user.id, 'delete_snapshot', vc_id, moref, vm_name, 'success', f'Snap moref: {snap_moref}')
        if request.is_json:
            return jsonify({'message': 'Snapshot deleted successfully'})
        flash('Snapshot deleted successfully.', 'success')
    except Exception as e:
        log_action(current_user.id, 'delete_snapshot', vc_id, moref, vm_name, 'error', str(e))
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Failed to delete snapshot: {str(e)}', 'danger')

    return redirect(url_for('vms.detail', vc_id=vc_id, moref=moref))
