# Work Hour Calculator

A simple, friendly web app to track worked hours per person using start/end times and a break. Data is stored locally in a JSON file.

This guide targets Ubuntu 22.04 (Jammy) for local and production-style setups.

## Features

- Add records with name, start/end time (HH:MM), and break minutes
- List all records with per-row and total hours
- Edit an existing record
- Delete a record with confirmation
- Handles overnight shifts (e.g., 22:00 to 06:00)
- Per-IP data isolation: each visitor sees only their own records by default

## Requirements

- Ubuntu 22.04 with Python 3.10+ (default on 22.04)
- See `requirements.txt`

## Quick start (Ubuntu 22.04)

Install system packages and run the app in a virtual environment:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
export FLASK_SECRET_KEY="change-me"  # optional
python app.py
```

Open http://127.0.0.1:5000/ in your browser.

Tips:
- Data is saved to `data.json` in the project directory (git-ignored).
- Set `FLASK_SECRET_KEY` to customize the session key used for flash messages.

## Per-IP behavior and proxies

This app isolates data by client IP. When running behind a reverse proxy (nginx, Cloudflare, etc.), set:

```bash
export TRUST_PROXY=true
```

Ensure your proxy sets `X-Forwarded-For` or `X-Real-IP`. If you have multiple proxies, adjust `ProxyFix` in `app.py` accordingly.

## Optional: systemd service (Ubuntu 22.04)

Run the app as a service with Gunicorn for resilience. From the project directory:

```bash
source .venv/bin/activate
pip install gunicorn
```

Create a systemd unit (as root):

```bash
sudo tee /etc/systemd/system/time-app.service > /dev/null <<'UNIT'
[Unit]
Description=Work Hour Calculator (Gunicorn)
After=network.target

[Service]
User=%i
WorkingDirectory=/home/%i/time.lvh.lol/time.lvh.lol
Environment="FLASK_SECRET_KEY=change-me"
Environment="TRUST_PROXY=true"
ExecStart=/home/%i/time.lvh.lol/time.lvh.lol/.venv/bin/gunicorn -w 2 -b 127.0.0.1:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable time-app.service
sudo systemctl start time-app.service
sudo systemctl status time-app.service --no-pager
```

Adjust `WorkingDirectory` and paths to match where your repo lives. You can also hardcode the username instead of `%i` if preferred.

## Optional: Nginx reverse proxy

Install and configure Nginx to serve on port 80 and forward to Gunicorn on 127.0.0.1:8000:

```bash
sudo apt install -y nginx
sudo tee /etc/nginx/sites-available/time-app > /dev/null <<'NGINX'
server {
	listen 80;
	server_name _;

	location / {
		proxy_set_header Host $host;
		proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
		proxy_set_header X-Forwarded-Proto $scheme;
		proxy_pass http://127.0.0.1:8000;
	}
}
NGINX

sudo ln -s /etc/nginx/sites-available/time-app /etc/nginx/sites-enabled/time-app
sudo nginx -t
sudo systemctl reload nginx
```

Now browse to your server's IP or domain.

## Troubleshooting

- Permission denied on `data.json`: make sure the service user has write access to the project directory.
- Seeing other users' data: verify `TRUST_PROXY=true` is set and Nginx forwards `X-Forwarded-For`.
- 500 errors on edit/delete: the record may not belong to your IP; add a new record from your client to test.
