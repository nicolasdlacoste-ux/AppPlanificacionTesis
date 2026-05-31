import json
import datetime
from typing import Dict, List, Any, Optional


class SyncObservatoryService:
    """
    [SYNC_OBSERVATORY]
    Servicio de observabilidad operacional para el pipeline de sincronización.
    Centraliza métricas de salud, trazabilidad de decisiones y detección de drift.
    """

    def __init__(self, db):
        self.db = db

    def get_dashboard_snapshot(self) -> Dict[str, Any]:
        """Retorna un snapshot de métricas de salud del sistema."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT status, COUNT(*) FROM sync_queue GROUP BY status")
            queue_stats = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("SELECT sync_status, COUNT(*) FROM eventos GROUP BY sync_status")
            event_sync_stats = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("SELECT status, COUNT(*) FROM poll_review_queue GROUP BY status")
            review_stats = {row[0]: row[1] for row in cursor.fetchall()}

            poll_status = self.db.get_poll_status()

            cursor.execute("SELECT COUNT(*) FROM eventos WHERE extended_props LIKE '%CANCELLED_IN_GOOGLE%'")
            cancelled_in_google = cursor.fetchone()[0]

            return {
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "sync_queue": {
                    "pending": queue_stats.get("PENDING", 0),
                    "failed": queue_stats.get("FAILED", 0),
                    "done": queue_stats.get("DONE", 0)
                },
                "event_health": {
                    "success": event_sync_stats.get("SUCCESS", 0),
                    "pending": event_sync_stats.get("PENDING", 0),
                    "failed": event_sync_stats.get("FAILED", 0),
                    "cancelled_in_google": cancelled_in_google
                },
                "conflict_management": {
                    "pending_reviews": review_stats.get("PENDING", 0),
                    "applied": review_stats.get("APPLIED", 0),
                    "dismissed": review_stats.get("DISMISSED", 0)
                },
                "polling_health": poll_status
            }

    def get_event_timeline(self, event_id: str) -> List[Dict[str, Any]]:
        """Construye un timeline cronológico de todas las acciones sobre un evento."""
        timeline = []

        poll_logs = self.db.get_poll_logs(limit=200, event_type=None)
        for log in poll_logs:
            if log["event_id"] == event_id:
                timeline.append({
                    "timestamp": log["timestamp"],
                    "engine": "POLLING",
                    "action": log["event_type"],
                    "detail": log["detail"]
                })

        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, direction, operation, result, detail
                FROM sync_log WHERE event_id = ?
                ORDER BY timestamp ASC
            """, (event_id,))
            for r in cursor.fetchall():
                timeline.append({
                    "timestamp": r[0],
                    "engine": "SYNC_WORKER",
                    "action": f"{r[1]}:{r[2]}",
                    "result": r[3],
                    "detail": r[4]
                })

        timeline.sort(key=lambda x: x["timestamp"])
        return timeline

    # ── Drift ─────────────────────────────────────────────────────────────────

    def get_drift_report(self) -> Dict[str, Any]:
        """[LEGACY] Alias a get_full_drift_report para retrocompatibilidad."""
        return self.get_full_drift_report()

    def get_full_drift_report(self) -> Dict[str, Any]:
        """
        [DRIFT_DETECTION]
        Reporte completo de drift entre el estado local (SQLite) y Google Calendar.

        Indicadores:
          - events_without_google_id : Eventos locales nunca sincronizados con Google
          - duplicate_events         : Mismo google_event_id en más de una fila
          - pending_reviews          : Reviews esperando arbitraje humano
          - reopened_reviews         : Reviews en PENDING que ya tuvieron resolved_at (fantasmas)
          - cancelled_visible        : Eventos CANCELLED_IN_GOOGLE aún visibles en DB
          - sync_failures            : Ítems FAILED en sync_queue outbound
          - polling_lag              : Calendarios sin poll reciente (> 12 min)
          - orphan_events            : grupo_id en metadata pero grupo no existe en DB
          - lookup_misses_24h        : LOOKUP_MISS en las últimas 24h

        Emite [DRIFT_DETECTED] si hay indicadores críticos activos.
        """
        now = datetime.datetime.utcnow()
        now_iso = now.isoformat() + "Z"
        report: Dict[str, Any] = {
            "timestamp": now_iso,
            "summary": {},
            "indicators": {}
        }
        total_issues = 0

        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # ── 1. Sin google_event_id ────────────────────────────────────────
            cursor.execute("""
                SELECT id, summary, tecnico_nombre, sync_status, updated_at
                FROM eventos
                WHERE (google_event_id IS NULL OR google_event_id LIKE 'local_%')
                  AND sync_status != 'CANCELLED_IN_GOOGLE'
            """)
            without_gid = [
                {"event_id": r[0], "summary": r[1], "tecnico": r[2],
                 "sync_status": r[3], "updated_at": r[4]}
                for r in cursor.fetchall()
            ]
            report["indicators"]["events_without_google_id"] = {
                "count": len(without_gid),
                "items": without_gid[:10]
            }
            total_issues += len(without_gid)

            # ── 2. Duplicados ─────────────────────────────────────────────────
            cursor.execute("""
                SELECT google_event_id, COUNT(*) as cnt, GROUP_CONCAT(id) as local_ids
                FROM eventos
                WHERE google_event_id IS NOT NULL AND google_event_id NOT LIKE 'local_%'
                GROUP BY google_event_id
                HAVING cnt > 1
            """)
            duplicates = [
                {"google_event_id": r[0], "count": r[1],
                 "local_ids": r[2].split(",") if r[2] else []}
                for r in cursor.fetchall()
            ]
            report["indicators"]["duplicate_events"] = {
                "count": len(duplicates),
                "items": duplicates
            }
            total_issues += len(duplicates)

            # ── 3. Reviews pendientes ─────────────────────────────────────────
            cursor.execute("""
                SELECT prq.review_id, prq.event_id, prq.calendar_id,
                       prq.conflict_type, prq.detected_at, ev.summary
                FROM poll_review_queue prq
                LEFT JOIN eventos ev ON ev.id = prq.event_id
                WHERE prq.status = 'PENDING'
                ORDER BY prq.detected_at ASC
            """)
            pending_reviews = [
                {"review_id": r[0], "event_id": r[1], "calendar_id": r[2],
                 "conflict_type": r[3], "detected_at": r[4], "summary": r[5]}
                for r in cursor.fetchall()
            ]
            report["indicators"]["pending_reviews"] = {
                "count": len(pending_reviews),
                "items": pending_reviews[:10]
            }

            # ── 4. Reviews reabiertos (fantasmas) ─────────────────────────────
            cursor.execute("""
                SELECT review_id, event_id, calendar_id, conflict_type,
                       detected_at, resolved_at
                FROM poll_review_queue
                WHERE status = 'PENDING' AND resolved_at IS NOT NULL
                ORDER BY detected_at ASC
            """)
            reopened = [
                {"review_id": r[0], "event_id": r[1], "calendar_id": r[2],
                 "conflict_type": r[3], "detected_at": r[4], "prev_resolved_at": r[5]}
                for r in cursor.fetchall()
            ]
            report["indicators"]["reopened_reviews"] = {
                "count": len(reopened),
                "items": reopened
            }
            total_issues += len(reopened)

            # ── 5. CANCELLED visibles ─────────────────────────────────────────
            cursor.execute("""
                SELECT id, summary, tecnico_nombre, updated_at
                FROM eventos
                WHERE extended_props LIKE '%CANCELLED_IN_GOOGLE%'
                   OR sync_status = 'CANCELLED_IN_GOOGLE'
            """)
            cancelled_visible = [
                {"event_id": r[0], "summary": r[1], "tecnico": r[2], "updated_at": r[3]}
                for r in cursor.fetchall()
            ]
            report["indicators"]["cancelled_visible"] = {
                "count": len(cancelled_visible),
                "items": cancelled_visible[:10]
            }

            # ── 6. Fallas sync outbound ───────────────────────────────────────
            cursor.execute("""
                SELECT queue_id, event_id, calendar_id, operation, created_at, error_msg
                FROM sync_queue
                WHERE status = 'FAILED'
                ORDER BY created_at DESC
            """)
            sync_failures = [
                {"queue_id": r[0], "event_id": r[1], "calendar_id": r[2],
                 "operation": r[3], "created_at": r[4], "error": r[5]}
                for r in cursor.fetchall()
            ]
            report["indicators"]["sync_failures"] = {
                "count": len(sync_failures),
                "items": sync_failures[:10]
            }
            total_issues += len(sync_failures)

            # ── 7. Polling lag ────────────────────────────────────────────────
            LAG_THRESHOLD_MINUTES = 12  # 2 ciclos de 5 min + margen
            cursor.execute("""
                SELECT calendar_id, last_poll_time, last_poll_ok, error_count, last_error
                FROM poll_calendar_state
            """)
            lagging_calendars = []
            for r in cursor.fetchall():
                cal_id, last_poll_time, last_poll_ok, error_count, last_error = r
                lag_minutes = None
                is_lagging = False
                if last_poll_time:
                    try:
                        lpt = datetime.datetime.fromisoformat(
                            last_poll_time.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                        lag_minutes = (now - lpt).total_seconds() / 60
                        is_lagging = lag_minutes > LAG_THRESHOLD_MINUTES
                    except Exception:
                        is_lagging = True
                else:
                    is_lagging = True  # nunca polleó

                if is_lagging:
                    lagging_calendars.append({
                        "calendar_id": cal_id,
                        "last_poll_time": last_poll_time,
                        "lag_minutes": round(lag_minutes, 1) if lag_minutes else None,
                        "last_poll_ok": bool(last_poll_ok),
                        "error_count": error_count,
                        "last_error": last_error
                    })
            report["indicators"]["polling_lag"] = {
                "count": len(lagging_calendars),
                "threshold_minutes": LAG_THRESHOLD_MINUTES,
                "items": lagging_calendars
            }
            total_issues += len(lagging_calendars)

            # ── 8. Orphan events ──────────────────────────────────────────────
            cursor.execute("""
                SELECT id, summary, tecnico_nombre, extended_props
                FROM eventos
                WHERE extended_props LIKE '%"grupo_id"%'
            """)
            orphans = []
            for r in cursor.fetchall():
                ev_id, summary, tec, ext_raw = r
                try:
                    ext = json.loads(ext_raw or "{}")
                    grupo_id = ext.get("private", {}).get("grupo_id")
                    if grupo_id:
                        cur2 = conn.cursor()
                        cur2.execute("SELECT 1 FROM grupos WHERE grupo_id = ?", (grupo_id,))
                        if not cur2.fetchone():
                            orphans.append({
                                "event_id": ev_id,
                                "summary": summary,
                                "tecnico": tec,
                                "stale_grupo_id": grupo_id
                            })
                except Exception:
                    pass
            report["indicators"]["orphan_events"] = {
                "count": len(orphans),
                "items": orphans
            }
            total_issues += len(orphans)

            # ── 9. Lookup misses últimas 24h ──────────────────────────────────
            cutoff_24h = (now - datetime.timedelta(hours=24)).isoformat() + "Z"
            cursor.execute("""
                SELECT event_id, timestamp, detail
                FROM poll_log
                WHERE event_type LIKE 'LOOKUP_MISS%'
                  AND timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT 50
            """, (cutoff_24h,))
            lookup_misses = [
                {"event_id": r[0], "timestamp": r[1], "detail": r[2]}
                for r in cursor.fetchall()
            ]
            report["indicators"]["lookup_misses_24h"] = {
                "count": len(lookup_misses),
                "items": lookup_misses[:10]
            }
            total_issues += len(lookup_misses)

            # ── 10. GROUP HEALTH ──────────────────────────────────────────
            try:
                group_health = self.get_group_health()
                report["indicators"]["group_health"] = group_health
                total_issues += group_health.get("inconsistent_groups", 0)
            except Exception as gh_err:
                report["indicators"]["group_health"] = {"error": str(gh_err)}

            # ── 11. Partial Group Operations ──────────────────────────────
            try:
                self.db.ensure_group_operations_table()
                pending_ops = self.db.get_pending_group_operations(limit=20)
                partial_ops = [o for o in pending_ops if o["status"] == "PARTIAL"]
                report["indicators"]["partial_group_operations"] = {
                    "count": len(partial_ops),
                    "items": partial_ops
                }
                total_issues += len(partial_ops)
            except Exception as po_err:
                report["indicators"]["partial_group_operations"] = {"error": str(po_err)}

        # ── Summary ───────────────────────────────────────────────────────────
        report["summary"] = {
            "total_issues": total_issues,
            "has_drift": total_issues > 0,
            "critical": (
                report["indicators"]["sync_failures"]["count"] > 0
                or report["indicators"]["duplicate_events"]["count"] > 0
                or report["indicators"]["reopened_reviews"]["count"] > 0
            )
        }

        # [DRIFT_DETECTED] log canónico si hay problemas
        if total_issues > 0:
            try:
                from utils import OperationalLogger
                OperationalLogger.log(
                    self.db, "DRIFT_DETECTED", "full_drift_report",
                    {
                        "total_issues": total_issues,
                        "sync_failures": report["indicators"]["sync_failures"]["count"],
                        "without_google_id": report["indicators"]["events_without_google_id"]["count"],
                        "duplicates": report["indicators"]["duplicate_events"]["count"],
                        "reopened_reviews": report["indicators"]["reopened_reviews"]["count"],
                        "orphans": report["indicators"]["orphan_events"]["count"],
                        "polling_lag": report["indicators"]["polling_lag"]["count"],
                        "lookup_misses_24h": report["indicators"]["lookup_misses_24h"]["count"],
                    }
                )
            except Exception:
                pass

        return report

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_reconciliation_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Recupera las últimas decisiones tomadas por el motor de reconciliación."""
        return self.db.get_poll_logs(limit=limit, event_type="FIELD_OWNERSHIP")

    def get_sync_lag(self) -> List[Dict[str, Any]]:
        """Calcula el lag de sincronización."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tecnico_nombre, id, summary, updated_at, last_synced_at
                FROM eventos
                WHERE sync_status = 'PENDING' OR pending_sync = 1
                ORDER BY updated_at ASC
            """)
            return [
                {"tecnico": r[0], "event_id": r[1], "summary": r[2],
                 "last_local_update": r[3], "last_google_sync": r[4]}
                for r in cursor.fetchall()
            ]

    def get_polling_health(self) -> Dict[str, Any]:
        """Retorna un resumen extendido de la salud del PollingManager."""
        return self.db.get_poll_status()

    def get_last_heartbeat(self) -> Optional[Dict[str, Any]]:
        """Recupera el último heartbeat del PollingManager."""
        logs = self.db.get_poll_logs(limit=1, event_type="POLL_HEARTBEAT")
        return logs[0] if logs else None

    def get_recent_inbound_traces(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Recupera los últimos rastreos de entrada (decisiones de reconciliación)."""
        return self.db.get_poll_logs(limit=limit, event_type="POLL_INBOUND_TRACE")

    # ── GROUP HEALTH ───────────────────────────────────────────────

    def get_group_health(self) -> Dict[str, Any]:
        """
        [GROUP_HEALTH] Sección de salud de grupos.
        Detecta:
          - total_groups          : cuantos grupos hay
          - inconsistent_groups   : grupos con drift temporal o miembros faltantes
          - orphan_groups         : grupos con todos los event_ids inexistentes
          - orphan_events         : eventos con grupo_id que ya no existe en tabla grupos
          - stale_title_groups    : grupos con al menos 1 título desactualizado
          - partial_operations    : operaciones grupales PARTIAL sin cerrar
          - drift_rate            : % de grupos con problemas
          - group_drift_reviews   : reviews con conflict_type GROUP_*
        """
        now = datetime.datetime.utcnow()
        result: Dict[str, Any] = {}

        with self.db._get_connection() as conn:
            cursor = conn.cursor()

            # Total grupos
            cursor.execute("SELECT COUNT(*) FROM grupos")
            total_groups = cursor.fetchone()[0]
            result["total_groups"] = total_groups

            # Grupos con event_ids inexistentes (orphan o inconsistent)
            cursor.execute("SELECT grupo_id, event_ids FROM grupos")
            grupo_rows = cursor.fetchall()

            orphan_groups      = []
            inconsistent_groups = []
            temporal_drift     = []

            for g_row in grupo_rows:
                g_id   = g_row[0]
                e_ids  = json.loads(g_row[1]) if g_row[1] else []
                if not e_ids:
                    orphan_groups.append(g_id)
                    continue

                # Verificar existencia de miembros
                existing = []
                for eid in e_ids:
                    cursor.execute(
                        "SELECT id, inicio, fin FROM eventos WHERE id = ? OR google_event_id = ?",
                        (eid, eid)
                    )
                    ev_row = cursor.fetchone()
                    if ev_row:
                        existing.append({"id": ev_row[0], "inicio": ev_row[1], "fin": ev_row[2]})

                if not existing:
                    orphan_groups.append(g_id)
                    continue

                if len(existing) < len(e_ids):
                    inconsistent_groups.append({"group_id": g_id, "issue": "MISSING_MEMBERS",
                                                "expected": len(e_ids), "found": len(existing)})

                # Verificar coherencia temporal
                ref_date = existing[0]["inicio"][:10] if existing[0]["inicio"] else None
                for ev_info in existing[1:]:
                    ev_date = ev_info["inicio"][:10] if ev_info["inicio"] else None
                    if ev_date and ref_date and ev_date != ref_date:
                        temporal_drift.append({"group_id": g_id,
                                               "ref_date": ref_date, "divergent_date": ev_date})
                        if not any(g["group_id"] == g_id for g in inconsistent_groups):
                            inconsistent_groups.append({"group_id": g_id,
                                                        "issue": "TEMPORAL_DRIFT",
                                                        "ref_date": ref_date,
                                                        "divergent_date": ev_date})
                        break

            result["orphan_groups"]       = {"count": len(orphan_groups),  "items": orphan_groups}
            result["inconsistent_groups"] = len(inconsistent_groups)
            result["temporal_drift"]      = {"count": len(temporal_drift), "items": temporal_drift[:10]}

            # Orphan events (grupo_id en metadata pero grupo no existe)
            cursor.execute("SELECT id, extended_props FROM eventos WHERE extended_props LIKE '%\"grupo_id\"%'")
            orphan_ev_count = 0
            for ev_id, ext_raw in cursor.fetchall():
                try:
                    ext      = json.loads(ext_raw or "{}")
                    g_id_meta = ext.get("private", {}).get("grupo_id")
                    if g_id_meta:
                        cursor2 = conn.cursor()
                        cursor2.execute("SELECT 1 FROM grupos WHERE grupo_id = ?", (g_id_meta,))
                        if not cursor2.fetchone():
                            orphan_ev_count += 1
                except Exception:
                    pass
            result["orphan_events"] = orphan_ev_count

            # Reviews de GROUP_DRIFT pendientes
            cursor.execute("""
                SELECT COUNT(*) FROM poll_review_queue
                WHERE status = 'PENDING'
                  AND conflict_type LIKE 'GROUP_%'
            """)
            group_drift_reviews = cursor.fetchone()[0]
            result["group_drift_reviews"] = group_drift_reviews

        # Partial group operations
        try:
            self.db.ensure_group_operations_table()
            partial_ops = [o for o in self.db.get_pending_group_operations(limit=100)
                           if o["status"] == "PARTIAL"]
            result["partial_operations"] = len(partial_ops)
        except Exception:
            result["partial_operations"] = 0

        # Drift rate
        result["drift_rate"] = (
            round((result["inconsistent_groups"] / total_groups * 100), 1)
            if total_groups > 0 else 0.0
        )

        return result

    def get_group_drift_reviews(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retorna reviews con conflict_type GROUP_* (GROUP_TEMPORAL_DRIFT, etc.)"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT review_id, event_id, calendar_id, conflict_type,
                       detected_at, status, local_snapshot, remote_snapshot
                FROM poll_review_queue
                WHERE conflict_type LIKE 'GROUP_%'
                ORDER BY detected_at DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                local_snap = r[6]
                try:
                    local_snap = json.loads(local_snap) if local_snap else {}
                except Exception:
                    local_snap = {}
                results.append({
                    "review_id":     r[0],
                    "event_id":      r[1],
                    "calendar_id":   r[2],
                    "conflict_type": r[3],
                    "detected_at":   r[4],
                    "status":        r[5],
                    "group_payload": local_snap.get("group_payload", {})
                })
            return results
