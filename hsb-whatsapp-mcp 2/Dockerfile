FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng poppler-utils && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --uid 10001 --create-home hsb && mkdir /data && chown hsb:hsb /data
COPY hsb_mcp ./hsb_mcp
USER hsb
EXPOSE 8000
CMD ["python", "-m", "hsb_mcp", "serve"]
