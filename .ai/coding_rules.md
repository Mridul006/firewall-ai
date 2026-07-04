# coding_rules.md

Rules that apply to every file written in this project.
Claude Code must follow these without being reminded.

---

## Python rules

### General
- Python 3.11+ only
- Type hints on every function — arguments and return types
- Docstrings on every class and every non-trivial function
- Max line length: 88 characters (Black formatter standard)
- Use f-strings, never .format() or %

### Imports
- Standard library first, third-party second, local imports third
- Each group separated by a blank line
- Never use wildcard imports (from x import *)

### Environment variables
- Always load via python-dotenv at the top of the entry point
- Never hardcode secrets, URLs, or credentials anywhere
- Every env var must also exist in .env.example with a placeholder value

```python
# Correct
from dotenv import load_dotenv
import os
load_dotenv()
DB_URL = os.getenv("POSTGRES_URL")

# Wrong
DB_URL = "postgresql://admin:secret@localhost:5432/firewallai"
```

### Pydantic
- Every API request body and response body must be a Pydantic model
- Define all models in backend/models/ — never inline in route files
- Use model_config = ConfigDict(from_attributes=True) for ORM models

### Error handling
- Never use bare except — always catch specific exceptions
- Log errors with context, not just the exception message
- FastAPI routes must return structured error responses, not raw strings

```python
# Correct
try:
    result = await db.execute(query)
except SQLAlchemyError as e:
    logger.error(f"DB query failed: {e}")
    raise HTTPException(status_code=500, detail="Database error")

# Wrong
try:
    result = await db.execute(query)
except:
    pass
```

### Async
- Use async/await throughout FastAPI routes and DB calls
- Never block the event loop with synchronous I/O
- Use asyncpg or SQLAlchemy async engine for all DB operations

---

## FastAPI rules

### Route structure
- All routes prefixed with /api/v1/
- Group routes by domain in separate router files under backend/routes/
- Use dependency injection for DB sessions and auth

```python
# backend/routes/rules.py
router = APIRouter(prefix="/api/v1/rules", tags=["rules"])

@router.get("/", response_model=list[RuleResponse])
async def get_rules(db: AsyncSession = Depends(get_db)):
    ...
```

### Response models
- Every route must declare a response_model
- Never return raw dicts from routes
- Use HTTP status codes correctly: 200 GET, 201 POST, 204 DELETE

### Authentication
- JWT-based auth via Bearer token
- Auth dependency injected per route — never global middleware only
- User context available as current_user dependency in protected routes

---

## ML rules

### Model files
- Every model lives in ml/ with its own file
- Training and inference must be separate functions
- Save trained models to ml/models/ as .pkl or .joblib files
- Never retrain on every request — load once at startup

### Claude API calls
- Always use claude-sonnet-4-6
- Always set max_tokens explicitly
- Wrap every API call in try/except with fallback behavior
- Prompt templates live in knowledge/prompts/ — never hardcode prompts inline

```python
# Correct
from pathlib import Path
prompt_template = Path("knowledge/prompts/rule_gen.txt").read_text()
prompt = prompt_template.format(traffic_summary=summary)

# Wrong
prompt = f"Generate a firewall rule for this traffic: {summary}"
```

### Isolation Forest
- Retrain weekly minimum, or when traffic pattern drift detected
- Log anomaly scores alongside predictions for debugging
- Configurable contamination parameter via env var — never hardcode

---

## Docker rules

- Every infrastructure service runs via docker-compose — never native install
- Each service in docker-compose must have a health check defined
- Application code never runs inside docker-compose in development — only infra
- Use named volumes for persistent data (postgres, clickhouse)

---

## Frontend rules

### React
- Functional components only — no class components
- Custom hooks for all data fetching (useRules, useTraffic, useAlerts)
- No inline styles — Tailwind classes only
- Component files: PascalCase.jsx
- Hook files: useCamelCase.js

### API calls
- All API calls via a central api.js client — never fetch() directly in components
- Handle loading and error states for every async operation
- WebSocket connection managed in a single useWebSocket hook

### State management
- useState for local component state
- Context API for global state (auth, theme) — no Redux for now
- No prop drilling beyond 2 levels — lift state or use context

---

## Git rules

- Commit after every working component — never commit broken code
- Commit message format: type(scope): description
  - feat(api): add rule approval endpoint
  - fix(ml): handle empty traffic window in anomaly detector
  - docs(knowledge): add MTD rotation architecture decision
- Never commit: .env, venv/, node_modules/, __pycache__/, *.pyc, ml/models/
- Branch naming: feature/what-it-does, fix/what-it-fixes

---

## Documentation rules

- After every significant feature or architecture change, update the relevant
  docs in the same pass — do this automatically, without being asked:
  - `knowledge/architecture/decisions.md` — append an entry for any new design
    decision
  - `knowledge/architecture/layerX_design.md` — update the matching layer's
    design doc when its design changes
  - `CLAUDE.md` — update if the tech stack or build status/current focus changed
  - `.env.example` — add a placeholder for every new env var introduced

---

## What NOT to do

- Do not use LangChain, LlamaIndex, or any agent framework — call Claude API directly
- Do not add a new dependency without checking if existing ones cover the need
- Do not create microservices — monorepo with clear module boundaries only
- Do not write synchronous database calls in async FastAPI routes
- Do not skip Pydantic models for "simple" endpoints — consistency matters
- Do not add Kubernetes, Terraform, or cloud infra config yet
- Do not build features not in the current build order phase