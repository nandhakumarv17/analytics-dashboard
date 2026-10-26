FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DASHBOARD_UPLOAD_DIR=/tmp/dashboard_uploads \
    MAX_CONTENT_LENGTH=67108864

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /tmp/dashboard_uploads && \
    chown -R nobody:nogroup /app /tmp/dashboard_uploads

USER nobody

EXPOSE 10000

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]
