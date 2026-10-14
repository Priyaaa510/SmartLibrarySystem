# Smart Library Management & Book Recommendation System

A full-stack library management system modelled on how real libraries work.

- **Backend:** Python, FastAPI, SQLAlchemy 2.0 and **PostgreSQL** (psycopg 3), with JWT auth
- **Frontend:** React 18, TypeScript, Vite and React Router

## Features

| Area | What it does |
|---|---|
| **Accounts & roles** | Admin, librarian and member roles; self-registration; JWT login; profile and password change; member codes (`LIB000003`) |
| **Membership plans** | Student / Faculty / Public tiers, each with its own borrowing limit, loan period, renewals, fine per day, fine ceiling and validity; membership expiry & renewal |
| **Catalog (OPAC)** | Title records plus **physical copies** with barcodes, shelf locations, condition and price; search by title/author/ISBN/publisher/subject; filters, sorting and pagination; cover images |
| **Circulation desk** | Issue by barcode or title, return by barcode, renew, mark lost, mark damaged. Eligibility is checked before every issue: active account, membership not expired, under the borrowing limit, no overdue items, unpaid fines under the ceiling |
| **Holds / reservations** | Queue with positions. A returned copy goes to the **hold shelf** for the next member, who has 3 days to collect it. Uncollected holds expire and pass to the next member. A book with members waiting can't be renewed |
| **Fines** | Overdue fines added automatically on return (rate per plan); lost-book charge (replacement price + processing fee); damage fees; manual charges; pay or waive |
| **Notifications** | In-app bell: book issued or returned, hold ready, due soon, overdue, fines. Reminders are sent by an hourly background job and de-duplicated per day |
| **Reviews & ratings** | Members who have borrowed a book can rate and review it |
| **Recommendations** | Strategy pattern: *category* (your interests), *history* (similar to what you borrowed), *popular*, and a *hybrid* blend; plus "similar books" |
| **Reports** | Dashboard KPIs, circulation trend chart, loans by category, top books, overdue list, per-member report (computed concurrently with a thread pool), audit log, **CSV export** (books / loans / overdue / fines / members), search-performance benchmark |
| **Data integrity** | Row-level locks (`SELECT … FOR UPDATE`) during circulation; partial unique indexes so a copy can have only one active loan and a member only one open hold per title; members are deactivated, never deleted |

## Setup

### 1. PostgreSQL
Create two databases. The second one is wiped by the test suite.
```sql
CREATE DATABASE smart_library;
CREATE DATABASE smart_library_test;
```

### 2. Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
copy .env.example .env            # then set your Postgres password in .env
uvicorn app.main:app --reload
uvicorn app.main:app --reload --port 8002 
```
On first start the app creates the tables and loads demo data: 34 books, 6 members, plus loan history, holds and fines.
- API: http://127.0.0.1:8000
- Swagger docs: http://127.0.0.1:8000/docs (click **Authorize** and paste a token from `/api/auth/login`)

To reset to fresh demo data:
```bash
python -m app.seed --reset
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. Vite proxies `/api` to the backend.

### Demo accounts
| Role | Email | Password |
|---|---|---|
| Admin | admin@library.com | admin123 |
| Librarian | librarian@library.com | librarian123 |
| Member | rahul@example.com (also priya, arjun, sneha, vikram, ananya @example.com) | member123 |

## Tests & quality
```bash
cd backend
python -m pytest                                   # 31 tests against smart_library_test
python -m pytest --cov=app --cov-report=term-missing
python -m ruff check app tests
python -m mypy app
```
The tests move a mocked library clock forward to exercise overdue fines, renewal limits and hold expiry.

## Demo walkthrough
1. **Librarian → Dashboard:** KPIs, the 30-day circulation chart, overdue items and the hold shelf.
2. **Circulation Desk:** issue *The Alchemist* to Arjun. He hits his Student limit (3/3) and the desk blocks further issues.
3. **Return** barcode `BK00005-001` (*Refactoring*). The desk says to put it on the hold shelf for Rahul, who is first in the queue.
4. **Sign in as Rahul:** a "ready for pickup" banner, an overdue warning with the fine so far, notifications, and renew buttons. Recommendations exclude books he has borrowed or is waiting for.
5. **Reports:** charts, member report, CSV exports and the search-performance benchmark.
6. **Settings (admin):** change a plan's borrowing rules or manage categories.

## Project layout
```
backend/app
  main.py              FastAPI app, startup (create tables, seed, scheduler), error handlers
  config.py            settings from .env
  database.py          engine / session
  models.py            ORM models (users, plans, books, copies, loans, reservations, fines, reviews, notifications, audit)
  schemas.py           Pydantic request/response models
  security.py          bcrypt + JWT, role dependencies
  services/            circulation rules, catalog queries, members
  routers/             auth, catalog, members, circulation, account, reports
  recommendations.py   Strategy-pattern recommenders
  reports.py           analytics, concurrent member report, CSV export
  performance.py       linear scan vs dict vs Postgres index
  seed.py              demo data
frontend/src
  api.ts, auth.tsx     API client + auth context
  components/          layout, tables, charts, forms, UI kit
  pages/               dashboard, desk, catalog, book, loans/holds/fines, members, reports, settings, profile
```

> **Note on schema changes:** tables are created with `Base.metadata.create_all`. After changing models during development, run `python -m app.seed --reset`. A production deployment should add Alembic migrations.
