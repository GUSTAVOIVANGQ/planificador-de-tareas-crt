# -*- coding: utf-8 -*-
"""Planificador CRT: servidor local sin bibliotecas externas. Python 3.10+."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import json
import mimetypes
from pathlib import Path
import sqlite3
import threading
from urllib.parse import urlsplit, parse_qs
import webbrowser

from lfpa import CalendarioLFPA, FUENTE_LFPA, _fecha, _validar_url_oficial

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
DATA_DIR = BASE / "datos"
DB_PATH = DATA_DIR / "crt_planificador.sqlite3"
LOCK = threading.RLock()
MAX_BODY = 64 * 1024
ESTADOS = {"pendiente", "en_proceso", "concluida", "cancelada"}
PRIORIDADES = {"baja", "media", "alta"}
TIPOS = {"interna", "plazo_lfpa"}


def db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def setup():
    with LOCK, db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS tareas (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          titulo TEXT NOT NULL, responsable TEXT NOT NULL DEFAULT '', area TEXT NOT NULL DEFAULT '',
          tipo TEXT NOT NULL, fecha_inicio TEXT NOT NULL, fecha_vencimiento TEXT NOT NULL,
          dias_habiles INTEGER, estado TEXT NOT NULL DEFAULT 'pendiente',
          prioridad TEXT NOT NULL DEFAULT 'media', detalle TEXT NOT NULL DEFAULT '',
          creado TEXT NOT NULL, actualizado TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS excepciones (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          fecha TEXT NOT NULL UNIQUE, tipo TEXT NOT NULL, motivo TEXT NOT NULL,
          fuenteUrl TEXT NOT NULL, registrado TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auditoria (
          id INTEGER PRIMARY KEY AUTOINCREMENT, tarea_id INTEGER,
          accion TEXT NOT NULL, descripcion TEXT NOT NULL, fecha TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_vencimiento ON tareas(fecha_vencimiento);
        """)


def motor():
    with LOCK, db() as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM excepciones ORDER BY fecha")]
    return CalendarioLFPA(
        dias_adicionales=[{"fecha": x["fecha"], "motivo": x["motivo"], "fuenteUrl": x["fuenteUrl"]}
                         for x in rows if x["tipo"] == "inhabil"],
        dias_habilitados=[{"fecha": x["fecha"], "motivo": x["motivo"], "fuenteUrl": x["fuenteUrl"]}
                         for x in rows if x["tipo"] == "habilitado"],
    )


def iso_today():
    return date.today().isoformat()


def ahora():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def error_if(cond, message):
    if cond:
        raise ValueError(message)


def text_field(payload, key, limit=200, required=False):
    val = payload.get(key, "")
    error_if(not isinstance(val, str), f"El campo {key} debe ser texto")
    val = val.strip()
    error_if(required and not val, f"Falta el campo {key}")
    error_if(len(val) > limit, f"{key} excede {limit} caracteres")
    return val


def task_input(p):
    error_if(not isinstance(p, dict), "Formato de tarea inválido")
    titulo = text_field(p, "titulo", 160, True)
    responsable = text_field(p, "responsable", 120)
    area = text_field(p, "area", 120)
    detalle = text_field(p, "detalle", 2000)
    tipo = text_field(p, "tipo", 30, True)
    estado = text_field(p, "estado", 30) or "pendiente"
    prioridad = text_field(p, "prioridad", 30) or "media"
    error_if(tipo not in TIPOS, "Tipo de tarea no admitido")
    error_if(estado not in ESTADOS, "Estado no admitido")
    error_if(prioridad not in PRIORIDADES, "Prioridad no admitida")
    inicio = _fecha(p.get("fecha_inicio")).isoformat()
    plazo = None
    if tipo == "plazo_lfpa":
        raw = p.get("dias_habiles")
        error_if(type(raw) is not int or not 1 <= raw <= 10000,
                 "El plazo debe ser un entero de 1 a 10000 días hábiles")
        plazo = raw
        vence = motor().sumar_dias_habiles(inicio, plazo)
    else:
        vence = _fecha(p.get("fecha_vencimiento")).isoformat()
        error_if(vence < inicio, "El vencimiento no puede ser anterior al inicio")
    return (titulo, responsable, area, tipo, inicio, vence, plazo, estado, prioridad, detalle)


def audit(conn, task_id, action, description):
    conn.execute("INSERT INTO auditoria(tarea_id, accion, descripcion, fecha) VALUES (?,?,?,?)",
                 (task_id, action, description, ahora()))


def task_out(row, cal):
    d = dict(row)
    d["fecha_sugerida"] = None
    d["necesita_revision"] = False
    if d["tipo"] == "plazo_lfpa":
        suggested = cal.sumar_dias_habiles(d["fecha_inicio"], d["dias_habiles"])
        if suggested != d["fecha_vencimiento"]:
            d["fecha_sugerida"] = suggested
            d["necesita_revision"] = True
    d["vencimiento_lfpa"] = cal.consultar_fecha(d["fecha_vencimiento"])
    return d


def list_tasks():
    cal = motor()
    with LOCK, db() as conn:
        rows = list(conn.execute("SELECT * FROM tareas ORDER BY fecha_vencimiento, id"))
    return [task_out(row, cal) for row in rows]


def create_task(p):
    vals = task_input(p)
    with LOCK, db() as conn:
        cur = conn.execute("""INSERT INTO tareas
          (titulo,responsable,area,tipo,fecha_inicio,fecha_vencimiento,dias_habiles,estado,prioridad,detalle,creado,actualizado)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (*vals, ahora(), ahora()))
        audit(conn, cur.lastrowid, "CREADA", vals[0])
        ident = cur.lastrowid
    return get_task(ident)


def get_task(ident):
    with LOCK, db() as conn:
        row = conn.execute("SELECT * FROM tareas WHERE id=?", (ident,)).fetchone()
    if row is None:
        raise LookupError("No existe esa tarea")
    return task_out(row, motor())


def update_task(ident, p):
    vals = task_input(p)
    with LOCK, db() as conn:
        old = conn.execute("SELECT id FROM tareas WHERE id=?", (ident,)).fetchone()
        if not old:
            raise LookupError("No existe esa tarea")
        conn.execute("""UPDATE tareas SET titulo=?,responsable=?,area=?,tipo=?,fecha_inicio=?,
          fecha_vencimiento=?,dias_habiles=?,estado=?,prioridad=?,detalle=?,actualizado=? WHERE id=?""",
          (*vals, ahora(), ident))
        audit(conn, ident, "EDITADA", vals[0])
    return get_task(ident)


def delete_task(ident):
    with LOCK, db() as conn:
        row = conn.execute("SELECT titulo FROM tareas WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise LookupError("No existe esa tarea")
        conn.execute("DELETE FROM tareas WHERE id=?", (ident,))
        audit(conn, ident, "ELIMINADA", row["titulo"])


def approve_recalc(ident):
    with LOCK, db() as conn:
        row = conn.execute("SELECT * FROM tareas WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise LookupError("No existe esa tarea")
        if row["tipo"] != "plazo_lfpa":
            raise ValueError("No es una tarea con plazo LFPA")
        date_new = motor().sumar_dias_habiles(row["fecha_inicio"], row["dias_habiles"])
        if date_new != row["fecha_vencimiento"]:
            conn.execute("UPDATE tareas SET fecha_vencimiento=?, actualizado=? WHERE id=?", (date_new, ahora(), ident))
            audit(conn, ident, "RECALCULADA", f"{row['fecha_vencimiento']} → {date_new}")
    return get_task(ident)


def add_exception(p):
    error_if(not isinstance(p, dict), "Solicitud inválida")
    fecha = _fecha(p.get("fecha")).isoformat()
    tipo = text_field(p, "tipo", 20, True)
    motivo = text_field(p, "motivo", 260, True)
    fuente = _validar_url_oficial(p.get("fuenteUrl"))
    error_if(tipo not in ("inhabil", "habilitado"), "Tipo de excepción inválido")
    error_if(p.get("confirmado") is not True, "Confirma que revisaste el acuerdo oficial")
    # Avoid claiming to parse or validate the legal content of the URL.
    with LOCK, db() as conn:
        try:
            cur = conn.execute("INSERT INTO excepciones(fecha,tipo,motivo,fuenteUrl,registrado) VALUES(?,?,?,?,?)",
                               (fecha, tipo, motivo, fuente, ahora()))
        except sqlite3.IntegrityError as exc:
            raise ValueError("Ya existe una excepción para esta fecha") from exc
        return {"id": cur.lastrowid, "fecha": fecha, "tipo": tipo, "motivo": motivo, "fuenteUrl": fuente}


def list_exceptions():
    with LOCK, db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM excepciones ORDER BY fecha")]


def delete_exception(ident):
    with LOCK, db() as conn:
        n = conn.execute("DELETE FROM excepciones WHERE id=?", (ident,)).rowcount
    if not n:
        raise LookupError("No existe la excepción")


def as_csv(headers, rows):
    s = StringIO()
    writer = csv.writer(s)
    writer.writerow(headers)
    writer.writerows(rows)
    return "\ufeff" + s.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "CRTPlanificador/1.0"
    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _headers(self, status, mime="application/json; charset=utf-8", length=None, download=None):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.end_headers()

    def send_data(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._headers(status, length=len(data))
        self.wfile.write(data)

    def send_text(self, value, mimetype, download=None):
        data = value.encode("utf-8")
        self._headers(200, mimetype, len(data), download)
        self.wfile.write(data)

    def serve_file(self, name):
        files = {"/": "index.html", "/index.html": "index.html", "/styles.css": "styles.css", "/app.js": "app.js"}
        fname = files.get(name)
        if not fname:
            self.send_data({"error": "Ruta no encontrada"}, 404)
            return
        path = STATIC / fname
        data = path.read_bytes()
        kind, _ = mimetypes.guess_type(path.name)
        self._headers(200, (kind or "application/octet-stream") + "; charset=utf-8", len(data))
        self.wfile.write(data)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= MAX_BODY:
            raise ValueError("El contenido enviado está vacío o es demasiado grande")
        try:
            val = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Se esperaba JSON válido") from exc
        if not isinstance(val, dict):
            raise ValueError("Se esperaba un objeto JSON")
        return val

    def route(self, method):
        parsed = urlsplit(self.path)
        path = parsed.path
        q = parse_qs(parsed.query)
        def query(key, default=None):
            return q.get(key, [default])[0]
        if path.startswith("/api/"):
            if method == "GET":
                cal = None
                if path == "/api/info":
                    return self.send_data({"fuente": FUENTE_LFPA, "hoy": iso_today(), "modo": "local_sin_autenticacion"})
                if path == "/api/tasks":
                    return self.send_data({"tareas": list_tasks()})
                if path == "/api/exceptions":
                    return self.send_data({"excepciones": list_exceptions()})
                if path == "/api/day":
                    cal = motor()
                    fecha = _fecha(query("date"))
                    return self.send_data(cal.consultar_fecha(fecha))
                if path == "/api/month":
                    year = int(query("year"))
                    month = int(query("month"))
                    if not 1900 <= year <= 9999 or not 1 <= month <= 12:
                        raise ValueError("Año o mes inválido")
                    cal = motor()
                    from calendar import monthrange
                    maxday = monthrange(year, month)[1]
                    days = [cal.consultar_fecha(date(year, month, x)) for x in range(1, maxday + 1)]
                    return self.send_data({"anio": year, "mes": month, "dias": days})
                if path == "/api/year":
                    year = int(query("year"))
                    cal = motor()
                    days = cal.calendario_anual(year)
                    return self.send_data({"anio": year, "inhabiles": sum(not d["habil"] for d in days),
                                           "habiles": sum(d["habil"] for d in days),
                                           "festivos": [d for d in days if d["clasificacion"] in
                                                        ("INHABIL_LFPA", "INHABIL_ADICIONAL_VALIDADO", "HABILITADO_EXCEPCIONALMENTE")]})
                if path == "/api/calculate":
                    cal = motor()
                    start = _fecha(query("start"))
                    days = int(query("days"))
                    due = cal.sumar_dias_habiles(start, days)
                    return self.send_data({"inicio": start.isoformat(), "dias_habiles": days,
                                           "vencimiento": due, "detalle": cal.consultar_fecha(due),
                                           "regla": "Cuenta desde el día siguiente a la fecha de inicio"})
                if path == "/api/export/calendar.csv":
                    year = int(query("year"))
                    cal = motor()
                    records = cal.calendario_anual(year)
                    headers = ("fecha", "habil", "clasificacion", "motivo", "fundamento", "fuenteUrl")
                    rows = ([d[h] for h in headers] for d in records)
                    return self.send_text(as_csv(headers, rows), "text/csv; charset=utf-8", f"CRT_LFPA_{year}.csv")
                if path == "/api/export/tasks.csv":
                    tasks = list_tasks()
                    headers = ("id", "titulo", "responsable", "area", "tipo", "fecha_inicio",
                               "fecha_vencimiento", "dias_habiles", "prioridad", "estado", "detalle")
                    return self.send_text(as_csv(headers, ([t[h] for h in headers] for t in tasks)),
                                          "text/csv; charset=utf-8", "Tareas_CRT.csv")
                if path == "/api/audit":
                    with LOCK, db() as conn:
                        rows = [dict(r) for r in conn.execute("SELECT * FROM auditoria ORDER BY id DESC LIMIT 100")]
                    return self.send_data({"auditoria": rows})
                return self.send_data({"error": "API no encontrada"}, 404)
            data = self.read_json() if method in ("POST", "PUT", "PATCH") else None
            if method == "POST" and path == "/api/tasks":
                return self.send_data({"tarea": create_task(data)}, 201)
            if method == "POST" and path == "/api/exceptions":
                return self.send_data({"excepcion": add_exception(data)}, 201)
            parts = path.strip("/").split("/")
            if len(parts) >= 3 and parts[:2] == ["api", "tasks"] and parts[2].isdigit():
                ident = int(parts[2])
                if method == "PUT" and len(parts) == 3:
                    return self.send_data({"tarea": update_task(ident, data)})
                if method == "DELETE" and len(parts) == 3:
                    delete_task(ident)
                    return self.send_data({"ok": True})
                if method == "POST" and len(parts) == 4 and parts[3] == "recalculate":
                    return self.send_data({"tarea": approve_recalc(ident)})
            if len(parts) == 3 and parts[:2] == ["api", "exceptions"] and parts[2].isdigit() and method == "DELETE":
                delete_exception(int(parts[2]))
                return self.send_data({"ok": True})
            return self.send_data({"error": "Acción no encontrada"}, 404)
        if method == "GET":
            return self.serve_file(path)
        return self.send_data({"error": "Método no permitido"}, 405)

    def do_GET(self):
        self.handle_call("GET")
    def do_POST(self):
        self.handle_call("POST")
    def do_PUT(self):
        self.handle_call("PUT")
    def do_PATCH(self):
        self.handle_call("PATCH")
    def do_DELETE(self):
        self.handle_call("DELETE")

    def handle_call(self, method):
        try:
            self.route(method)
        except LookupError as exc:
            self.send_data({"error": str(exc)}, 404)
        except (ValueError, OverflowError, TypeError, sqlite3.Error) as exc:
            self.send_data({"error": str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            print("Error interno:", repr(exc))
            try:
                self.send_data({"error": "Error interno del servidor"}, 500)
            except OSError:
                pass


def main():
    ap = argparse.ArgumentParser(description="Planificador web local CRT - LFPA")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1",
                    help="IP donde escucha el servidor (predeterminado 127.0.0.1)")
    ap.add_argument("--no-browser", action="store_true")
    opts = ap.parse_args()
    setup()
    host = opts.host
    if not 1 <= opts.port <= 65535:
        ap.error("El puerto debe estar entre 1 y 65535")
    httpd = ThreadingHTTPServer((host, opts.port), Handler)
    url = f"http://{host}:{httpd.server_port}/"
    print(f"\nPlanificador CRT funcionando: {url}")
    print(f"Datos guardados en: {DB_PATH}")
    print("Para cerrar, pulsa Ctrl + C en esta ventana.\n")
    if not opts.no_browser and host in ("127.0.0.1", "localhost"):
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Servidor detenido")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
