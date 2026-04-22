from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import VCenter, AuditLog, VMPermission, db
from app import vcenter_client
import threading

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def dashboard():
    vcenters = VCenter.query.filter_by(is_active=True).all()
    vcenter_stats = []

    def fetch_stats(vc):
        try:
            vms = vcenter_client.get_all_vms(vc)
            powered_on = sum(1 for v in vms if v['power_state'] == 'poweredOn')
            powered_off = sum(1 for v in vms if v['power_state'] == 'poweredOff')
            return {
                'vcenter': vc,
                'total_vms': len(vms),
                'powered_on': powered_on,
                'powered_off': powered_off,
                'status': 'connected'
            }
        except Exception as e:
            return {
                'vcenter': vc,
                'total_vms': 0,
                'powered_on': 0,
                'powered_off': 0,
                'status': 'error',
                'error': str(e)
            }

    results = []
    threads = []
    result_lock = threading.Lock()

    for vc in vcenters:
        def thread_func(v=vc):
            stat = fetch_stats(v)
            with result_lock:
                results.append(stat)

        t = threading.Thread(target=thread_func)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=10)

    results.sort(key=lambda x: x['vcenter'].name)

    recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(20).all()

    total_vms = sum(r['total_vms'] for r in results)
    total_powered_on = sum(r['powered_on'] for r in results)

    return render_template(
        'main/dashboard.html',
        vcenter_stats=results,
        recent_logs=recent_logs,
        total_vms=total_vms,
        total_powered_on=total_powered_on,
    )
