# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS builder

WORKDIR /source/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./

ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_ENABLE_PROJECT_ROADMAP_SEED=true
RUN npm run build

FROM nginx:1.27-alpine

COPY deploy/bootstrap/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /source/frontend/dist /usr/share/nginx/html

EXPOSE 8080
