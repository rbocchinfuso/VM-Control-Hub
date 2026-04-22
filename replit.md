# Workspace

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.

Also contains a standalone Python/Flask VMware vCenter Manager application in `vcenter-manager/`.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)

## Key Commands

- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `pnpm --filter @workspace/api-server run dev` — run API server locally

See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details.

## vCenter Manager (Python/Flask — `vcenter-manager/`)

A standalone containerized application for managing VMware vCenter servers.

### Quick Start
```bash
cd vcenter-manager
cp .env.example .env  # Edit SECRET_KEY and credentials
docker-compose up -d
```

Access at http://localhost:5000 — default login: `admin` / `changeme123`

### Features
- Multi-vCenter server management
- VM status monitoring and performance metrics
- Power controls: graceful reboot/shutdown, hard reset, power cycle
- Snapshot management: create, revert, delete
- Role-based access: Admin, Operator, Viewer
- Per-VM user permission assignment
- Audit log of all actions

### Stack
- Python 3.12 + Flask 3.x
- pyVmomi (VMware vSphere SDK for Python)
- Flask-SQLAlchemy + Flask-Login
- SQLite (default) or PostgreSQL
- Gunicorn (production WSGI server)
- Bootstrap 5.3 (dark theme UI)
- Docker + Docker Compose
