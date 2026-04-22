from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import VCenter, AuditLog, VMPermission, db
from app import vcenter_client
import threading

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def dashboard():
    # Resolve the real user object before spawning threads
    user = current_user._get_current_object()

    # Determine which vCenters this user can see
    accessible_ids = user.accessible_vcenter_ids()
    all_active = VCenter.query.filter_by(is_active=True).order_by(VCenter.name).all()
    visible_vcenters = [vc for vc in all_active if vc.id in accessible_ids]

    lock = threading.Lock()
    results = []

    def fetch_stats(vc):
        try:
            all_vms = vcenter_client.get_all_vms(vc)
            # For non-admins/operators filter to only accessible VMs
            if user.role in ['admin', 'operator']:
                vms = all_vms
            else:
                vms = [v for v in all_vms if user.can_view_vm(v['moref'], vc.id)]

            powered_on = sum(1 for v in vms if v['power_state'] == 'poweredOn')
            stat = {
                'vcenter': vc,
                'total_vms': len(vms),
                'powered_on': powered_on,
                'powered_off': len(vms) - powered_on,
                'status': 'connected',
            }
        except Exception as e:
            stat = {
                'vcenter': vc,
                'total_vms': 0,
                'powered_on': 0,
                'powered_off': 0,
                'status': 'error',
                'error': str(e),
            }
        with lock:
            results.append(stat)

    threads = []
    for vc in visible_vcenters:
        t = threading.Thread(target=fetch_stats, args=(vc,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join(timeout=10)

    results.sort(key=lambda x: x['vcenter'].name)

    # Audit log — admins see everyone's actions, others see only their own
    log_q = AuditLog.query
    if not user.is_admin():
        log_q = log_q.filter_by(user_id=user.id)
    recent_logs = log_q.order_by(AuditLog.timestamp.desc()).limit(20).all()

    total_vms = sum(r['total_vms'] for r in results)
    total_powered_on = sum(r['powered_on'] for r in results)

    return render_template(
        'main/dashboard.html',
        vcenter_stats=results,
        recent_logs=recent_logs,
        total_vms=total_vms,
        total_powered_on=total_powered_on,
    )
