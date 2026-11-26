# ForgeAI — industrial sales automation prototype

Independent Poka Labs-inspired demo, not affiliated with Poka Labs.

## Run locally (macOS/Linux)

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```
Open http://localhost:8000 and API documentation at http://localhost:8000/docs. Windows activation: `.venv\Scripts\activate`. Docker alternative: `docker build -t forgeai . && docker run -p 127.0.0.1:8000:8000 forgeai`.

Optional AI: export OPENAI_API_KEY before launching; OPENAI_MODEL defaults to gpt-4o-mini. Without a key, a limited regex parser accepts semicolon-separated lines like `500 kg of Sodium chloride industrial grade; 200 L of Ethanol 99%`. Do not submit confidential data. AI extraction is not verified against live API in this package.

## Demo walkthrough
1. Select demo-sales and Acme; process the prefilled request.
2. Review items and pricing (API monetary amounts are integer USD cents).
3. Approve, send to simulated outbox, then accept to reserve inventory and create order.
4. Switch to demo-manager to update a product cost. A stale quote cannot be sent if recalculation changes its line prices.
5. Try an unknown product to trigger clarification. Try 1000 kg of a product with Globex to trigger margin approval.
6. Switch to other-sales to see a separate tenant. Inspect audit, orders and outbox.

## Tests
`PYTHONPATH=. pytest -q` (Windows PowerShell: `$env:PYTHONPATH='.'; pytest -q`). Three automated API tests cover happy path, repeated RFQ, duplicate acceptance, tenant separation, unknown product and missing authentication.

## Architecture and limitations
FastAPI serves a browser UI and REST API; SQLite persists tenant-scoped records and serializes inventory reservation transactions. Optional OpenAI extraction uses validated Pydantic output. Product matching uses exact SKU/name and fuzzy string matching, not embeddings. Pricing uses integer cents and Decimal rounding, with seeded discounts and contract overrides. Quote lifecycle is explicit and persistent; send is simulated, not email. Catalog and customer data are mock ERP/CRM records. Five products and three customers per tenant are seeded. Guidance is a rule-based candidate list, not a validated substitute recommendation. No real email, ERP/CRM connectors, document uploads, PDF quote export, Temporal, LangGraph, MCP, PostgreSQL, Redis, vector search, production authentication, comprehensive evaluations or cloud deployment are implemented. The browser exposes demo credentials intentionally; do not deploy publicly. No quote editing/versioning or full extraction completeness validation; human review is mandatory. Production work must add robust identity, authorization, audit timestamps, secure secrets, connector retries/outbox delivery, document ingestion, validation and expanded testing. This is a runnable vertical slice, not full feature parity.
