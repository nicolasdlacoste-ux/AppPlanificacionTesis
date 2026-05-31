"""
group_repair.py
───────────────
Herramienta de reparación manual de grupos para AppPlanificacion.

GROUP CONSISTENCY HARDENING — FASE 1
Objetivo: reparar grupos inconsistentes de forma segura y controlada.

IMPORTANTE:
  - NO muta Google Calendar automáticamente.
  - Solo repara SQLite y marca pending_sync.
  - Todas las acciones quedan registradas en logs.
  - Requiere ejecución manual / aprobación del operador.

Capacidades:
  1. Temporal Re-align  — realinear fechas de miembros divergentes
  2. Title Regeneration — recalcular format_group_summary() y aplicar
  3. Metadata Repair    — reinyectar grupo_id en extended_props
  4. Orphan Cleanup     — eliminar referencias a event_ids inexistentes
  5. Sync Reconcile     — re-encolar miembros con sync_status=FAILED

Logs:
  [GROUP_REPAIR_START]
  [GROUP_REPAIR_ACTION]
  [GROUP_REPAIR_COMPLETE]
"""

import json
import datetime
import copy
from typing import Optional


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_ext(ev: dict) -> dict:
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


def _log_repair_action(db, group_id: str, action_type: str, detail: dict):
    db.log_trace(
        group_id,
        f"GROUP_REPAIR_ACTION:{action_type}",
        detail,
        tag="GROUP_REPAIR"
    )


# ── reparador principal ───────────────────────────────────────────────────────

def repair_group(db, group_id: str,
                 temporal_strategy: str = "majority",
                 dry_run: bool = False) -> dict:
    """
    Repara un grupo inconsistente aplicando todas las estrategias disponibles.

    Parámetros:
      temporal_strategy: "earliest" | "latest" | "majority" | "first_member"
      dry_run: si True, solo calcula sin persistir

    Retorna:
    {
      "group_id": str,
      "actions_taken": [...],
      "skipped": [...],
      "errors": [...],
      "dry_run": bool
    }
    """
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"
    actions_taken = []
    skipped       = []
    errors_list   = []

    db.log_trace(group_id, "GROUP_REPAIR_START",
                 {"strategy": temporal_strategy, "dry_run": dry_run, "timestamp": now_iso},
                 tag="GROUP_REPAIR")

    # 1. Obtener grupo
    grupo = db.obtener_grupo(group_id)
    if not grupo:
        err = {"code": "GROUP_NOT_FOUND", "msg": f"Grupo {group_id} no existe"}
        db.log_trace(group_id, "GROUP_REPAIR_COMPLETE",
                     {"status": "FAILED", "errors": [err]}, tag="GROUP_REPAIR")
        return {"group_id": group_id, "actions_taken": [], "skipped": [],
                "errors": [err], "dry_run": dry_run}

    event_ids   = grupo.get("event_ids", [])
    tec_nombres = grupo.get("tecnico_nombres", [])

    # 2. Resolver miembros físicos
    member_events = []
    missing_ids   = []
    for eid in event_ids:
        ev = db.resolve_event(eid)
        if ev:
            member_events.append(ev)
        else:
            missing_ids.append(eid)

    # ── REPAIR 1: Orphan Cleanup ──────────────────────────────────────────────
    if missing_ids:
        if not dry_run:
            new_event_ids   = [eid for eid in event_ids  if eid not in missing_ids]
            new_tec_nombres = []
            for eid, tec in zip(event_ids, tec_nombres):
                if eid not in missing_ids:
                    new_tec_nombres.append(tec)
            grupo["event_ids"]      = new_event_ids
            grupo["tecnico_nombres"] = new_tec_nombres
            db.crear_o_actualizar_grupo(grupo)
        action = {
            "type":    "ORPHAN_CLEANUP",
            "detail":  f"Eliminadas {len(missing_ids)} referencias a eventos inexistentes",
            "removed": missing_ids,
            "dry_run": dry_run
        }
        actions_taken.append(action)
        _log_repair_action(db, group_id, "ORPHAN_CLEANUP", action)

    if not member_events:
        msg = "Sin miembros válidos tras limpieza de orphans"
        db.log_trace(group_id, "GROUP_REPAIR_COMPLETE",
                     {"status": "ABORTED", "reason": msg}, tag="GROUP_REPAIR")
        return {"group_id": group_id, "actions_taken": actions_taken,
                "skipped": skipped, "errors": [{"code": "NO_VALID_MEMBERS", "msg": msg}],
                "dry_run": dry_run}

    # ── REPAIR 2: Temporal Re-align ───────────────────────────────────────────
    inicios = [ev.get("inicio") for ev in member_events if ev.get("inicio")]
    fins    = [ev.get("fin")    for ev in member_events if ev.get("fin")]

    if inicios and fins:
        # Elegir timestamp de referencia según estrategia
        if temporal_strategy == "earliest":
            target_inicio = min(inicios)
            target_fin    = min(fins)
        elif temporal_strategy == "latest":
            target_inicio = max(inicios)
            target_fin    = max(fins)
        elif temporal_strategy == "first_member":
            target_inicio = member_events[0].get("inicio")
            target_fin    = member_events[0].get("fin")
        else:  # majority
            # Elegir la fecha que aparece más veces en inicio
            from collections import Counter
            date_counts = Counter(ts[:10] for ts in inicios if ts)
            most_common_date = date_counts.most_common(1)[0][0]
            # Usar primer miembro que tenga esa fecha como referencia
            ref_ev = next(
                (ev for ev in member_events
                 if ev.get("inicio", "")[:10] == most_common_date),
                member_events[0]
            )
            target_inicio = ref_ev.get("inicio")
            target_fin    = ref_ev.get("fin")

        realigned_count = 0
        for ev in member_events:
            if ev.get("inicio") != target_inicio or ev.get("fin") != target_fin:
                if not dry_run:
                    try:
                        db.actualizar_evento_individual(
                            ev["id"], ev["calendar_id"],
                            {"inicio": target_inicio, "fin": target_fin},
                            sync_status="PENDING",
                            pending_sync=1,
                            origin="group_repair_temporal"
                        )
                        realigned_count += 1
                    except Exception as e:
                        errors_list.append({
                            "code":     "TEMPORAL_REALIGN_ERROR",
                            "event_id": ev["id"],
                            "msg":      str(e)
                        })
                else:
                    realigned_count += 1

        if realigned_count > 0:
            action = {
                "type":            "TEMPORAL_REALIGN",
                "strategy":        temporal_strategy,
                "target_inicio":   target_inicio,
                "target_fin":      target_fin,
                "realigned_count": realigned_count,
                "dry_run":         dry_run
            }
            actions_taken.append(action)
            _log_repair_action(db, group_id, "TEMPORAL_REALIGN", action)
        else:
            skipped.append({"type": "TEMPORAL_REALIGN", "reason": "Todos los miembros ya están alineados"})
    else:
        skipped.append({"type": "TEMPORAL_REALIGN", "reason": "Sin timestamps válidos para alinear"})

    # ── REPAIR 3: Metadata Repair — grupo_id ──────────────────────────────────
    meta_fixed = 0
    for ev in member_events:
        ext  = _safe_ext(ev)
        priv = ext.get("private", {})
        if priv.get("grupo_id") != group_id:
            if not dry_run:
                try:
                    new_ext = copy.deepcopy(ext)
                    new_ext["private"]["grupo_id"] = group_id
                    db.actualizar_evento_individual(
                        ev["id"], ev["calendar_id"],
                        {"extended_props": new_ext},
                        sync_status="PENDING",
                        pending_sync=1,
                        origin="group_repair_metadata"
                    )
                    meta_fixed += 1
                except Exception as e:
                    errors_list.append({
                        "code":     "METADATA_REPAIR_ERROR",
                        "event_id": ev["id"],
                        "msg":      str(e)
                    })
            else:
                meta_fixed += 1

    if meta_fixed > 0:
        action = {"type": "METADATA_REPAIR", "fixed_count": meta_fixed, "dry_run": dry_run}
        actions_taken.append(action)
        _log_repair_action(db, group_id, "METADATA_REPAIR", action)
    else:
        skipped.append({"type": "METADATA_REPAIR", "reason": "grupo_id ya correcto en todos"})

    # ── REPAIR 4: Title Regeneration ──────────────────────────────────────────
    try:
        from utils import format_group_summary, get_ot_base_from_event
        tecnicos_db = db.obtener_tecnicos()
        ini_map     = {t["nombre"]: t.get("iniciales", "") for t in tecnicos_db}
        ini_list    = [ini_map.get(n, "") for n in grupo.get("tecnico_nombres", [])]
        ref_ev      = member_events[0]
        ot_base     = get_ot_base_from_event(ref_ev)
        new_title   = format_group_summary(ot_base, ini_list)

        title_fixed = 0
        for ev in member_events:
            if ev.get("summary") != new_title and new_title:
                if not dry_run:
                    try:
                        db.actualizar_evento_individual(
                            ev["id"], ev["calendar_id"],
                            {"evento": new_title},
                            sync_status="PENDING",
                            pending_sync=1,
                            origin="group_repair_title"
                        )
                        title_fixed += 1
                    except Exception as e:
                        errors_list.append({
                            "code":     "TITLE_REPAIR_ERROR",
                            "event_id": ev["id"],
                            "msg":      str(e)
                        })
                else:
                    title_fixed += 1

        if title_fixed > 0:
            action = {
                "type":        "TITLE_REGENERATION",
                "new_title":   new_title,
                "fixed_count": title_fixed,
                "dry_run":     dry_run
            }
            actions_taken.append(action)
            _log_repair_action(db, group_id, "TITLE_REGENERATION", action)
        else:
            skipped.append({"type": "TITLE_REGENERATION", "reason": "Títulos ya correctos"})
    except Exception as e:
        errors_list.append({"code": "TITLE_REPAIR_SKIPPED", "msg": str(e)})

    # ── REPAIR 5: Sync Reconciliation ─────────────────────────────────────────
    failed_members = [ev for ev in member_events if ev.get("sync_status") == "FAILED"]
    requeued = 0
    for ev in failed_members:
        if not dry_run:
            try:
                db.enqueue_sync(
                    ev.get("google_event_id") or ev["id"],
                    ev["calendar_id"],
                    ev.get("tecnico_nombre", ""),
                    "UPDATE",
                    origin="group_repair_sync"
                )
                db.actualizar_evento_individual(
                    ev["id"], ev["calendar_id"],
                    {},
                    sync_status="PENDING",
                    pending_sync=1,
                    origin="group_repair_sync"
                )
                requeued += 1
            except Exception as e:
                errors_list.append({
                    "code":     "SYNC_RECONCILE_ERROR",
                    "event_id": ev["id"],
                    "msg":      str(e)
                })
        else:
            requeued += 1

    if requeued > 0:
        action = {"type": "SYNC_RECONCILE", "requeued_count": requeued, "dry_run": dry_run}
        actions_taken.append(action)
        _log_repair_action(db, group_id, "SYNC_RECONCILE", action)
    else:
        skipped.append({"type": "SYNC_RECONCILE", "reason": "Sin miembros con sync_status=FAILED"})

    # ── COMPLETE ──────────────────────────────────────────────────────────────
    result = {
        "group_id":     group_id,
        "actions_taken": actions_taken,
        "skipped":      skipped,
        "errors":       errors_list,
        "dry_run":      dry_run,
        "repaired_at":  now_iso
    }
    db.log_trace(group_id, "GROUP_REPAIR_COMPLETE",
                 {
                     "actions": len(actions_taken),
                     "skipped": len(skipped),
                     "errors":  len(errors_list),
                     "dry_run": dry_run
                 },
                 tag="GROUP_REPAIR")

    return result


def repair_all_groups(db, temporal_strategy: str = "majority",
                      dry_run: bool = False) -> dict:
    """
    Repara todos los grupos existentes.
    Retorna un resumen con el resultado por grupo.
    """
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT grupo_id FROM grupos")
        group_ids = [row[0] for row in cursor.fetchall()]

    results          = []
    total_actions    = 0
    total_errors     = 0
    repaired_groups  = 0

    for gid in group_ids:
        r = repair_group(db, gid, temporal_strategy=temporal_strategy, dry_run=dry_run)
        results.append(r)
        total_actions += len(r.get("actions_taken", []))
        total_errors  += len(r.get("errors", []))
        if r.get("actions_taken"):
            repaired_groups += 1

    return {
        "timestamp":       now_iso,
        "total_groups":    len(group_ids),
        "repaired_groups": repaired_groups,
        "total_actions":   total_actions,
        "total_errors":    total_errors,
        "dry_run":         dry_run,
        "strategy":        temporal_strategy,
        "results":         results
    }
