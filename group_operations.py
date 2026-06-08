"""
group_operations.py — Transactional Group Operations (Fase 1)
=============================================================

Implementa el modelo:
    1. Build Mutation Plan          (sin tocar la BD)
    2. Atomic SQLite Mutation       (una sola transacción, sin side effects)
    3. Post-Commit Side Effects     (enqueue_sync, log_trace, journal)

Uso en api_server.py:
    ctx = GroupOperationContext("move_date", grupo_id, "drag_drop", trigger_event_id)
    ctx.load_group(db)
    ctx.validate(params)
    ctx.build_plan(db, params, tecs_db)
    with db.group_transaction() as conn:
        ctx.execute_mutation_phase(conn)
    ctx.execute_post_commit_phase(db)
    return ctx.to_snapshot_response(db)

Restricciones:
- execute_mutation_phase NO llama enqueue_sync, log_trace ni APIs externas.
- No modifica el SyncWorker ni la integración Google.
- No cambia el schema SQLite (sólo usa columnas existentes + group_version).
"""

import uuid
import json
import datetime
import threading
from typing import Optional

# ── Locks de grupo en memoria ──────────────────────────────────────────────────
# Protege grupos que están en vuelo de mutación.
_group_locks: dict[str, str] = {}      # grupo_id -> operation_id
_group_lock_mutex = threading.Lock()


def acquire_group_lock(grupo_id: str, operation_id: str) -> bool:
    """Intenta adquirir el lock del grupo. Retorna True si lo obtuvo, False si ya está locked."""
    with _group_lock_mutex:
        if grupo_id in _group_locks:
            return False
        _group_locks[grupo_id] = operation_id
        return True


def release_group_lock(grupo_id: str) -> None:
    """Libera el lock del grupo."""
    with _group_lock_mutex:
        _group_locks.pop(grupo_id, None)


def is_group_locked(grupo_id: str) -> bool:
    """Consulta si un grupo tiene un lock activo."""
    with _group_lock_mutex:
        return grupo_id in _group_locks


# ── GroupOperationContext ──────────────────────────────────────────────────────

class GroupOperationContext:
    """
    Contexto de una operación grupal transaccional.

    Ciclo de vida:
        load_group → validate → build_plan → execute_mutation_phase →
        execute_post_commit_phase → to_snapshot_response
    """

    def __init__(
        self,
        operation_type: str,
        grupo_id: str,
        initiated_by: str,
        trigger_event_id: Optional[str] = None,
    ):
        self.operation_id      = str(uuid.uuid4())
        self.operation_type    = operation_type   # 'move_date' | 'reassign' | 'batch_edit'
        self.grupo_id          = grupo_id
        self.initiated_by      = initiated_by     # 'drag_drop' | 'right_panel' | 'batch'
        self.trigger_event_id  = trigger_event_id
        self.started_at        = datetime.datetime.utcnow().isoformat() + "Z"

        self.grupo_meta        = None   # raw grupo dict de la BD
        self.members_before    = []     # snapshots pre-mutación
        self._updated_grupo    = None   # grupo meta calculado por build_plan
        self._new_group_title  = ""
        self._final_tec_nombres = []
        self._is_reassignment  = False
        self._reassignment_id  = None

        self.mutation_plan     = []     # [{event_id, calendar_id_original, calendar_id_target, data, operation}]
        self.deferred_sync_jobs = []    # [{event_id, calendar_id, tecnico, operation, origin, original_calendar_id}]
        self._post_commit_traces = []   # [(event_id, step, detail, calendar_id, tag)]

        self.validation_errors = []
        self._lock_acquired    = False

    # ── 1. LOAD ─────────────────────────────────────────────────────────────────

    def load_group(self, db) -> "GroupOperationContext":
        """Carga el grupo y resuelve todos sus miembros físicos."""
        self.grupo_meta = db.obtener_grupo(self.grupo_id)
        if not self.grupo_meta:
            self.validation_errors.append(f"Grupo {self.grupo_id} no encontrado en la BD.")
            return self

        self.members_before = []
        for eid in self.grupo_meta.get("event_ids", []):
            ev = db.resolve_event(eid)
            if ev:
                self.members_before.append(ev)
            else:
                # Registrar huérfano como trace diferido — no bloquear la operación
                self._post_commit_traces.append((
                    eid, "GROUP_ORPHAN_DETECTED",
                    {"grupo_id": self.grupo_id, "missing_event_id": eid},
                    None, "GROUP_TX"
                ))

        return self

    # ── 2. VALIDATE ─────────────────────────────────────────────────────────────

    def validate(self, params=None) -> "GroupOperationContext":
        """Valida invariantes pre-mutación. Agrega errores a self.validation_errors."""
        if not self.grupo_meta:
            self.validation_errors.append("Grupo no cargado (llamar load_group primero).")
            return self

        if not self.members_before:
            self.validation_errors.append("El grupo no tiene miembros válidos resolvibles en la BD.")
            return self

        if params:
            cambio_tecnico = False
            nueva_fecha    = params.nueva_fecha

            if params.correo_destino and self.trigger_event_id:
                trigger_ev = next(
                    (m for m in self.members_before
                     if m["id"] == self.trigger_event_id
                     or m.get("google_event_id") == self.trigger_event_id),
                    None
                )
                if trigger_ev and trigger_ev.get("calendar_id", "").lower() != params.correo_destino.lower():
                    cambio_tecnico = True

            if cambio_tecnico and nueva_fecha and self.trigger_event_id:
                trigger_ev = next(
                    (m for m in self.members_before
                     if m["id"] == self.trigger_event_id
                     or m.get("google_event_id") == self.trigger_event_id),
                    None
                )
                if trigger_ev:
                    fecha_actual = (trigger_ev.get("inicio") or "")[:10]
                    if nueva_fecha != fecha_actual:
                        self.validation_errors.append(
                            "No se puede cambiar fecha y técnico a la vez en un evento de grupo."
                        )

        return self

    # ── 3. BUILD PLAN ───────────────────────────────────────────────────────────

    def build_plan(self, db, params, tecs_db: list) -> "GroupOperationContext":
        """
        Calcula el estado final de cada miembro SIN escribir en la BD.
        Genera mutation_plan y deferred_sync_jobs.
        """
        if self.validation_errors:
            return self

        from utils import (
            format_group_summary,
            get_ot_base_from_event,
            EventAdapter,
            generar_descripcion_enriquecida,
        )

        grupo = self.grupo_meta
        event_ids   = grupo.get("event_ids", [])
        tec_nombres = grupo.get("tecnico_nombres", [])

        map_correo_nombre = {t["correo"]: t["nombre"] for t in tecs_db}
        map_nombre_correo = {t["nombre"]: t["correo"] for t in tecs_db}
        map_nombre_init   = {t["nombre"]: t.get("iniciales", "") for t in tecs_db}

        # Determinar si hay cambio de técnico en el evento trigger
        cambio_tecnico = False
        nuevo_correo_destino = params.correo_destino if params.correo_destino else None
        if nuevo_correo_destino and self.trigger_event_id:
            trigger_ev = next(
                (m for m in self.members_before
                 if m["id"] == self.trigger_event_id
                 or m.get("google_event_id") == self.trigger_event_id),
                None
            )
            if trigger_ev and trigger_ev.get("calendar_id", "").lower() != nuevo_correo_destino.lower():
                cambio_tecnico = True

        self._is_reassignment = cambio_tecnico
        self._reassignment_id = str(uuid.uuid4()) if cambio_tecnico else None

        # Calcular lista de técnicos final (necesaria para el título canónico)
        final_tec_nombres = list(tec_nombres)
        if cambio_tecnico and self.trigger_event_id:
            nuevo_tec = map_correo_nombre.get(nuevo_correo_destino, nuevo_correo_destino)
            for i, eid in enumerate(event_ids):
                ev_mem = self._resolve_member(eid)
                if ev_mem and (ev_mem["id"] == self.trigger_event_id
                               or ev_mem.get("google_event_id") == self.trigger_event_id):
                    if i < len(final_tec_nombres):
                        final_tec_nombres[i] = nuevo_tec
                    break

        self._final_tec_nombres = final_tec_nombres

        # Calcular el título canónico UNA SOLA VEZ para todos los miembros
        ini_list = [map_nombre_init.get(n, "") for n in final_tec_nombres if n]
        ref_ev   = self.members_before[0] if self.members_before else {}
        ot_base  = get_ot_base_from_event(ref_ev)
        self._new_group_title = format_group_summary(ot_base, ini_list)

        # Preparar nueva_fecha (guard: si no viene, usar la del trigger event)
        nueva_fecha = params.nueva_fecha
        if not nueva_fecha and self.members_before:
            nueva_fecha = (self.members_before[0].get("inicio") or "")[:10]

        tz_suffix = "-03:00"

        # Construir plan por miembro
        for i, ev_mem in enumerate(self.members_before):
            eid = ev_mem["id"]
            is_trigger = (
                eid == self.trigger_event_id
                or ev_mem.get("google_event_id") == self.trigger_event_id
            )

            # Técnico y calendario destino
            if is_trigger and cambio_tecnico:
                cal_target = nuevo_correo_destino
                tec_nombre = map_correo_nombre.get(cal_target, cal_target)
            else:
                # Mantener el técnico actual del grupo para este slot
                tec_nombre = final_tec_nombres[i] if i < len(final_tec_nombres) else ev_mem.get("tecnico_nombre", "")
                cal_target = map_nombre_correo.get(tec_nombre) or ev_mem.get("calendar_id", "")

            # Calcular fechas
            nuevo_s, nuevo_e = self._calc_fechas(
                nueva_fecha,
                ev_mem.get("inicio", ""),
                ev_mem.get("fin", ""),
                params,
                tz_suffix,
            )

            # Metadata: partir de la normalización canónica del miembro
            ev_norm  = EventAdapter.normalize_event(ev_mem)
            metadata = (ev_norm.get("extended_props") or {}).get("private", {}).copy()

            if params.ots is not None:
                metadata["app_ots"] = json.dumps(params.ots)
            if params.patrones is not None:
                metadata["app_patrones"] = json.dumps(params.patrones)
            if params.vehiculo is not None:
                metadata["app_vehiculo"] = params.vehiculo
            if hasattr(params, "requiere_vehiculo") and params.requiere_vehiculo is not None:
                metadata["app_requiere_vehiculo"] = str(params.requiere_vehiculo).lower()

            # Siempre preservar grupo_id en metadata
            metadata["grupo_id"] = self.grupo_id

            # Metadata de reassign (solo para el miembro trigger)
            if is_trigger and cambio_tecnico:
                metadata["reassignment_in_progress"] = "true"
                metadata["reassignment_id"]          = self._reassignment_id
                metadata["reassignment_started_at"]  = datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat()
                metadata["previous_google_event_id"] = ev_mem.get("google_event_id", eid)
                metadata["previous_calendar_id"]     = ev_mem.get("calendar_id", "")
                metadata["reassignment_origin"]      = "group_move"

            full_props = (ev_norm.get("extended_props") or {}).copy()
            full_props["private"] = metadata

            # Descripción
            try:
                pats_actuales = json.loads(metadata.get("app_patrones", "[]") or "[]")
            except Exception:
                pats_actuales = []

            base_desc = (
                params.descripcion
                if params.descripcion is not None
                else ev_norm.get("descripcion", "")
            )

            if any(x is not None for x in [params.descripcion, params.patrones, params.vehiculo]):
                desc_final = generar_descripcion_enriquecida(
                    base_desc,
                    params.patrones if params.patrones is not None else pats_actuales,
                    params.vehiculo if params.vehiculo is not None else metadata.get("app_vehiculo", ""),
                )
            else:
                desc_final = base_desc

            # Operación de sync para este miembro
            is_reassign_member = is_trigger and cambio_tecnico
            sync_status_val    = "REASSIGN_PENDING" if is_reassign_member else "PENDING"
            operation_val      = "REMOTE_REASSIGNMENT" if is_reassign_member else "UPDATE"

            ubicacion = (
                params.direccion
                if params.direccion is not None
                else ev_norm.get("ubicacion", "")
            )

            self.mutation_plan.append({
                "event_id":            eid,
                "calendar_id_original": ev_mem.get("calendar_id", ""),
                "calendar_id_target":  cal_target,
                "data": {
                    "tecnico_nombre": tec_nombre,
                    "summary":        self._new_group_title,
                    "inicio":         nuevo_s,
                    "fin":            nuevo_e,
                    "ubicacion":      ubicacion,
                    "descripcion":    desc_final,
                    "extended_props": full_props,
                    "calendar_id":    cal_target,
                    "sync_status":    sync_status_val,
                    "pending_sync":   1,
                },
                "operation":      operation_val,
                "is_reassign":    is_reassign_member,
            })

            sync_origin = (
                self._reassignment_id
                if is_reassign_member
                else f"group_move_{self.operation_id[:8]}"
            )
            self.deferred_sync_jobs.append({
                "event_id":            eid,
                "calendar_id":         cal_target,
                "tecnico":             tec_nombre,
                "operation":           operation_val,
                "origin":              sync_origin,
                "original_calendar_id": ev_mem.get("calendar_id", ""),
            })

        # Grupo meta actualizado
        self._updated_grupo = {
            **grupo,
            "fecha":          nueva_fecha or grupo.get("fecha"),
            "tecnico_nombres": final_tec_nombres,
        }
        if params.vehiculo is not None:
            self._updated_grupo["vehiculo"] = params.vehiculo
        if params.patrones is not None:
            self._updated_grupo["patrones"] = params.patrones

        self._post_commit_traces.append((
            self.grupo_id, "GROUP_PLAN_BUILT",
            {
                "operation_id":    self.operation_id,
                "operation_type":  self.operation_type,
                "initiated_by":    self.initiated_by,
                "members_count":   len(self.mutation_plan),
                "is_reassignment": self._is_reassignment,
                "reassignment_id": self._reassignment_id,
                "new_title":       self._new_group_title,
            },
            None, "GROUP_TX"
        ))

        return self

    def build_arbitration_plan(self, data_to_apply: dict, sync_state_to_apply: Optional[str] = None) -> "GroupOperationContext":
        """
        Construye el plan de mutación para arbitraje (resolución de conflictos).
        Aplica los mismos cambios a TODOS los miembros del grupo.
        """
        self.mutation_plan = []
        self.deferred_sync_jobs = []

        if self.validation_errors:
            return self

        grupo = self.grupo_meta
        if not grupo:
            return self

        for ev_mem in self.members_before:
            eid = ev_mem["id"]
            cal_target = ev_mem.get("calendar_id", "")
            
            # Copiamos de ev_mem y pisamos con data_to_apply
            updated = {
                "tecnico_nombre": ev_mem.get("tecnico_nombre", ""),
                "summary": ev_mem.get("summary", ""),
                "inicio": ev_mem.get("inicio", ""),
                "fin": ev_mem.get("fin", ""),
                "ubicacion": ev_mem.get("ubicacion", ""),
                "descripcion": ev_mem.get("descripcion", ""),
                "extended_props": ev_mem.get("extended_props", {}),
                "calendar_id": cal_target,
                "sync_status": "SUCCESS",
                "sync_state": sync_state_to_apply if sync_state_to_apply else ev_mem.get("sync_state"),
                "pending_sync": 0 # arbitration accepting means it came from google
            }
            
            for k, v in data_to_apply.items():
                if k in updated:
                    updated[k] = v

            self.mutation_plan.append({
                "event_id": eid,
                "calendar_id_original": cal_target,
                "calendar_id_target": cal_target,
                "data": updated,
                "operation": "UPDATE",
                "is_reassign": False
            })

        self._updated_grupo = grupo.copy()

        self._post_commit_traces.append((
            self.grupo_id, "GROUP_ARBITRATION_PLAN_BUILT",
            {
                "operation_id": self.operation_id,
                "members_count": len(self.mutation_plan),
                "data_applied": data_to_apply
            },
            None, "GROUP_TX"
        ))

        return self

    # ── 4. EXECUTE MUTATION (dentro de una transacción ya abierta) ───────────────

    def execute_mutation_phase(self, conn) -> "GroupOperationContext":
        """
        Escribe TODOS los miembros y el grupo dentro de la transacción abierta.
        PRE: conn ya tiene BEGIN IMMEDIATE (vía db.group_transaction()).
        POST: No hace COMMIT — el caller (group_transaction) lo hace.
        PROHIBIDO: enqueue_sync, log_trace, llamadas externas.
        """
        from utils import _now_iso

        now = _now_iso()
        cursor = conn.cursor()

        for plan_item in self.mutation_plan:
            eid        = plan_item["event_id"]
            data       = plan_item["data"]
            cal_target = plan_item["calendar_id_target"]
            cal_orig   = plan_item.get("calendar_id_original")

            # Leer versión actual dentro de la transacción
            cursor.execute(
                "SELECT id, version FROM eventos WHERE (id = ? OR google_event_id = ?) AND calendar_id = ? LIMIT 1",
                (eid, eid, cal_orig),
            )
            row = cursor.fetchone()
            if not row:
                self._post_commit_traces.append((
                    eid, "GROUP_MUTATION_MEMBER_SKIPPED",
                    {"reason": "not_found_in_tx", "calendar_id": cal_orig},
                    None, "GROUP_TX"
                ))
                continue

            actual_id, current_version = row
            new_version = (current_version or 0) + 1

            ext_serialized = (
                json.dumps(data["extended_props"])
                if isinstance(data["extended_props"], dict)
                else data["extended_props"]
            )

            cursor.execute(
                """
                UPDATE eventos
                SET tecnico_nombre = ?, summary = ?, inicio = ?, fin = ?,
                    ubicacion = ?, descripcion = ?, extended_props = ?,
                    calendar_id = ?, version = ?, updated_at = ?,
                    pending_sync = ?, sync_status = ?, sync_state = ?
                WHERE id = ? AND calendar_id = ?
                """,
                (
                    data["tecnico_nombre"],
                    data["summary"],
                    data["inicio"],
                    data["fin"],
                    data["ubicacion"],
                    data["descripcion"],
                    ext_serialized,
                    cal_target,
                    new_version,
                    now,
                    data["pending_sync"],
                    data["sync_status"],
                    data.get("sync_state"),
                    actual_id,
                    cal_orig
                ),
            )

        # Actualizar tabla grupos dentro de la MISMA transacción
        ug = self._updated_grupo
        cursor.execute(
            """
            INSERT OR REPLACE INTO grupos
                (grupo_id, ot_nro, fecha, event_ids, tecnico_nombres, patrones, vehiculo, group_version)
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                COALESCE((SELECT group_version FROM grupos WHERE grupo_id = ?), 0) + 1
            )
            """,
            (
                ug["grupo_id"],
                ug.get("ot_nro"),
                ug.get("fecha"),
                json.dumps(ug.get("event_ids", [])),
                json.dumps(ug.get("tecnico_nombres", [])),
                json.dumps(ug.get("patrones", [])),
                ug.get("vehiculo"),
                ug["grupo_id"],
            ),
        )

        self._post_commit_traces.append((
            self.grupo_id, "GROUP_MUTATION_COMMIT",
            {
                "operation_id":   self.operation_id,
                "members_written": len(self.mutation_plan),
            },
            None, "GROUP_TX"
        ))

        return self

    # ── 5. POST-COMMIT EFFECTS ───────────────────────────────────────────────────

    def execute_post_commit_phase(self, db) -> "GroupOperationContext":
        """
        Ejecuta todos los side effects después del COMMIT.
        Orden: sync jobs → traces → journal.
        """
        self._post_commit_traces.append((
            self.grupo_id, "GROUP_POST_COMMIT_START",
            {
                "operation_id": self.operation_id,
                "sync_jobs":    len(self.deferred_sync_jobs),
                "traces":       len(self._post_commit_traces),
            },
            None, "GROUP_TX"
        ))

        # 1. Enqueue sync jobs
        for job in self.deferred_sync_jobs:
            try:
                db.enqueue_sync(
                    job["event_id"],
                    job["calendar_id"],
                    job["tecnico"],
                    job["operation"],
                    origin=job["origin"],
                    original_calendar_id=job["original_calendar_id"],
                )
            except Exception as e:
                self._post_commit_traces.append((
                    job["event_id"], "GROUP_ENQUEUE_FAILED",
                    {"error": str(e), "operation": job["operation"]},
                    None, "GROUP_TX"
                ))

        # 2. Flush traces
        for trace_args in self._post_commit_traces:
            try:
                event_id, step, detail, calendar_id, tag = trace_args
                db.log_trace(event_id, step, detail, calendar_id=calendar_id, tag=tag)
            except Exception:
                pass  # Traces nunca deben romper el flujo

        # 3. Journal entry
        try:
            db.write_group_journal(
                operation_id=self.operation_id,
                operation_type=self.operation_type,
                grupo_id=self.grupo_id,
                initiated_by=self.initiated_by,
                started_at=self.started_at,
                expected_members=len(self.mutation_plan),
                status="COMPLETED",
                detail=json.dumps({
                    "new_title":       self._new_group_title,
                    "is_reassignment": self._is_reassignment,
                    "reassignment_id": self._reassignment_id,
                }),
            )
        except Exception:
            pass

        db.log_trace(
            self.grupo_id, "GROUP_POST_COMMIT_DONE",
            {"operation_id": self.operation_id},
            tag="GROUP_TX"
        )
        
        # [HEARTBEAT] Notificar al frontend que hubo mutación
        db.bump_mutation_time()

        return self

    # ── 6. SNAPSHOT RESPONSE ─────────────────────────────────────────────────────

    def to_snapshot_response(self, db) -> dict:
        """
        Serializa el estado post-mutación del grupo para la respuesta HTTP.
        Incluye group_snapshot con miembros actualizados para que el frontend
        pueda parchear su estado local sin necesidad de un full refresh.
        """
        grupo = db.obtener_grupo(self.grupo_id)
        members = []
        if grupo:
            for eid in grupo.get("event_ids", []):
                ev = db.resolve_event(eid)
                if ev:
                    members.append({
                        "id":             ev.get("id"),
                        "google_event_id": ev.get("google_event_id"),
                        "tecnico_nombre": ev.get("tecnico_nombre"),
                        "calendar_id":    ev.get("calendar_id"),
                        "inicio":         ev.get("inicio"),
                        "fin":            ev.get("fin"),
                        "summary":        ev.get("summary"),
                        "sync_status":    ev.get("sync_status"),
                        "version":        ev.get("version"),
                    })

        return {
            "success":        True,
            "status":         "ok",
            "moved":          len(self.mutation_plan),
            "correlation_id": self.operation_id,
            "group_snapshot": {
                "grupo_id":      self.grupo_id,
                "members":       members,
                "group_version": grupo.get("group_version", 0) if grupo else 0,
            },
        }

    # ── Rollback (restaurar members_before si algo falló post-commit) ────────────

    def rollback(self, db) -> None:
        """
        Intenta restaurar el estado pre-mutación.
        Solo se invoca en casos excepcionales donde el commit ocurrió pero
        un side effect crítico falló y se necesita deshacer.
        """
        from utils import _now_iso
        now = _now_iso()
        for ev in self.members_before:
            try:
                db.actualizar_evento_individual(
                    ev["id"], ev.get("calendar_id", ""),
                    {
                        "tecnico_nombre": ev.get("tecnico_nombre"),
                        "summary":        ev.get("summary"),
                        "inicio":         ev.get("inicio"),
                        "fin":            ev.get("fin"),
                        "extended_props": ev.get("extended_props"),
                        "calendar_id":    ev.get("calendar_id"),
                        "sync_status":    "PENDING",
                        "pending_sync":   1,
                    },
                    origin="group_rollback",
                )
            except Exception:
                pass
        db.log_trace(
            self.grupo_id, "GROUP_MUTATION_ROLLBACK",
            {"operation_id": self.operation_id, "members_restored": len(self.members_before)},
            tag="GROUP_TX"
        )

    # ── Helpers privados ─────────────────────────────────────────────────────────

    def _resolve_member(self, eid: str) -> Optional[dict]:
        """Busca un miembro ya cargado en members_before por su id o google_event_id."""
        for m in self.members_before:
            if m["id"] == eid or m.get("google_event_id") == eid:
                return m
        return None

    def _calc_fechas(
        self,
        nueva_fecha: Optional[str],
        start_orig: str,
        end_orig: str,
        params,
        tz_suffix: str,
    ) -> tuple[str, str]:
        """Calcula inicio/fin final para un miembro dado los parámetros del move."""
        nueva_f = datetime.date.fromisoformat(nueva_fecha) if nueva_fecha else None

        if params.h_start is not None and nueva_f:
            dur = params.h_dur
            if dur is None:
                try:
                    dt_s = datetime.datetime.fromisoformat(start_orig.replace("Z", "+00:00"))
                    dt_e = datetime.datetime.fromisoformat(end_orig.replace("Z", "+00:00"))
                    dur  = (dt_e - dt_s).total_seconds() / 3600.0
                except Exception:
                    dur = 1.0
            dt_base  = datetime.datetime.combine(nueva_f, datetime.time(0, 0))
            dt_s_new = dt_base + datetime.timedelta(hours=params.h_start)
            dt_e_new = dt_base + datetime.timedelta(hours=params.h_start + dur)
            return (
                dt_s_new.strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}"),
                dt_e_new.strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}"),
            )

        if "T" in start_orig and nueva_f:
            try:
                dt_s  = datetime.datetime.fromisoformat(start_orig.replace("Z", "+00:00"))
                dt_e  = datetime.datetime.fromisoformat(end_orig.replace("Z", "+00:00"))
                delta = (nueva_f - dt_s.date()).days
                return (
                    (dt_s + datetime.timedelta(days=delta)).strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}"),
                    (dt_e + datetime.timedelta(days=delta)).strftime(f"%Y-%m-%dT%H:%M:%S{tz_suffix}"),
                )
            except Exception:
                pass

        if nueva_f:
            return nueva_f.isoformat(), (nueva_f + datetime.timedelta(days=1)).isoformat()

        return start_orig, end_orig
