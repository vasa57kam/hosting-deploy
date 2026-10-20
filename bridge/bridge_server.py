import os, sqlite3, subprocess
from flask import Flask, request, jsonify

BASE = "/opt/hosting"
DB = os.path.join(BASE, "bridge.db")
TOKEN = os.environ.get("BRIDGE_TOKEN", "")
PORT = int(os.environ.get("BRIDGE_PORT", "8098"))
HOST_IP = os.environ.get("HOST_IP", "")
SITES = "/etc/caddy/sites"

app = Flask(__name__)

def db():
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS services (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, name TEXT, port INTEGER, status TEXT DEFAULT 'active', created_at TEXT DEFAULT (datetime('now')))")
    conn.execute("CREATE TABLE IF NOT EXISTS domains (id INTEGER PRIMARY KEY AUTOINCREMENT, service_id INTEGER, domain TEXT UNIQUE, verified INTEGER DEFAULT 0)")
    return conn

def auth():
    return TOKEN != "" and request.headers.get("X-Bridge-Token", "") == TOKEN

def caddy_reload():
    subprocess.run(["systemctl", "reload", "caddy"], check=False)

def write_snippet(service_id, domain, port):
    with open(f"{SITES}/hs-{service_id}-{domain}.caddy", "w") as f:
        f.write(f"http://{domain} {{\n\treverse_proxy 127.0.0.1:{port}\n}}\n")

@app.get("/ping")
def ping():
    return jsonify({"ok": True, "service": "hosting-bridge"})

@app.post("/create_service")
def create_service():
    if not auth(): return jsonify({"ok": False, "error": "bad token"}), 403
    d = request.get_json(silent=True) or {}
    kind = d.get("kind", "static")
    if kind not in ("static", "php", "python"):
        return jsonify({"ok": False, "error": "kind must be static|php|python"}), 400
    conn = db()
    cur = conn.execute("INSERT INTO services (kind, name) VALUES (?, ?)", (kind, d.get("name") or f"site-{kind}"))
    sid = cur.lastrowid
    port = 9100 + sid
    conn.execute("UPDATE services SET port=? WHERE id=?", (port, sid))
    conn.commit()
    conn.close()
    vol = f"{BASE}/apps/{sid}" if kind == "python" else f"{BASE}/sites/{sid}"
    os.makedirs(vol, exist_ok=True)
    if kind == "static":
        cmd = ["docker", "run", "-d", f"--name=hs-{sid}", "--restart=unless-stopped",
               "-v", f"{vol}:/usr/share/nginx/html:ro", "-p", f"127.0.0.1:{port}:80", "nginx:alpine"]
    elif kind == "php":
        cmd = ["docker", "run", "-d", f"--name=hs-{sid}", "--restart=unless-stopped",
               "-v", f"{vol}:/app", "-p", f"127.0.0.1:{port}:80", "webdevops/php-nginx:8.2-alpine"]
    else:
        cmd = ["docker", "run", "-d", f"--name=hs-{sid}", "--restart=unless-stopped",
               "-v", f"{vol}:/app", "-p", f"127.0.0.1:{port}:8000", "python:3.11-slim",
               "sh", "-c", "pip install -q -r /app/requirements.txt 2>/dev/null; exec python /app/server.py"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0: return jsonify({"ok": False, "error": r.stderr[:400]}), 500
    return jsonify({"ok": True, "service_id": sid, "port": port, "volume": vol, "kind": kind})

@app.post("/attach_domain")
def attach_domain():
    if not auth(): return jsonify({"ok": False, "error": "bad token"}), 403
    d = request.get_json(silent=True) or {}
    sid = int(d.get("service_id", 0))
    domain = (d.get("domain") or "").strip().lower()
    force = bool(d.get("force"))
    if not domain or not sid: return jsonify({"ok": False, "error": "service_id and domain required"}), 400
    conn = db()
    svc = conn.execute("SELECT * FROM services WHERE id=?", (sid,)).fetchone()
    if svc is None: conn.close(); return jsonify({"ok": False, "error": "service not found"}), 404
    if not force and HOST_IP:
        try:
            import socket
            ip = socket.gethostbyname(domain)
        except Exception: ip = None
        if ip != HOST_IP:
            conn.close()
            return jsonify({"ok": False, "error": f"DNS указывает на {ip}, нужно на {HOST_IP}"}), 400
    conn.execute("INSERT OR REPLACE INTO domains (service_id, domain, verified) VALUES (?, ?, 1)", (sid, domain))
    conn.commit()
    conn.close()
    write_snippet(sid, domain, svc["port"])
    caddy_reload()
    return jsonify({"ok": True, "domain": domain, "url": f"https://{domain}"})

@app.get("/caddy/allow")
def caddy_allow():
    domain = (request.args.get("domain") or "").strip().lower()
    conn = db()
    row = conn.execute("SELECT d.id FROM domains d JOIN services s ON s.id=d.service_id WHERE d.domain=? AND s.status='active'", (domain,)).fetchone()
    conn.close()
    if row is None: return jsonify({"ok": False}), 403
    return jsonify({"ok": True})

@app.get("/services")
def services():
    if not auth(): return jsonify({"ok": False, "error": "bad token"}), 403
    conn = db()
    rows = conn.execute("SELECT * FROM services ORDER BY id").fetchall()
    doms = conn.execute("SELECT service_id, domain FROM domains").fetchall()
    conn.close()
    dm = {}
    for r in doms: dm.setdefault(r["service_id"], []).append(r["domain"])
    return jsonify({"ok": True, "services": [dict(r, domains=dm.get(r["id"], [])) for r in rows]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
