import os
import json
import hashlib
import httpx
import pandas as pd
from io import BytesIO
from pathlib import Path
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from icalendar import Calendar
from datetime import date
import uvicorn

app = FastAPI()

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

CLIENTS_FILE = DATA_DIR / "clients.json"
SA_FILE = DATA_DIR / "sa_list.json"

APP_PASSWORD = os.environ.get("APP_PASSWORD", "sdtcalctime")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "AIzaSyALDvkmkGoptesgXcyECfwuKGvnXhHRysw")
SECRET_KEY = os.environ.get("SECRET_KEY", "sdt-secret-key-change-in-prod")

INSTRUCTORS = {
    "Christian Lagos": {
        "base": "1/80 Para Road, Montmorency VIC 3094",
        "ics": "https://calsync.nookal.com/icsFile.php?HhXBkBCdHTLQaK4lrqfVa9ew%2FKnxwK8N60bfEsnM4Tix4fvM5lyQStblMTQiqaNaGeCeSgeSmXf%2F4kKI9OvU2fnXpnN%2FtMeidfD9E6WmLBWPsPF881mF4%2FDKjqX6mENEnlggTWF2jMn8Em8aKgSGXA%3D%3D"
    },
    "Gabriel Lagos": {
        "base": "36 Main Street, Croydon VIC 3136",
        "ics": "https://calsync.nookal.com/icsFile.php?HhXBkBCdHTLQaK4lrqfVa9ew%2FKnxwK8N60bfEsnM4Tix4fvM5lyQStblMTQiqaNaGeCeSgeSmXf%2F4kKI9OvU2a52GEgwyPVJ%2B0I6mOab2rD4%2Bmqr7EYvQGR9ykfeKAj%2F"
    },
    "Greg Ekkel": {
        "base": "Kilsyth VIC 3137",
        "ics": "https://calsync.nookal.com/icsFile.php?HhXBkBCdHTLQaK4lrqfVa9ew%2FKnxwK8N60bfEsnM4Tix4fvM5lyQStblMTQiqaNaGeCeSgeSmXf%2F4kKI9OvU2fgA7lzqZCrNH6P0mJPZWpJqu4G4d87qHmXHYUUq3ZhplneSIXp12lfHZzfvGyQdDw%3D%3D"
    },
    "Jason Simmonds": {
        "base": "Wandin VIC 3139",
        "ics": "https://calsync.nookal.com/icsFile.php?HhXBkBCdHTLQaK4lrqfVa9ew%2FKnxwK8N60bfEsnM4Tix4fvM5lyQStblMTQiqaNaGeCeSgeSmXf%2F4kKI9OvU2Sks8REnxfIzFLWWhJgXRykKsTkQKIlND6Q3P8UWc8WWFJCS5Y5gIU0xiqPfnSz%2FkQ%3D%3D"
    },
    "Marc Seow": {
        "base": "Townley Boulevard, Werribee VIC 3030",
        "ics": "https://calsync.nookal.com/icsFile.php?HhXBkBCdHTLQaK4lrqfVa9ew%2FKnxwK8N60bfEsnM4Tix4fvM5lyQStblMTQiqaNaGeCeSgeSmXf%2F4kKI9OvU2ecoRZN2xzdtmsUYY9vDrAuMuEJAzQSivaNXrwqSOqrMT982Jq4gficfE9XDNSVl0A%3D%3D"
    },
    "Yves Salzmann": {
        "base": "Iolanda Street, Rye VIC 3941",
        "ics": "https://calsync.nookal.com/icsFile.php?HhXBkBCdHTLQaK4lrqfVa9ew%2FKnxwK8N60bfEsnM4Tix4fvM5lyQStblMTQiqaNaJ6xepUO6AS0mQIBuSqW%2BOWjh2dEdLM2ryJYQQBbgLemmcR6jFHgrJeGdQCO3yfSW7dInaTI63gFq7aNCi2ArGCg%3D%3D"
    },
    "Sherri Simmonds": {
        "base": "Wandin VIC 3139",
        "ics": "https://calsync.nookal.com/icsFile.php?HhXBkBCdHTLQaK4lrqfVa9ew%2FKnxwK8N60bfEsnM4Tix4fvM5lyQStblMTQiqaNaGeCeSgeSmXf%2F4kKI9OvU2Qm9F8eQzb%2B6bu2IC%2FLaNBOOWmK9yskJZYl8guOGtP67bXXfuA0nBVLMaaPL2rsqew%3D%3D"
    }
}

# ── Auth helpers ──────────────────────────────────────────────────────────────

def check_auth(request: Request) -> bool:
    token = request.cookies.get("auth")
    expected = hashlib.sha256(APP_PASSWORD.encode()).hexdigest()
    return token == expected

def require_auth(request: Request):
    if not check_auth(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

# ── Name helpers ──────────────────────────────────────────────────────────────

def clean_name(name: str) -> str:
    if not name:
        return ""
    import re
    name = re.sub(r'^(Mr|Ms|Mrs|Miss|Dr)\.?\s+', '', name, flags=re.IGNORECASE)
    return name.strip().lower()

def load_clients() -> dict:
    if CLIENTS_FILE.exists():
        return json.loads(CLIENTS_FILE.read_text())
    return {}

def load_sa() -> list:
    if SA_FILE.exists():
        return json.loads(SA_FILE.read_text())
    return []

def has_sa(name: str, sa_list: list) -> bool:
    cn = clean_name(name)
    sa_set = set(sa_list)
    if cn in sa_set:
        return True
    parts = cn.split()
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        for sa in sa_set:
            if first in sa and last in sa:
                return True
    return False

def lookup_client(name: str, clients: dict):
    cn = clean_name(name)
    if cn in clients:
        return clients[cn]
    parts = cn.split()
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        for k, v in clients.items():
            if first in k and last in k:
                return v
    return None

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse(LOGIN_HTML)

@app.post("/login")
async def do_login(password: str = Form(...)):
    if password == APP_PASSWORD:
        token = hashlib.sha256(APP_PASSWORD.encode()).hexdigest()
        resp = RedirectResponse(url="/", status_code=302)
        resp.set_cookie("auth", token, max_age=86400 * 30, httponly=True, samesite="lax")
        return resp
    return HTMLResponse(LOGIN_HTML.replace("<!--ERROR-->", '<p class="error">Wrong password. Try again.</p>'))

@app.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie("auth")
    return resp

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not check_auth(request):
        return RedirectResponse(url="/login")
    clients_loaded = CLIENTS_FILE.exists()
    sa_loaded = SA_FILE.exists()
    clients_count = len(load_clients()) if clients_loaded else 0
    sa_count = len(load_sa()) if sa_loaded else 0
    return HTMLResponse(get_main_html(clients_count, sa_count))

# ── Data upload ───────────────────────────────────────────────────────────────

@app.post("/upload/clients")
async def upload_clients(request: Request, file: UploadFile = File(...)):
    require_auth(request)
    content = await file.read()
    try:
        if file.filename.endswith(".xlsx"):
            df = pd.read_excel(BytesIO(content))
        else:
            df = pd.read_csv(BytesIO(content))

        if "Client Name" not in df.columns or "Address" not in df.columns:
            return JSONResponse({"error": "File must have 'Client Name' and 'Address' columns"}, status_code=400)

        clients = {}
        for _, row in df.iterrows():
            name = str(row.get("Client Name", "")).strip()
            address = str(row.get("Address", "")).strip()
            if not name or not address or address in ("nan", "") or len(address) < 8:
                continue
            cn = clean_name(name)
            if cn:
                clients[cn] = [name, address]

        CLIENTS_FILE.write_text(json.dumps(clients))
        return JSONResponse({"success": True, "count": len(clients)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@app.post("/upload/sa")
async def upload_sa(request: Request, file: UploadFile = File(...)):
    require_auth(request)
    content = await file.read()
    try:
        df = pd.read_csv(BytesIO(content))
        sa_names = set()
        for col in ["Participant Name", "Client Name"]:
            if col in df.columns:
                for n in df[col].dropna():
                    cn = clean_name(str(n).strip())
                    if cn:
                        sa_names.add(cn)
        SA_FILE.write_text(json.dumps(list(sa_names)))
        return JSONResponse({"success": True, "count": len(sa_names)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

# ── Calendar fetch ────────────────────────────────────────────────────────────

@app.get("/calendar/{instructor_key}")
async def get_calendar(instructor_key: str, request: Request, date_str: str = ""):
    require_auth(request)
    instructor = instructor_key.replace("_", " ")
    if instructor not in INSTRUCTORS:
        return JSONResponse({"error": "Unknown instructor"}, status_code=404)

    ics_url = INSTRUCTORS[instructor]["ics"]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(ics_url)
            resp.raise_for_status()
    except Exception as e:
        return JSONResponse({"error": f"Could not fetch calendar: {str(e)}"}, status_code=500)

    try:
        cal = Calendar.from_ical(resp.content)
        events = []
        clients = load_clients()
        sa_list = load_sa()

        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            summary = str(component.get("SUMMARY", "")).strip()
            dtstart = component.get("DTSTART")
            if not summary or not dtstart:
                continue

            dt = dtstart.dt
            if hasattr(dt, 'date'):
                event_date = dt.date()
                hour = dt.hour
                minute = dt.minute
            else:
                event_date = dt
                hour = 0
                minute = 0

            if date_str:
                try:
                    filter_date = date.fromisoformat(date_str)
                    if event_date != filter_date:
                        continue
                except:
                    pass

            match = lookup_client(summary, clients)
            events.append({
                "name": summary,
                "displayName": match[0] if match else summary,
                "address": match[1] if match else "",
                "isNDIS": True,
                "hasSA": has_sa(summary, sa_list),
                "hour": hour,
                "minute": minute,
                "date": event_date.isoformat()
            })

        events.sort(key=lambda e: e["hour"] * 60 + e["minute"])
        return JSONResponse({"events": events, "count": len(events)})
    except Exception as e:
        return JSONResponse({"error": f"Could not parse calendar: {str(e)}"}, status_code=500)

# ── Distance calculation ──────────────────────────────────────────────────────

@app.post("/distance")
async def get_distance(request: Request):
    require_auth(request)
    body = await request.json()
    origin = body.get("origin", "")
    destination = body.get("destination", "")
    if not origin or not destination:
        return JSONResponse({"error": "Missing origin or destination"}, status_code=400)

    url = (
        f"https://maps.googleapis.com/maps/api/distancematrix/json"
        f"?origins={httpx.URL(origin)}&destinations={httpx.URL(destination)}"
        f"&units=metric&key={GOOGLE_API_KEY}"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/distancematrix/json",
                params={"origins": origin, "destinations": destination, "units": "metric", "key": GOOGLE_API_KEY}
            )
            data = resp.json()
        element = data["rows"][0]["elements"][0]
        if element["status"] == "OK":
            km = element["distance"]["value"] / 1000
            return JSONResponse({"km": round(km, 3)})
        else:
            return JSONResponse({"error": f"No route found: {element['status']}"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ── Client lookup ─────────────────────────────────────────────────────────────

@app.get("/client/search")
async def search_client(request: Request, q: str = ""):
    require_auth(request)
    if len(q) < 2:
        return JSONResponse({"results": []})
    clients = load_clients()
    sa_list = load_sa()
    cn = clean_name(q)
    results = []
    for k, v in clients.items():
        if cn in k or (cn.split()[0] in k if cn.split() else False):
            results.append({
                "key": k,
                "name": v[0],
                "address": v[1],
                "hasSA": has_sa(v[0], sa_list)
            })
        if len(results) >= 8:
            break
    return JSONResponse({"results": results})

# ── HTML ──────────────────────────────────────────────────────────────────────

LOGIN_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SDT Travel Billing — Login</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'DM Sans', sans-serif; background: #0f0f0f; color: #f0f0f0; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
  .box { background: #1a1a1a; border: 1px solid #2e2e2e; border-radius: 16px; padding: 40px; width: 100%; max-width: 380px; }
  .logo { font-family: 'DM Mono', monospace; font-size: 12px; color: #e8ff47; letter-spacing: 0.15em; text-transform: uppercase; margin-bottom: 24px; }
  h1 { font-size: 22px; font-weight: 600; margin-bottom: 8px; }
  p { color: #777; font-size: 14px; margin-bottom: 28px; }
  label { font-size: 11px; color: #777; font-family: 'DM Mono', monospace; text-transform: uppercase; letter-spacing: 0.08em; display: block; margin-bottom: 6px; }
  input[type="password"] { width: 100%; background: #222; border: 1px solid #2e2e2e; border-radius: 8px; color: #f0f0f0; padding: 12px 14px; font-family: 'DM Sans', sans-serif; font-size: 15px; outline: none; margin-bottom: 16px; }
  input[type="password"]:focus { border-color: #e8ff47; }
  button { width: 100%; background: #e8ff47; color: #000; border: none; border-radius: 8px; padding: 12px; font-family: 'DM Sans', sans-serif; font-size: 15px; font-weight: 600; cursor: pointer; }
  button:hover { background: #d4ea3a; }
  .error { color: #ff6b6b; font-size: 13px; margin-bottom: 14px; background: rgba(255,107,107,0.1); padding: 8px 12px; border-radius: 6px; }
</style>
</head>
<body>
<div class="box">
  <div class="logo">SDT / Travel Billing</div>
  <h1>Sign in</h1>
  <p>Enter the password to access the calculator.</p>
  <!--ERROR-->
  <form method="post" action="/login">
    <label>Password</label>
    <input type="password" name="password" autofocus placeholder="••••••••••••">
    <button type="submit">Continue</button>
  </form>
</div>
</body>
</html>"""


def get_main_html(clients_count: int, sa_count: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SDT Travel Billing Calculator</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');
  :root {{
    --bg:#0f0f0f; --surface:#1a1a1a; --surface2:#222; --border:#2e2e2e;
    --accent:#e8ff47; --accent2:#47b3ff; --danger:#ff6b6b; --success:#47ffb3;
    --text:#f0f0f0; --muted:#777;
  }}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;}}
  header{{background:var(--surface);border-bottom:1px solid var(--border);padding:14px 32px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;}}
  .logo{{font-family:'DM Mono',monospace;font-size:13px;color:var(--accent);letter-spacing:0.1em;text-transform:uppercase;}}
  .logo span{{color:var(--muted);}}
  .header-right{{display:flex;align-items:center;gap:16px;}}
  .data-status{{font-family:'DM Mono',monospace;font-size:11px;color:var(--muted);}}
  .data-status .ok{{color:var(--success);}}
  .data-status .warn{{color:#ffc800;}}
  .btn-logout{{font-family:'DM Mono',monospace;font-size:11px;color:var(--muted);background:none;border:1px solid var(--border);border-radius:6px;padding:4px 10px;cursor:pointer;text-decoration:none;}}
  .btn-logout:hover{{color:var(--danger);border-color:var(--danger);}}
  main{{max-width:900px;margin:0 auto;padding:32px 24px;}}
  h1{{font-size:26px;font-weight:600;margin-bottom:4px;letter-spacing:-0.02em;}}
  .subtitle{{color:var(--muted);font-size:14px;margin-bottom:28px;}}
  .card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:22px;margin-bottom:18px;}}
  .step-header{{display:flex;align-items:center;gap:12px;margin-bottom:16px;}}
  .step-num{{width:26px;height:26px;border-radius:50%;background:var(--accent);color:#000;font-family:'DM Mono',monospace;font-size:12px;font-weight:500;display:flex;align-items:center;justify-content:center;flex-shrink:0;}}
  .step-num.done{{background:var(--success);}}
  .step-num.inactive{{background:var(--border);color:var(--muted);}}
  .step-title{{font-size:15px;font-weight:500;}}
  select,input[type=text],input[type=date],input[type=number]{{background:var(--surface2);border:1px solid var(--border);border-radius:8px;color:var(--text);padding:10px 14px;font-family:'DM Sans',sans-serif;font-size:14px;outline:none;transition:border-color 0.2s;}}
  select:focus,input:focus{{border-color:var(--accent);}}
  select{{cursor:pointer;}}
  .form-row{{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;}}
  .form-group{{display:flex;flex-direction:column;gap:5px;}}
  .form-group label{{font-size:11px;color:var(--muted);font-family:'DM Mono',monospace;text-transform:uppercase;letter-spacing:0.08em;}}
  .btn{{padding:10px 20px;border-radius:8px;border:none;cursor:pointer;font-family:'DM Sans',sans-serif;font-size:14px;font-weight:500;transition:all 0.15s;}}
  .btn-primary{{background:var(--accent);color:#000;}}
  .btn-primary:hover{{background:#d4ea3a;}}
  .btn-primary:disabled{{background:var(--border);color:var(--muted);cursor:not-allowed;}}
  .btn-secondary{{background:var(--surface2);color:var(--text);border:1px solid var(--border);}}
  .btn-secondary:hover{{border-color:var(--accent);color:var(--accent);}}
  .btn-sm{{padding:6px 12px;font-size:12px;border-radius:6px;}}
  .btn-danger{{background:transparent;color:var(--danger);border:1px solid var(--danger);}}
  .btn-danger:hover{{background:var(--danger);color:#000;}}
  .client-list{{display:flex;flex-direction:column;gap:8px;margin-top:14px;}}
  .client-row{{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:11px 14px;display:flex;align-items:center;gap:10px;}}
  .client-row.from-cal{{border-left:3px solid var(--accent2);}}
  .drag-handle{{color:var(--muted);cursor:grab;font-size:16px;user-select:none;}}
  .client-num{{font-family:'DM Mono',monospace;font-size:12px;color:var(--muted);width:18px;flex-shrink:0;}}
  .client-info{{flex:1;min-width:0;}}
  .client-name{{font-size:13px;font-weight:500;display:flex;align-items:center;gap:6px;flex-wrap:wrap;}}
  .client-address{{font-size:12px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  .badge{{font-family:'DM Mono',monospace;font-size:10px;padding:2px 6px;border-radius:4px;text-transform:uppercase;letter-spacing:0.04em;flex-shrink:0;}}
  .badge-sa{{background:rgba(71,255,179,0.15);color:var(--success);}}
  .badge-no-sa{{background:rgba(255,107,107,0.15);color:var(--danger);}}
  .badge-no-addr{{background:rgba(255,200,0,0.15);color:#ffc800;}}
  .badge-ndis{{background:rgba(232,255,71,0.1);color:var(--accent);}}
  .badge-priv{{background:rgba(120,120,120,0.2);color:var(--muted);}}
  .client-controls{{display:flex;gap:6px;align-items:center;flex-shrink:0;}}
  .ndis-label{{font-size:11px;color:var(--muted);display:flex;align-items:center;gap:4px;}}
  .toggle{{width:34px;height:19px;background:var(--border);border-radius:10px;position:relative;transition:background 0.2s;cursor:pointer;border:none;outline:none;flex-shrink:0;}}
  .toggle.on{{background:var(--success);}}
  .toggle::after{{content:'';position:absolute;width:13px;height:13px;background:white;border-radius:50%;top:3px;left:3px;transition:left 0.2s;}}
  .toggle.on::after{{left:18px;}}
  .addr-wrap{{position:relative;flex:1;}}
  .addr-wrap input{{width:100%;}}
  .suggestions{{position:absolute;top:100%;left:0;right:0;background:var(--surface);border:1px solid var(--border);border-radius:8px;z-index:50;max-height:220px;overflow-y:auto;margin-top:4px;display:none;}}
  .suggestion{{padding:10px 14px;cursor:pointer;font-size:13px;border-bottom:1px solid var(--border);}}
  .suggestion:last-child{{border-bottom:none;}}
  .suggestion:hover{{background:var(--surface2);color:var(--accent);}}
  .add-row{{display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap;}}
  .or-div{{display:flex;align-items:center;gap:12px;margin:16px 0;color:var(--muted);font-size:12px;}}
  .or-div::before,.or-div::after{{content:'';flex:1;height:1px;background:var(--border);}}
  .results-table{{width:100%;border-collapse:collapse;font-size:13px;}}
  .results-table th{{font-family:'DM Mono',monospace;font-size:10px;text-transform:uppercase;letter-spacing:0.07em;color:var(--muted);padding:8px 10px;text-align:left;border-bottom:1px solid var(--border);}}
  .results-table td{{padding:9px 10px;border-bottom:1px solid var(--border);vertical-align:middle;}}
  .results-table tr:last-child td{{border-bottom:none;}}
  .results-table tr.eligible td{{color:var(--success);}}
  .results-table tr.not-elig td{{color:var(--muted);}}
  .results-table tr.base-row td{{color:var(--muted);font-style:italic;}}
  .charge{{font-family:'DM Mono',monospace;font-size:15px;font-weight:500;color:var(--accent);}}
  .summary-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:18px;}}
  .sc{{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:14px;}}
  .sc-label{{font-family:'DM Mono',monospace;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:var(--muted);margin-bottom:5px;}}
  .sc-val{{font-size:21px;font-weight:600;font-family:'DM Mono',monospace;color:var(--accent);}}
  .sc-sub{{font-size:11px;color:var(--muted);margin-top:2px;}}
  .status-msg{{font-family:'DM Mono',monospace;font-size:12px;padding:10px 14px;border-radius:6px;margin-top:10px;line-height:1.5;}}
  .s-info{{background:rgba(71,179,255,0.1);color:var(--accent2);}}
  .s-error{{background:rgba(255,107,107,0.1);color:var(--danger);}}
  .s-success{{background:rgba(71,255,179,0.1);color:var(--success);}}
  .spinner{{display:inline-block;width:13px;height:13px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin 0.7s linear infinite;vertical-align:middle;margin-right:5px;}}
  @keyframes spin{{to{{transform:rotate(360deg);}}}}
  .info-note{{font-size:12px;color:var(--muted);padding:9px 13px;background:rgba(255,255,255,0.03);border-radius:6px;border-left:3px solid var(--border);margin-top:10px;line-height:1.5;}}
  .hidden{{display:none!important;}}
  .leg-note{{font-family:'DM Mono',monospace;font-size:11px;color:var(--muted);}}
  .r-note{{font-size:12px;color:#ffc800;margin-top:10px;padding:9px 13px;background:rgba(255,200,0,0.07);border-radius:6px;}}
  .export-bar{{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap;}}
  .data-cards{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:4px;}}
  .data-card{{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:14px;}}
  .data-card-title{{font-family:'DM Mono',monospace;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:var(--muted);margin-bottom:8px;}}
  .data-card-count{{font-size:18px;font-weight:600;color:var(--accent);font-family:'DM Mono',monospace;margin-bottom:8px;}}
  .data-card-sub{{font-size:12px;color:var(--muted);margin-bottom:10px;}}
  .upload-btn{{display:inline-block;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:7px 14px;font-size:12px;cursor:pointer;transition:all 0.15s;color:var(--text);}}
  .upload-btn:hover{{border-color:var(--accent);color:var(--accent);}}
  .upload-input{{display:none;}}
  @media(max-width:600px){{main{{padding:16px;}}header{{padding:12px 16px;}}.form-row,.add-row{{flex-direction:column;}}.data-cards{{grid-template-columns:1fr;}}}}
</style>
</head>
<body>
<header>
  <div class="logo">SDT <span>/</span> Travel Billing</div>
  <div class="header-right">
    <div class="data-status">
      Clients: <span class="{'ok' if clients_count > 0 else 'warn'}">{clients_count if clients_count > 0 else 'not loaded'}</span>
      &nbsp;·&nbsp;
      SAs: <span class="{'ok' if sa_count > 0 else 'warn'}">{sa_count if sa_count > 0 else 'not loaded'}</span>
    </div>
    <a href="/logout" class="btn-logout">Sign out</a>
  </div>
</header>

<main>
  <h1>Travel Cost Calculator</h1>
  <p class="subtitle">NDIS non-labour travel costs · $0.97/km · Auto-split across eligible clients</p>

  <!-- DATA MANAGEMENT -->
  <div class="card">
    <div class="step-header">
      <div class="step-num" style="background:var(--surface2);color:var(--muted);border:1px solid var(--border);">↑</div>
      <div class="step-title">Data Files</div>
    </div>
    <div class="data-cards">
      <div class="data-card">
        <div class="data-card-title">Client Database (Nookal)</div>
        <div class="data-card-count" id="clientCount">{clients_count if clients_count > 0 else '—'}</div>
        <div class="data-card-sub">{'clients with addresses' if clients_count > 0 else 'Not loaded — upload your Nookal client export (.xlsx)'}</div>
        <label class="upload-btn">
          {'Update' if clients_count > 0 else 'Upload'} Client File
          <input type="file" class="upload-input" accept=".xlsx,.csv" onchange="uploadFile('clients', this)">
        </label>
        <div id="clientUploadStatus"></div>
      </div>
      <div class="data-card">
        <div class="data-card-title">Service Agreements (Snapforms)</div>
        <div class="data-card-count" id="saCount">{sa_count if sa_count > 0 else '—'}</div>
        <div class="data-card-sub">{'signed agreements on file' if sa_count > 0 else 'Not loaded — upload your Snapforms SA export (.csv)'}</div>
        <label class="upload-btn">
          {'Update' if sa_count > 0 else 'Upload'} SA File
          <input type="file" class="upload-input" accept=".csv" onchange="uploadFile('sa', this)">
        </label>
        <div id="saUploadStatus"></div>
      </div>
    </div>
  </div>

  <!-- STEP 1 -->
  <div class="card">
    <div class="step-header">
      <div class="step-num">1</div>
      <div class="step-title">Select Instructor & Date</div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Instructor</label>
        <select id="instructorSelect" onchange="onInstructorChange()">
          <option value="">— Choose —</option>
          <option>Christian Lagos</option>
          <option>Gabriel Lagos</option>
          <option>Greg Ekkel</option>
          <option>Jason Simmonds</option>
          <option>Marc Seow</option>
          <option>Yves Salzmann</option>
          <option>Sherri Simmonds</option>
        </select>
      </div>
      <div class="form-group">
        <label>Date</label>
        <input type="date" id="dateInput" onchange="checkReady()">
      </div>
      <div class="form-group" style="justify-content:flex-end;">
        <button class="btn btn-secondary" id="loadCalBtn" onclick="loadCalendar()" disabled>
          Load from Calendar
        </button>
      </div>
    </div>
    <div id="baseInfo" class="info-note hidden"></div>
    <div id="calStatus"></div>
  </div>

  <!-- STEP 2 -->
  <div class="card">
    <div class="step-header">
      <div class="step-num inactive" id="step2Num">2</div>
      <div class="step-title">Clients for This Day</div>
    </div>
    <div class="client-list" id="clientList">
      <div style="color:var(--muted);font-size:13px;">No clients yet — load from calendar or add manually below.</div>
    </div>
    <div class="or-div">add manually</div>
    <div class="add-row">
      <div class="form-group" style="flex:1;min-width:160px;">
        <label>Name</label>
        <div class="addr-wrap">
          <input type="text" id="manualName" placeholder="Start typing..." oninput="searchClient(this.value)" autocomplete="off">
          <div class="suggestions" id="nameSuggestions"></div>
        </div>
      </div>
      <div class="form-group" style="flex:2;min-width:180px;">
        <label>Address</label>
        <input type="text" id="manualAddress" placeholder="Full address">
      </div>
      <div class="form-group">
        <label>Type</label>
        <select id="manualType"><option value="ndis">NDIS</option><option value="private">Private</option></select>
      </div>
      <div class="form-group" style="justify-content:flex-end;">
        <button class="btn btn-primary" onclick="addManualClient()">Add</button>
      </div>
    </div>
    <div class="info-note">Drag to reorder. Green SA badge = signed service agreement on file. Toggle manually to override.</div>
  </div>

  <!-- STEP 3 -->
  <div class="card">
    <div class="step-header">
      <div class="step-num inactive">3</div>
      <div class="step-title">Tolls (if any)</div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label>Total Tolls ($)</label>
        <input type="number" id="tollAmount" value="0" min="0" step="0.01" style="width:120px;">
      </div>
      <div class="form-group" style="flex:1;">
        <label>Note</label>
        <input type="text" id="tollNote" placeholder="e.g. EastLink x2" style="width:100%;">
      </div>
    </div>
    <div class="info-note">Tolls split equally across NDIS clients with signed SAs only.</div>
  </div>

  <!-- STEP 4 -->
  <div class="card">
    <div class="step-header">
      <div class="step-num inactive">4</div>
      <div class="step-title">Calculate</div>
    </div>
    <button class="btn btn-primary" id="calcBtn" onclick="calculate()" disabled style="font-size:15px;padding:14px 32px;">
      Calculate Travel Costs
    </button>
    <div id="calcStatus"></div>
  </div>

  <!-- RESULTS -->
  <div class="card hidden" id="resultsCard">
    <div class="step-header">
      <div class="step-num done">✓</div>
      <div class="step-title">Results</div>
    </div>
    <div class="summary-grid" id="summaryGrid"></div>
    <table class="results-table">
      <thead><tr><th>#</th><th>Client</th><th>Leg</th><th>Km</th><th>SA</th><th>Charge</th><th>Note</th></tr></thead>
      <tbody id="resultsBody"></tbody>
    </table>
    <div id="rNote" class="r-note hidden"></div>
    <div class="export-bar">
      <button class="btn btn-primary" onclick="exportCSV()">Export CSV</button>
      <button class="btn btn-secondary" onclick="copyResults()">Copy to Clipboard</button>
      <button class="btn btn-secondary" onclick="window.print()">Print / PDF</button>
    </div>
  </div>
</main>

<script>
const KM_RATE = 0.97;
const INSTRUCTORS = {json.dumps(INSTRUCTORS)};
let clients = [];
let calcResults = null;

// ── File uploads ──────────────────────────────────────────────────────────────
async function uploadFile(type, input) {{
  const file = input.files[0];
  if (!file) return;
  const statusId = type === 'clients' ? 'clientUploadStatus' : 'saUploadStatus';
  showStatus(statusId, '<span class="spinner"></span>Uploading...', 'info');
  const fd = new FormData();
  fd.append('file', file);
  try {{
    const resp = await fetch('/upload/' + type, {{method:'POST', body:fd}});
    const data = await resp.json();
    if (data.success) {{
      showStatus(statusId, `✓ Loaded ${{data.count}} ${{type === 'clients' ? 'clients' : 'signed SAs'}}`, 'success');
      if (type === 'clients') document.getElementById('clientCount').textContent = data.count;
      else document.getElementById('saCount').textContent = data.count;
    }} else {{
      showStatus(statusId, 'Error: ' + data.error, 'error');
    }}
  }} catch(e) {{
    showStatus(statusId, 'Upload failed: ' + e.message, 'error');
  }}
}}

// ── Instructor / calendar ─────────────────────────────────────────────────────
function onInstructorChange() {{
  const sel = document.getElementById('instructorSelect').value;
  const bi = document.getElementById('baseInfo');
  const btn = document.getElementById('loadCalBtn');
  if (sel && INSTRUCTORS[sel]) {{
    bi.textContent = 'Base: ' + INSTRUCTORS[sel].base;
    bi.classList.remove('hidden');
    btn.disabled = false;
  }} else {{
    bi.classList.add('hidden');
    btn.disabled = true;
  }}
  checkReady();
}}

async function loadCalendar() {{
  const instructor = document.getElementById('instructorSelect').value;
  const dateStr = document.getElementById('dateInput').value;
  if (!instructor) return;
  showStatus('calStatus', '<span class="spinner"></span>Loading calendar from Nookal...', 'info');
  try {{
    const key = instructor.replace(/ /g, '_');
    const resp = await fetch(`/calendar/${{key}}?date_str=${{dateStr}}`);
    const data = await resp.json();
    if (data.error) return showStatus('calStatus', 'Error: ' + data.error, 'error');
    if (!data.events.length) return showStatus('calStatus', `No appointments found${{dateStr ? ' for ' + dateStr : ''}}. Check the date or add manually.`, 'error');
    clients = data.events.map(e => ({{...e, fromCalendar: true}}));
    renderClientList();
    showStatus('calStatus', `✓ Loaded ${{data.count}} appointment(s). Check SA badges and reorder if needed.`, 'success');
    document.getElementById('step2Num').classList.remove('inactive');
    checkReady();
  }} catch(e) {{
    showStatus('calStatus', 'Failed to load calendar: ' + e.message, 'error');
  }}
}}

// ── Client list ───────────────────────────────────────────────────────────────
function renderClientList() {{
  const list = document.getElementById('clientList');
  if (!clients.length) {{ list.innerHTML = '<div style="color:var(--muted);font-size:13px;">No clients yet.</div>'; return; }}
  list.innerHTML = '';
  clients.forEach((c, i) => {{
    const saBadge = c.isNDIS ? (c.hasSA ? '<span class="badge badge-sa">SA ✓</span>' : '<span class="badge badge-no-sa">No SA</span>') : '<span class="badge badge-priv">Private</span>';
    const addrBadge = !c.address ? '<span class="badge badge-no-addr">No Addr</span>' : '';
    const row = document.createElement('div');
    row.className = 'client-row' + (c.fromCalendar ? ' from-cal' : '');
    row.draggable = true;
    row.innerHTML = `
      <span class="drag-handle">⠿</span>
      <span class="client-num">${{i+1}}</span>
      <div class="client-info">
        <div class="client-name">${{c.displayName || c.name}} ${{saBadge}} ${{addrBadge}}</div>
        <div class="client-address">${{c.address || '— address not found —'}}</div>
      </div>
      <div class="client-controls">
        <label class="ndis-label">NDIS <button class="toggle ${{c.isNDIS?'on':''}}" onclick="toggleNDIS(${{i}})"></button></label>
        <button class="btn btn-secondary btn-sm" onclick="toggleSA(${{i}})" style="width:52px;">${{c.hasSA?'SA ✓':'SA ✗'}}</button>
        <button class="btn btn-danger btn-sm" onclick="removeClient(${{i}})">✕</button>
      </div>`;
    row.addEventListener('dragstart', e => {{ e.dataTransfer.setData('text/plain', i); row.style.opacity='0.4'; }});
    row.addEventListener('dragend', () => row.style.opacity='1');
    row.addEventListener('dragover', e => {{ e.preventDefault(); row.style.borderColor='var(--accent)'; }});
    row.addEventListener('dragleave', () => row.style.borderColor='');
    row.addEventListener('drop', e => {{
      e.preventDefault(); row.style.borderColor='';
      const from=parseInt(e.dataTransfer.getData('text/plain')), to=i;
      if(from!==to){{ const item=clients.splice(from,1)[0]; clients.splice(to,0,item); renderClientList(); }}
    }});
    list.appendChild(row);
  }});
  checkReady();
}}

function toggleNDIS(i) {{ clients[i].isNDIS=!clients[i].isNDIS; renderClientList(); }}
function toggleSA(i) {{ clients[i].hasSA=!clients[i].hasSA; renderClientList(); }}
function removeClient(i) {{ clients.splice(i,1); renderClientList(); checkReady(); }}

// ── Manual add ────────────────────────────────────────────────────────────────
async function searchClient(val) {{
  const sug = document.getElementById('nameSuggestions');
  if (!val || val.length < 2) {{ sug.style.display='none'; return; }}
  const resp = await fetch('/client/search?q=' + encodeURIComponent(val));
  const data = await resp.json();
  if (!data.results.length) {{ sug.style.display='none'; return; }}
  sug.innerHTML = data.results.map(r =>
    `<div class="suggestion" onclick="selectClient('${{r.name.replace(/'/g,"\\\\'")}}',' ${{r.address.replace(/'/g,"\\\\'")}}',${{r.hasSA}})">
      <strong>${{r.name}}</strong><br>
      <span style="color:var(--muted);font-size:11px;">${{r.address}}</span>
    </div>`
  ).join('');
  sug.style.display='block';
}}

function selectClient(name, address, hasSA) {{
  document.getElementById('manualName').value = name;
  document.getElementById('manualAddress').value = address.trim();
  document.getElementById('nameSuggestions').style.display='none';
}}

function addManualClient() {{
  const name = document.getElementById('manualName').value.trim();
  const address = document.getElementById('manualAddress').value.trim();
  if (!name) return;
  clients.push({{ name, displayName:name, address, isNDIS: document.getElementById('manualType').value==='ndis', hasSA:false, fromCalendar:false }});
  document.getElementById('manualName').value='';
  document.getElementById('manualAddress').value='';
  renderClientList();
  document.getElementById('step2Num').classList.remove('inactive');
  checkReady();
}}

document.addEventListener('click', e => {{ if(!e.target.closest('#manualName')) document.getElementById('nameSuggestions').style.display='none'; }});

function checkReady() {{
  document.getElementById('calcBtn').disabled = !(clients.length >= 1 && document.getElementById('instructorSelect').value);
}}

// ── Calculate ─────────────────────────────────────────────────────────────────
async function getKm(origin, dest) {{
  const resp = await fetch('/distance', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{origin, destination:dest}})
  }});
  const data = await resp.json();
  if (data.error) throw new Error(data.error);
  return data.km;
}}

async function calculate() {{
  const instructor = document.getElementById('instructorSelect').value;
  const tollAmount = parseFloat(document.getElementById('tollAmount').value) || 0;
  const tollNote = document.getElementById('tollNote').value.trim();
  const base = INSTRUCTORS[instructor].base;

  document.getElementById('calcBtn').disabled = true;
  document.getElementById('resultsCard').classList.add('hidden');
  showStatus('calcStatus', '<span class="spinner"></span>Calculating distances...', 'info');

  try {{
    const waypoints = [base, ...clients.map(c => c.address || base), base];
    const legs = [];

    for (let i=0; i<waypoints.length-1; i++) {{
      showStatus('calcStatus', `<span class="spinner"></span>Leg ${{i+1}} of ${{waypoints.length-1}}...`, 'info');
      const from=waypoints[i], to=waypoints[i+1];
      if (!from || !to || from===to) {{ legs.push(0); continue; }}
      legs.push(await getKm(from, to));
      await new Promise(r=>setTimeout(r,120));
    }}

    const eligible = clients.map((c,i) => ({{...c, idx:i, eligible: c.isNDIS && c.hasSA && !!c.address}}));
    const eligCount = eligible.filter(e=>e.eligible).length;
    const firstLeg = legs[0];
    const midLegs = legs.slice(1, legs.length-1);
    let returnKm = legs[legs.length-1];
    let returnNote = 'Return from last client';

    const lastEligIdx = eligible.reduce((l,e,i) => e.eligible?i:l, -1);
    if (lastEligIdx >= 0 && lastEligIdx < clients.length-1 && clients[lastEligIdx].address) {{
      showStatus('calcStatus', '<span class="spinner"></span>Checking return reasonableness...', 'info');
      const alt = await getKm(clients[lastEligIdx].address, base);
      if (alt < returnKm) {{ returnKm=alt; returnNote=`Return from ${{clients[lastEligIdx].displayName?.split(' ')[0]}} (last SA client — lower)`; }}
    }}

    const totalKm = midLegs.reduce((s,k)=>s+k,0) + returnKm;
    const perAll = clients.length > 0 ? totalKm/clients.length : 0;
    const perElig = eligCount > 0 ? totalKm/eligCount : 0;
    const chosenRate = Math.min(perAll, perElig);
    const method = perAll<=perElig ? `÷ ${{clients.length}} all clients` : `÷ ${{eligCount}} eligible`;
    const tollPer = eligCount > 0 ? tollAmount/eligCount : 0;
    const chargePerClient = chosenRate * KM_RATE + tollPer;

    calcResults = {{ instructor, date:document.getElementById('dateInput').value, base, clients:eligible, legs, firstLeg, midLegs, returnKm, returnNote, totalKm, eligCount, chosenRate, method, chargePerClient, tollAmount, tollPer, tollNote, perAll, perElig }};
    renderResults(calcResults);
    clearStatus('calcStatus');
  }} catch(e) {{
    showStatus('calcStatus', 'Error: ' + e.message, 'error');
  }} finally {{
    document.getElementById('calcBtn').disabled = false;
  }}
}}

// ── Results ───────────────────────────────────────────────────────────────────
function renderResults(r) {{
  document.getElementById('resultsCard').classList.remove('hidden');
  document.getElementById('summaryGrid').innerHTML = `
    <div class="sc"><div class="sc-label">Charge Per Eligible Client</div><div class="sc-val">$${{r.chargePerClient.toFixed(2)}}</div><div class="sc-sub">${{r.eligCount}} eligible · ${{r.method}}</div></div>
    <div class="sc"><div class="sc-label">Total Chargeable Km</div><div class="sc-val">${{r.totalKm.toFixed(1)}}</div><div class="sc-sub">@ $${{KM_RATE}}/km = $${{(r.totalKm*KM_RATE).toFixed(2)}}</div></div>
    ${{r.tollAmount>0?`<div class="sc"><div class="sc-label">Tolls</div><div class="sc-val">$${{r.tollAmount.toFixed(2)}}</div><div class="sc-sub">$${{r.tollPer.toFixed(2)}} / eligible client</div></div>`:''}}
  `;
  const tbody = document.getElementById('resultsBody');
  tbody.innerHTML = '';
  const addRow = (cls, cells) => {{
    const tr=document.createElement('tr'); tr.className=cls;
    tr.innerHTML=cells.map(c=>`<td>${{c}}</td>`).join(''); tbody.appendChild(tr);
  }};
  addRow('base-row',['—',`Base: ${{r.base.split(',')[0]}}`,'—','—','—','—','Start']);
  addRow('not-elig',['→',r.clients[0]?.displayName||'—',`Base → ${{r.clients[0]?.displayName?.split(' ')[0]||'—'}} <span class="leg-note">(commute)</span>`,`${{r.firstLeg.toFixed(1)}} km`,'—','—','Not charged']);
  r.clients.forEach((c,i) => {{
    const leg = i<r.midLegs.length?r.midLegs[i]:0;
    const legLabel = i===0?'(at client)':`${{r.clients[i-1]?.displayName?.split(' ')[0]||'—'}} → ${{c.displayName?.split(' ')[0]}}`;
    addRow(c.eligible?'eligible':'not-elig',[
      i+1, c.displayName||c.name,
      `<span class="leg-note">${{legLabel}}</span>`,
      i===0?'—':`${{leg.toFixed(1)}} km`,
      c.isNDIS?(c.hasSA?'✓':'✗'):'n/a',
      c.eligible?`<span class="charge">$${{r.chargePerClient.toFixed(2)}}</span>`:'—',
      !c.isNDIS?'Private':!c.hasSA?'No SA':!c.address?'No address':''
    ]);
  }});
  addRow('base-row',['↩','Return to Base',`<span class="leg-note">${{r.clients[r.clients.length-1]?.displayName?.split(' ')[0]||'—'}} → Base</span>`,`${{r.returnKm.toFixed(1)}} km`,'—','—',r.returnNote]);
  const rn=document.getElementById('rNote');
  if (Math.abs(r.perAll-r.perElig)>3) {{
    rn.textContent=`Reasonableness: all-client split = $${{(r.perAll*KM_RATE).toFixed(2)}}, eligible-only = $${{(r.perElig*KM_RATE).toFixed(2)}}. Using lower: $${{(r.chosenRate*KM_RATE).toFixed(2)}}/client.`;
    rn.classList.remove('hidden');
  }} else rn.classList.add('hidden');
  document.getElementById('resultsCard').scrollIntoView({{behavior:'smooth'}});
}}

// ── Export ────────────────────────────────────────────────────────────────────
function exportCSV() {{
  if (!calcResults) return;
  const r=calcResults;
  let csv=`SDT Travel Billing,${{r.instructor}},${{r.date}}\\nClient,Address,NDIS,SA,Charge\\n`;
  r.clients.forEach(c=>{{ csv+=`"${{c.displayName}}","${{c.address}}",${{c.isNDIS}},${{c.hasSA}},${{c.eligible?r.chargePerClient.toFixed(2):'0'}}\\n`; }});
  csv+=`\\nTotal km,${{r.totalKm.toFixed(1)}}\\n@ ${{KM_RATE}}/km\\nPer eligible client,$${{r.chargePerClient.toFixed(2)}}\\n`;
  const a=Object.assign(document.createElement('a'),{{href:URL.createObjectURL(new Blob([csv],{{type:'text/csv'}})),download:`SDT-Travel-${{r.instructor.split(' ')[0]}}-${{r.date||'nodate'}}.csv`}});
  a.click();
}}

function copyResults() {{
  if (!calcResults) return;
  const r=calcResults;
  let text=`SDT Travel — ${{r.instructor}} — ${{r.date}}\\n\\n`;
  r.clients.filter(c=>c.eligible).forEach(c=>{{ text+=`${{c.displayName}}: $${{r.chargePerClient.toFixed(2)}}\\n`; }});
  text+=`\\nTotal km: ${{r.totalKm.toFixed(1)}} | $${{KM_RATE}}/km | Per client: $${{r.chargePerClient.toFixed(2)}}`;
  navigator.clipboard.writeText(text).then(()=>{{ showStatus('calcStatus','✓ Copied','success'); setTimeout(()=>clearStatus('calcStatus'),2000); }});
}}

function showStatus(id,msg,type) {{ document.getElementById(id).innerHTML=`<div class="status-msg s-${{type}}">${{msg}}</div>`; }}
function clearStatus(id) {{ document.getElementById(id).innerHTML=''; }}

document.getElementById('dateInput').value = new Date().toISOString().split('T')[0];
</script>
</body>
</html>"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
