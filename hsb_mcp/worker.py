import argparse
import base64
import hashlib
import json
import logging
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlparse

import httpx

from .config import Settings
from .store import Store, record_id

log = logging.getLogger(__name__)
MEDIA_HOSTS = {"lookaside.fbsbx.com", "mmg.whatsapp.net", "graph.facebook.com"}


def download_media(settings: Settings, media_id: str, phone_id: str):
    if not settings.meta_access_token:
        raise ValueError("Meta media credentials are not configured")
    if not re.fullmatch(r"\d+", media_id) or not re.fullmatch(r"v\d+\.\d+", settings.graph_version):
        raise ValueError("Invalid media ID or Graph version")
    folder = settings.data_dir / "media"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = folder / (record_id(phone_id, media_id) + ".bin")
    headers = {"Authorization": f"Bearer {settings.meta_access_token}"}
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        response = client.get(f"https://graph.facebook.com/{settings.graph_version}/{media_id}",
                              params={"phone_number_id": phone_id}, headers=headers)
        response.raise_for_status()
        metadata = response.json()
        media_url = metadata["url"]
        parsed = urlparse(media_url)
        if parsed.scheme != "https" or parsed.hostname not in MEDIA_HOSTS or parsed.port not in {None, 443}:
            raise ValueError("Unapproved media download host")
        if parsed.username or parsed.password:
            raise ValueError("Credentials in media URL")
        mime = metadata.get("mime_type", "application/octet-stream").split(";")[0]
        if int(metadata.get("file_size", 0)) > settings.max_media_bytes:
            raise ValueError("Pilot media size limit exceeded")
        temporary = destination.with_suffix(".part")
        digest = hashlib.sha256()
        size = 0
        try:
            with client.stream("GET", media_url, headers=headers) as stream:
                stream.raise_for_status()
                if stream.is_redirect:
                    raise ValueError("Media redirects are not followed")
                with temporary.open("wb") as out:
                    for chunk in stream.iter_bytes():
                        size += len(chunk)
                        if size > settings.max_media_bytes:
                            raise ValueError("Pilot media size limit exceeded")
                        digest.update(chunk)
                        out.write(chunk)
            expected = metadata.get("sha256")
            if expected and expected not in {digest.hexdigest(), base64.b64encode(digest.digest()).decode()}:
                raise ValueError("Media hash mismatch")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return destination, mime, digest.hexdigest()


def process_attachment(store, settings, row_id, phone_id, attachment, base_metadata):
    path, mime, digest = download_media(settings, str(attachment["id"]), phone_id)
    run = subprocess.run([sys.executable, "-m", "hsb_mcp.extract", str(path.resolve()), mime],
                         capture_output=True, timeout=180, check=True)
    extracted = json.loads(run.stdout)
    if extracted["status"] == "extraction_failed":
        raise RuntimeError("Attachment extraction failed; retry or inspect locally")
    for page in extracted["pages"]:
        text = page["text"]
        for start in range(0, len(text), 12_000):
            child_id = f"{row_id}-p{page['page']}-c{start // 12_000 + 1}"
            metadata = {**base_metadata, "parent_record_id": row_id, "page": page["page"],
                        "extraction_method": page["method"], "extraction_status": extracted["status"],
                        "sha256": digest, "mime_type": mime,
                        "note": "OCR can contain mistakes. A text index cannot explain a photo's visual content."}
            store.upsert(child_id, phone_id,
                         f"{attachment.get('filename', 'WhatsApp attachment')} | page {page['page']}",
                         text[start:start + 12_000], metadata)
    return {"attachment_status": extracted["status"], "attachment_mime": mime,
            "attachment_sha256": digest, "attachment_local_file": path.name,
            "extracted_pages": len(extracted["pages"])}


def process_payload(store: Store, settings: Settings, payload: dict):
    accepted = 0
    unsupported = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            # History/coexistence echoes are retained in raw events but need their own adapter.
            if change.get("field") != "messages":
                unsupported += 1
                continue
            value = change.get("value", {})
            phone_id = str(value.get("metadata", {}).get("phone_number_id", ""))
            if phone_id not in settings.allowed_phone_ids:
                continue
            contacts = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in value.get("contacts", [])}
            for msg in value.get("messages", []):
                if not isinstance(msg, dict) or not msg.get("id"):
                    continue
                kind = msg.get("type", "unknown")
                sender = str(msg.get("from", "unknown"))
                stamp = str(msg.get("timestamp", ""))
                body = msg.get("text", {}).get("body", "") if kind == "text" else ""
                attachment = msg.get(kind, {}) if kind in {"document", "image", "audio", "video"} else None
                if attachment:
                    body = attachment.get("caption", "")
                metadata = {"source": "meta_webhook", "meta_message_id": msg["id"], "phone_number_id": phone_id,
                            "sender": sender, "sender_name": contacts.get(sender, ""), "sent_at_unix": stamp,
                            "message_type": kind, "reply_to_message_id": msg.get("context", {}).get("id"),
                            "forwarded": bool(msg.get("context", {}).get("forwarded", False)),
                            "attachment_status": "pending" if attachment else "none"}
                id = record_id(phone_id, str(msg["id"]))
                title = f"{contacts.get(sender) or sender} | {kind} | {stamp}"
                store.upsert(id, phone_id, title, body or f"[{kind} message; see metadata]", metadata)
                if attachment:
                    try:
                        metadata.update(process_attachment(store, settings, id, phone_id, attachment, metadata))
                    except Exception as exc:
                        metadata["attachment_status"] = "processing_failed"
                        metadata["attachment_error_type"] = type(exc).__name__
                        store.upsert(id, phone_id, title, body or f"[{kind} message]", metadata)
                        raise
                    store.upsert(id, phone_id, title, body or f"[{kind} message]", metadata)
                accepted += 1
    return accepted, unsupported


def run_once(store, settings):
    event = store.claim()
    if event is None:
        return False
    try:
        count, unsupported = process_payload(store, settings, json.loads(event["payload"]))
        store.finish(event, status="needs_adapter" if unsupported else "done")
        log.info("Processed event: records=%s unsupported_fields=%s", count, unsupported)
    except Exception as exc:
        store.finish(event, error=exc)
        log.warning("Event processing failed: %s", type(exc).__name__)
    return True


def main():
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    if not settings.allowed_phone_ids:
        raise SystemExit("Configure META_PHONE_NUMBER_IDS first")
    store = Store(settings.data_dir)
    logging.basicConfig(level=logging.INFO)
    # HTTP client logging may contain signed media URLs. Keep it disabled.
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    logging.getLogger("httpcore").setLevel(logging.CRITICAL)
    if args.once:
        run_once(store, settings)
        return
    while True:
        if not run_once(store, settings):
            time.sleep(2)


if __name__ == "__main__":
    main()
