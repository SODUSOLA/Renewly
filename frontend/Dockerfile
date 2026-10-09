# syntax=docker/dockerfile:1
# Builds the React app and serves the static files with nginx.

# ---- build stage ---------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# The API address is baked into the JavaScript at build time (Vite replaces
# import.meta.env.VITE_API_URL). Railway passes service variables as build args.
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ---- serve stage -----------------------------------------------------------
FROM nginx:1.27-alpine
# nginx renders templates in this folder with environment variables on start-up.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
ENV PORT=8080
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD wget -q --spider http://127.0.0.1:${PORT}/ || exit 1
