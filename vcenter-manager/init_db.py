"""Initialize the database and create a default admin user."""
import os
from app import create_app, db
from app.models import User, Group, GroupVMPermission, VCenter, VMPermission, AuditLog

app = create_app()

with app.app_context():
    db.create_all()
    print("Database tables created.")

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
