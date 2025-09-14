from flask import Flask, request, render_template, redirect, url_for, flash, abort
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime, timedelta, date as date_cls
import os
import json
import uuid

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")
if os.environ.get("TRUST_PROXY", "false").lower() in {"1", "true", "yes"}:
    # Trust first proxy in front (adjust x_for if more proxies)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1)  # type: ignore

# Simple JSON file persistence
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")


def load_records():
    """Load records from JSON file."""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def save_records(records):
    """Safely save records to JSON file (atomic write)."""
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def compute_worked_hours(start_str: str, end_str: str, break_minutes: int) -> float:
    """Compute worked hours between two HH:MM times minus break minutes.

    Supports overnight shifts by rolling end time to next day if needed.
    """
    start_dt = datetime.strptime(start_str, "%H:%M")
    end_dt = datetime.strptime(end_str, "%H:%M")
    if end_dt < start_dt:
        end_dt += timedelta(days=1)
    worked_time = end_dt - start_dt - timedelta(minutes=int(break_minutes or 0))
    # Prevent negative values if break > duration
    seconds = max(0, int(worked_time.total_seconds()))
    return round(seconds / 3600.0, 2)


def get_client_ip() -> str:
    """Best-effort client IP extraction, aware of common proxy headers.

    Note: Only trust X-Forwarded-For/X-Real-IP if your reverse proxy is configured
    to set them correctly. For production, prefer enabling ProxyFix or equivalent.
    """
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        # May contain a list like "client, proxy1, proxy2"; take the first
        first = xff.split(",")[0].strip()
        if first:
            return first
    xri = request.headers.get("X-Real-IP", "").strip()
    if xri:
        return xri
    return request.remote_addr or "unknown"


@app.get("/")
def index():
    all_records = load_records()
    current_ip = get_client_ip()
    # Selected date from query, default to today (redirect to canonical URL)
    today_str = date_cls.today().isoformat()
    if "date" not in request.args:
        return redirect(url_for("index", date=today_str))
    selected_date = request.args.get("date") or today_str
    # Validate date format
    try:
        datetime.strptime(selected_date, "%Y-%m-%d")
    except Exception:
        selected_date = today_str

    # Show only records created by this IP
    relevant = [r for r in all_records if r.get("ip") == current_ip]

    # Back-compat: if a record lacks 'date', show it under today by default
    filtered = [r for r in relevant if (r.get("date") or today_str) == selected_date]

    enriched = []
    total = 0.0
    for r in filtered:
        hours = compute_worked_hours(
            r["start_time"], r["end_time"], r.get("break_minutes", 0)
        )
        total += hours
        enriched.append({**r, "worked_hours": hours})

    # Navigation dates
    try:
        sel_dt = datetime.strptime(selected_date, "%Y-%m-%d").date()
    except Exception:
        sel_dt = date_cls.today()
    prev_date = (sel_dt - timedelta(days=1)).isoformat()
    next_date = (sel_dt + timedelta(days=1)).isoformat()

    # Available dates for quick jump
    available_dates = sorted({(r.get("date") or today_str) for r in relevant})

    return render_template(
        "index.html",
        records=enriched,
        total_hours=round(total, 2),
        current_ip=current_ip,
        selected_date=selected_date,
        prev_date=prev_date,
        next_date=next_date,
        available_dates=available_dates,
    )


@app.post("/add")
def add():
    current_ip = get_client_ip()
    name = (request.form.get("name") or "").strip()
    start_time = request.form.get("start_time") or ""
    end_time = request.form.get("end_time") or ""
    date_str = (request.form.get("date") or "").strip()
    if not date_str:
        date_str = date_cls.today().isoformat()
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        date_str = date_cls.today().isoformat()
    break_minutes_raw = request.form.get("break_minutes")
    try:
        break_minutes = (
            int(break_minutes_raw) if break_minutes_raw not in (None, "") else 0
        )
    except ValueError:
        break_minutes = 0

    if not name:
        flash("Name is required.", "danger")
        return redirect(url_for("index"))
    try:
        datetime.strptime(start_time, "%H:%M")
        datetime.strptime(end_time, "%H:%M")
    except Exception:
        flash("Start and End time must be in HH:MM format.", "danger")
        return redirect(url_for("index"))

    records = load_records()
    new_record = {
        "id": str(uuid.uuid4()),
        "name": name,
        "start_time": start_time,
        "end_time": end_time,
        "break_minutes": break_minutes,
        "ip": current_ip,
        "date": date_str,
    }
    records.append(new_record)
    save_records(records)
    flash(f"Added record for {name}.", "success")
    return redirect(url_for("index", date=date_str))


@app.get("/edit/<record_id>")
def edit_form(record_id):
    records = load_records()
    current_ip = get_client_ip()
    record = next(
        (r for r in records if r.get("id") == record_id and r.get("ip") == current_ip),
        None,
    )
    if not record:
        abort(404)
    return render_template("edit.html", record=record)


@app.post("/edit/<record_id>")
def edit(record_id):
    records = load_records()
    current_ip = get_client_ip()
    idx = next(
        (
            i
            for i, r in enumerate(records)
            if r.get("id") == record_id and r.get("ip") == current_ip
        ),
        None,
    )
    if idx is None:
        abort(404)

    name = (request.form.get("name") or "").strip()
    start_time = request.form.get("start_time") or ""
    end_time = request.form.get("end_time") or ""
    date_str = (request.form.get("date") or "").strip()
    if not date_str:
        date_str = records[idx].get("date") or date_cls.today().isoformat()
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        date_str = records[idx].get("date") or date_cls.today().isoformat()
    break_minutes_raw = request.form.get("break_minutes")
    try:
        break_minutes = (
            int(break_minutes_raw) if break_minutes_raw not in (None, "") else 0
        )
    except ValueError:
        break_minutes = 0

    if not name:
        flash("Name is required.", "danger")
        return redirect(url_for("edit_form", record_id=record_id))
    try:
        datetime.strptime(start_time, "%H:%M")
        datetime.strptime(end_time, "%H:%M")
    except Exception:
        flash("Start and End time must be in HH:MM format.", "danger")
        return redirect(url_for("edit_form", record_id=record_id))

    records[idx].update(
        {
            "name": name,
            "start_time": start_time,
            "end_time": end_time,
            "break_minutes": break_minutes,
            "date": date_str,
        }
    )
    save_records(records)
    flash("Record updated.", "success")
    return redirect(url_for("index", date=date_str))


@app.post("/delete/<record_id>")
def delete(record_id):
    records = load_records()
    current_ip = get_client_ip()
    # Only allow deleting records from same IP
    new_records = [
        r
        for r in records
        if not (r.get("id") == record_id and r.get("ip") == current_ip)
    ]
    if len(new_records) == len(records):
        abort(404)
    save_records(new_records)
    flash("Record deleted.", "info")
    return_date = request.form.get("return_date")
    if return_date:
        try:
            datetime.strptime(return_date, "%Y-%m-%d")
        except Exception:
            return_date = None
    return redirect(url_for("index", **({"date": return_date} if return_date else {})))


if __name__ == "__main__":
    # Allow overriding host/port/debug via environment variables for local runs
    # PORT: numeric port (default 5000)
    # HOST: bind address (default 127.0.0.1)
    # DEBUG or FLASK_DEBUG: enable debug when set to 1/true/yes (default False)
    host = os.environ.get("HOST", "127.0.0.1")
    port_env = os.environ.get("PORT")
    try:
        port = int(port_env) if port_env else 5000
    except (TypeError, ValueError):
        port = 5000
    debug_env = os.environ.get("FLASK_DEBUG") or os.environ.get("DEBUG")
    debug = str(debug_env).lower() in {"1", "true", "yes"}
    app.run(host=host, port=port, debug=debug)
