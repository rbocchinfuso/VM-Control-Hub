# vCenter Manager

A Python/Flask web application for managing VMware vCenter servers. Monitor VM status and performance, control VM power states, manage snapshots, and enforce role-based access control — all from a single web interface.

## Features

- **Multi-vCenter support** — connect to and manage multiple vCenter servers simultaneously
- **VM Dashboard** — real-time VM status, CPU/memory/disk usage, guest OS info
- **Power Controls**:
  - Graceful Reboot (via VMware Tools)
  - Graceful Shutdown (via VMware Tools)
  - Hard Reset (equivalent to pressing the reset button)
  - Power Cycle (hard off → power on)
  - Power On / Power Off
- **Snapshot Management** — create, revert, and delete snapshots with optional memory and quiesce support
- **Role-Based Access Control**:
  - **Admin** — full access to everything
  - **Operator** — can view and control assigned VMs
  - **Viewer** — read-only access to assigned VMs
  - Per-VM permission assignment for Operator and Viewer roles
- **Audit Log** — all power and snapshot actions are logged with user and result
- **Dockerized** — ships with Docker Compose for easy deployment

## Quick Start (Docker)

### SQLite (simple, single-node)

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env and set SECRET_KEY to a long random string

# Build and start
docker-compose up -d

# Check logs
docker-compose logs -f app
```

Access the app at **http://localhost:5000**

Default credentials: `admin` / `changeme123` — **change this immediately after login!**

### PostgreSQL (production recommended)

```bash
cp .env.example .env
# Set SECRET_KEY, ADMIN_PASSWORD, DB_PASSWORD in .env

docker-compose -f docker-compose.postgres.yml up -d
```

## Configuration

Set these environment variables (or use `.env`):

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *required* | Flask session secret (use a long random string) |
| `DATABASE_URL` | SQLite | PostgreSQL: `postgresql://user:pass@host/db` |
| `ADMIN_USERNAME` | `admin` | Initial admin username |
| `ADMIN_EMAIL` | `admin@example.com` | Initial admin email |
| `ADMIN_PASSWORD` | `changeme123` | Initial admin password |
| `WORKERS` | `4` | Gunicorn worker count |

## Architecture

```
vcenter-manager/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── models.py            # SQLAlchemy models (User, VCenter, VMPermission, AuditLog)
│   ├── vcenter_client.py    # pyVmomi vCenter connection and VM operations
│   ├── routes/
│   │   ├── auth.py          # Login, logout, profile
│   │   ├── main.py          # Dashboard
│   │   ├── vcenters.py      # vCenter CRUD
│   │   ├── vms.py           # VM list, detail, power actions
│   │   ├── snapshots.py     # Snapshot create/revert/delete
│   │   ├── users.py         # User management and permissions
│   │   └── api.py           # JSON API endpoints
│   ├── static/              # CSS, JS
│   └── templates/           # Jinja2 HTML templates
├── run.py                   # Gunicorn entry point
├── init_db.py               # Database initialization script
├── Dockerfile
├── docker-compose.yml       # SQLite deployment
└── docker-compose.postgres.yml  # PostgreSQL deployment
```

## Security Notes

- Change the default admin password immediately after first login
- Set `SECRET_KEY` to a cryptographically random string (e.g., `python -c "import secrets; print(secrets.token_hex(32))"`)
- Consider enabling SSL verification for vCenter connections in production
- Use PostgreSQL in production (more robust than SQLite for concurrent access)
- Place behind an nginx reverse proxy with HTTPS for external access
- vCenter credentials are stored in the database — secure your database accordingly
