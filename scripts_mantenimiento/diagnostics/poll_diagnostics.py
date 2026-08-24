"""
poll_diagnostics.py
───────────────────
Módulo de diagnóstico operacional y reporte analítico para el PollingManager.
Genera reportes sobre el comportamiento del polling, decisiones tomadas y detección de drift.
"""

import datetime
import json
import traceback
import sqlite3

class PollingDiagnosticReporter:
    def __init__(self, db, google_service_factory=None):
        self.db = db
        self.google_service_factory = google_service_factory

    def get_cycle_report(self, cycle_id: str) -> dict:
        """Genera un reporte detallado para un ciclo específico."""
        logs = self.db.get_poll_logs(limit=1000, event_type="POLL_TRACE")
        cycle_logs = [l for l in logs if l.get("detail", {}).get("cycle_id") == cycle_id]
        
        # También buscar el inicio y fin del ciclo en logs de POLLING
        all_polling_logs = self.db.get_poll_logs(limit=500, event_type="POLLING")
        start_log = next((l for l in all_polling_logs if l["event_type"] == "POLLING:cycle_started" and l["detail"].get("cycle_id") == cycle_id), None)
        end_log = next((l for l in all_polling_logs if l["event_type"] == "POLLING:cycle_completed" and l["detail"].get("cycle_id") == cycle_id), None)

        if not cycle_logs and not start_log:
            return {"error": f"Cycle {cycle_id} not found"}

        # 1. Summary
        summary = {
            "cycle_id": cycle_id,
            "timestamp": start_log["timestamp"] if start_log else None,
            "duration_s": end_log["detail"].get("duration_s") if end_log else None,
            "processed": 0,
            "modified": 0,
            "ignored": 0,
            "anti_loop": 0,
            "hydration": 0,
            "deletes": 0,
            "conflicts": 0,
            "errors": 0,
            "decisions": {}
        }

        if end_log:
            summary.update({
                "processed": end_log["detail"].get("processed", 0),
                "modified": end_log["detail"].get("modified", 0),
                "conflicts": end_log["detail"].get("conflicts", 0),
                "ignored": end_log["detail"].get("ignored", 0),
                "errors": end_log["detail"].get("errors", 0),
            })

        # 2. Event Decisions
        events = []
        DECISION_MAP = {
            "no_op": "NO_DIFF",
            "no_op_diff_empty": "NO_DIFF",
            "auto_applied": "SAFE_APPLY",
            "queued_for_review": "CRITICAL_DIFF",
            "anti_loop": "ANTI_LOOP_SKIP",
            "no_change": "STALE_SKIP",
            "delete_detected": "DELETE_DETECTED",
            "hydration_applied": "HYDRATION_APPLIED",
            "overwrite_prevented": "OVERWRITE_PREVENTED",
            "planner_owned_only": "OWNERSHIP_FILTERED",
            "create_new": "NEW_EVENT",
            "failed": "ERROR"
        }

        for l in cycle_logs:
            detail = l["detail"]
            raw_decision = detail.get("decision", "UNKNOWN")
            norm_decision = DECISION_MAP.get(raw_decision, raw_decision)
            
            # Clasificación de decisiones
            summary["decisions"][norm_decision] = summary["decisions"].get(norm_decision, 0) + 1
            if norm_decision == "ANTI_LOOP_SKIP": summary["anti_loop"] += 1
            if norm_decision == "HYDRATION_APPLIED": summary["hydration"] += 1
            if norm_decision == "DELETE_DETECTED": summary["deletes"] += 1

            events.append({
                "google_event_id": detail.get("google_event_id"),
                "tecnico": detail.get("calendar_id"),
                "local_updated_at": detail.get("local_state", {}).get("updated_at"),
                "google_updated_at": detail.get("google_state", {}).get("updated"),
                "diff": detail.get("diff_result"),
                "decision": norm_decision,
                "persistence": detail.get("persistence")
            })

        return {
            "summary": summary,
            "events": events
        }

    def get_recent_cycles(self, limit: int = 10) -> list:
        """Retorna una lista de los últimos ciclos con su resumen."""
        logs = self.db.get_poll_logs(limit=500, event_type="POLLING:cycle_started")
        cycles = []
        for l in logs:
            cid = l["detail"].get("cycle_id")
            if cid:
                report = self.get_cycle_report(cid)
                if "error" not in report:
                    cycles.append(report["summary"])
            if len(cycles) >= limit:
                break
        return cycles

    def get_event_history(self, google_event_id: str) -> list:
        """Retorna el historial completo de reconciliación de un evento."""
        # Necesitamos buscar en todos los logs de polling donde aparezca este event_id
        # El método db.get_poll_logs no filtra por event_id, así que lo haremos en memoria o añadiremos el método
        all_logs = self.db.get_poll_logs(limit=2000) # Un poco pesado pero para debug está ok
        history = []
        for l in all_logs:
            if l.get("event_id") == google_event_id or l.get("detail", {}).get("google_event_id") == google_event_id:
                history.append(l)
        
        # Ordenar por tiempo descendente
        history.sort(key=lambda x: x["timestamp"], reverse=True)
        return history

    def perform_drift_detection(self, calendar_id: str) -> dict:
        """
        Analiza discrepancias entre Google y SQLite para un calendario dado.
        ESTO ES UNA OPERACIÓN ACTIVA (fetch a Google).
        """
        if not self.google_service_factory:
            return {"error": "Google service factory not provided"}

        try:
            svc = self.google_service_factory()
            now = datetime.datetime.utcnow()
            time_min = (now - datetime.timedelta(days=30)).isoformat() + "Z"
            time_max = (now + datetime.timedelta(days=90)).isoformat() + "Z"

            result = svc.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                showDeleted=False
            ).execute()
            google_events = result.get("items", [])
            
            # Usar una query directa para evitar problemas con mapeos de dicts antiguos
            with self.db._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM eventos WHERE calendar_id = ?", (calendar_id,))
                local_events = cursor.fetchall()
            
            local_map = {e["google_event_id"]: e for e in local_events if e["google_event_id"]}

            drift = {
                "calendar_id": calendar_id,
                "timestamp": now.isoformat() + "Z",
                "only_in_google": [],
                "only_in_sqlite": [],
                "metadata_drift": [],
                "timestamp_drift": []
            }

            google_ids = set()
            for g_ev in google_events:
                gid = g_ev["id"]
                google_ids.add(gid)
                
                if gid not in local_map:
                    drift["only_in_google"].append({
                        "id": gid,
                        "summary": g_ev.get("summary"),
                        "start": g_ev.get("start")
                    })
                else:
                    local = local_map[gid]
                    # Check metadata completeness
                    local_ext = json.loads(local["extended_props"] or "{}")
                    if not local_ext.get("private"):
                        drift["metadata_drift"].append({
                            "id": gid,
                            "reason": "Missing private extendedProperties in SQLite"
                        })
                    
                    # Check timestamp consistency
                    g_updated = g_ev.get("updated")
                    l_updated = local["updated_at"]
                    if g_updated and l_updated and g_updated != l_updated:
                        drift["timestamp_drift"].append({
                            "id": gid,
                            "google_updated": g_updated,
                            "sqlite_updated": l_updated
                        })

            # Check for events only in SQLite (within the same time window)
            # Nota: Esto es aproximado porque la ventana de Google puede variar
            for lid, l_ev in local_map.items():
                if lid not in google_ids:
                    # Solo reportar si cae dentro de la ventana de tiempo analizada
                    l_start = l_ev["inicio"]
                    if l_start and l_start >= time_min and l_start <= time_max:
                        drift["only_in_sqlite"].append({
                            "id": lid,
                            "summary": l_ev["summary"],
                            "start": l_start
                        })

            return drift

        except Exception as e:
            return {"error": str(e), "trace": traceback.format_exc()}
