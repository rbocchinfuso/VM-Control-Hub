from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


# Association table — users <-> groups (many-to-many)
user_groups = db.Table(
    'user_groups',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('groups.id', ondelete='CASCADE'), primary_key=True),
)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='viewer')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    mfa_secret = db.Column(db.String(64), nullable=True)
    mfa_enabled = db.Column(db.Boolean, default=False, nullable=False)

    vm_permissions = db.relationship('VMPermission', backref='user', lazy='dynamic',
                                     cascade='all, delete-orphan')
    groups = db.relationship('Group', secondary=user_groups, back_populates='members',
                             lazy='select')

    ROLES = ['admin', 'operator', 'viewer']

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

    def is_operator(self):
        return self.role in ['admin', 'operator']

    def _group_ids(self):
        return [g.id for g in self.groups]

    def can_control_vm(self, vm_moref, vcenter_id):
        """Power operations: admin always yes; operator/viewer need can_power=True on a permission."""
        if self.role == 'admin':
            return True
        # Direct per-user permission
        perm = VMPermission.query.filter_by(
            user_id=self.id, vm_moref=vm_moref, vcenter_id=vcenter_id
        ).first()
        if perm and perm.can_power:
            return True
        # Group-inherited permission
        gids = self._group_ids()
        if gids:
            gperm = GroupVMPermission.query.filter(
                GroupVMPermission.group_id.in_(gids),
                GroupVMPermission.vm_moref == vm_moref,
                GroupVMPermission.vcenter_id == vcenter_id,
                GroupVMPermission.can_power == True,
            ).first()
            if gperm:
                return True
        return False

    def can_snapshot_vm(self, vm_moref, vcenter_id):
        """Snapshot operations: admin always yes; operators never; viewers need can_snapshot=True."""
        if self.role == 'admin':
            return True
        if self.role == 'operator':
            return False  # Operators are power-only; snapshots are admin privilege
        # Viewer: need explicit can_snapshot grant
        perm = VMPermission.query.filter_by(
            user_id=self.id, vm_moref=vm_moref, vcenter_id=vcenter_id
        ).first()
        if perm and perm.can_snapshot:
            return True
        gids = self._group_ids()
        if gids:
            gperm = GroupVMPermission.query.filter(
                GroupVMPermission.group_id.in_(gids),
                GroupVMPermission.vm_moref == vm_moref,
                GroupVMPermission.vcenter_id == vcenter_id,
                GroupVMPermission.can_snapshot == True,
            ).first()
            if gperm:
                return True
        return False

    def can_view_vm(self, vm_moref, vcenter_id):
        """Visibility: admin always yes; operator and viewer need an explicit permission."""
        if self.role == 'admin':
            return True
        # Direct per-user permission (operator or viewer)
        perm = VMPermission.query.filter_by(
            user_id=self.id, vm_moref=vm_moref, vcenter_id=vcenter_id
        ).first()
        if perm:
            return True
        # Group-inherited permission
        gids = self._group_ids()
        if gids:
            gperm = GroupVMPermission.query.filter(
                GroupVMPermission.group_id.in_(gids),
                GroupVMPermission.vm_moref == vm_moref,
                GroupVMPermission.vcenter_id == vcenter_id,
            ).first()
            if gperm:
                return True
        return False

    def accessible_vcenter_ids(self):
        """Return a set of vcenter IDs this user is allowed to see.

        Admins see every active vCenter.
        Operators and viewers only see vCenters where they have at least one
        VM permission (granted directly or through a group).
        """
        if self.role == 'admin':
            from app.models import VCenter
            return {vc.id for vc in VCenter.query.filter_by(is_active=True).all()}

        ids = set()
        for perm in self.vm_permissions:
            ids.add(perm.vcenter_id)
        for group in self.groups:
            for gperm in group.vm_permissions:
                ids.add(gperm.vcenter_id)
        return ids

    def __repr__(self):
        return f'<User {self.username}>'


class Group(db.Model):
    __tablename__ = 'groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    members = db.relationship('User', secondary=user_groups, back_populates='groups',
                              lazy='select')
    vm_permissions = db.relationship('GroupVMPermission', backref='group',
                                     lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Group {self.name}>'


class GroupVMPermission(db.Model):
    __tablename__ = 'group_vm_permissions'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id', ondelete='CASCADE'), nullable=False)
    vcenter_id = db.Column(db.Integer, db.ForeignKey('vcenters.id', ondelete='CASCADE'), nullable=False)
    vm_moref = db.Column(db.String(50), nullable=False)
    vm_name = db.Column(db.String(255))
    can_power = db.Column(db.Boolean, default=True)
    can_snapshot = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('group_id', 'vcenter_id', 'vm_moref', name='unique_group_vm_permission'),
    )


class VCenter(db.Model):
    __tablename__ = 'vcenters'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    host = db.Column(db.String(255), nullable=False)
    port = db.Column(db.Integer, default=443)
    username = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(256), nullable=False)
    verify_ssl = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_connected = db.Column(db.DateTime)
    connection_status = db.Column(db.String(20), default='unknown')

    vm_permissions = db.relationship('VMPermission', backref='vcenter', lazy='dynamic')

    def __repr__(self):
        return f'<VCenter {self.name} ({self.host})>'


class VMPermission(db.Model):
    __tablename__ = 'vm_permissions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    vcenter_id = db.Column(db.Integer, db.ForeignKey('vcenters.id', ondelete='CASCADE'), nullable=False)
    vm_moref = db.Column(db.String(50), nullable=False)
    vm_name = db.Column(db.String(255))
    can_power = db.Column(db.Boolean, default=True)
    can_snapshot = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'vcenter_id', 'vm_moref', name='unique_vm_permission'),
    )


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    target = db.Column(db.String(255))
    vcenter_id = db.Column(db.Integer, db.ForeignKey('vcenters.id'))
    vm_moref = db.Column(db.String(50))
    vm_name = db.Column(db.String(255))
    result = db.Column(db.String(20))
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='audit_logs')
