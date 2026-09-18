FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
# ci, not install: the lockfile is authoritative so builds are reproducible.
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Run unprivileged. nginx needs its pid file and cache dirs writable by the
# runtime user, and a port above 1024 since a non-root process cannot bind 80.
# Both listen directives move together: dropping the IPv6 one would make the
# healthcheck below fail against a perfectly healthy server.
RUN sed -i 's|listen 80;|listen 8080;|; s|listen \[::\]:80;|listen [::]:8080;|' /etc/nginx/conf.d/default.conf \
 && sed -i 's|^pid .*|pid /tmp/nginx.pid;|' /etc/nginx/nginx.conf \
 && sed -i '/^user /d' /etc/nginx/nginx.conf \
 && chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /etc/nginx/conf.d
USER nginx

EXPOSE 8080

# 127.0.0.1 rather than localhost. localhost resolves to ::1 first in this
# image, so a resolution-order mismatch would report a working server as
# permanently unhealthy and break `docker compose up --wait` in CI.
HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=15s \
  CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1
CMD ["nginx", "-g", "daemon off;"]
