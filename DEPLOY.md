# Deployment notes

- This app segments data per client IP. Only the records created by a specific IP are visible and editable from that IP.
- Behind a reverse proxy (e.g., nginx, Cloudflare), set the environment variable `TRUST_PROXY=true` so the app uses `X-Forwarded-For`/`X-Real-IP` headers. Ensure your proxy sets these headers correctly.
- If multiple proxies are chained, adjust the `ProxyFix` configuration in `app.py` accordingly.
