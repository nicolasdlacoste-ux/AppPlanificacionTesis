"""
patch_polling.py — aplica todos los cambios de backend del plan de polling.
Modifica: poll_manager.py, api_server.py
Ejecutar una sola vez desde AppPlanificacion/.
"""
import re

# ─────────────────────────────────────────────────────────────
# 1. poll_manager.py — _handle_cancelled + _loop dinámico
# ─────────────────────────────────────────────────────────────

with open("poll_manager.py", "r", encoding="utf-8") as f:
    src = f.read()

OLD_HANDLE = '''    def _handle_cancelled(self, event_id: str, calendar_id: str):
        """
        Marca un evento cancelado por Google.
        NO borra: solo loggea para revisión humana futura.
        """
        _poll_log(self.db, "CANCELLED_EVENT", "DETECTED",
                  {"note": "No borrado automáticamente — requiere revisión"},
                  calendar_id=calendar_id, event_id=event_id)'''

NEW_HANDLE = '''    def _handle_cancelled(self, event_id: str, calendar_id: str):
        """
        Encola un evento cancelado en Google para revisión humana.
        Si el operador acepta, el evento se borra localmente.
        """
        local = self.db.find_by_google_event_id(event_id)
        if local:
            self.db.enqueue_review(local["id"], calendar_id, {
                "_action": {"old": "EXISTS", "new": "DELETE", "category": "critical"}
            })
            _poll_log(self.db, "CANCELLED_EVENT", "QUEUED_FOR_REVIEW",
                      {"local_id": local["id"],
                       "note": "Cancelado en Google — pendiente de aprobación para borrar localmente"},
                      calendar_id=calendar_id, event_id=event_id)
        else:
            _poll_log(self.db, "CANCELLED_EVENT", "NOT_FOUND_LOCALLY",
                      {"note": "Evento cancelado no existe localmente, nada que hacer"},
                      calendar_id=calendar_id, event_id=event_id)'''

OLD_LOOP = '''            time.sleep(POLL_INTERVAL_SECONDS)'''
NEW_LOOP = '''            # Leer intervalo dinámicamente para que cambios desde la UI surtan efecto
            try:
                cfg = self.db.get_app_config()
                interval = int(cfg.get("poll_interval_seconds", POLL_INTERVAL_SECONDS))
                interval = max(60, min(3600, interval))  # clamp 1min–1h
            except Exception:
                interval = POLL_INTERVAL_SECONDS
            time.sleep(interval)'''

if OLD_HANDLE in src:
    src = src.replace(OLD_HANDLE, NEW_HANDLE)
    print("OK: _handle_cancelled actualizado")
else:
    print("WARN: _handle_cancelled no encontrado — puede que ya esté actualizado")

if OLD_LOOP in src:
    src = src.replace(OLD_LOOP, NEW_LOOP)
    print("OK: _loop actualizado con intervalo dinámico")
else:
    print("WARN: time.sleep(POLL_INTERVAL_SECONDS) no encontrado")

with open("poll_manager.py", "w", encoding="utf-8") as f:
    f.write(src)
print("poll_manager.py guardado.")


# ─────────────────────────────────────────────────────────────
# 2. api_server.py — startup auto-poll + 3 nuevos endpoints
# ─────────────────────────────────────────────────────────────

with open("api_server.py", "r", encoding="utf-8") as f:
    api = f.read()

# 2a. Auto-inicio del polling en startup (antes del primer @app.get)
STARTUP_BLOCK = '''
# ── AUTO-INICIO DEL POLLING ───────────────────────────────────
@app.on_event("startup")
async def on_startup():
    """Inicia el ciclo de polling automáticamente al arrancar la app."""
    import asyncio
    await asyncio.sleep(2)   # pequeña espera para que la DB quede lista
    ok = poll_manager.start(sync_worker)
    if ok:
        print("[POLL] Polling iniciado automáticamente al arrancar.")
    else:
        print("[POLL] Checklist falló — polling no iniciado automáticamente. Usar /api/poll/start manualmente.")

'''

ANCHOR_STARTUP = '# ─────────────────────────────────────────────\n# HELPERS'
if '@app.on_event("startup")' not in api:
    api = api.replace(ANCHOR_STARTUP, STARTUP_BLOCK + ANCHOR_STARTUP)
    print("OK: startup event agregado")
else:
    print("SKIP: startup event ya existe")

# 2b. Los 3 nuevos endpoints — insertarlos antes del mount de la webapp
NEW_ENDPOINTS = '''
# ─────────────────────────────────────────────────────────────────────────────
# POLL CONFIG — intervalo configurable desde UI
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/poll/config")
async def get_poll_config():
    """Lee la configuración de polling (intervalo)."""
    cfg = db.get_app_config()
    return {"interval_seconds": cfg.get("poll_interval_seconds", 300)}

@app.post("/api/poll/config")
async def set_poll_config(interval_seconds: int = Query(..., ge=60, le=3600)):
    """Guarda el intervalo de polling en app_config."""
    await check_authorization()
    cfg = db.get_app_config()
    cfg["poll_interval_seconds"] = interval_seconds
    db.save_app_config(cfg)
    import poll_manager as pm
    pm.POLL_INTERVAL_SECONDS = interval_seconds
    return {"status": "ok", "interval_seconds": interval_seconds}

@app.post("/api/poll/review_queue/{review_id}/apply")
async def apply_review_change(review_id: str):
    """
    Aplica un cambio crítico aprobado por el operador al evento local.
    Marca el review como APPLIED y, si es un DELETE, borra el evento.
    """
    await check_authorization()
    import traceback as tb
    try:
        row = db.get_review_by_id(review_id)
        if not row:
            raise HTTPException(status_code=404, detail="Review no encontrado")
        diff = json.loads(row["diff_json"])
        db.apply_poll_critical_change(row["event_id"], diff)
        with db._get_connection() as conn:
            conn.execute(
                "UPDATE poll_review_queue SET status='APPLIED' WHERE review_id=?",
                (review_id,)
            )
            conn.commit()
        return {"status": "APPLIED", "review_id": review_id, "event_id": row["event_id"]}
    except HTTPException:
        raise
    except Exception as e:
        print("[apply_review]", tb.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

'''

WEBAPP_MOUNT = 'webapp_path = get_resource_path("webapp")'
if '/api/poll/review_queue/{review_id}/apply' not in api:
    api = api.replace(WEBAPP_MOUNT, NEW_ENDPOINTS + WEBAPP_MOUNT)
    print("OK: 3 nuevos endpoints poll agregados")
else:
    print("SKIP: endpoints /apply ya existen")

with open("api_server.py", "w", encoding="utf-8") as f:
    f.write(api)
print("api_server.py guardado.")
print("\n✅ Paso 2 y 3 completados.")
