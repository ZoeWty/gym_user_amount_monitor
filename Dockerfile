# --- build the SPA ---------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Vite substitutes these into the bundle at build time, so they are build args
# rather than runtime env. No token means the chat bubble is simply absent.
ARG VITE_DIFY_TOKEN=""
ARG VITE_DIFY_URL="http://localhost"
ENV VITE_DIFY_TOKEN=$VITE_DIFY_TOKEN
ENV VITE_DIFY_URL=$VITE_DIFY_URL
RUN npm run build

# --- runtime ---------------------------------------------------------------
# One image serves both the api and the poller; they differ only by command.
FROM python:3.13-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend /app/dist /app/static
ENV STATIC_DIR=/app/static

# This image is reachable from the public internet via the tunnel; don't run
# the process as root.
RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
