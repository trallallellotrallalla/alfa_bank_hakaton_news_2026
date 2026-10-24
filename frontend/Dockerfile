# syntax=docker/dockerfile:1

# ---------- Сборка фронтенда ----------
FROM node:24-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
# mock — встроенные демо-данные, http — реальный бэкенд за /api
ARG VITE_API_MODE=mock
ARG VITE_API_BASE_URL=/api
ENV VITE_API_MODE=$VITE_API_MODE \
    VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# ---------- Раздача статики ----------
FROM nginx:1.27-alpine
# Адрес бэкенда для режима http; шаблон подставляется entrypoint-ом nginx (envsubst)
ENV API_UPSTREAM=http://backend:8000
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
