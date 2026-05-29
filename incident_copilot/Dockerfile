FROM python:3.12-slim

WORKDIR /app

# Install Node.js 18 + npm (required for npx @arizeai/phoenix-mcp at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Pre-install Phoenix MCP server globally so npx uses cache (no cold-start download)
RUN npm install -g @arizeai/phoenix-mcp@latest

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV APP_HOST=0.0.0.0
ENV APP_PORT=8080

EXPOSE 8080

# Cloud Run sets PORT env var; uvicorn reads APP_PORT
CMD ["sh", "-c", "uvicorn api.main:app --host $APP_HOST --port ${PORT:-$APP_PORT}"]
