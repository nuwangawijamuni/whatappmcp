# HSB WhatsApp Knowledge MCP — starter 0.1.0

This is a runnable pilot for an HSB-controlled WhatsApp knowledge service. It receives **supported incoming messages** from Meta's official WhatsApp Business Cloud API, keeps a local search index and originals, and exposes read-only MCP `search` and `fetch` tools for ChatGPT.

**Status:** source code and local verification, not a deployed service. No HSB account has been connected. All bundled examples are synthetic. An actual Meta account, hosting/DNS and an OAuth authorization server must be configured before live use. OAuth token validation is implemented; an OAuth login/token-issuing service is **not** bundled.

## Start with the local demonstration

Use Python 3.12+ in Terminal, inside the extracted project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python tools/demo_check.py
python -m unittest discover -s tests -v
```

The demonstration starts the real MCP server as a local subprocess and exercises tool discovery, search and fetch using synthetic quotations. It does not start a public web server, use Meta credentials, call an AI model or upload the index. The printed localhost record URLs are illustrative in this stdio-only demo.

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` instead of the `source` command. The supplied deployment path uses Linux containers.

Read **[SETUP.md](SETUP.md)** for the live setup, in order.

## What is included

| Component | Implemented behaviour |
|---|---|
| Webhook verification | GET challenge with a separate verify token; POST HMAC-SHA256 validation using the Meta app secret |
| Durable intake | Raw event committed before HTTP acknowledgement; message-ID deduplication and a retry queue |
| Text records | Incoming `messages` events from explicitly allowed business phone-number IDs |
| Attachments | Authenticated Meta download, host allowlist, hash check when provided, a 25 MB pilot cap and private local storage |
| Text PDFs | Local pypdf extraction, page references and chunks |
| Scanned PDF pages | Local Poppler rendering and English Tesseract OCR when a page has no embedded text |
| Images | English Tesseract OCR for JPEG/PNG; image descriptions are not implemented |
| MCP | Real Streamable HTTP transport; typed read-only `search(query)` and `fetch(id)` tools |
| Search | SQLite FTS5 keyword search on one Docker host; no embeddings or semantic search |
| Access | RS256 OAuth access-token verification plus explicit per-employee, per-business-inbox grants |
| Sources | Protected JSON record endpoint at `/records/{id}`; OAuth bearer token required |
| Historical import | An operator-run normalized JSONL importer; no automatic WhatsApp export parser |
| Deployment | Dockerfile, two-service Compose file and an example Caddy TLS configuration |

## Exact boundaries

- **Existing WhatsApp groups are not continuously captured by this starter or unlocked by MCP.** Meta's official API access limits still apply. The code does not implement the separate Groups API.
- Coexistence/history/echo events are **retained but marked `needs_adapter`**, not claimed as indexed. Coexistence onboarding, outbound echo handling and historical sync adapters are not implemented. Ordinary incoming `messages` are the implemented live path.
- Access grants apply to an entire configured business inbox. Per-contact, per-project and per-group access filters require additional implementation before users share one inbox with different access requirements.
- Keyword matching is intentionally simple. ChatGPT should search short terms; natural-language semantic retrieval would be a later feature.
- Original files remain on disk. There is no browser download UI for originals. Source record URLs return authenticated JSON; direct browser SSO is not bundled. Add an approved browser login/source viewer if staff need clickable source pages without using an authenticated API client.
- A scanned page with a text layer may have incomplete embedded text. The pilot does not automatically decide when an existing text layer needs replacing with OCR. OCR can misread numbers and names. Site photos with no visible writing are retained, but their visual meaning is not indexed.
- Audio/video are retained but have no transcription or visual analysis in this version. Encryption/password-protected PDFs and PDFs over 50 pages are flagged as processing failures. Text per page is capped at 250,000 characters. Worker extraction is bounded to 180 seconds per attachment.
- The service neither sends WhatsApp messages nor creates tasks. Commitment tracking and task updates require a separate, reviewed extraction workflow.
- This is a single-host pilot, not a high-availability deployment. Backups, encryption at rest, retention/deletion procedures, monitoring, dependency review and the final OAuth integration must be completed for company rollout.

## Data flow and ownership

Meta delivers an event to HSB's webhook. HSB's local worker downloads supported media, performs local extraction and updates the local index. ChatGPT calls HSB's MCP server with an employee's OAuth token and receives the authorised search/fetch results.

There is no Perisclaw, Zapier, hosted OCR or external embedding service in the code. Meta still processes Cloud API traffic. Any content returned to ChatGPT is sent to OpenAI. Installing this source on an HSB server does not make ChatGPT run locally.

## Files

- `hsb_mcp/server.py`: webhook and MCP endpoints.
- `hsb_mcp/auth.py`: JWT verification and employee grants.
- `hsb_mcp/store.py`: records, FTS search and event queue.
- `hsb_mcp/worker.py`: message intake and attachment downloads.
- `hsb_mcp/extract.py`: isolated local PDF/OCR processing.
- `hsb_mcp/__main__.py`: serving, synthetic demo, stats and JSONL import.
- `.env.example`, `access-policy.example.json`: local configuration templates.
- `tests/test_core.py`: security and integration checks using synthetic data.
- `VERIFICATION.md`: what was and was not tested.
- `SOURCES.md`: current primary documentation used for the design.

## Useful operator commands

```bash
# On the deployment host, after real .env and policy files have been configured:
docker compose up -d --build
docker compose exec api python -m hsb_mcp stats
docker compose logs --tail=50 worker
docker compose stop
```

Do not use `docker compose down -v` unless you intentionally want to delete the stored knowledge volume. Do not publish port 8000 directly; Compose binds it to localhost for the TLS proxy.

The source is provided as a starting point for HSB implementation. Review it and test with approved sample data before connecting a real business inbox.
