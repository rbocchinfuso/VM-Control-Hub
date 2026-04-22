from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app.models import VCenter, AuditLog, db
from app import vcenter_client

api_bp = Blueprint('api', __name__)


@api_bp.route('/vcenters/<int:vc_id>/vms')
@login_required
def get_vms(vc_id):
    vc = VCenter.query.get_or_404(vc_id)
    try:
        vms = vcenter_client.get_all_vms(vc)
        if not current_user.is_admin():
            vms = [vm for vm in vms if current_user.can_view_vm(vm['moref'], vc_id)]
        return jsonify({'vms': vms, 'count': len(vms)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/vcenters/<int:vc_id>/vms/<moref>')
@login_required
def get_vm(vc_id, moref):
    if not current_user.can_view_vm(moref, vc_id):
        return jsonify({'error': 'Permission denied'}), 403

    vc = VCenter.query.get_or_404(vc_id)
    try:
        vm = vcenter_client.get_vm_by_moref(vc, moref)
        if not vm:
            return jsonify({'error': 'VM not found'}), 404
        return jsonify(vm)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/vcenters/<int:vc_id>/vms/<moref>/performance')
@login_required
def get_vm_performance(vc_id, moref):
    if not current_user.can_view_vm(moref, vc_id):
        return jsonify({'error': 'Permission denied'}), 403

    vc = VCenter.query.get_or_404(vc_id)
    try:
        vm = vcenter_client.get_vm_by_moref(vc, moref)
        if not vm:
            return jsonify({'error': 'VM not found'}), 404

        metrics = vcenter_client.get_vm_performance(vc, moref)
        return jsonify({
            'vm': vm,
            'metrics': metrics,
            'cpu_percent': round((vm['cpu_usage_mhz'] / max(vm['num_cpu'] * 1000, 1)) * 100, 1) if vm['num_cpu'] else 0,
            'memory_percent': round((vm['memory_usage_mb'] / max(vm['memory_mb'], 1)) * 100, 1) if vm['memory_mb'] else 0,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/vcenters/<int:vc_id>/vms/<moref>/snapshots')
@login_required
def get_snapshots(vc_id, moref):
    if not current_user.can_view_vm(moref, vc_id):
        return jsonify({'error': 'Permission denied'}), 403

    vc = VCenter.query.get_or_404(vc_id)
    try:
        snapshots = vcenter_client.get_snapshots(vc, moref)
        return jsonify({'snapshots': snapshots, 'count': len(snapshots)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/audit-log')
@login_required
def audit_log():
    if not current_user.is_admin():
        return jsonify({'error': 'Permission denied'}), 403
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=50)
    return jsonify({
        'logs': [
            {
                'id': l.id,
                'user': l.user.username if l.user else 'unknown',
                'action': l.action,
                'vm_name': l.vm_name,
                'result': l.result,
                'details': l.details,
                'timestamp': l.timestamp.isoformat()
            } for l in logs.items
        ],
        'total': logs.total,
        'pages': logs.pages,
        'current_page': page,
    })
