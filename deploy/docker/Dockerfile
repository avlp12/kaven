FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn \
    && addgroup --system kaven \
    && adduser --system --ingroup kaven --home /app kaven

COPY --chown=kaven:kaven src /app/src
COPY --chown=kaven:kaven webapp /app/webapp
RUN mkdir -p /app/src/kaven/logs && chown -R kaven:kaven /app

USER kaven

EXPOSE 8000
CMD ["uvicorn", "webapp.backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
