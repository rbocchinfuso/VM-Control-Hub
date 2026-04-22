from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import VCenter, VMPermission, AuditLog, db
from app import vcenter_client
import threading

vms_bp = Blueprint('vms', __name__, url_prefix='/vms')


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


@vms_bp.route('/')
@login_required
def index():
    # Resolve the real user object before spawning threads
    user = current_user._get_current_object()

    accessible_ids = user.accessible_vcenter_ids()
    all_active = VCenter.query.filter_by(is_active=True).order_by(VCenter.name).all()
    visible_vcenters = [vc for vc in all_active if vc.id in accessible_ids]

    lock = threading.Lock()
    safe_vms = []
    safe_errors = []

    def thread_fetch(v):
        try:
            vms = vcenter_client.get_all_vms(v)
            filtered = []
            for vm in vms:
                if user.can_view_vm(vm['moref'], v.id):
                    vm['vcenter_name'] = v.name
                    filtered.append(vm)
            with lock:
                safe_vms.extend(filtered)
        except Exception as e:
            with lock:
                safe_errors.append(f"{v.name}: {str(e)}")

    threads = []
    for vc in visible_vcenters:
        t = threading.Thread(target=thread_fetch, args=(vc,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join(timeout=15)

    safe_vms.sort(key=lambda x: (x['vcenter_name'], x['name']))

    vcenter_filter = request.args.get('vcenter', '')
    power_filter = request.args.get('power', '')
    search = request.args.get('search', '').lower()

    filtered_vms = safe_vms
    if vcenter_filter:
        filtered_vms = [v for v in filtered_vms if str(v['vcenter_id']) == vcenter_filter]
    if power_filter:
        filtered_vms = [v for v in filtered_vms if v['power_state'] == power_filter]
    if search:
        filtered_vms = [v for v in filtered_vms if search in v['name'].lower() or
                        (v.get('ip_address') and search in v['ip_address'])]

    return render_template(
        'vms/index.html',
        vms=filtered_vms,
        vcenters=visible_vcenters,   # only the ones the user can see
        errors=safe_errors,
        vcenter_filter=vcenter_filter,
        power_filter=power_filter,
        search=search,
    )


@vms_bp.route('/<int:vc_id>/<moref>')
@login_required
def detail(vc_id, moref):
    # Gate access: user must be able to see this vCenter AND this VM
    if vc_id not in current_user.accessible_vcenter_ids():
        flash('You do not have permission to access this vCenter.', 'danger')
        return redirect(url_for('vms.index'))

    if not current_user.can_view_vm(moref, vc_id):
        flash('You do not have permission to view this VM.', 'danger')
        return redirect(url_for('vms.index'))

    vc = VCenter.query.get_or_404(vc_id)

    try:
        vm = vcenter_client.get_vm_by_moref(vc, moref)
        if not vm:
            flash('VM not found.', 'danger')
            return redirect(url_for('vms.index'))
    except Exception as e:
        flash(f'Error retrieving VM: {str(e)}', 'danger')
        return redirect(url_for('vms.index'))

    try:
        snapshots = vcenter_client.get_snapshots(vc, moref)
    except Exception:
        snapshots = []

    vm['vcenter_name'] = vc.name
    can_control = current_user.can_control_vm(moref, vc_id)
    can_snapshot = current_user.can_snapshot_vm(moref, vc_id)

    return render_template(
        'vms/detail.html',
        vm=vm,
        vcenter=vc,
        snapshots=snapshots,
        can_control=can_control,
        can_snapshot=can_snapshot,
    )


@vms_bp.route('/<int:vc_id>/<moref>/power', methods=['POST'])
@login_required
def power_action(vc_id, moref):
    if not current_user.can_control_vm(moref, vc_id):
        return jsonify({'error': 'Permission denied'}), 403

    vc = VCenter.query.get_or_404(vc_id)
    action = request.json.get('action') if request.is_json else request.form.get('action')
    vm_name = request.json.get('vm_name', moref) if request.is_json else request.form.get('vm_name', moref)

    try:
        if action == 'power_on':
            vcenter_client.power_on_vm(vc, moref)
            msg = 'VM powered on'
        elif action == 'power_off':
            vcenter_client.power_off_vm(vc, moref)
            msg = 'VM powered off (hard)'
        elif action == 'shutdown':
            vcenter_client.shutdown_vm(vc, moref)
            msg = 'Guest shutdown initiated'
        elif action == 'reboot_guest':
            vcenter_client.reboot_vm_guest(vc, moref)
            msg = 'Guest reboot initiated'
        elif action == 'reset':
            vcenter_client.reset_vm(vc, moref)
            msg = 'VM hard reset initiated'
        elif action == 'power_cycle':
            vcenter_client.power_cycle_vm(vc, moref)
            msg = 'VM power cycled'
        else:
            return jsonify({'error': 'Invalid action'}), 400

        log_action(current_user.id, action, vc_id, moref, vm_name, 'success', msg)

        if request.is_json:
            return jsonify({'message': msg, 'action': action})
        flash(msg, 'success')
        return redirect(url_for('vms.detail', vc_id=vc_id, moref=moref))

    except Exception as e:
        log_action(current_user.id, action, vc_id, moref, vm_name, 'error', str(e))
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'Action failed: {str(e)}', 'danger')
        return redirect(url_for('vms.detail', vc_id=vc_id, moref=moref))
