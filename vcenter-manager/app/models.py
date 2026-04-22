from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


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

    vm_permissions = db.relationship('VMPermission', backref='user', lazy='dynamic')

    ROLES = ['admin', 'operator', 'viewer']

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

    def is_operator(self):
        return self.role in ['admin', 'operator']

    def can_control_vm(self, vm_moref, vcenter_id):
        if self.role == 'admin':
            return True
        if self.role == 'operator':
            perm = VMPermission.query.filter_by(
                user_id=self.id, vm_moref=vm_moref, vcenter_id=vcenter_id
            ).first()
            return perm is not None
        return False

    def can_view_vm(self, vm_moref, vcenter_id):
        if self.role in ['admin', 'operator']:
            return True
        perm = VMPermission.query.filter_by(
            user_id=self.id, vm_moref=vm_moref, vcenter_id=vcenter_id
        ).first()
        return perm is not None

    def __repr__(self):
        return f'<User {self.username}>'


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
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    vcenter_id = db.Column(db.Integer, db.ForeignKey('vcenters.id'), nullable=False)
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
