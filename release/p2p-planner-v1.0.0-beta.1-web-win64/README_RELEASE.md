# P2P Planner v1.0.0-beta.1 — Web Core
This is the first beta web/self-host release of P2P Planner.

## Requirements

- Windows x64
- Docker Desktop for PostgreSQL
- Node.js for serving the built frontend

## Start PostgreSQL

From this folder:

`powershell
docker compose -f docker-compose.dev.yml up -d
``nConfigure backend
Copy:
backend\.env.example
to:
backend\.env
For local beta testing, default values are usually enough.
Start backend
cd backend
.\p2p-planner-backend.exe
Backend listens on:
[http://127.0.0.1:18080](http://127.0.0.1:18080)
Health check:
[http://127.0.0.1:18080/api/v1/health](http://127.0.0.1:18080/api/v1/health)
Start frontend
In another terminal:
cd frontend
npx serve -s dist -l 5173
Open:
[http://127.0.0.1:5173](http://127.0.0.1:5173)
Current beta scope
Working:
sign up / sign in / refresh session
workspaces
boards
columns
cards
card details drawer
drag-and-drop cards between columns
user appearance
board appearance
activity/audit surfaces
Not ready yet:
native mobile app
desktop installer
real offline/local-first runtime
sync between devices
P2P/relay
full backup/import/export
labels/checklists/comments

