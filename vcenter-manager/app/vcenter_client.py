import ssl
from datetime import datetime
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
import threading
import time


_connection_cache = {}
_cache_lock = threading.Lock()


def get_vcenter_connection(vcenter):
    """Get or create a vCenter connection, cached per vcenter id."""
    with _cache_lock:
        cache_entry = _connection_cache.get(vcenter.id)
        if cache_entry:
            try:
                cache_entry['si'].CurrentTime()
                return cache_entry['si']
            except Exception:
                _connection_cache.pop(vcenter.id, None)

        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            if not vcenter.verify_ssl:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

            si = SmartConnect(
                host=vcenter.host,
                user=vcenter.username,
                pwd=vcenter.password,
                port=vcenter.port,
                sslContext=context,
                connectionPoolTimeout=30
            )
            _connection_cache[vcenter.id] = {'si': si, 'connected_at': datetime.utcnow()}
            return si
        except Exception as e:
            raise ConnectionError(f"Failed to connect to vCenter {vcenter.host}: {str(e)}")


def disconnect_vcenter(vcenter_id):
    with _cache_lock:
        entry = _connection_cache.pop(vcenter_id, None)
        if entry:
            try:
                Disconnect(entry['si'])
            except Exception:
                pass


def test_connection(vcenter):
    """Test connection to a vCenter server."""
    try:
        si = get_vcenter_connection(vcenter)
        si.CurrentTime()
        return True, "Connected successfully"
    except Exception as e:
        return False, str(e)


def get_all_vms(vcenter):
    """Get all VMs from a vCenter server with basic info."""
    si = get_vcenter_connection(vcenter)
    content = si.RetrieveContent()

    container = content.rootFolder
    view_type = [vim.VirtualMachine]
    recursive = True
    container_view = content.viewManager.CreateContainerView(container, view_type, recursive)

    vms = []
    for vm in container_view.view:
        try:
            vm_info = _extract_vm_info(vm, vcenter.id)
            vms.append(vm_info)
        except Exception:
            continue

    container_view.Destroy()
    return vms


def _extract_vm_info(vm, vcenter_id):
    """Extract VM information from a VM object."""
    config = vm.config
    runtime = vm.runtime
    summary = vm.summary
    guest = vm.guest

    power_state = runtime.powerState if runtime else 'unknown'
    if power_state == vim.VirtualMachinePowerState.poweredOn:
        power_state = 'poweredOn'
    elif power_state == vim.VirtualMachinePowerState.poweredOff:
        power_state = 'poweredOff'
    elif power_state == vim.VirtualMachinePowerState.suspended:
        power_state = 'suspended'

    num_cpu = config.hardware.numCPU if config and config.hardware else 0
    memory_mb = config.hardware.memoryMB if config and config.hardware else 0
    guest_os = config.guestFullName if config else 'Unknown'
    vm_version = config.version if config else 'Unknown'

    ip_address = None
    guest_state = 'unknown'
    if guest:
        ip_address = guest.ipAddress
        guest_state = guest.guestState

    cpu_usage = 0
    memory_usage = 0
    if summary and summary.quickStats:
        cpu_usage = summary.quickStats.overallCpuUsage or 0
        memory_usage = summary.quickStats.guestMemoryUsage or 0

    num_snapshots = 0
    try:
        if vm.snapshot:
            num_snapshots = _count_snapshots(vm.snapshot.rootSnapshotList)
    except Exception:
        pass

    datastores = []
    try:
        for ds in (vm.datastore or []):
            datastores.append(ds.name)
    except Exception:
        pass

    disk_committed = 0
    try:
        if summary and summary.storage:
            disk_committed = (summary.storage.committed or 0) // (1024 * 1024)
    except Exception:
        pass

    return {
        'moref': vm._moId,
        'name': vm.name,
        'vcenter_id': vcenter_id,
        'power_state': power_state,
        'guest_os': guest_os,
        'num_cpu': num_cpu,
        'memory_mb': memory_mb,
        'memory_usage_mb': memory_usage,
        'cpu_usage_mhz': cpu_usage,
        'ip_address': ip_address,
        'guest_state': guest_state,
        'num_snapshots': num_snapshots,
        'datastores': datastores,
        'disk_committed_mb': disk_committed,
        'vm_version': vm_version,
    }


def _count_snapshots(snapshot_list):
    count = 0
    for snap in (snapshot_list or []):
        count += 1
        count += _count_snapshots(snap.childSnapshotList)
    return count


def get_vm_by_moref(vcenter, moref):
    """Get a specific VM by its managed object reference."""
    si = get_vcenter_connection(vcenter)
    content = si.RetrieveContent()

    vm = _get_vm_object(content, moref)
    if not vm:
        return None
    return _extract_vm_info(vm, vcenter.id)


def get_vm_performance(vcenter, moref):
    """Get detailed performance metrics for a VM."""
    si = get_vcenter_connection(vcenter)
    content = si.RetrieveContent()

    vm = _get_vm_object(content, moref)
    if not vm:
        return None

    perf_manager = content.perfManager

    metric_ids = []
    counter_map = {}
    for counter in perf_manager.perfCounter:
        full_name = f"{counter.groupInfo.key}.{counter.nameInfo.key}.{counter.rollupType}"
        counter_map[counter.key] = full_name
        if counter.groupInfo.key in ('cpu', 'mem', 'net', 'disk'):
            metric_ids.append(vim.PerformanceManager.MetricId(
                counterId=counter.key,
                instance='*'
            ))

    if not metric_ids:
        return {}

    query_spec = vim.PerformanceManager.QuerySpec(
        entity=vm,
        metricId=metric_ids[:20],
        maxSample=1,
        intervalId=20
    )

    try:
        result = perf_manager.QueryPerf(querySpec=[query_spec])
        metrics = {}
        if result:
            for stat in result[0].value:
                counter_name = counter_map.get(stat.id.counterId, str(stat.id.counterId))
                if stat.value:
                    metrics[counter_name] = stat.value[-1]
        return metrics
    except Exception:
        return {}


def _get_vm_object(content, moref):
    """Retrieve a VM object by its moref string."""
    try:
        vm_ref = vim.VirtualMachine(moref)
        vm_ref._stub = content._stub
        _ = vm_ref.name
        return vm_ref
    except Exception:
        container = content.rootFolder
        view_type = [vim.VirtualMachine]
        container_view = content.viewManager.CreateContainerView(container, view_type, True)
        for vm in container_view.view:
            if vm._moId == moref:
                container_view.Destroy()
                return vm
        container_view.Destroy()
        return None


def power_on_vm(vcenter, moref):
    si = get_vcenter_connection(vcenter)
    content = si.RetrieveContent()
    vm = _get_vm_object(content, moref)
    if not vm:
        raise ValueError("VM not found")
    task = vm.PowerOn()
    _wait_for_task(task)


def power_off_vm(vcenter, moref):
    si = get_vcenter_connection(vcenter)
    content = si.RetrieveContent()
    vm = _get_vm_object(content, moref)
    if not vm:
        raise ValueError("VM not found")
    task = vm.PowerOff()
    _wait_for_task(task)


def shutdown_vm(vcenter, moref):
    """Graceful shutdown via VMware Tools."""
    si = get_vcenter_connection(vcenter)
    content = si.RetrieveContent()
    vm = _get_vm_object(content, moref)
    if not vm:
        raise ValueError("VM not found")
    vm.ShutdownGuest()


def reboot_vm_guest(vcenter, moref):
    """Graceful reboot via VMware Tools."""
    si = get_vcenter_connection(vcenter)
    content = si.RetrieveContent()
    vm = _get_vm_object(content, moref)
    if not vm:
        raise ValueError("VM not found")
    vm.RebootGuest()


def reset_vm(vcenter, moref):
    """Hard reset (power cycle) the VM."""
    si = get_vcenter_connection(vcenter)
    content = si.RetrieveContent()
    vm = _get_vm_object(content, moref)
    if not vm:
        raise ValueError("VM not found")
    task = vm.Reset()
    _wait_for_task(task)


def power_cycle_vm(vcenter, moref):
    """Power off then power on (hard power cycle)."""
    si = get_vcenter_connection(vcenter)
    content = si.RetrieveContent()
    vm = _get_vm_object(content, moref)
    if not vm:
        raise ValueError("VM not found")
    if vm.runtime.powerState == vim.VirtualMachinePowerState.poweredOn:
        task = vm.PowerOff()
        _wait_for_task(task)
    task = vm.PowerOn()
    _wait_for_task(task)


def get_snapshots(vcenter, moref):
    """Get all snapshots for a VM."""
    si = get_vcenter_connection(vcenter)
    content = si.RetrieveContent()
    vm = _get_vm_object(content, moref)
    if not vm:
        return []

    snapshots = []
    if vm.snapshot:
        current_snap = vm.snapshot.currentSnapshot
        current_moref = current_snap._moId if current_snap else None
        _collect_snapshots(vm.snapshot.rootSnapshotList, snapshots, current_moref)
    return snapshots


def _collect_snapshots(snapshot_list, result, current_moref, depth=0):
    for snap in (snapshot_list or []):
        result.append({
            'moref': snap.snapshot._moId,
            'name': snap.name,
            'description': snap.description,
            'create_time': snap.createTime.isoformat() if snap.createTime else None,
            'state': snap.state,
            'is_current': snap.snapshot._moId == current_moref,
            'depth': depth,
            'quiesced': snap.quiesced,
        })
        _collect_snapshots(snap.childSnapshotList, result, current_moref, depth + 1)


def create_snapshot(vcenter, moref, name, description='', memory=False, quiesce=False):
    """Create a snapshot of a VM."""
    si = get_vcenter_connection(vcenter)
    content = si.RetrieveContent()
    vm = _get_vm_object(content, moref)
    if not vm:
        raise ValueError("VM not found")
    task = vm.CreateSnapshot(
        name=name,
        description=description,
        memory=memory,
        quiesce=quiesce
    )
    _wait_for_task(task)


def revert_to_snapshot(vcenter, snapshot_moref):
    """Revert VM to a specific snapshot."""
    si = get_vcenter_connection(vcenter)
    snap_ref = vim.vm.Snapshot(snapshot_moref)
    snap_ref._stub = si._stub
    task = snap_ref.Revert()
    _wait_for_task(task)


def delete_snapshot(vcenter, snapshot_moref, remove_children=False):
    """Delete a snapshot."""
    si = get_vcenter_connection(vcenter)
    snap_ref = vim.vm.Snapshot(snapshot_moref)
    snap_ref._stub = si._stub
    task = snap_ref.Remove(removeChildren=remove_children)
    _wait_for_task(task)


def _wait_for_task(task, timeout=300):
    """Wait for a vSphere task to complete."""
    start = time.time()
    while time.time() - start < timeout:
        state = task.info.state
        if state == vim.TaskInfo.State.success:
            return task.info.result
        elif state == vim.TaskInfo.State.error:
            error_msg = str(task.info.error.msg) if task.info.error else "Unknown error"
            raise RuntimeError(f"Task failed: {error_msg}")
        time.sleep(1)
    raise TimeoutError(f"Task timed out after {timeout} seconds")
