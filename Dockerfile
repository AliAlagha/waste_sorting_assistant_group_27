FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
# CPU-only torch keeps the image small (no CUDA libraries)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt gunicorn

# download the trained model at build time, so the container starts fast and needs no download later
RUN python -c "from transformers import AutoImageProcessor, AutoModelForImageClassification as M; \
AutoImageProcessor.from_pretrained('watersplash/waste-classification'); M.from_pretrained('watersplash/waste-classification')"

COPY . .

EXPOSE 5000
HEALTHCHECK --interval=30s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"
# one worker because the login sessions are kept in memory
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "120", "main:app"]
