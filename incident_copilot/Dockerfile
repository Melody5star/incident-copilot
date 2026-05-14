FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV APP_HOST=0.0.0.0
ENV APP_PORT=8080

EXPOSE 8080

# Cloud Run sets PORT env var; uvicorn reads APP_PORT
CMD ["sh", "-c", "uvicorn api.main:app --host $APP_HOST --port ${PORT:-$APP_PORT}"]
