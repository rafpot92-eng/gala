# Development Guide

## 1. Prerequisites

Install:

* Git
* Python 3.11+
* Node.js 20+
* npm
* PostgreSQL client
* Databricks CLI
* access to a Databricks workspace
* access to the project's Lakebase/PostgreSQL instance

You also need permission to:

* create/use Databricks jobs
* create/use notebooks
* access the required model/embedding endpoint
* connect to Lakebase
* create the PostgreSQL schema

---

# 2. Clone the repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd meczyki-editorial
```

---

# 3. Configure environment

Copy:

```bash
cp .env.example .env
```

The root `.env` contains local development configuration.

Example:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE

JWT_SECRET=replace-with-a-long-random-value

FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000

DATABRICKS_WORKSPACE_URL=https://YOUR-WORKSPACE.cloud.databricks.com
DATABRICKS_CLIENT_ID=...
DATABRICKS_CLIENT_SECRET=...

COOKIE_SECURE=false
COOKIE_SAMESITE=lax
```

Do not commit `.env`.

---

# 4. Initialize the database

Run:

```bash
./scripts/db-init.sh
```

This executes:

```text
database/001_schema.sql
database/002_indexes.sql
database/003_seed_development.sql
```

The production database should be initialized using the controlled deployment/migration process rather than development seed data.

---

# 5. Backend setup

```bash
cd backend

python -m venv .venv
```

Activate the environment.

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows:

```powershell
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start FastAPI:

```bash
uvicorn app.main:app --reload --port 8000
```

Test:

```bash
curl http://localhost:8000/health
```

Expected:

```json
{
  "status": "ok"
}
```

---

# 6. Frontend setup

Open another terminal:

```bash
cd frontend
npm install
```

Create:

```bash
cp .env.local.example .env.local
```

Set:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Start:

```bash
npm run dev
```

Open:

```text
http://localhost:3000
```

---

# 7. Authentication

Click:

```text
Continue with Databricks
```

The browser is redirected to Databricks.

After authentication:

```text
Databricks
    ↓
FastAPI callback
    ↓
Lakebase user lookup
    ↓
HTTP-only session cookie
    ↓
Next.js dashboard
```

The application does not store the JWT in `localStorage`.

---

# 8. Local development roles

The database controls application roles.

Possible roles:

```text
viewer
editor
publisher
```

Example:

```sql
UPDATE users
SET role = 'editor'
WHERE email = 'editor@example.com';
```

Publisher:

```sql
UPDATE users
SET role = 'publisher'
WHERE email = 'publisher@example.com';
```

Do not automatically give every authenticated Databricks user editor permissions.

New users should default to:

```text
viewer
```

---

# 9. Running the complete application

Terminal 1:

```bash
./scripts/dev.sh
```

Or manually:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Terminal 2:

```bash
cd frontend
npm run dev
```

Databricks jobs run independently.

---

# 10. Testing

Run backend tests:

```bash
./scripts/test.sh
```

Frontend:

```bash
cd frontend
npm run build
```

The production build must complete successfully before deployment.

---

# 11. Development workflow

When implementing a feature:

```text
1. Modify database schema if required
2. Modify Databricks code if required
3. Modify FastAPI
4. Modify frontend
5. Run tests
6. Test workflow manually
7. Commit
8. Deploy
```

Never modify the production database manually without recording the migration.

---

# 12. Important development rule

The AI agent must never directly perform:

```text
approved
published
```

The agent only creates:

```text
draft
```

Human editors move articles to:

```text
ready_for_review
```

Authorized editors approve:

```text
approved
```

Only publishers can move:

```text
approved → published
```
