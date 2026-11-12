# Verification record — 4 November 2026

All examples and test data were synthetic. No company WhatsApp account, real documents or employee credentials were used.

## Verified locally

- Automated suite: **20 tests passed**, using `python -m unittest discover -s tests -v`.
- Actual MCP stdio client/server demonstration: initialization, discovery of `search`/`fetch`, structured search output and record retrieval.
- Actual Streamable HTTP MCP request handling in an in-process ASGI client, with an explicitly mocked OAuth verifier.
- Unauthorized MCP requests rejected; protected resource metadata discovered at the expected path.
- Per-inbox grants enforced in search, fetch and source-record endpoints.
- JWT verification tested with locally generated RS256 keys: wrong issuer, wrong audience, expired token, insufficient scope and unknown employee rejected. JWKS transport was mocked.
- Employee access-policy changes applied without a service restart.
- Valid webhook challenge accepted; incorrect verify token rejected.
- Valid POST signature accepted and durably queued; unsigned POST rejected.
- Repeated webhook/message deliveries produced one message record.
- Unapproved phone numbers excluded from the index.
- Unimplemented history events retained and marked `needs_adapter`.
- Media URL host restrictions, streaming size limits and hash checking tested with mocked HTTP responses.
- PDF attachment download-to-index path tested using a mocked download and a real local extraction subprocess, preserving sender/page evidence.
- Selectable PDF text extraction tested with a synthetic PDF.
- Local Tesseract OCR tested separately on a synthetic PNG and an image-only scanned PDF; both recovered the test amount `2400`.
- Python source compilation completed.
- A dependency constraints file records the Python package versions from the verified environment.

## Not verified or not implemented

- No live Meta webhook, WABA subscription, production access token or business-number onboarding was tested.
- No live media was downloaded from Meta; network interactions in automated tests were mocked.
- No real OAuth authorization-code/PKCE login, identity-provider configuration, remote JWKS retrieval or ChatGPT plugin connection was tested. The code verifies tokens; the authorization server is an external setup dependency.
- No DNS/TLS endpoint was provisioned, and no service/plugin was deployed or installed.
- Docker build/Compose execution was not run because Docker is unavailable in the execution environment. The Python service code was tested directly. Validate the container build and reverse proxy on the actual host.
- Coexistence history/outgoing echoes, the Groups API, raw WhatsApp export parsing, original-file browser downloads, visual photo understanding, audio transcription, semantic embeddings, automatic commitment extraction and outgoing actions are not included.
- The access policy operates at business-inbox level. Project/contact-level separation, broader production hardening and deployment operations remain rollout work.

This verifies a starter implementation, not production readiness or account eligibility.
