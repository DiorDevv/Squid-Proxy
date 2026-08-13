FROM node:26-slim AS build
WORKDIR /app
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    npm_config_proxy=${HTTP_PROXY} \
    npm_config_https_proxy=${HTTPS_PROXY}
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Empty defaults mean "same origin as the page" -- nginx.conf (below) proxies
# /api and /ws to the backend container, so the SPA never needs an absolute
# backend URL baked in. Override at build time only for a split-origin setup.
ARG VITE_API_BASE_URL=""
ARG VITE_WS_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_WS_URL=${VITE_WS_URL}
RUN npm run build
FROM nginx:1.31-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
