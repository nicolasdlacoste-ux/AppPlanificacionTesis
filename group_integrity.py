"""
group_integrity.py
──────────────────
Validador de integridad grupal para AppPlanificacion.

GROUP CONSISTENCY HARDENING — FASE 1
Objetivo: detectar grupos inconsistentes SIN modificar datos.

Invariantes que valida:
  - TEMPORAL   : todos los miembros comparten inicio/fin
  - EXISTENCE  : todos los event_ids existen físicamente en eventos
  - OWNERSHIP  : sin calendar_id duplicado dentro del grupo
  - TITLE      : summary es coherente con format_group_summary()
  - METADATA   : grupo_id inyectado en extended_props de cada miembro
  - SYNC       : sync_state compatible entre miembros

Logs:
  [GROUP_VALIDATION_START]
  [GROUP_VALIDATION_FAILED]
  [GROUP_VALIDATION_OK]
"""

import json
import datetime
from typing import Optional


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_ext(ev: dict) -> dict:
    """Parsea extended_props defensivamente (puede llegar como str desde SQLite)."""
    raw = ev.get("extended_props") or ev.get("extendedProperties") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    priv = raw.get("private") or {}
    if isinstance(priv, str):
        try:
            priv = json.loads(priv)
        except Exception:
            priv = {}
    raw["private"] = priv
    return raw


def _date_part(ts: Optional[str]) -> Optional[str]:
    """Extrae la parte YYYY-MM-DD de un timestamp ISO."""
    if not ts:
        return None
    return ts[:10]


def _tiempo_compatible(inicio: Optional[str], fin: Optional[str],
                        ref_inicio: Optional[str], ref_fin: Optional[str]) -> bool:
    """
    Compara la fecha del inicio/fin de un miembro contra la referencia.
    Para eventos con timestamp (T), compara solo la parte de fecha.
    Para todo-el-día, compara directamente.
    """
    return _date_part(inicio) == _date_part(ref_inicio) and \
           _date_part(fin) == _date_part(ref_fin)

def snapshot_group_state(db, group_id: str) -> dict:
    """
    [GROUP_CONSISTENCY_SNAPSHOTS] Captura el estado estructural y físico del grupo.
    Útil para auditoría BEFORE vs AFTER de mutaciones atómicas.
    """
    grupo = db.obtener_grupo(group_id)
    if not grupo:
        return {"group_id": group_id, "exists_in_logic": False}

    event_ids = grupo.get("event_ids", [])
    members_data = []
    
    for eid in event_ids:
        ev = db.resolve_event(eid)
        if ev:
            members_data.append({
                "event_id": ev.get("id"),
                "calendar_id": ev.get("calendar_id"),
                "google_event_id": ev.get("google_event_id"),
                "tecnico_nombre": ev.get("tecnico_nombre"),
                "inicio": ev.get("inicio"),
                "fin": ev.get("fin"),
                "summary": ev.get("summary"),
                "sync_status": ev.get("sync_status"),
                "extended_props": _safe_ext(ev)
            })
        else:
            members_data.append({
                "event_id": eid,
                "missing_in_db": True
            })

    return {
        "group_id": group_id,
        "exists_in_logic": True,
        "ot_nro": grupo.get("ot_nro"),
        "tecnico_nombres": grupo.get("tecnico_nombres"),
        "patrones": grupo.get("patrones"),
        "vehiculo": grupo.get("vehiculo"),
        "members": members_data,
        "snapshot_time": datetime.datetime.utcnow().isoformat() + "Z"
    }


# ── validador principal ───────────────────────────────────────────────────────

def validate_group_integrity(db, group_id: str) -> dict:
    """
    Valida la integridad completa de un grupo.

    Retorna:
    {
      "group_id": str,
      "valid": bool,
      "errors": [...],          # invariantes rotas
      "warnings": [...],        # inconsistencias menores
      "members_checked": int,
      "integrity_score": 0-100  # 100 = perfecto, 0 = completamente roto
    }
    """
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"
    errors   = []
    warnings = []

    # Log inicio
    db.log_trace(group_id, "GROUP_VALIDATION_START",
                 {"group_id": group_id, "timestamp": now_iso},
                 tag="GROUP_INTEGRITY")

    # 1. Obtener el grupo
    grupo = db.obtener_grupo(group_id)
    if not grupo:
        err = {"code": "GROUP_NOT_FOUND", "msg": f"Grupo {group_id} no existe en tabla grupos"}
        db.log_trace(group_id, "GROUP_VALIDATION_FAILED",
                     {"errors": [err]}, tag="GROUP_INTEGRITY")
        return {
            "group_id": group_id,
            "valid": False,
            "errors": [err],
            "warnings": [],
            "members_checked": 0,
            "integrity_score": 0
        }

    event_ids      = grupo.get("event_ids", [])
    tec_nombres    = grupo.get("tecnico_nombres", [])
    members_checked = len(event_ids)

    # 2. Resolver eventos físicos
    member_events = []
    missing_ids   = []
    for eid in event_ids:
        ev = db.resolve_event(eid)
        if ev:
            member_events.append(ev)
        else:
            missing_ids.append(eid)

    # ── INVARIANT: EXISTENCE ─────────────────────────────────────────────────
    if missing_ids:
        errors.append({
            "code": "MEMBER_NOT_FOUND",
            "msg": f"event_ids inexistentes en tabla eventos: {missing_ids}",
            "severity": "critical",
            "affected_ids": missing_ids
        })

    if not member_events:
        db.log_trace(group_id, "GROUP_VALIDATION_FAILED",
                     {"errors": errors}, tag="GROUP_INTEGRITY")
        return {
            "group_id": group_id,
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "members_checked": members_checked,
            "integrity_score": 0
        }

    # ── INVARIANT: MÍNIMO 2 MIEMBROS ────────────────────────────────────────
    if len(member_events) < 2:
        warnings.append({
            "code": "SINGLE_MEMBER_GROUP",
            "msg": "Un grupo debería tener al menos 2 miembros activos",
            "severity": "warning",
            "count": len(member_events)
        })

    # ── INVARIANT: TEMPORAL INTEGRITY ────────────────────────────────────────
    ref = member_events[0]
    ref_inicio = ref.get("inicio")
    ref_fin    = ref.get("fin")
    for ev in member_events[1:]:
        if not _tiempo_compatible(ev.get("inicio"), ev.get("fin"), ref_inicio, ref_fin):
            errors.append({
                "code": "TEMPORAL_DRIFT",
                "msg": "Divergencia temporal entre miembros del grupo",
                "severity": "critical",
                "reference": {"event_id": ref.get("id"), "inicio": ref_inicio, "fin": ref_fin},
                "divergent": {"event_id": ev.get("id"), "inicio": ev.get("inicio"), "fin": ev.get("fin")},
                "tecnico": ev.get("tecnico_nombre")
            })

    # ── INVARIANT: UNIQUE OWNERSHIP (calendar_id / google_event_id) ──────────
    cal_ids    = [ev.get("calendar_id") for ev in member_events]
    gids       = [ev.get("google_event_id") for ev in member_events if ev.get("google_event_id")]
    dup_cals   = [c for c in set(cal_ids) if cal_ids.count(c) > 1]
    dup_gids   = [g for g in set(gids)    if gids.count(g) > 1]
    if dup_cals:
        errors.append({
            "code": "DUPLICATE_CALENDAR_ID",
            "msg": f"calendar_id duplicado en el grupo: {dup_cals}",
            "severity": "high"
        })
    if dup_gids:
        errors.append({
            "code": "DUPLICATE_GOOGLE_EVENT_ID",
            "msg": f"google_event_id duplicado en el grupo: {dup_gids}",
            "severity": "high"
        })

    # ── INVARIANT: METADATA — grupo_id inyectado ─────────────────────────────
    for ev in member_events:
        ext  = _safe_ext(ev)
        priv = ext.get("private", {})
        gid_meta = priv.get("grupo_id")
        if gid_meta != group_id:
            warnings.append({
                "code": "MISSING_GRUPO_ID_IN_METADATA",
                "msg": f"Evento {ev.get('id')} no tiene grupo_id correcto en extended_props",
                "severity": "warning",
                "event_id": ev.get("id"),
                "found": gid_meta,
                "expected": group_id
            })

    # ── INVARIANT: TITLE CONSISTENCY ─────────────────────────────────────────
    try:
        from utils import format_group_summary, get_ot_base_from_event
        tecnicos_db  = db.obtener_tecnicos()
        ini_map      = {t["nombre"]: t.get("iniciales", "") for t in tecnicos_db}
        ini_list     = [ini_map.get(n, "") for n in tec_nombres]
        ot_base      = get_ot_base_from_event(ref)
        expected_title = format_group_summary(ot_base, ini_list)
        for ev in member_events:
            actual = ev.get("summary", "")
            if expected_title and actual != expected_title:
                warnings.append({
                    "code": "STALE_TITLE",
                    "msg": f"Título desactualizado en {ev.get('id')}",
                    "severity": "warning",
                    "event_id": ev.get("id"),
                    "actual": actual,
                    "expected": expected_title
                })
    except Exception as e:
        warnings.append({"code": "TITLE_CHECK_ERROR", "msg": str(e), "severity": "info"})

    # ── INVARIANT: SYNC CONSISTENCY ──────────────────────────────────────────
    sync_statuses = [ev.get("sync_status") for ev in member_events]
    failed_syncs  = [ev for ev in member_events if ev.get("sync_status") == "FAILED"]
    if failed_syncs:
        errors.append({
            "code": "SYNC_FAILED_MEMBER",
            "msg": f"{len(failed_syncs)} miembro(s) con sync_status=FAILED",
            "severity": "high",
            "affected_ids": [ev.get("id") for ev in failed_syncs]
        })

    # ── INTEGRITY SCORE ───────────────────────────────────────────────────────
    critical_errors = [e for e in errors if e.get("severity") in ("critical", "high")]
    minor_issues    = [e for e in errors if e.get("severity") not in ("critical", "high")] + warnings
    deductions      = len(critical_errors) * 30 + len(minor_issues) * 5
    score           = max(0, 100 - deductions)

    valid = len(errors) == 0

    result = {
        "group_id":        group_id,
        "valid":           valid,
        "errors":          errors,
        "warnings":        warnings,
        "members_checked": members_checked,
        "integrity_score": score,
        "checked_at":      now_iso,
        "member_summary":  [
            {
                "event_id":    ev.get("id"),
                "tecnico":     ev.get("tecnico_nombre"),
                "calendar_id": ev.get("calendar_id"),
                "inicio":      ev.get("inicio"),
                "fin":         ev.get("fin"),
                "sync_status": ev.get("sync_status"),
                "summary":     ev.get("summary")
            }
            for ev in member_events
        ]
    }

    if valid:
        db.log_trace(group_id, "GROUP_VALIDATION_OK",
                     {"integrity_score": score, "members": members_checked},
                     tag="GROUP_INTEGRITY")
    else:
        db.log_trace(group_id, "GROUP_VALIDATION_FAILED",
                     {
                         "integrity_score": score,
                         "errors": [e["code"] for e in errors],
                         "warnings": [w["code"] for w in warnings],
                         "members": members_checked
                     },
                     tag="GROUP_INTEGRITY")

    return result


def validate_all_groups(db) -> dict:
    """
    Valida todos los grupos existentes.
    Retorna un resumen ejecutivo con métricas y lista de grupos problemáticos.
    """
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT grupo_id FROM grupos")
        group_ids = [row[0] for row in cursor.fetchall()]

    total         = len(group_ids)
    valid_count   = 0
    invalid_count = 0
    results       = []

    for gid in group_ids:
        r = validate_group_integrity(db, gid)
        results.append(r)
        if r["valid"]:
            valid_count += 1
        else:
            invalid_count += 1

    # Agregar métricas de orphan events (grupo_id en metadata pero sin grupo en tabla)
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, extended_props FROM eventos WHERE extended_props LIKE '%\"grupo_id\"%'")
        rows = cursor.fetchall()

    orphan_event_count = 0
    for ev_id, ext_raw in rows:
        try:
            ext      = json.loads(ext_raw or "{}")
            grupo_id = ext.get("private", {}).get("grupo_id")
            if grupo_id:
                with db._get_connection() as conn2:
                    cursor2 = conn2.cursor()
                    cursor2.execute("SELECT 1 FROM grupos WHERE grupo_id = ?", (grupo_id,))
                    if not cursor2.fetchone():
                        orphan_event_count += 1
        except Exception:
            pass

    drift_rate = round((invalid_count / total * 100), 1) if total > 0 else 0.0

    return {
        "timestamp":        now_iso,
        "total_groups":     total,
        "valid_groups":     valid_count,
        "inconsistent_groups": invalid_count,
        "orphan_events":    orphan_event_count,
        "drift_rate":       drift_rate,
        "groups": results
    }
