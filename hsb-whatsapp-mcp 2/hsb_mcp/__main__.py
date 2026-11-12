import argparse
from dataclasses import replace
import json
from pathlib import Path

from dotenv import load_dotenv

from .config import Settings
from .server import create_app, create_mcp
from .store import Store, record_id


def seed_demo(store):
    for message_id, title, text in [
        ("demo-quotation", "Demo Supplier | quotation", "DEMO DATA ONLY. The revised pump quotation is USD 2,400. Delivery estimate: 10 working days."),
        ("demo-drawings", "Demo Engineer | drawings", "DEMO DATA ONLY. The latest pontoon drawings are awaiting structural review."),
    ]:
        store.upsert(record_id("demo-inbox", message_id), "demo-inbox", title, text,
                     {"source": "synthetic_demo", "message_id": message_id})


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="HSB WhatsApp MCP pilot")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve")
    commands.add_parser("stats")
    commands.add_parser("demo-stdio")
    importer = commands.add_parser("import-jsonl")
    importer.add_argument("path", type=Path)
    importer.add_argument("--phone-id", required=True)
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.command == "demo-stdio":
        settings = replace(settings, data_dir=Path("./demo-data"), public_url="http://localhost:8000")
        store = Store(settings.data_dir)
        seed_demo(store)
        # Local subprocess only; no unauthenticated HTTP service is started.
        create_mcp(settings, store, demo=True).run(transport="stdio")
    elif args.command == "serve":
        import uvicorn
        app = create_app(settings)
        uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False, proxy_headers=False)
    elif args.command == "stats":
        print(json.dumps(Store(settings.data_dir).stats(), indent=2))
    else:
        if args.phone_id not in settings.allowed_phone_ids:
            raise SystemExit("Import phone ID is not configured for this deployment")
        store = Store(settings.data_dir)
        count = 0
        with args.path.open(encoding="utf-8") as source:
            for line in source:
                if not line.strip():
                    continue
                item = json.loads(line)
                if not all(isinstance(item.get(k), str) and item[k] for k in ("id", "title", "text")):
                    raise ValueError("Each JSONL line must have nonempty string id, title and text fields")
                metadata = item.get("metadata", {})
                if not isinstance(metadata, dict):
                    raise ValueError("metadata must be an object")
                store.upsert(record_id(args.phone_id, "import:" + item["id"]), args.phone_id,
                             item["title"], item["text"], {**metadata, "source": "manual_import", "original_id": item["id"]})
                count += 1
        print(json.dumps({"imported": count}))


if __name__ == "__main__":
    main()
