"""Панель управления хостингом ITKAM34 (VM 104, порт 8097)."""
import os
import subprocess
import zipfile

import requests
from flask import Flask, request, render_template, session, redirect, jsonify

BASE = "/opt/hosting"


def envfile(path):
    d = {}
    try:
        for line in open(path):
            if "=" in line:
                k, v = line.strip().split("=", 1)
                d[k] = v
    except OSError:
        pass
    return d


BE = envfile(f"{BASE}/.bridge_env")
PE = envfile(f"{BASE}/.panel_env")
TOKEN = BE.get("BRIDGE_TOKEN", "")
BRIDGE = f"http://127.0.0.1:{BE.get('BRIDGE_PORT', '8098')}"

app = Flask(__name__)
app.secret_key = PE.get("PANEL_PASSWORD", "change-me") + "-panel"


def b(method, path, payload=None):
    r = requests.request(method, BRIDGE + path, json=payload,
                         headers={"X-Bridge-Token": TOKEN}, timeout=60)
    try:
        return r.json()
    except ValueError:
        return {"ok": False, "error": r.text[:200]}


def login_ok():
    return session.get("panel") == "yes"


@app.route("/login", methods=["GET", "POST"])
def login():
    err = None
    if request.method == "POST":
        if request.form.get("password") == PE.get("PANEL_PASSWORD"):
            session["panel"] = "yes"
            return redirect("/")
        err = "Неверный пароль"
    return render_template("login.html", error=err)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/")
def index():
    if not login_ok():
        return redirect("/login")
    data = b("GET", "/services") or {}
    return render_template("index.html", services=data.get("services", []))


@app.route("/create", methods=["POST"])
def create():
    if not login_ok():
        return redirect("/login")
    kind = request.form.get("kind", "static")
    domain = (request.form.get("domain") or "").strip().lower()
    force = "1" if request.form.get("force") else "0"
    res = b("POST", "/create_service", {"kind": kind, "name": domain or kind})
    if not res.get("ok"):
        return jsonify(res), 400
    sid = res["service_id"]
    vol = res.get("volume", f"{BASE}/sites/{sid}")
    os.makedirs(vol, exist_ok=True)
    msg = ""
    f = request.files.get("archive")
    if f and f.filename.endswith(".zip"):
        msg = unzip_into(f, vol)
    if domain:
        att = b("POST", "/attach_domain", {"service_id": sid, "domain": domain, "force": force == "1"})
        if not att.get("ok"):
            msg += " Домен: " + str(att.get("error"))
    return redirect(f"/service/{sid}?created=1&msg={msg[:140]}")


def unzip_into(f, vol):
    tmp = f"/tmp/upload_{os.getpid()}.zip"
    f.save(tmp)
    try:
        with zipfile.ZipFile(tmp) as z:
            for n in z.namelist():
                if n.startswith("/") or ".." in n:
                    continue
                z.extract(n, vol)
        return "Файлы распакованы."
    except zipfile.BadZipFile:
        return "Некорректный zip."
    finally:
        os.remove(tmp)


@app.route("/service/<int:sid>")
def service(sid):
    if not login_ok():
        return redirect("/login")
    logs = subprocess.run(["docker", "logs", "--tail", "80", f"hs-{sid}"],
                          capture_output=True, text=True)
    data = b("GET", "/services") or {}
    svc = next((s for s in data.get("services", []) if s["id"] == sid), None)
    return render_template("service.html", svc=svc, sid=sid,
                           logs=(logs.stdout + logs.stderr)[-4000:],
                           created=request.args.get("created"),
                           msg=request.args.get("msg", ""))


@app.route("/service/<int:sid>/<action>", methods=["POST"])
def service_action(sid, action):
    if not login_ok():
        return redirect("/login")
    if action in ("stop", "start"):
        subprocess.run(["docker", action, f"hs-{sid}"], check=False, capture_output=True)
        b("POST", "/set_active", {"service_id": sid, "active": action == "start"})
    elif action == "delete":
        b("POST", "/delete_service", {"service_id": sid})
        return redirect("/")
    elif action == "attach":
        domain = (request.form.get("domain") or "").strip().lower()
        force = bool(request.form.get("force"))
        r = b("POST", "/attach_domain", {"service_id": sid, "domain": domain, "force": force})
        if not r.get("ok"):
            return redirect(f"/service/{sid}?msg={str(r.get('error'))[:140]}")
    elif action == "upload":
        kind = "python" if os.path.isdir(f"{BASE}/apps/{sid}") else ("php" if _is_php(sid) else "static")
        vol = f"{BASE}/apps/{sid}" if kind == "python" else f"{BASE}/sites/{sid}"
        f = request.files.get("archive")
        if f and f.filename.endswith(".zip"):
            unzip_into(f, vol)
    return redirect(f"/service/{sid}")


def _is_php(sid):
    st = subprocess.run(["docker", "inspect", "-f", "{{.Config.Image}}", f"hs-{sid}"],
                        capture_output=True, text=True)
    return "php" in (st.stdout or "")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8097)
