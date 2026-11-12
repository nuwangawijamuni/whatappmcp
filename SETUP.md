# HSB setup: from local demo to a private ChatGPT plugin

The recommended first release covers one HSB business inbox, incoming text/PDF/image messages and read-only search. Existing group monitoring is outside the official-API scope established for this project.

Follow the steps in order. Credentials belong in HSB's own configuration or secret store, never in a ChatGPT message, plugin package, screenshot or source repository.

## 1. Prove the local MCP connection

Unzip the project and run the commands in README.md. `tools/demo_check.py` starts the official MCP client/server protocol locally, discovers `search` and `fetch`, searches synthetic data and retrieves a record. No Meta or OpenAI API key is needed for this test.

This local demo proves the protocol and retrieval code. It does not prove remote ChatGPT access or your Meta account eligibility.

## 2. Choose the HSB deployment host and hostname

Use a Linux host in an HSB-controlled cloud account, or a company server that can securely receive external HTTPS requests. A Mac can run the local demo; publicly hosting from an office Mac also requires reliable uptime and networking.

Install Docker Engine/Compose on the Linux host and a maintained TLS reverse proxy such as Caddy. Choose a real hostname under a domain HSB controls. The `.example` names in this package are placeholders, not provisioned services.

Create the DNS record for that host. Meta's webhook and the ChatGPT MCP client must be able to reach the necessary HTTPS endpoints. Keep the data volume and administrative access private. Use encrypted disks, appropriate backups and a host firewall.

The core endpoints will be:

| Endpoint | Purpose | Access |
|---|---|---|
| `GET /healthz` | Basic process liveness | Public; no content or queue statistics |
| `GET /webhooks/whatsapp` | Meta verification challenge | Matching verify token |
| `POST /webhooks/whatsapp` | Meta notifications | Valid app-secret HMAC signature |
| `/mcp` | Streamable HTTP MCP tools | OAuth access token and employee grant |
| `/.well-known/oauth-protected-resource/mcp` | OAuth resource discovery | Public metadata |
| `GET /records/{id}` | Citation/source JSON | OAuth access token and employee grant |

## 3. Configure an established OAuth authorization server

This is required before publishing the MCP endpoint. The starter verifies access tokens but does **not** implement login, client registration, authorization codes or token issuance.

Use an HSB-managed authorization server or an approved identity provider with an MCP-compatible OAuth flow. An HSB-managed identity broker can use Google Workspace for employee login. A Google API access token by itself is not a substitute for an access token whose audience is this MCP server.

Configure:

1. Authorization Code flow with PKCE **S256**.
2. OAuth/OIDC discovery metadata with the exact issuer, authorization endpoint, token endpoint and `code_challenge_methods_supported` containing `S256`.
3. A dedicated MCP resource/audience equal to the exact HTTPS URL `https://YOUR_REAL_HOST/mcp`.
4. A read-only scope named `whatsapp.read`.
5. An appropriate client registration method: a predefined ChatGPT client is a straightforward initial choice; CIMD/DCR are alternatives when supported by the provider and chosen plugin configuration.
6. The exact ChatGPT callback URI displayed during plugin setup. Allow that URI explicitly; do not use a wildcard callback. Copy the displayed value instead of guessing it.
7. Tokens with RS256 signatures and `iss`, `sub`, `aud`, `iat`, `exp` and a space-delimited `scope` claim. `aud` must contain the exact MCP resource URL and `scope` must include `whatsapp.read`.
8. Correct handling of MCP's OAuth `resource` parameter so issued tokens are bound to this resource. Configure the audience mapping and test the complete flow.

Record the **exact issuer**, including any trailing slash, and its **JWKS endpoint**. Do not assume the JWKS endpoint is at a particular path; use the authorization server's discovery document.

In `access-policy.json`, map each approved employee's immutable OAuth `sub` to the Meta business **phone-number IDs** they may search. Unknown employees receive no access. Example structure:

```json
{
  "employees": {
    "actual-immutable-sub-from-your-identity-provider": ["actual-meta-phone-number-id"]
  }
}
```

The example grants access to an entire inbox. Add more precise row filtering before granting different staff different access within that same inbox.

Reference: https://developers.openai.com/plugins/build/auth

## 4. Prepare Meta's WhatsApp Business Cloud API

In HSB's own Meta Business Portfolio/developer account:

1. Create or select the company developer app and WhatsApp Business Account.
2. Start with Meta's test number and approved test recipients, then complete the necessary production business-number setup. Do not migrate a valuable live number as an experiment.
3. Record the WhatsApp **Phone Number ID**, the **WABA ID**, the **App Secret** and the currently supported **Graph API version** shown for your integration. The Phone Number ID is an API asset ID, not the displayed `+94...`/`+971...` telephone number.
4. Configure a server-side access token with the necessary WhatsApp messaging permissions and asset assignments. Business-management operations may need the corresponding management permission. Short-lived dashboard tokens are for testing; configure token lifecycle and rotation for production.
5. Decide whether this is a standard Cloud API number or eligible Coexistence onboarding. History sync is not enabled by simply creating an access token.

The code implements ordinary inbound `messages` notifications. Coexistence `history`/`smb_message_echoes` and the Groups API require separate adapters before you rely on them.

Reference: https://www.postman.com/meta/whatsapp-business-platform/overview

## 5. Configure and start the services

On your own host, inside the project folder:

```bash
cp .env.example .env
cp access-policy.example.json access-policy.json
```

Edit both files locally. Replace **every** placeholder. In particular:

| Variable | Value to supply |
|---|---|
| `HSB_PUBLIC_URL` | Your HTTPS origin, without `/mcp` and without a trailing slash |
| `OAUTH_ISSUER` | The issuer exactly as published in OAuth discovery |
| `OAUTH_JWKS_URL` | The discovery document's actual signing-key URL |
| `META_APP_SECRET` | Meta app secret used to verify webhook POST signatures |
| `META_WEBHOOK_VERIFY_TOKEN` | A new random secret of at least 32 characters, chosen by HSB |
| `META_ACCESS_TOKEN` | Meta API token held only by this backend |
| `META_GRAPH_VERSION` | The currently supported version for your Meta app, such as the actual `vN.N` value shown there |
| `META_PHONE_NUMBER_IDS` | Comma-separated approved numeric Phone Number IDs |

The Meta access token, Meta App Secret, webhook verify token and employee OAuth access tokens are **four different credentials**. Do not substitute one for another.

Generate the webhook verify token in your own Terminal if needed:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy that generated value locally into `.env` and later into Meta's verification field. Do not paste the completed configuration into chat.

Start the server and worker:

```bash
docker compose up -d --build
docker compose exec api python -m hsb_mcp stats
```

Compose uses a private named volume and binds the API to localhost. Copy `Caddyfile.example` into your Caddy setup, substitute the real host and enable HTTPS. Have the operator validate and reload Caddy using its installed service workflow. Do not expose an anonymous MCP endpoint or a database port.

Configure the final host backup/retention policy. A backup of live SQLite needs the SQLite backup API or a coordinated snapshot; copying only `knowledge.sqlite3` while writes continue may miss WAL changes. A full backup also needs original media and the access policy, with secrets managed separately.

## 6. Connect Meta's webhook

In the WhatsApp configuration for your Meta app:

1. Set the callback URL to `https://YOUR_REAL_HOST/webhooks/whatsapp`.
2. Enter the same locally generated webhook verify token.
3. Complete Meta's verification challenge.
4. Subscribe to incoming `messages` and ensure the app is subscribed to the correct WABA. Follow the current app dashboard/Graph subscription procedure for your API version.
5. Put the app/account in the required production state before relying on non-test messages; complete Meta's required permissions, asset access and account setup.

The app acknowledges only after storing a signed event. The worker then processes it. Inspect counts using:

```bash
docker compose exec api python -m hsb_mcp stats
docker compose logs --tail=50 worker
```

`pending` means waiting/retrying; `failed` means retries were exhausted; `needs_adapter` means a field this starter does not index. Build monitoring for those states. Do not assume an HTTP 200 means every attachment has already been indexed.

## 7. Verify the business data path with approved samples

Send the connected business number:

- A text containing a distinctive test phrase.
- A short PDF with selectable text.
- A clear scanned PDF.
- A JPEG/PNG containing printed English text.

Confirm records and page chunks are created. Check original attachments locally on the private data volume. A photo without text may legitimately be marked `no_text_detected`; this starter has no image-captioning model.

Check that the worker's test file stays under 25 MB, that a message repeated by Meta is not duplicated, and that failures remain visible. English OCR is the bundled setting; Turkish/Sinhala or other language coverage requires installed language packs and an explicit extraction-language change and test.

## 8. Add the private MCP connection in ChatGPT

After HTTPS and OAuth have been tested:

1. In ChatGPT **Plugins**, choose the plus button, then **Add custom MCP server**.
2. Enter the real server URL ending in `/mcp`.
3. Choose OAuth and the appropriate client configuration. If using a predefined OAuth client, enter its actual client details through the configuration UI.
4. Copy the callback URL shown by ChatGPT to your authorization server's allowlist.
5. Create/install the plugin privately and complete employee login.
6. Confirm ChatGPT discovers the read-only tools **`search`** and **`fetch`**.
7. Test: “Search the HSB WhatsApp knowledge base for TEST-PHRASE and show its source.”
8. Test a second employee without an inbox grant. Their token must not retrieve any protected record, including when given a known record ID.

Depending on workspace permissions, a workspace owner may need to enable or approve the custom plugin connection. Keep the plugin private during testing; workspace sharing is a separate action after verification.

Official setup reference: https://developers.openai.com/api/docs/mcp

The MCP endpoint must be reachable by the ChatGPT service. A localhost URL, private office IP or VPN connection available only to your laptop does not by itself make the endpoint reachable by ChatGPT.

The starter supplies protected source JSON URLs. A browser click will require a compatible authenticated source viewer/SSO layer; the MCP tools already retrieve the same record content after OAuth. Do not make source URLs public to remove the login requirement.

## 9. Add selected old chats as a separate import

WhatsApp exports need a deliberate normalization step: export formats vary by locale/date format, and forwarded/exported files may omit parts of the original context. This package's importer reads **normalized JSONL**, not raw WhatsApp TXT/ZIP exports.

For each selected exported message, create one JSON object per line with:

```json
{"id":"stable-export-message-id","title":"Project — original sender — original time","text":"Original message text or extracted document text","metadata":{"original_timestamp":"original timestamp","conversation":"original conversation","import_note":"imported from an approved export"}}
```

Use stable IDs so repeating the same import updates the same record. Assign the import to a configured inbox ID with the intended access grants. Run on the private host, with the file deliberately mounted/copied into the container, or in the Python environment configured to use the same private data directory:

```bash
python -m hsb_mcp import-jsonl approved-export.jsonl --phone-id YOUR_APPROVED_PHONE_NUMBER_ID
```

`sample-import.jsonl` is a synthetic schema example. It contains no real WhatsApp history. Matching exported attachments and converting old chats should be tested before a bulk import; neither is automatic in this version.

Existing group exports remain snapshots. They do not enable future live group updates via Meta's API.

## 10. Extend after the pilot works

Then add, as separate verified work:

1. Coexistence onboarding and history/echo adapters if the HSB number and integration qualify. Retain raw events and account for messages sent from the app as well as received messages.
2. A browser source viewer with HSB login, original-file access and audit records.
3. Finer project/contact permissions and automated retention/deletion.
4. Multilingual OCR, local embeddings/semantic search and approved image/voice understanding.
5. PostgreSQL/object storage and operational monitoring if the single-host pilot becomes a shared production service.
6. Commitment extraction that records owner, requester, deadline, status and supporting message evidence. Keep ambiguous dates/owners under review instead of auto-assigning them.

Do not add outgoing WhatsApp messages or task creation tools merely to test the knowledge connection. They are separate functional additions, with their own authorization and messaging constraints.
