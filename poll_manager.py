"""
poll_manager.py
───────────────
Sistema de polling seguro desde Google Calendar hacia la base de datos local.

Reglas de oro:
  - SOLO lectura desde Google. Nunca escribe de vuelta.
  - Cambios críticos (horario, título, técnico) → poll_review_queue, nunca auto-aplicados.
  - Cambios seguros (ubicación, descripción) → se aplican directamente.
  - Anti-loop: eventos con source='internal' se ignoran completamente.
  - Requiere pasar run_pre_polling_checklist() antes de iniciar.
"""

import threading
import time
import datetime
import json
import uuid
import traceback
from typing import Optional
from utils import _now_iso, _parse_dt, _normalize, _poll_log
from field_ownership import FieldOwnershipRegistry, FieldOwnership

# ── CONSTANTES ───────────────────────────────────────────────────────────────

POLL_INTERVAL_SECONDS  = 300       # Intervalo entre ciclos (5 minutos)
POLL_WINDOW_DAYS_BACK  = 30        # Ventana hacia atrás para updatedMin baseline
POLL_WINDOW_DAYS_FWD   = 180       # Ventana hacia adelante para timeMax

# Legacy aliases — mantenidos para compatibilidad, pero la autoridad está en FieldOwnershipRegistry
SAFE_FIELDS     = {"ubicacion", "descripcion"}
CRITICAL_FIELDS = {"summary", "inicio", "fin", "tecnico_nombre"}


# ── LOGGING ──────────────────────────────────────────────────────────────────
# Movid a utils.py: _poll_log


# ── CHECKLIST DE VALIDACIONES PREVIAS ────────────────────────────────────────

def run_pre_polling_checklist(db, *args, **kwargs) -> bool:
    """
    Valida que el sistema esté en estado seguro antes de iniciar polling.
    Retorna True solo si TODAS las validaciones pasan.
    Si alguna falla, loggea y retorna False sin iniciar el ciclo.
    
    # RIESGO DE ORQUESTACIÓN: Se eliminó el chequeo interno de si el `sync_worker` 
    # estaba encendido para desacoplar este módulo de `api_server.py`.
    # Ahora es responsabilidad exclusiva de quien llame a `start()` asegurarse de que 
    # la subida de datos esté detenida antes de iniciar el polling.
    """
    checks = []

    # 1. Todos los eventos tienen version >= 1
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM eventos WHERE version IS NULL OR version < 1")
        n = cursor.fetchone()[0]
    checks.append(("VERSION_COVERAGE",      n == 0,     f"{n} eventos sin version"))

    # 2. Columna google_event_id existe
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(eventos)")
        ev_cols = [c[1] for c in cursor.fetchall()]
    checks.append(("GOOGLE_EVENT_ID_COL",   "google_event_id" in ev_cols, "columna ausente"))

    # 3. Columna updated_at existe y está poblada
    has_uat = "updated_at" in ev_cols
    if has_uat:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM eventos WHERE updated_at IS NULL")
            nulls = cursor.fetchone()[0]
    else:
        nulls = -1
    checks.append(("UPDATED_AT_POPULATED",  has_uat and nulls == 0,
                   f"{'col ausente' if not has_uat else f'{nulls} NULLs'}"))

    # 4. Fuente única de verdad: todos internal
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM eventos WHERE source != 'internal'")
        bad = cursor.fetchone()[0]
    checks.append(("SINGLE_SOURCE_OF_TRUTH", bad == 0, f"{bad} eventos con source no-interno"))

    # (Check 5 eliminado: El acoplamiento a `sync_worker` fue removido.
    #  La orquestación de exclusión mutua debe hacerse a un nivel superior.)

    # 6. Tabla poll_calendar_state existe
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='poll_calendar_state'")
        ok = cursor.fetchone()[0] > 0
    checks.append(("POLL_STATE_TABLE",      ok, "tabla poll_calendar_state ausente"))

    # 7. Tabla poll_log existe
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='poll_log'")
        ok = cursor.fetchone()[0] > 0
    checks.append(("POLL_LOG_TABLE",        ok, "tabla poll_log ausente"))

    # 8. Tabla poll_review_queue existe
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='poll_review_queue'")
        ok = cursor.fetchone()[0] > 0
    checks.append(("POLL_REVIEW_TABLE",     ok, "tabla poll_review_queue ausente"))

    # ── Evaluar y loggear ────────────────────────────────────────────────────
    all_passed = True
    for name, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        _poll_log(db, "CHECKLIST", status, {"check": name, "detail": detail if not passed else "OK"})
        if not passed:
            all_passed = False

    if not all_passed:
        failed = [n for n, ok, _ in checks if not ok]
        _poll_log(db, "CHECKLIST", "ABORT",
                  {"reason": "Validaciones fallidas — polling NO iniciado", "failed": failed})
    else:
        # [POLL_STARTUP] Resumen de condiciones iniciales
        from utils import _now_iso
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM eventos")
            total_evs = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM poll_calendar_state")
            total_cals = cursor.fetchone()[0]
            
        _poll_log(db, "POLL_STARTUP", "READY", {
            "timestamp": _now_iso(),
            "events_in_db": total_evs,
            "calendars_tracked": total_cals,
            "checklist": {n: ("PASS" if ok else "FAIL") for n, ok, _ in checks},
            "config": {
                "window_back_days": POLL_WINDOW_DAYS_BACK,
                "window_fwd_days": POLL_WINDOW_DAYS_FWD,
                "interval_s": POLL_INTERVAL_SECONDS
            }
        })

    return all_passed


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _is_internal_change(g_ev: dict) -> bool:
    """True si el evento fue escrito por este sistema (anti-loop)."""
    props = g_ev.get("extendedProperties", {}).get("private", {})
    return props.get("source") == "internal"


def _map_google_to_local(g_ev: dict, calendar_id: str, tec_nombre: str) -> dict:
    """Convierte un evento de Google al esquema local normalizado usando EventAdapter."""
    from utils import EventAdapter
    can = EventAdapter.google_to_canonical(g_ev, calendar_id, tec_nombre)
    
    # Inyectar campos específicos de polling para trazabilidad
    can["poll_source"] = "google_poll"
    can["google_updated"] = g_ev.get("updated")
    
    # El DataManager espera extended_props como string JSON
    if "extended_props" in can and isinstance(can["extended_props"], dict):
        can["extended_props"] = json.dumps(can["extended_props"], ensure_ascii=False)
        
    return can


def _compute_diff(local: dict, g_mapped: dict) -> dict:
    """
    Retorna solo los campos que cambiaron.
    Clasifica cada campo según FieldOwnershipRegistry.
    Categorías: 'safe', 'critical', 'planner_owned', 'google_owned', 'metadata_change'.
    """
    return FieldOwnershipRegistry.classify_diff(local, g_mapped, normalize_fn=_normalize)


def detect_group_membership(db, event_id: str) -> dict:
    """
    [GROUP_DRIFT_DETECTION] Determina si un evento pertenece a un grupo activo.
    Busca por:
      1. ID directo en tabla grupos (event_ids JSON)
      2. google_event_id si differía del id local
      3. grupo_id en extended_props del evento (metadata lineage)

    Retorna:
    {
      "is_grouped": bool,
      "group_id": str | None,
      "member_count": int,
      "member_event_ids": [...]
    }
    """
    # Estrategia 1: buscar directamente en tabla grupos por event_id
    grupo = db.obtener_grupo_de_evento(event_id)

    # Estrategia 2: si no encontró, buscar el evento local y probar con google_event_id
    if not grupo:
        local = db.find_by_google_event_id(event_id) or db.get_evento_dict(event_id)
        if local:
            gid_alt = local.get("google_event_id")
            if gid_alt and gid_alt != event_id:
                grupo = db.obtener_grupo_de_evento(gid_alt)

    # Estrategia 3: leer grupo_id desde extended_props del evento
    if not grupo:
        local = db.find_by_google_event_id(event_id) or db.get_evento_dict(event_id)
        if local:
            try:
                ext = json.loads(local.get("extended_props") or "{}")
                grupo_id_meta = ext.get("private", {}).get("grupo_id")
                if grupo_id_meta:
                    grupo = db.obtener_grupo(grupo_id_meta)
            except Exception:
                pass

    if not grupo:
        return {"is_grouped": False, "group_id": None,
                "member_count": 0, "member_event_ids": []}

    return {
        "is_grouped":       True,
        "group_id":         grupo.get("grupo_id"),
        "member_count":     len(grupo.get("event_ids", [])),
        "member_event_ids": grupo.get("event_ids", [])
    }


# ── CLASE PRINCIPAL ───────────────────────────────────────────────────────────

class PollingManager:
    """
    Orquesta el ciclo de polling desde Google Calendar.
    Debe iniciarse con start() tras pasar el checklist.
    """

    def __init__(self, db, google_service_factory, hydration_service=None):
        """
        db: instancia de DataManager
        google_service_factory: callable sin args que retorna un servicio de Google Calendar API
        hydration_service: instancia de HydrationService (opcional). Si es None, el polling
                           opera en modo pasivo (comportamiento original sin hydration).
        """
        self.db = db
        self.google_service_factory = google_service_factory
        self._hydrator = hydration_service
        self._running = False
        self._thread:  Optional[threading.Thread] = None
        self._lock     = threading.Lock()
        self._dry_run  = False
        self._current_cycle_id = None

    # ── CICLO DE VIDA ─────────────────────────────────────────────────────────

    def start(self, *args, **kwargs) -> bool:
        """Inicia el polling tras validar el checklist. Retorna True si arrancó."""
        if self._running:
            return True
        if not run_pre_polling_checklist(self.db, *args, **kwargs):
            return False
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True, name="PollingManager")
        self._thread.start()
        _poll_log(self.db, "POLL_MANAGER", "STARTED",
                  {"interval_s": POLL_INTERVAL_SECONDS})
        return True

    def stop(self):
        """Detiene el ciclo de polling de forma limpia."""
        self._running = False
        _poll_log(self.db, "POLL_MANAGER", "STOPPED", {})

    def trigger_now(self, dry_run=False):
        """Dispara un ciclo inmediato desde un hilo separado (para testing/admin)."""
        t = threading.Thread(target=self._poll_all_calendars, args=(dry_run,), daemon=True)
        t.start()

    # ── BUCLE PRINCIPAL ───────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            try:
                # Leer dry_run desde ENV (prioridad) o config
                import os
                dry_run_env = os.getenv("POLL_DRY_RUN", "false").lower() == "true"
                
                cfg = self.db.get_app_config()
                dry_run_db = cfg.get("poll_dry_run", False)
                
                dry_run = dry_run_env or dry_run_db
                self._poll_all_calendars(dry_run=dry_run)
            except Exception as e:
                _poll_log(self.db, "POLL_MANAGER", "LOOP_ERROR",
                          {"error": str(e), "trace": traceback.format_exc()[-500:]})
            # Leer intervalo dinámicamente para que cambios desde la UI surtan efecto
            try:
                cfg = self.db.get_app_config()
                interval = int(cfg.get("poll_interval_seconds", POLL_INTERVAL_SECONDS))
                interval = max(60, min(3600, interval))  # clamp entre 1min y 1h
            except Exception:
                interval = POLL_INTERVAL_SECONDS
            time.sleep(interval)

    # ── CICLO POR CALENDARIOS ─────────────────────────────────────────────────

    def _poll_all_calendars(self, dry_run=False):
        start_time = time.time()
        self._current_cycle_id = str(uuid.uuid4())[:8]
        self._dry_run = dry_run
        
        # ── Refrescar OTs, Patrones y Vehículos de Google Sheets ─────────────
        try:
            print("[PollingManager] Refrescando OTs, Patrones y Vehículos desde Google Sheets...")
            import extractor
            _, svc_sheets = extractor._safe_get_google_services()
            
            # 1. OTs (Backlog)
            ots, headers = extractor.actualizar_ots_desde_sheets(svc_sheets)
            if headers:
                ots_list = [headers] + [[item.get(h, "") for h in headers] for item in ots]
                self.db.guardar_bd_ots(ots_list)
                print(f"[PollingManager] OK - OTs actualizadas ({len(ots)} registradas).")
                
            # 2. Patrones
            patrones = extractor.actualizar_patrones_desde_sheets(svc_sheets)
            self.db.guardar_patrones(patrones)
            
            # 3. Vehículos
            vehiculos = extractor.actualizar_vehiculos_desde_sheets(svc_sheets)
            self.db.guardar_vehiculos(vehiculos)
            
            self.db.update_last_sync()
        except Exception as sheet_err:
            print(f"[PollingManager] Advertencia: No se pudo actualizar Google Sheets en este ciclo: {sheet_err}")
        
        tecnicos = self.db.obtener_tecnicos()
        _poll_log(self.db, "POLLING", "cycle_started", 
                  {"calendars": len(tecnicos), "cycle_id": self._current_cycle_id, "dry_run": dry_run})

        totals = {"processed": 0, "changes": 0, "conflicts": 0, "ignored": 0, "errors": 0}

        for tec in tecnicos:
            cal_id = tec["correo"]
            try:
                stats = self._poll_calendar(cal_id, tec["nombre"])
                for k in ("processed", "changes", "conflicts", "ignored"):
                    totals[k] += stats.get(k, 0)
                self.db.update_last_poll_time(cal_id,
                    datetime.datetime.utcnow().isoformat() + "Z")
            except Exception as e:
                totals["errors"] += 1
                self.db.register_calendar_poll_error(cal_id, str(e)[:500])
                _poll_log(self.db, "POLLING", "calendar_error",
                          {"error": str(e)[:300]}, calendar_id=cal_id)

        duration = round(time.time() - start_time, 2)
        
        # [POLL_HEARTBEAT] Resumen métricas del ciclo
        _poll_log(self.db, "POLL_HEARTBEAT", "CYCLE_COMPLETED", {
            "cycle_id": self._current_cycle_id,
            "duration_ms": int(duration * 1000),
            "dry_run": self._dry_run,
            "metrics": {
                "calendars_processed": len(tecnicos),
                "events_scanned": totals["processed"],
                "events_changed": totals["changes"],
                "events_ignored": totals["ignored"],
                "conflicts_found": totals["conflicts"],
                "errors_encountered": totals["errors"]
            }
        })

    def _poll_calendar(self, calendar_id: str, tec_nombre: str) -> dict:
        """Descarga eventos modificados de un calendario y los procesa."""
        last_sync = self.db.get_last_poll_time(calendar_id)
        svc = self.google_service_factory()

        now      = datetime.datetime.utcnow()
        time_min = (now - datetime.timedelta(days=POLL_WINDOW_DAYS_BACK)).isoformat() + "Z"
        time_max = (now + datetime.timedelta(days=POLL_WINDOW_DAYS_FWD)).isoformat()  + "Z"

        params = dict(
            calendarId   = calendar_id,
            timeMin      = time_min,
            timeMax      = time_max,
            maxResults   = 500,
            singleEvents = True,
            orderBy      = "startTime",
            showDeleted  = True,
        )
        if last_sync:
            params["updatedMin"] = last_sync

        result       = svc.events().list(**params).execute()
        google_events = result.get("items", [])

        _poll_log(self.db, "TRACE_EVENT_FLOW", "POLL_FETCHED",
                  {"count": len(google_events), "updatedMin": last_sync or "FULL"},
                  calendar_id=calendar_id)

        stats = {"processed": 0, "changes": 0, "conflicts": 0, "ignored": 0}
        for g_ev in google_events:
            outcome = self._process_incoming_event(g_ev, calendar_id, tec_nombre)
            stats["processed"] += 1
            stats[outcome]      = stats.get(outcome, 0) + 1

        return stats

    # ── PROCESAMIENTO DE EVENTO INDIVIDUAL ───────────────────────────────────

    def _process_incoming_event(self, g_ev: dict, calendar_id: str, tec_nombre: str) -> str:
        """
        Procesa un único evento de Google.
        Retorna: 'changes' | 'conflicts' | 'ignored'
        """
        gid    = g_ev.get("id", "UNKNOWN")
        correlation_id = str(uuid.uuid4())[:8]
        status = g_ev.get("status", "confirmed")
        
        # 1. Trazabilidad inicial
        trace = {
            "cycle_id": self._current_cycle_id,
            "correlation_id": correlation_id,
            "google_event_id": gid,
            "calendar_id": calendar_id,
            "dry_run": self._dry_run
        }

        # 0. Ignorar eventos de sistema o metadatos
        ev_type = g_ev.get('eventType', 'default')
        if ev_type in ['workingLocation', 'focusTime', 'outOfOffice']:
            trace["decision"] = "ignored"
            trace["reason"] = f"eventType {ev_type}"
            _poll_log(self.db, "POLL_TRACE", "EVENT_IGNORED", trace)
            return "ignored"

        # 0.5 Buscar evento local tempranamente para protecciones de race condition
        local = self.db.find_by_google_event_id(gid)
        if local:
            try:
                local_ext = json.loads(local.get("extended_props") or "{}")
                if local_ext.get("private", {}).get("reassignment_in_progress") == "true":
                    trace["decision"] = "ignored"
                    trace["reason"] = "reassignment_in_progress"
                    _poll_log(self.db, "POLL_TRACE", "EVENT_IGNORED_RACE_PROTECTION", trace)
                    print(f"[REASSIGN_TRACE:POLLING] Ignorando evento local_id={local.get('id')}, google_event_id={gid} por reassignment_in_progress")
                    return "ignored"
            except Exception:
                pass

        # 1. Evento cancelado/eliminado en Google
        if status == "cancelled":
            trace["decision"] = "delete_detected"
            if not self._dry_run:
                self._handle_cancelled(gid, calendar_id, g_ev)
                trace["persistence"] = "review_queued"
            else:
                trace["persistence"] = "skipped_dry_run"
            _poll_log(self.db, "POLL_TRACE", "DELETE_DETECTED", trace)
            return "ignored"

        # 2. Anti-loop: evento escrito por nosotros → ignorar
        if _is_internal_change(g_ev):
            trace["decision"] = "ANTI_LOOP_SKIP"
            trace["reason"] = "source='internal' metadata detected"
            _poll_log(self.db, "POLL_INBOUND_TRACE", "ANTI_LOOP", trace)
            return "ignored"

        # 3. Estado del evento local para trazas
        trace["local_status"] = "exists" if local else "new"
        if local:
            trace["local_state"] = {
                "summary": local.get("summary"),
                "tecnico": local.get("tecnico_nombre"),
                "start": local.get("inicio"),
                "end": local.get("fin"),
                "updated_at": local.get("updated_at"),
                "extended_props": local.get("extended_props")
            }

        trace["google_state"] = {
            "summary": g_ev.get("summary"),
            "start": g_ev.get("start"),
            "end": g_ev.get("end"),
            "updated": g_ev.get("updated"),
            "extendedProperties": g_ev.get("extendedProperties")
        }

        # 4. Evento nuevo en Google → encolar para revisión humana (Arbitraje de creación)
        if local is None:
            trace["decision"] = "queued_for_review"
            if not self._dry_run:
                try:
                    # Enriquecer/hidratar el evento nuevo antes de guardarlo en el remote_snapshot
                    if self._hydrator:
                        g_ev = self._hydrator.hydrate_event(g_ev)

                    g_mapped = _map_google_to_local(g_ev, calendar_id, tec_nombre)
                    
                    # Diff visual de creación
                    create_diff = {
                        "summary": {"old": "—", "new": g_mapped.get("summary", "Sin título"), "category": "critical"},
                        "inicio": {"old": "—", "new": g_mapped.get("inicio"), "category": "critical"},
                        "fin": {"old": "—", "new": g_mapped.get("fin"), "category": "critical"},
                        "tecnico_nombre": {"old": "—", "new": g_mapped.get("tecnico_nombre", tec_nombre), "category": "critical"}
                    }

                    review_id = self.db.enqueue_review(
                        event_id=gid,
                        calendar_id=calendar_id,
                        diff=create_diff,
                        conflict_type="REMOTE_CREATE",
                        google_event_id=gid,
                        local_snapshot={},
                        remote_snapshot=g_ev,
                        recommended_action="ACCEPT_REMOTE",
                        g_updated=g_ev.get("updated")
                    )
                    
                    if review_id:
                        trace["persistence"] = "review_queued"
                        trace["review_id"] = review_id
                    else:
                        trace["persistence"] = "duplicate_ignored"
                except Exception as e:
                    trace["persistence"] = "failed"
                    trace["error"] = str(e)
            else:
                trace["persistence"] = "skipped_dry_run"
            _poll_log(self.db, "POLL_INBOUND_TRACE", "REVIEW_REQUIRED", trace)
            return "conflicts"

        # 5. ¿Google tiene algo más nuevo?
        g_updated     = _parse_dt(g_ev.get("updated"))
        local_updated = _parse_dt(local.get("updated_at"))
        if local_updated and g_updated and g_updated <= local_updated:
            trace["reason"] = f"g_updated({g_updated}) <= local_updated({local_updated})"
            _poll_log(self.db, "POLL_INBOUND_TRACE", "NO_OP_STALE", trace)
            return "ignored"

        # [NUEVO] Re-hidratar eventos existentes
        if self._hydrator and local is not None:
            local_ext = json.loads(local.get("extended_props") or "{}")
            if self._hydrator.needs_hydration({"extendedProperties": local_ext}):
                enriched_ev = self._hydrator.hydrate_event(g_ev)
                enriched_ext = enriched_ev.get("extendedProperties", {})
                if enriched_ext.get("hydrated"):
                    trace["decision"] = "hydration_applied"
                    if not self._dry_run:
                        try:
                            self.db.actualizar_extended_props_incremental(local["id"], enriched_ext)
                            trace["persistence"] = "metadata_merged"
                        except Exception as e:
                            trace["persistence"] = "failed"
                            trace["error"] = str(e)
                    else:
                        trace["persistence"] = "skipped_dry_run"
                    _poll_log(self.db, "POLL_INBOUND_TRACE", "HYDRATION_APPLIED", trace)

        # 6. Calcular diff (con clasificación de ownership)
        g_mapped = _map_google_to_local(g_ev, calendar_id, tec_nombre)
        diff     = _compute_diff(local, g_mapped)
        trace["diff_result"] = diff

        if not diff:
            trace["decision"] = "NO_OP_DIFF_EMPTY"
            _poll_log(self.db, "POLL_INBOUND_TRACE", "NO_OP", trace)
            return "ignored"

        # 6b. Separar por ownership
        safe_diff     = {k: v for k, v in diff.items() if v.get("category") == "safe"}
        critical_diff = {k: v for k, v in diff.items() if v.get("category") == "critical"}
        planner_diff  = {k: v for k, v in diff.items() if v.get("category") == "planner_owned"}
        metadata_diff = {k: v for k, v in diff.items() if v.get("category") == "metadata_change"}

        # 6c. Log [FIELD_OWNERSHIP] para campos filtrados por ownership
        if planner_diff:
            ownership_logs = []
            for field, d in planner_diff.items():
                ownership_logs.append(
                    FieldOwnershipRegistry.build_ownership_log(
                        field=field,
                        ownership=FieldOwnership.PLANNER_OWNED,
                        incoming_source="google_poll",
                        action="blocked",
                        old_val=d.get("old"),
                        new_val=d.get("new"),
                    )
                )
            _poll_log(self.db, "FIELD_OWNERSHIP", "PLANNER_OWNED_BLOCKED", {
                "cycle_id": self._current_cycle_id,
                "google_event_id": gid,
                "fields_blocked": len(planner_diff),
                "details": ownership_logs,
            }, calendar_id=calendar_id, event_id=gid)

        # 6d. Log para metadata diffs con campos internos filtrados
        if metadata_diff:
            for field, d in metadata_diff.items():
                filtered = d.get("planner_owned_filtered", [])
                if filtered:
                    _poll_log(self.db, "FIELD_OWNERSHIP", "METADATA_FILTERED", {
                        "cycle_id": self._current_cycle_id,
                        "google_event_id": gid,
                        "planner_owned_filtered": filtered,
                    }, calendar_id=calendar_id, event_id=gid)

        # Si SOLO quedan diffs planner_owned → ignorar silenciosamente
        actionable_diff = {**safe_diff, **critical_diff, **metadata_diff}
        if not actionable_diff:
            trace["decision"] = "PLANNER_OWNED_ONLY_SKIP"
            trace["planner_fields_ignored"] = list(planner_diff.keys())
            _poll_log(self.db, "POLL_INBOUND_TRACE", "OWNERSHIP_FILTERED", trace)
            return "ignored"

        # 7a. Aplicar cambios seguros (SHARED_SAFE)
        if safe_diff:
            trace["decision"] = "auto_applied"
            if not self._dry_run:
                try:
                    self.db.apply_poll_safe_changes(local["id"], safe_diff)
                    trace["persistence"] = "sqlite_updated_safe"
                except Exception as e:
                    trace["persistence"] = "failed"
                    trace["error"] = str(e)
            else:
                trace["persistence"] = "skipped_dry_run"
            _poll_log(self.db, "POLL_INBOUND_TRACE", "AUTO_APPLY_SAFE", trace)

        # 7b. Cambios críticos (SHARED_CRITICAL) → verificar si pertenece a grupo
        if critical_diff:
            # [GROUP_DRIFT_DETECTION] Verificar membership antes de encolar review individual
            membership = detect_group_membership(self.db, gid)

            if membership["is_grouped"]:
                # → Elevar a GROUP_DRIFT en lugar de review individual
                group_id     = membership["group_id"]
                member_ids   = membership["member_event_ids"]
                member_count = membership["member_count"]

                # Snapshot local de todos los miembros del grupo
                local_group_snapshot = []
                for mid in member_ids:
                    m_ev = self.db.resolve_event(mid)
                    if m_ev:
                        local_group_snapshot.append({
                            "event_id":    m_ev.get("id"),
                            "tecnico":     m_ev.get("tecnico_nombre"),
                            "calendar_id": m_ev.get("calendar_id"),
                            "inicio":      m_ev.get("inicio"),
                            "fin":         m_ev.get("fin"),
                            "summary":     m_ev.get("summary"),
                            "sync_status": m_ev.get("sync_status")
                        })

                # Determinar tipo de drift
                drift_type = "GROUP_METADATA_DRIFT"
                broken_invariants = []
                if any(k in critical_diff for k in ("inicio", "fin")):
                    drift_type = "GROUP_TEMPORAL_DRIFT"
                    broken_invariants.append("TEMPORAL_INTEGRITY")
                if "tecnico_nombre" in critical_diff or "calendar_id" in critical_diff:
                    drift_type = "GROUP_OWNERSHIP_DRIFT"
                    broken_invariants.append("OWNERSHIP_INTEGRITY")
                if "summary" in critical_diff:
                    broken_invariants.append("TITLE_CONSISTENCY")

                group_drift_payload = {
                    "group_id":              group_id,
                    "trigger_event_id":      gid,
                    "trigger_local_id":      local["id"],
                    "affected_members":      member_ids,
                    "member_count":          member_count,
                    "local_group_snapshot":  local_group_snapshot,
                    "remote_member_snapshot": trace.get("google_state", {}),
                    "drift_type":            drift_type,
                    "broken_invariants":     broken_invariants,
                    "critical_diff":         critical_diff
                }

                # [GROUP_DRIFT_DETECTED]
                print(f"[GROUP_DRIFT_DETECTED] group={group_id} trigger={gid} "
                      f"type={drift_type} invariants={broken_invariants}")
                _poll_log(self.db, "GROUP_DRIFT", "GROUP_DRIFT_DETECTED", {
                    **trace,
                    **group_drift_payload
                }, calendar_id=calendar_id, event_id=gid)

                trace["decision"]  = "group_drift_escalated"
                trace["drift_type"] = drift_type

                if not self._dry_run:
                    # Encolar como GROUP_DRIFT con payload enriquecido
                    local_snap   = trace.get("local_state", {})
                    remote_snap  = trace.get("google_state", {})
                    review_id = self.db.enqueue_review(
                        local["id"], calendar_id, critical_diff,
                        conflict_type=drift_type,
                        google_event_id=gid,
                        local_snapshot={**local_snap, "group_payload": group_drift_payload},
                        remote_snapshot=remote_snap,
                        g_updated=g_ev.get("updated")
                    )
                    trace["persistence"] = "group_drift_review_queued"
                    trace["review_id"]   = review_id

                    # [GROUP_DRIFT_ESCALATED]
                    print(f"[GROUP_DRIFT_ESCALATED] review_id={review_id} "
                          f"group={group_id} drift={drift_type}")
                    _poll_log(self.db, "GROUP_DRIFT", "GROUP_DRIFT_ESCALATED", {
                        "review_id": review_id,
                        "group_id":  group_id,
                        "drift_type": drift_type,
                        "members_at_risk": member_ids
                    }, calendar_id=calendar_id, event_id=gid)
                else:
                    trace["persistence"] = "skipped_dry_run"

                _poll_log(self.db, "GROUP_DRIFT", "GROUP_REVIEW_CREATED", trace,
                          calendar_id=calendar_id, event_id=gid)

            else:
                # Evento individual (sin grupo) → flujo normal
                trace["decision"] = "queued_for_review"
                if not self._dry_run:
                    local_snap  = trace.get("local_state", {})
                    remote_snap = trace.get("google_state", {})
                    self.db.enqueue_review(
                        local["id"], calendar_id, critical_diff,
                        conflict_type="FIELD_CHANGE",
                        google_event_id=gid,
                        local_snapshot=local_snap,
                        remote_snapshot=remote_snap,
                        g_updated=g_ev.get("updated")
                    )
                    trace["persistence"] = "review_queued"
                else:
                    trace["persistence"] = "skipped_dry_run"
                _poll_log(self.db, "POLL_INBOUND_TRACE", "REVIEW_REQUIRED", trace)

            return "conflicts"

        return "changes" if safe_diff else "ignored"

    # ── ACCIONES AUXILIARES ───────────────────────────────────────────────────

    def _create_from_google(self, g_ev: dict, calendar_id: str, tec_nombre: str):
        """
        Inserta en la base de datos local un evento nuevo encontrado en Google.
        Solo se invoca cuando el evento no existe localmente.
        Si hay un HydrationService configurado, enriquece el evento antes de persistir.
        """
        # [NUEVO] Hidratar el evento crudo antes de mapearlo
        if self._hydrator:
            g_ev = self._hydrator.hydrate_event(g_ev)
            ext = g_ev.get("extendedProperties", {})
            if ext.get("hydrated"):
                _poll_log(self.db, "TRACE_EVENT_FLOW", "POLL_HYDRATION_APPLIED",
                          {"ot": ext.get("app_ot"),
                           "vehiculo": ext.get("app_vehiculo"),
                           "patrones": ext.get("app_patrones")},
                          event_id=g_ev.get("id"))
            else:
                _poll_log(self.db, "POLLING", "hydration_failed",
                          {"reason": "OT no encontrada o titulo sin OT",
                           "summary": g_ev.get("summary", "")[:60]},
                          event_id=g_ev.get("id"))

        mapped = _map_google_to_local(g_ev, calendar_id, tec_nombre)
        with self.db._lock:
            with self.db._get_connection() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO eventos
                        (id, calendar_id, tecnico_nombre, summary, inicio, fin,
                         ubicacion, descripcion, extended_props, version,
                         sync_status, updated_at, source, google_event_id, poll_source, pending_sync)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
                """, (
                    mapped["id"],           mapped["calendar_id"],
                    mapped["tecnico_nombre"], mapped["summary"],
                    mapped["inicio"],        mapped["fin"],
                    mapped["ubicacion"],     mapped["descripcion"],
                    mapped["extended_props"], 1,
                    "SUCCESS",               mapped["updated_at"],
                    "internal",             mapped["google_event_id"],
                    "google_poll"
                ))
                conn.commit()

    def _handle_cancelled(self, event_id: str, calendar_id: str, g_ev: dict = None):
        """
        [ARBITRATION] Encola un evento cancelado en Google para revisión humana.
        NO aplica borrado automático. El operador debe aceptar o rechazar.
        - Aceptar → evento marcado como CANCELLED_IN_GOOGLE
        - Rechazar → evento restaurado en Google (CREATE outbound)
        """
        local = self.db.find_by_google_event_id(event_id)
        if local:
            # Capturar snapshot local antes de encolar
            local_snapshot = {
                "summary": local.get("summary"),
                "tecnico": local.get("tecnico_nombre"),
                "inicio": local.get("inicio"),
                "fin": local.get("fin"),
                "extended_props": local.get("extended_props"),
            }
            # [WATERMARK_ANTI_REOPEN] Para REMOTE_DELETE, el g_ev viene del ciclo de polling
            # Los eventos cancelados pueden tener un campo 'updated' que usamos como watermark
            g_updated = g_ev.get("updated") if g_ev else None
            review_id = self.db.enqueue_review(
                event_id=local["id"],
                calendar_id=calendar_id,
                diff={"_action": {"old": "EXISTS", "new": "DELETE", "category": "critical"}},
                conflict_type="REMOTE_DELETE",
                google_event_id=event_id,
                local_snapshot=local_snapshot,
                remote_snapshot={"status": "cancelled"},
                recommended_action="REVIEW_DELETE",
                g_updated=g_updated,
            )
            _poll_log(self.db, "POLL_INBOUND_TRACE", "DELETE_DETECTED",
                      {
                          "cycle_id": self._current_cycle_id,
                          "google_event_id": event_id,
                          "local_id": local["id"],
                          "review_id": review_id,
                          "decision": "delete_detected",
                          "persistence": "review_queued",
                          "note": "Cancelado en Google — pendiente de arbitraje humano"
                      },
                      calendar_id=calendar_id, event_id=event_id)
        else:
            _poll_log(self.db, "POLL_INBOUND_TRACE", "DELETE_IGNORED",
                      {"note": "Evento cancelado no existe localmente"},
                      calendar_id=calendar_id, event_id=event_id)
