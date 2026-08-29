# Schemes & Integrations Backend (Backend Dev 3)

A production-structured but hackathon-friendly FastAPI backend implementing:

- **Feature 10** — Automatic government scheme matching (deterministic rule engine)
- **Feature 12** — Eligibility explanation (condition-by-condition, reusing the same engine)
- **Feature 9** — Post-loan business health checks via WhatsApp (Twilio Sandbox / DEMO_MODE), with a mentor-alert rule

> ⚠️ **Government eligibility disclaimer**: The scheme criteria bundled in `app/data/schemes.json` are **demo/configurable data only**, simplified for hackathon purposes. They are **not** an authoritative source of government scheme rules. **Final eligibility is subject to government/lender verification.** This line is surfaced everywhere the system reports eligibility.

---

## 1. Architecture

```
User Profile
     ↓
Deterministic Rule Engine   (app/rules.py, reads app/data/schemes.json)
     ↓
Matched Scheme IDs           (Feature 10 — /api/schemes/match)
     ↓
Condition-by-condition results (Feature 12 — /api/schemes/explain)
     ↓
AI/RAG Layer (owned by AI/RAG lead — NOT part of this backend)
     ↓
Natural-language explanation
```

Key design principles:

- **One rule engine, no duplication.** `app/rules.py` contains a single deterministic evaluation function (`evaluate_scheme`) used by *both* the matching endpoint and the explanation endpoint. There is no second, independent eligibility engine.
- **Rules are data, not code.** All scheme eligibility criteria live in `app/data/schemes.json`. Adding/editing/removing a scheme never requires touching Python.
- **The LLM never decides eligibility.** The rule engine's structured JSON output (pass/fail, score, condition list, actual vs expected) is designed to be handed directly to an AI/RAG layer, which may only *explain* the deterministic result in natural language — it must not override it.
- **DEMO_MODE by default.** The whole project — including WhatsApp messaging — runs with zero external credentials. Twilio is only required if you explicitly set `DEMO_MODE=false`.

---

## 2. Folder structure

```
backend/
│
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI app, all HTTP routes, startup/shutdown
│   ├── config.py          # Environment-variable driven settings (no hardcoded secrets)
│   ├── database.py        # SQLite connection + schema (loans, survey_requests, survey_responses, mentor_alerts)
│   ├── schemas.py         # Pydantic request/response models
│   ├── rules.py           # THE deterministic scheme rule engine (Feature 10 & 12)
│   ├── health_checks.py   # Survey send/parse/record + mentor-alert logic (Feature 9)
│   ├── whatsapp.py        # Twilio WhatsApp wrapper + DEMO_MODE simulation
│   ├── scheduler.py       # APScheduler periodic survey broadcast job
│   │
│   └── data/
│       └── schemes.json   # Scheme eligibility criteria (structured, editable, NOT Python)
│
├── tests/
│   ├── test_rules.py          # Feature 10 & 12 tests
│   └── test_health_checks.py  # Feature 9 tests
│
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── run.bat
```

---

## 3. Installation

### Prerequisites

- Python 3.10+
- pip

### Windows

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Or simply double-click / run `run.bat`, which does all of the above automatically (creates the venv if missing, installs requirements, copies `.env.example` to `.env` if missing, then starts the server).

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

The server starts on **http://127.0.0.1:8000** by default.

---

## 4. Environment variables

Copy `.env.example` to `.env` and adjust as needed. **`.env` is git-ignored — never commit real credentials.**

| Variable | Default | Description |
|---|---|---|
| `DEMO_MODE` | `true` | `true`: WhatsApp messages are simulated/logged, no Twilio account needed. `false`: real messages are sent via Twilio. |
| `TWILIO_ACCOUNT_SID` | *(empty)* | Required only when `DEMO_MODE=false`. |
| `TWILIO_AUTH_TOKEN` | *(empty)* | Required only when `DEMO_MODE=false`. Never hardcode this. |
| `TWILIO_WHATSAPP_FROM` | `whatsapp:+14155238886` | Twilio WhatsApp Sandbox sender number. |
| `SURVEY_INTERVAL_MINUTES` | `3` | How often the periodic health-check survey is broadcast to all loans. Fully configurable — never hardcoded in code. |
| `CONCERNING_ANSWER_ALERT_THRESHOLD` | `2` | Number of concerning answers (out of 3) that triggers a mentor alert. |
| `DATABASE_PATH` | `app_data.db` | Path to the SQLite database file. |

The application **never crashes if `.env` is missing** — `app/config.py` loads it with `python-dotenv` and falls back to sane defaults / OS environment variables.

---

## 5. Running the server

```bash
uvicorn app.main:app --reload
```

On startup the app:
1. Initializes the SQLite database (creates tables if they don't exist).
2. Starts the APScheduler background job that broadcasts the WhatsApp health-check survey to every loan on the `SURVEY_INTERVAL_MINUTES` interval (duplicate-job-safe — calling startup twice will not create a second job).

### Swagger documentation

Once running, open:

- **http://127.0.0.1:8000/docs** — interactive Swagger UI
- **http://127.0.0.1:8000/redoc** — ReDoc UI

---

## 6. API reference & examples

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + config check |
| GET | `/api/schemes` | List all configured schemes and their criteria |
| POST | `/api/schemes/match` | Feature 10 — match a business profile against all schemes |
| POST | `/api/schemes/explain` | Feature 12 — condition-by-condition eligibility explanation |
| POST | `/api/loans` | Register a loan (Feature 9 data) |
| GET | `/api/loans/{loan_id}` | Fetch a single loan |
| POST | `/api/health-checks/send/{loan_id}` | Send (or simulate) the WhatsApp survey for a loan |
| POST | `/api/health-checks/respond` | Record a survey reply; may create a mentor alert |
| GET | `/api/alerts` | List mentor alerts (optional `?resolved=true/false` filter) |
| PATCH | `/api/alerts/{alert_id}/resolve` | Mark a mentor alert resolved |

### Example — Feature 10: scheme matching

```bash
curl -X POST http://127.0.0.1:8000/api/schemes/match \
  -H "Content-Type: application/json" \
  -d '{
        "business_type": "Food Processing",
        "project_cost": 800000,
        "location": "Rural",
        "category": "Eligible Category"
      }'
```

Returns `matched_scheme_ids: ["PMFME", "PMEGP", "MUDRA"]` for the demo data, plus per-scheme condition breakdowns and scores.

### Example — Feature 12: eligibility explanation

```bash
curl -X POST http://127.0.0.1:8000/api/schemes/explain \
  -H "Content-Type: application/json" \
  -d '{
        "business_type": "Food Processing",
        "project_cost": 800000,
        "location": "Rural",
        "category": "Eligible Category"
      }'
```

Each condition includes `condition`, `passed`, `actual`, and `expected` — ready for direct frontend rendering (e.g. `✓ Business type matches`) or for the AI/RAG lead to turn into prose.

### Example — Feature 9: register a loan & run a health check

```bash
# 1. Create a loan
curl -X POST http://127.0.0.1:8000/api/loans \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","phone_number":"+919999999999","business_name":"Sharma Snacks","loan_amount":150000}'

# 2. Send the WhatsApp survey (simulated in DEMO_MODE)
curl -X POST http://127.0.0.1:8000/api/health-checks/send/LOAN-XXXXXXXXXX

# 3. Record the (simulated) reply
curl -X POST http://127.0.0.1:8000/api/health-checks/respond \
  -H "Content-Type: application/json" \
  -d '{"loan_id":"LOAN-XXXXXXXXXX","message":"FALLING, MISSED, NO"}'

# 4. Check mentor alerts
curl http://127.0.0.1:8000/api/alerts
```

Because sales are `FALLING` and EMI is `MISSED` (2 concerning answers ≥ threshold), a mentor alert is automatically created.

---

## 7. Twilio WhatsApp Sandbox setup (optional — only for `DEMO_MODE=false`)

1. Create a free Twilio account: https://www.twilio.com/try-twilio
2. Open **Messaging → Try it out → Send a WhatsApp message** to activate the Sandbox.
3. From your phone, send the Sandbox's join code (e.g. `join <your-code>`) to the Sandbox WhatsApp number to opt in.
4. Copy your **Account SID** and **Auth Token** from the Twilio Console into `.env`:
   ```
   DEMO_MODE=false
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
   ```
5. Restart the server. Messages sent via `/api/health-checks/send/{loan_id}` and the scheduler will now go out through Twilio.

**If `DEMO_MODE=false` and credentials are missing**, the API returns a clear `500` error explaining what's missing — it never crashes silently or leaks a stack trace with secrets.

### DEMO_MODE (default, recommended for judging)

With `DEMO_MODE=true` (the default), no Twilio account is needed at all. Every "send" call is logged to the console and returns `{"status": "simulated", "demo_mode": true, ...}` with a preview of the exact message that would have been sent. This lets the entire project — including the scheduler — run and be judged completely offline.

---

## 8. Adding / updating government schemes

Open `app/data/schemes.json`. Each scheme looks like:

```json
{
  "scheme_id": "MUDRA",
  "scheme_name": "Pradhan Mantri MUDRA Yojana (PMMY)",
  "description": "...",
  "criteria": {
    "business_types": [],
    "project_cost_min": 0,
    "project_cost_max": 1000000,
    "locations": [],
    "categories": ["Eligible Category"]
  },
  "disclaimer": "Demo criteria only. Final eligibility is subject to government/lender verification."
}
```

Rules:
- An **empty list** (`[]`) for `business_types`, `locations`, or `categories` means "any value matches" (wildcard).
- A **non-empty list** means the profile's value must match (case-insensitively) one of the listed values.
- `project_cost_min` / `project_cost_max` define an inclusive cost range.

No Python code changes or redeployment logic are required — the engine (`app/rules.py`) reads this file fresh on every request.

---

## 9. Running tests

```bash
pip install -r requirements.txt   # includes pytest + httpx
pytest tests/ -v
```

Tests cover:
1. Food Processing + ₹8 lakh + Rural + Eligible Category → matches PMFME, PMEGP, MUDRA
2. A clearly non-matching business profile → no matched schemes
3. `/api/schemes/explain` returns condition-by-condition results with `actual`/`expected`
4. Every explanation includes the mandatory verification condition
5. Two concerning health-check answers → mentor alert created
6. One concerning health-check answer → no mentor alert created
7. Additional edge cases: unknown loan → 404, malformed survey reply → 422, input validation → 422, alert resolution

`tests/test_health_checks.py` points the app at an isolated temporary SQLite file so tests never touch your real `app_data.db`.

---

## 10. AI/RAG integration

This backend is intentionally split so the AI/RAG lead can build on top of it without re-implementing eligibility logic:

- Call `POST /api/schemes/explain` to get the deterministic, structured, condition-by-condition result for a profile.
- Feed that JSON into your LLM/RAG prompt to generate natural-language explanations ("You qualify for PMFME because your business is Food Processing, in a Rural area, with a project cost within the eligible range...").
- **The LLM must never be asked to decide `passed`/`score`/eligibility itself** — those values are already deterministic and come straight from `app/rules.py`. The LLM's job is explanation and phrasing only.
- Because the rule data lives in `app/data/schemes.json`, the AI/RAG layer (or any other service) can also read the same file directly for scheme metadata/descriptions if useful for retrieval.

---

## 11. Error handling summary

- All request bodies are validated with Pydantic (`422` on bad input).
- Unknown loan IDs return `404` with a clear message.
- Missing/invalid Twilio credentials in live mode raise a descriptive `500`, never a silent failure or crash.
- The app runs fully in `DEMO_MODE` without any `.env` file at all (safe defaults).
- Malformed WhatsApp survey replies return `422` with guidance on the expected format.
- Database errors are caught and returned as `500` with a message instead of crashing the process.
- The scheduler guards against duplicate job registration (`replace_existing=True`, `max_instances=1`, and an explicit "already running" check).

---

## 12. Government eligibility disclaimer (repeated)

The scheme data bundled with this project (`app/data/schemes.json`) is **demo/configurable data for hackathon purposes only**. It does **not** represent the current, complete, or legally authoritative eligibility rules for PMFME, PMEGP, MUDRA, or any other government scheme. **Final eligibility is always subject to government/lender verification.**
