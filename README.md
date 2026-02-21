# BlackRock Retirement Savings API (AI GENENRATED)

Automated micro-savings system with investment projections for emerging markets retirement planning.

## Overview

This API implements an auto-saving strategy where each expense is rounded up to the next multiple of 100, and the difference (the "remanent") is invested. It applies temporal override rules (q, p, k periods), validates transactions, and projects returns across two investment vehicles: **NPS** (7.11%) and **NIFTY 50 Index Fund** (14.49%).

---

## Requirements

- **Docker** (for containerized deployment)
- **Python 3.12+** (for local development)
- `flask`, `psutil` (see `requirements.txt`)

---

## Quick Start (Docker)

```bash
# 1. Build the image
docker build -t blk-hacking-ind-{name-lastname} .

# 2. Run the container
docker run -d -p 5477:5477 blk-hacking-ind-{name-lastname}

# 3. Verify it's running
curl http://localhost:5477/health
```

Or with Docker Compose:
```bash
docker compose -f compose.yaml up -d
```

---

## Local Development

```bash
# Install dependencies
pip install flask psutil

# Run the server
python main.py
# → Listening on http://0.0.0.0:5477
```

---

## Running Tests

```bash
# From the project root:
python3 tests/test_api.py

# With pytest (if installed):
pip install pytest
pytest tests/ -v
```

Tests are organized as:
- **Unit tests** — business logic (ceiling, tax slabs, q/p rules, compound interest)
- **Integration tests** — all 5 Flask endpoints via test client

---

## API Endpoints

All endpoints are prefixed with `/blackrock/challenge/v1/`.

### `POST /transactions:parse`
Calculates `ceiling` (next multiple of 100) and `remanent` (ceiling − amount) for each expense.

**Input:**
```json
[
  {"date": "2023-10-12 20:15:30", "amount": 250},
  {"date": "2023-07-01 21:59:00", "amount": 620}
]
```

**Output:**
```json
[
  {"date": "2023-10-12 20:15:30", "amount": 250, "ceiling": 300, "remanent": 50},
  {"date": "2023-07-01 21:59:00", "amount": 620, "ceiling": 700, "remanent": 80}
]
```

---

### `POST /transactions:validator`
Validates transactions. Flags negative amounts and duplicate timestamps.

**Input:**
```json
{
  "wage": 50000,
  "transactions": [
    {"date": "2023-01-15 10:30:00", "amount": 2000},
    {"date": "2023-07-10 09:15:00", "amount": -250}
  ]
}
```

**Output:**
```json
{
  "valid": [{"date": "2023-01-15 10:30:00", "amount": 2000.0, ...}],
  "invalid": [{"date": "2023-07-10 09:15:00", "amount": -250.0, "message": "Negative amounts are not allowed"}]
}
```

---

### `POST /transactions:filter`
Applies q/p/k period rules with full validation. Returns `inkPeriod` flag per transaction.

**Period rules:**
- **q** — Fixed override: replaces remanent with `fixed` amount (latest-start q period wins on overlap; same-start → first in list)
- **p** — Additive: all matching p periods' `extra` amounts are summed and added to remanent
- **k** — Grouping: marks whether transaction falls in each k period

---

### `POST /returns:nps`
NPS returns with tax benefit calculation.

- Rate: **7.11%** compounded annually
- NPS Deduction: `min(invested, 10% of annual_income, ₹2,00,000)`
- Tax Benefit: `Tax(income) − Tax(income − NPS_Deduction)`
- Returns `profit` = inflation-adjusted real value − principal

### `POST /returns:index`
Index Fund returns (no restrictions).

- Rate: **14.49%** compounded annually
- No tax benefit

**Input (both):**
```json
{
  "age": 29,
  "wage": 50000,
  "inflation": 5.5,
  "q": [...], "p": [...], "k": [...],
  "transactions": [...]
}
```

**Output:**
```json
{
  "totalTransactionAmount": 1725.0,
  "totalCeiling": 1900.0,
  "savingsByDates": [
    {
      "start": "2023-01-01 00:00:00",
      "end": "2023-12-31 23:59:59",
      "amount": 145.0,
      "profit": 86.88,
      "taxBenefit": 0.0
    }
  ]
}
```

---

### `GET /performance`
System metrics: uptime, memory usage, thread count.

```json
{
  "time": "00:01:32.411",
  "memory": "28.43 MB",
  "threads": 4
}
```

---

## Key Formulas

| Formula | Expression |
|---|---|
| Ceiling | `ceil(amount / 100) * 100` |
| Compound Interest | `A = P × (1 + r)^t` |
| Inflation Adjustment | `A_real = A / (1 + inflation%)^t` |
| Years to Retirement | `max(60 - age, 5)` |
| NPS Deduction | `min(invested, 10% × annual_income, ₹2,00,000)` |

---

## Tax Slabs (Simplified Indian)

| Income Range | Rate |
|---|---|
| ₹0 – ₹7,00,000 | 0% |
| ₹7,00,001 – ₹10,00,000 | 10% on amount above ₹7L |
| ₹10,00,001 – ₹12,00,000 | 15% on amount above ₹10L |
| ₹12,00,001 – ₹15,00,000 | 20% on amount above ₹12L |
| Above ₹15,00,000 | 30% on amount above ₹15L |

---

## Project Structure

```
blackrock-api/
├── main.py          # Flask app + all 5 endpoints
├── business.py      # Financial logic (pure functions, no framework deps)
├── requirements.txt
├── Dockerfile
├── compose.yaml
├── README.md
└── tests/
    └── test_api.py  # 44 unit + integration tests
```

---

## Design Decisions

- **Flask** — lightweight, production-ready, zero cold-start overhead for a single-process API
- **Separation of concerns** — `business.py` contains only pure functions; `main.py` only HTTP handling
- **Non-root Docker user** — security best practice
- **Immutable intermediate rounding** — q/p are applied in strict order per spec (q overrides first, then p adds)
