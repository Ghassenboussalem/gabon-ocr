# Gabon OCR — upload + pipeline + review UI in one container.
#
#   docker build -t gabon-ocr .
#   docker run -p 8000:8000 -e GEMINI_API_KEY=... gabon-ocr
#
# Works as-is on Render / Railway / Fly.io / any Docker host.
# Required env: GEMINI_API_KEY   (deployed backend is gemini)
# Optional env: APP_PASSWORD     (HTTP Basic gate on the UI)
#               PUBLIC_BASE_URL  (https origin used inside the phone QR code)
FROM python:3.12-slim

# tesseract binary from apt; the FRENCH traineddata ships in this repo's
# tessdata/ and pipeline/locate.py points TESSDATA_PREFIX at it automatically
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PIPELINE_BACKEND=gemini \
    PYTHONUNBUFFERED=1

EXPOSE 8000
# $PORT is injected by Render/Railway; default to 8000 elsewhere
CMD ["sh", "-c", "uvicorn review.app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
