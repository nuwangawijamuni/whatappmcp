import asyncio
from dataclasses import replace
import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
from mcp.server.auth.provider import AccessToken
from starlette.testclient import TestClient

from hsb_mcp.auth import JWTVerifier, allowed_phones
from hsb_mcp.config import Settings
from hsb_mcp.extract import extract
from hsb_mcp.server import create_app
from hsb_mcp.store import Store, record_id
from hsb_mcp.worker import download_media, process_payload, run_once


def sample_payload(phone="111111", message="demo-1", text="Revised quotation for pontoon pumps"):
    return {"object": "whatsapp_business_account", "entry": [{"id": "demo-waba", "changes": [
        {"field": "messages", "value": {"metadata": {"phone_number_id": phone},
         "contacts": [{"wa_id": "demo-sender", "profile": {"name": "Demo Supplier"}}],
         "messages": [{"id": message, "from": "demo-sender", "timestamp": "1793754000",
                       "type": "text", "text": {"body": text}}]}}
    ]}]}


def small_pdf():
    # A complete synthetic PDF containing selectable text, without external fixtures.
    stream = b"BT /F1 18 Tf 50 750 Td (DEMO QUOTATION USD 2400) Tj ET"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    data = bytearray(b"%PDF-1.4\n")
    positions = [0]
    for index, obj in enumerate(objects, 1):
        positions.append(len(data))
        data.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    offset = len(data)
    data.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for pos in positions[1:]:
        data.extend(f"{pos:010} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{offset}\n%%EOF\n".encode())
    return bytes(data)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        policy = root / "access-policy.json"
        policy.write_text(json.dumps({"employees": {"alice": ["111111"], "bob": ["222222"]}}))
        self.settings = Settings(root / "data", policy, "https://mcp.hsb.example", "https://auth.hsb.example/",
            "https://auth.hsb.example/jwks", "demo-app-secret", "v"*40, "demo-meta-token", "v99.0",
            frozenset({"111111", "222222"}))
        self.store = Store(self.settings.data_dir)


class StoreTests(Fixture):
    def test_search_fetch_enforce_inbox_access(self):
        self.store.upsert("a", "111111", "Quotation", "Pump quotation", {})
        self.store.upsert("b", "222222", "Quotation", "Private pump quotation", {})
        self.assertEqual([r["id"] for r in self.store.search("pump", {"111111"})], ["a"])
        self.assertIsNone(self.store.fetch("b", {"111111"}))
        self.assertEqual(self.store.search("pump", set()), [])

    def test_input_is_not_sql_or_fts_code(self):
        self.store.upsert("a", "111111", "pump", "quotation", {})
        self.store.search('" OR * ; DROP TABLE records --', {"111111"})
        self.assertIsNotNone(self.store.fetch("a", {"111111"}))

    def test_repeated_events_and_messages_are_idempotent(self):
        raw = json.dumps(sample_payload()).encode()
        self.store.enqueue(raw)
        self.store.enqueue(raw)
        run_once(self.store, self.settings)
        self.assertFalse(run_once(self.store, self.settings))
        process_payload(self.store, self.settings, sample_payload())
        self.assertEqual(self.store.stats(), {"records": 1, "events": {"done": 1}})

    def test_unapproved_number_does_not_enter_search(self):
        count, _ = process_payload(self.store, self.settings, sample_payload(phone="333333"))
        self.assertEqual(count, 0)
        self.assertEqual(self.store.stats()["records"], 0)

    def test_unhandled_history_is_retained_and_flagged(self):
        payload = sample_payload()
        payload["entry"][0]["changes"][0]["field"] = "history"
        self.store.enqueue(json.dumps(payload).encode())
        run_once(self.store, self.settings)
        self.assertEqual(self.store.stats()["events"], {"needs_adapter": 1})

    def test_failed_jobs_retain_only_error_class(self):
        self.store.enqueue(json.dumps(sample_payload()).encode())
        event = self.store.claim()
        self.store.finish(event, error=RuntimeError("SENSITIVE TOKEN SHOULD NOT BE STORED"))
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM events").fetchone()
            self.assertEqual(row["last_error"], "RuntimeError")
            self.assertEqual(row["status"], "pending")


class FakeVerifier:
    async def verify_token(self, token):
        if token != "alice-token":
            return None
        return AccessToken(token=token, client_id="test-client", subject="alice",
            scopes=["whatsapp.read"], expires_at=int(time.time())+300, resource="https://mcp.hsb.example/mcp")


class HTTPTests(Fixture):
    def client(self):
        return TestClient(create_app(self.settings, verifier=FakeVerifier()), base_url=self.settings.public_url)

    def test_signed_webhook_is_durable_invalid_signature_rejected(self):
        raw = json.dumps(sample_payload()).encode()
        signature = "sha256=" + hmac.new(self.settings.app_secret.encode(), raw, hashlib.sha256).hexdigest()
        with self.client() as client:
            self.assertEqual(client.post("/webhooks/whatsapp", content=raw).status_code, 401)
            response = client.post("/webhooks/whatsapp", content=raw, headers={"x-hub-signature-256": signature})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.stats()["events"], {"pending": 1})

    def test_webhook_verification_requires_matching_token(self):
        with self.client() as client:
            url = "/webhooks/whatsapp"
            self.assertEqual(client.get(url, params={"hub.mode": "subscribe", "hub.verify_token": "wrong"}).status_code, 403)
            result = client.get(url, params={"hub.mode": "subscribe", "hub.verify_token": self.settings.verify_token, "hub.challenge": "12345"})
            self.assertEqual(result.text, "12345")

    def test_source_links_are_not_public_and_cross_inbox_fetch_is_denied(self):
        self.store.upsert("a", "111111", "demo", "allowed", {})
        self.store.upsert("b", "222222", "demo", "hidden", {})
        with self.client() as client:
            self.assertEqual(client.get("/records/a").status_code, 401)
            headers = {"Authorization": "Bearer alice-token"}
            self.assertEqual(client.get("/records/a", headers=headers).status_code, 200)
            self.assertEqual(client.get("/records/b", headers=headers).status_code, 404)

    def test_mcp_is_protected_and_advertises_oauth_resource(self):
        with self.client() as client:
            response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            self.assertEqual(response.status_code, 401)
            self.assertIn("resource_metadata", response.headers["www-authenticate"].lower())
            metadata = client.get("/.well-known/oauth-protected-resource/mcp")
            self.assertEqual(metadata.status_code, 200)
            self.assertEqual(metadata.json()["resource"], self.settings.resource_url)

    def test_actual_mcp_protocol_over_authenticated_http(self):
        self.store.upsert("a", "111111", "pump", "allowed quotation", {})
        self.store.upsert("b", "222222", "pump", "hidden quotation", {})
        headers = {"Authorization": "Bearer alice-token", "Accept": "application/json, text/event-stream"}
        with self.client() as client:
            initialized = client.post("/mcp", headers=headers, json={"jsonrpc":"2.0", "id":1,
                "method":"initialize", "params":{"protocolVersion":"2025-11-25", "capabilities":{},
                    "clientInfo":{"name":"hsb-test", "version":"1"}}})
            self.assertEqual(initialized.status_code, 200)
            self.assertIn("protocolVersion", initialized.json()["result"])
            headers["MCP-Protocol-Version"] = initialized.json()["result"]["protocolVersion"]
            result = client.post("/mcp", headers=headers, json={"jsonrpc":"2.0", "id":2,
                "method":"tools/call", "params":{"name":"search", "arguments":{"query":"pump"}}}).json()["result"]
            self.assertEqual([r["id"] for r in result["structuredContent"]["results"]], ["a"])
            hidden = client.post("/mcp", headers=headers, json={"jsonrpc":"2.0", "id":3,
                "method":"tools/call", "params":{"name":"fetch", "arguments":{"id":"b"}}}).json()["result"]
            self.assertTrue(hidden["isError"])

    def test_incomplete_http_configuration_fails_closed(self):
        with self.assertRaises(ValueError):
            create_app(replace(self.settings, issuer=""))


class AuthTests(Fixture):
    def setUp(self):
        super().setUp()
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.verifier = JWTVerifier(self.settings)

    def verify(self, **overrides):
        claims = {"iss": self.settings.issuer, "aud": self.settings.resource_url, "sub":"alice",
                  "iat": int(time.time())-1, "exp": int(time.time())+300, "scope":"whatsapp.read"}
        claims.update(overrides)
        token = jwt.encode(claims, self.key, algorithm="RS256", headers={"kid":"test"})
        with patch.object(self.verifier.jwks, "get_signing_key_from_jwt", return_value=SimpleNamespace(key=self.key.public_key())):
            return asyncio.run(self.verifier.verify_token(token))

    def test_valid_token_resolves_employee(self):
        self.assertEqual(self.verify().subject, "alice")

    def test_wrong_audience_issuer_expiry_scope_and_employee_rejected(self):
        for override in [{"aud":"https://wrong.example"}, {"iss":"https://wrong.example"},
                         {"exp":int(time.time())-10}, {"scope":"other.read"}, {"sub":"unknown"}]:
            with self.subTest(override=override):
                self.assertIsNone(self.verify(**override))

    def test_revocation_in_policy_applies_without_restart(self):
        self.assertEqual(allowed_phones(self.settings, "alice"), {"111111"})
        self.settings.policy_file.write_text('{"employees":{}}')
        self.assertIsNone(self.verify())


class AttachmentTests(Fixture):
    def test_attachment_pipeline_indexes_pdf_with_source_metadata(self):
        path = Path(self.temp.name) / "attachment.pdf"
        path.write_bytes(small_pdf())
        payload = sample_payload()
        message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        message["type"] = "document"
        message["document"] = {"id":"123", "filename":"synthetic-quotation.pdf", "caption":"Demo quotation"}
        with patch("hsb_mcp.worker.download_media", return_value=(path, "application/pdf", hashlib.sha256(path.read_bytes()).hexdigest())):
            process_payload(self.store, self.settings, payload)
        found = self.store.search("2400", {"111111"})
        self.assertEqual(len(found), 1)
        self.assertEqual(json.loads(found[0]["metadata"])["page"], 1)
        self.assertEqual(json.loads(found[0]["metadata"])["sender_name"], "Demo Supplier")
        parent = self.store.fetch(record_id("111111", "demo-1"), {"111111"})
        self.assertEqual(json.loads(parent["metadata"])["attachment_status"], "indexed")

    def test_pdf_selectable_text_is_extracted(self):
        path = Path(self.temp.name) / "synthetic.pdf"
        path.write_bytes(small_pdf())
        output = extract(path, "application/pdf")
        self.assertEqual(output["status"], "indexed")
        self.assertIn("2400", output["pages"][0]["text"])

    def test_metadata_cannot_redirect_token_to_unapproved_host(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda request:
            httpx.Response(200, json={"url":"https://attacker.example/file", "mime_type":"application/pdf"})))
        with patch("hsb_mcp.worker.httpx.Client", return_value=client):
            with self.assertRaises(ValueError):
                download_media(self.settings, "123", "111111")

    def test_media_size_limit_enforced_while_streaming(self):
        def handler(request):
            if request.url.host == "graph.facebook.com":
                return httpx.Response(200, json={"url":"https://lookaside.fbsbx.com/file", "mime_type":"application/pdf"})
            return httpx.Response(200, content=b"x"*100)
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch("hsb_mcp.worker.httpx.Client", return_value=client):
            with self.assertRaises(ValueError):
                download_media(replace(self.settings, max_media_bytes=20), "123", "111111")
        self.assertFalse(list((self.settings.data_dir / "media").glob("*.part")))

    def test_media_hash_verified(self):
        payload = small_pdf()
        def handler(request):
            if request.url.host == "graph.facebook.com":
                return httpx.Response(200, json={"url":"https://lookaside.fbsbx.com/file", "mime_type":"application/pdf",
                                               "sha256":hashlib.sha256(payload).hexdigest()})
            return httpx.Response(200, content=payload)
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch("hsb_mcp.worker.httpx.Client", return_value=client):
            path, mime, digest = download_media(self.settings, "123", "111111")
        self.assertEqual(path.read_bytes(), payload)
        self.assertEqual(mime, "application/pdf")
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())


if __name__ == "__main__":
    unittest.main()
