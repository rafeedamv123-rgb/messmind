# MessMind

Predictive food waste prevention for IIT Roorkee mess halls. Managers publish weekly menus, students share pre-meal preferences, and dashboards surface pre-meal forecasts, rule-based waste risk, and post-meal learning loops.

All meal times and cutoffs use **Asia/Kolkata**.

## Stack

- **Backend:** FastAPI, SQLAlchemy, SQLite (production-ready schema)
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, Recharts, Lucide icons

## Quick start

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Default API: `http://127.0.0.1:8000`  
Default UI: `http://127.0.0.1:5173`

Seed demo data: `python -m app.seed`

## Tests

```bash
cd backend
pytest
```

## Features

- Weekly menu management with version history and meal locking
- Student pre-meal preferences (separate from post-meal feedback)
- Pre-meal forecast reports with explicit denominators
- Rule-based waste risk (Stage 1) and historical regression when data allows (Stage 2)
- Estimated potential waste reduction (meal-level only)
- Manager recommendations and decision tracking
- Daily / weekly reports, waste anomaly detection, optional AI complaint analysis
- In-app notifications when risk thresholds are met
