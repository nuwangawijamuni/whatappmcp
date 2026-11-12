"""Local, bounded document processing; this module makes no network calls."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def ocr_image(path: Path) -> str:
    if shutil.which("tesseract") is None:
        raise RuntimeError("Local Tesseract OCR is not installed")
    result = subprocess.run(["tesseract", str(path), "stdout", "-l", "eng"],
                            capture_output=True, check=True, timeout=40)
    return result.stdout.decode("utf-8", errors="replace").strip()


def extract(path: Path, mime: str):
    if mime in {"image/jpeg", "image/png"}:
        text = ocr_image(path)
        return {"pages": [{"page": 1, "text": text, "method": "local_ocr"}],
                "status": "indexed" if text else "no_text_detected"}
    if mime == "application/pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF needs a separate approved process")
        if len(reader.pages) > 50:
            raise ValueError("Pilot PDF page limit exceeded")
        pages = []
        with tempfile.TemporaryDirectory() as tmp:
            for index, page in enumerate(reader.pages, start=1):
                text = (page.extract_text() or "").strip()
                method = "pdf_text"
                if not text:
                    if shutil.which("pdftoppm") is None:
                        raise RuntimeError("Local Poppler is not installed")
                    prefix = Path(tmp) / f"page-{index}"
                    subprocess.run(["pdftoppm", "-f", str(index), "-l", str(index),
                                    "-singlefile", "-scale-to", "2048", "-png", str(path), str(prefix)],
                                   capture_output=True, check=True, timeout=40)
                    text = ocr_image(prefix.with_suffix(".png"))
                    method = "local_ocr"
                if len(text) > 250_000:
                    raise ValueError("Pilot page text limit exceeded")
                pages.append({"page": index, "text": text, "method": method})
        return {"pages": pages, "status": "indexed" if any(p["text"] for p in pages) else "no_text_detected"}
    return {"pages": [], "status": "unsupported_type"}


def main():
    # Contain parsing failures in this child process. Containers provide additional limits.
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (150, 150))
    except (ImportError, ValueError):
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("mime")
    args = parser.parse_args()
    try:
        print(json.dumps(extract(args.path, args.mime), ensure_ascii=False))
    except Exception as exc:
        # Source content, filesystem paths and parser messages are not emitted to logs.
        print(json.dumps({"pages": [], "status": "extraction_failed", "error_type": type(exc).__name__}))


if __name__ == "__main__":
    main()
