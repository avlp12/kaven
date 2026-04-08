FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir aiohttp feedparser websockets fastapi uvicorn

EXPOSE 8000
CMD ["uvicorn", "webapp.backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
