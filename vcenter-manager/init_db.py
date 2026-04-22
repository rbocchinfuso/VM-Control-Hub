"""Initialize the database and create a default admin user.

Also applies lightweight column migrations for existing deployments so that
`docker-compose up -d --build` is the only step needed when new fields are added.
"""
import os
from sqlalchemy import text, inspect as sa_inspect
from app import create_app, db
from app.models import User, Group, GroupVMPermission, VCenter, VMPermission, AuditLog

app = create_app()

with app.app_context():
    # Create all tables that don't exist yet
    db.create_all()
    print("Database tables ensured.")

    # ── Lightweight column migrations ──────────────────────────────────────
    # Add new columns to existing tables without dropping data.
    _inspector = sa_inspect(db.engine)

    def _add_column_if_missing(table, column_def):
        cols = [c['name'] for c in _inspector.get_columns(table)]
        if column_def.split()[0] not in cols:
            with db.engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column_def}'))
            print(f"  Migrated: {table}.{column_def.split()[0]} added.")

    _add_column_if_missing('users', 'mfa_secret VARCHAR(64)')
    _add_column_if_missing('users', 'mfa_enabled BOOLEAN NOT NULL DEFAULT 0')

    # ── Default admin user ─────────────────────────────────────────────────
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
    admin_password = os.environ.get('ADMIN_PASSWORD', 'changeme123')

    existing = User.query.filter_by(username=admin_username).first()
    if not existing:
        admin = User(
            username=admin_username,
            email=admin_email,
            role='admin',
            is_active=True
        )
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()
        print(f"Admin user '{admin_username}' created with password '{admin_password}'")
        print("IMPORTANT: Change this password after first login!")
    else:
        print(f"Admin user '{admin_username}' already exists, skipping.")
