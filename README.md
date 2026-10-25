# SepticComply

**Septic Tank Pump-Out Reminder & Compliance Micro-SaaS**

Automated compliance scheduling for septic system operators across Texas, Florida, California, Ohio, and Pennsylvania.

## Features

- **5-State Compliance Engine**: Deterministic scheduling based on verified state regulations (TX, FL, CA, OH, PA)
- **Tank Management**: CRUD operations for septic tanks with validation
- **Compliance Scheduling**: Automatic next-due calculation with escalation chain (90/60/30/7 days)
- **Inspector Reports**: One-click PDF-ready compliance reports for regulators
- **Service History**: Track pump-outs, maintenance, and hauler records
- **Dashboard Analytics**: Real-time stats on compliance status across portfolio
- **OpenAPI Documentation**: Auto-generated API docs at `/openapi.json`

## Quick Start

### Prerequisites
- Python 3.11+
- pip

### Installation

```bash
cd septic-scheduler
pip install -r requirements.txt
```

### Run API Server

```bash
uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
```

API will be available at `http://localhost:8000`
- Interactive docs: `http://localhost:8000/docs`
- OpenAPI schema: `http://localhost:8000/openapi.json`
- Health check: `http://localhost:8000/health`

### Run Tests

```bash
pytest tests/ -v
```

## API Endpoints

### Tanks
- `POST /tanks` - Create tank
- `GET /tanks` - List tanks (paginated)
- `GET /tanks/{id}` - Get tank
- `PATCH /tanks/{id}` - Update tank
- `DELETE /tanks/{id}` - Delete tank

### Compliance
- `GET /tanks/{id}/schedule` - Get compliance schedule
- `GET /tanks/{id}/escalation-schedule` - Get notification escalation schedule
- `GET /tanks/{id}/inspector-report` - Generate inspector report

### Service History
- `POST /tanks/{id}/service` - Add service record
- `GET /tanks/{id}/service` - Get service history

### Dashboard
- `GET /dashboard/stats` - Get portfolio statistics

## Supported States & Rules

| State | Regulator | Default Interval | Key Features |
|-------|-----------|------------------|--------------|
| Texas (TX) | TCEQ | Table-driven (size × household) | ATU track, $25k/day penalty, annual July 1 report |
| Florida (FL) | FDEP | 3 years | County variance flags, $15k/day penalty |
| California (CA) | RWQCB/County | 3 years | Real estate transfer triggers, county overrides |
| Ohio (OH) | ODH/Local Boards | 3 years | Local board variance, hauler checklist |
| Pennsylvania (PA) | PA DEP/Municipal | 3 years (mandatory) | Municipal SMP overrides, PSMA haulers |

## Project Structure

```
septic-scheduler/
├── config/
│   └── compliance_rules_v1.json    # Versioned compliance rules
├── src/
│   ├── __init__.py
│   ├── api.py                      # FastAPI REST API
│   ├── compliance_engine.py        # Deterministic scheduling engine
│   ├── database.py                 # SQLite persistence layer
├── tests/
│   ├── test_compliance_engine.py   # Engine unit tests (24 tests)
│   ├── test_integration.py         # API integration tests (20 tests)
│   └── test_security_regression.py # Security regression tests (15 tests)
├── data/
│   └── septiccomply.db             # SQLite database
├── requirements.txt
└── README.md
```

## Compliance Rules Versioning

Rules are stored in `config/compliance_rules_v1.json` with:
- `version`: Engine version
- `verified_date`: Date rules were verified against sources
- Per-state rules with sources and verification dates
- Cross-state rules for ATU, cesspools, escalation chain

Regulatory drift detection runs quarterly via automated source URL checking.

## Deployment

### Railway (API + PostgreSQL)
```bash
railway login
railway up
# Add PostgreSQL plugin
# Set environment variables
```

### Vercel (Frontend)
```bash
vercel --prod
```

### GitHub Actions CI/CD
Pipeline runs on every push to main:
1. Lint (ruff)
2. Unit tests (pytest)
3. Integration tests
4. Security scan (bandit, pip-audit)
5. Compliance drift check
6. Deploy to Railway + Vercel

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `PORT` | API server port | No (default: 8000) |
| `DATABASE_URL` | PostgreSQL connection string | For Railway |
| `STRIPE_SECRET_KEY` | Stripe secret key | For payments |
| `STRIPE_PUBLISHABLE_KEY` | Stripe publishable key | For payments |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret | For payments |
| `RAZORPAY_KEY_ID` | Razorpay key ID | For INR payments |
| `RAZORPAY_KEY_SECRET` | Razorpay key secret | For INR payments |
| `RAZORPAY_WEBHOOK_SECRET` | Razorpay webhook secret | For INR payments |

## Testing

```bash
# All tests (112 tests)
pytest tests/ -v

# Engine tests only
pytest tests/test_compliance_engine.py -v

# Integration tests only
pytest tests/test_integration.py -v

# Security regression tests
pytest tests/test_security_regression.py -v
```

## License

Proprietary - Bee Ryzen Limited Company