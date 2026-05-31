"""
sync_manager.py — Worker de sincronización hacia Google Calendar (Fase 2)

Responsabilidades:
  - Procesar la sync_queue: enviar CREATEs, UPDATEs y DELETEs a Google Calendar.
  - Retry con backoff exponencial ante errores transitorios.
  - Anti-loop: marcar eventos con source='internal' en extendedProperties.
  - Loggear todas las operaciones en sync_log.

NO hace polling desde Google (eso es Fase 3).
"""

import datetime
import json
import threading
import time
import traceback

import googleapiclient.errors

# ─── Constantes ───────────────────────────────────────────────
QUEUE_POLL_SECONDS = 30   # cada cuántos segundos procesa la cola


from utils import _now_iso

def _exponential_backoff(attempts: int) -> datetime.datetime:
    """Calcula el próximo intento: 30s → 2min → 8min → 32min"""
    delay_seconds = 30 * (4 ** attempts)
    return datetime.datetime.now() + datetime.timedelta(seconds=delay_seconds)


# ─── Mapeadores ───────────────────────────────────────────────

def map_evento_to_google(event: dict) -> dict:
    """
    Transforma un evento de la DB interna al formato de Google Calendar API usando EventAdapter.
    """
    from utils import EventAdapter, _now_iso
    
    # 1. Asegurar que el evento esté en formato canónico antes de convertir
    # (DataManager puede devolver aliases, el adapter los resuelve)
    can = EventAdapter.normalize_event(event)
    
    # [EVENT_ADAPTER] Trace logs
    print(f"\n[EVENT_ADAPTER] Outbound Mapping for {can.get('id')}:")
    print(f"  - Source Dialect: SQLite/Internal")
    print(f"  - Target Dialect: Google Calendar API")
    
    # 2. Convertir a Google usando el adapter centralizado
    body = EventAdapter.canonical_to_google(can)
    
    # Trace del payload final para Google
    print("\n[GOOGLE_CREATE_PAYLOAD_TRACE] === PAYLOAD FINAL GOOGLE ===")
    print(json.dumps(body, indent=2))
    
    return body

# ─── SyncWorker ───────────────────────────────────────────────

class SyncWorker:
    """
    Worker de sincronización. Se instancia una sola vez en api_server.py
    y corre en un hilo daemon en background.

    Uso:
        worker = SyncWorker(db=data_manager_instance, extractor_module=extractor)
        worker.start()
    """

    def __init__(self, db, extractor_module):
        self.db        = db
        self.extractor = extractor_module
        self._stop     = threading.Event()
        self._active_locks = set()  # Proteccion: evitar doble proceso del mismo event_id
        self._lock_mutex   = threading.Lock()
        self._thread   = threading.Thread(
            target=self._loop,
            name="SyncQueueWorker",
            daemon=True
        )

    def start(self):
        """Arranca el hilo worker en background."""
        self._thread.start()
        print("[SyncWorker] Iniciado. Procesando cola cada "
              f"{QUEUE_POLL_SECONDS}s.")

    def stop(self):
        self._stop.set()

    # ── Loop principal ─────────────────────────────────────────

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.process_queue()
            except Exception:
                # Error inesperado en el worker: loggearlo y seguir
                print(f"[SyncWorker] Error inesperado:\n{traceback.format_exc()}")
            time.sleep(QUEUE_POLL_SECONDS)

    # ── Procesamiento de la cola ───────────────────────────────
    
    def _log(self, event_type, detail=None, event_id=None, calendar_id=None, tag=None):
        """Helper para logging estructurado [SYNC_WORKER] y [OUTBOUND_MUTATION]."""
        from utils import _poll_log
        if tag is None:
            tag = "SYNC_WORKER"
            if event_type in ("google_update_success", "permanent_failure", "retry_scheduled"):
                tag = "OUTBOUND_MUTATION"
                # Mapear nombres a los solicitados por el usuario
                if event_type == "google_update_success": event_type = "mutation_synced"
                elif event_type == "permanent_failure": event_type = "mutation_failed"
        
        _poll_log(self.db, tag, event_type, detail or {}, 
                 calendar_id=calendar_id, event_id=event_id)

    def process_queue(self):
        """
        Lee hasta 20 ítems PENDING de sync_queue y los procesa.
        """
        items = self.db.get_pending_queue_items(limit=20)
        if not items:
            return

        self._log("sync_started", {"items_count": len(items)})

        # Obtener servicio de Google Calendar (reusa token existente)
        try:
            svc_cal, _ = self.extractor._safe_get_google_services()
        except Exception as e:
            self._log("service_error", {"error": str(e)})
            return

        for item in items:
            event_id = item["event_id"]
            
            # Protección: evitar procesar si ya está bloqueado por este mismo hilo (reentrancia rara)
            # o por otro ciclo solapado.
            with self._lock_mutex:
                if event_id in self._active_locks:
                    continue
                self._active_locks.add(event_id)
            
            try:
                self._process_item(item, svc_cal)
            finally:
                with self._lock_mutex:
                    self._active_locks.discard(event_id)

        self._log("sync_completed")

    def _process_item(self, item: dict, svc_cal):
        """Procesa un único ítem de la cola."""
        queue_id   = item["queue_id"]
        event_id   = item["event_id"]
        calendar_id = item["calendar_id"]
        tecnico    = item["tecnico"]
        operation  = item["operation"]   # CREATE | UPDATE | DELETE
        attempts   = item["attempts"]
        original_calendar_id = item.get("original_calendar_id")
        mutation_context = item.get("mutation_context")

        self.db.update_queue_status(queue_id, "PROCESSING")
        self.db.update_evento_sync_status(event_id, tecnico, "PROCESSING")
        
        # [SYNC_MOVE_CONTEXT] move_context_consumed
        if mutation_context:
            try:
                ctx = json.loads(mutation_context)
                self._log("move_context_consumed", {
                    "original_calendar": ctx.get("original_calendar"),
                    "target_calendar": ctx.get("target_calendar"),
                    "origin": ctx.get("origin")
                }, event_id=event_id, calendar_id=calendar_id, tag="SYNC_MOVE_CONTEXT")
            except:
                pass

        self._log("item_processing", {"operation": operation}, event_id=event_id, calendar_id=calendar_id)

        try:
            if operation == "DELETE":
                self._do_delete(svc_cal, event_id, calendar_id, queue_id, tecnico)

            else:  # CREATE o UPDATE
                # Leer el evento actualizado de la DB
                event = self._get_event_from_db(event_id, tecnico)

                if event is None:
                    # Evento ya no existe en DB (fue borrado antes de procesarse)
                    self.db.update_queue_status(queue_id, "DONE")
                    self.db.write_sync_log(event_id, tecnico, "TO_GOOGLE",
                                           operation, "OK", "evento eliminado antes de sync")
                    return

                # Reconciliación Formal: Soft Delete State check
                sync_state = "ACTIVE"
                try:
                    ext = json.loads(event.get("extended_props") or "{}")
                    sync_state = ext.get("private", {}).get("sync_state", "ACTIVE")
                except:
                    pass
                
                if sync_state == "CANCELLED_IN_GOOGLE":
                    self.db.update_queue_status(queue_id, "DONE")
                    self.db.write_sync_log(event_id, tecnico, "TO_GOOGLE",
                                           operation, "IGNORED", "soft deleted (CANCELLED_IN_GOOGLE)")
                    self._log("sync_ignored", {"reason": "CANCELLED_IN_GOOGLE"}, event_id=event_id, calendar_id=calendar_id)
                    return

                if operation in ("CREATE", "INSERT"):
                    if operation == "INSERT":
                        self._log("deprecated_operation", {"normalized_to": "CREATE"}, event_id=event_id, calendar_id=calendar_id)
                    self._do_create(svc_cal, event, calendar_id, queue_id, tecnico)
                elif operation == "UPDATE":
                    self._do_update(svc_cal, event, calendar_id, queue_id, tecnico, original_calendar_id=original_calendar_id)
                elif operation == "REMOTE_REASSIGNMENT":
                    self._do_remote_reassignment(svc_cal, event, calendar_id, queue_id, tecnico, original_calendar_id)
                else:
                    self.db.fail_queue_item(queue_id, f"Operación desconocida: {operation}")
                    self._log("permanent_failure", {"error": f"unknown operation {operation}"}, event_id=event_id, calendar_id=calendar_id)

        except googleapiclient.errors.HttpError as http_err:
            status_code = http_err.status_code if hasattr(http_err, "status_code") else 0
            # 429 = Rate Limit, 500/503 = server errors → retry
            if status_code in (429, 500, 503) or status_code == 0:
                self._schedule_retry(queue_id, attempts, str(http_err))
                self._log("retry_scheduled", {"attempt": attempts + 1, "error": str(http_err)}, 
                         event_id=event_id, calendar_id=calendar_id)
            else:
                # 400/403/404 → error permanente, no reintentar
                self.db.fail_queue_item(queue_id, str(http_err))
                # Actualizar evento con error detallado
                final_status = "REASSIGN_REMOTE_CREATE_FAILED" if operation == "REMOTE_REASSIGNMENT" else "FAILED"
                with self.db._get_connection() as conn:
                    conn.execute("""
                        UPDATE eventos 
                        SET sync_status=?, pending_sync=0, sync_error=?, last_sync_attempt=?
                        WHERE id=? AND tecnico_nombre=?
                    """, (final_status, str(http_err), _now_iso(), event_id, tecnico))
                    conn.commit()
                
                self.db.write_sync_log(event_id, tecnico, "TO_GOOGLE",
                                       operation, "ERROR", str(http_err))
                self._log("permanent_failure", {"error": str(http_err), "status_code": status_code}, 
                         event_id=event_id, calendar_id=calendar_id)
                print(f"[SyncWorker] Error HTTP {status_code} en {operation} "
                      f"evento={event_id}: {http_err}")

        except Exception as e:
            err_str = str(e)
            new_attempts = attempts + 1
            if new_attempts >= item["max_attempts"]:
                self.db.fail_queue_item(queue_id, err_str)
                final_status = "REASSIGN_REMOTE_CREATE_FAILED" if operation == "REMOTE_REASSIGNMENT" else "FAILED"
                with self.db._get_connection() as conn:
                    conn.execute("""
                        UPDATE eventos 
                        SET sync_status=?, pending_sync=0, sync_error=?, last_sync_attempt=?
                        WHERE id=? AND tecnico_nombre=?
                    """, (final_status, err_str, _now_iso(), event_id, tecnico))
                    conn.commit()
                self.db.write_sync_log(event_id, tecnico, "TO_GOOGLE",
                                       operation, "ERROR", err_str)
                self._log("permanent_failure", {"error": err_str, "reason": "max_attempts"}, 
                         event_id=event_id, calendar_id=calendar_id)
            else:
                self._schedule_retry(queue_id, attempts, err_str)
                self._log("retry_scheduled", {"attempt": new_attempts, "error": err_str}, 
                         event_id=event_id, calendar_id=calendar_id)

    # ── Operaciones individuales ───────────────────────────────

    def _do_create(self, svc_cal, event: dict, calendar_id: str,
                   queue_id: str, tecnico: str):
        """Inserta el evento en Google Calendar."""
        body = map_evento_to_google(event)
        original_id = event["id"]
        self._log("TRACE_EVENT_FLOW", {"step": "SYNC_DO_CREATE_BODY", "body": body}, event_id=original_id, calendar_id=calendar_id)
        
        google_id = None
        # Determinar si es un ID local (ej: local_uuid) o un ID real de Google
        is_local = not original_id or original_id.startswith("local_")

        if is_local:
            # Forzar CREATE sin eventId para que Google lo asigne
            result = svc_cal.events().insert(calendarId=calendar_id, body=body).execute()
            google_id = result.get("id")
            operation = "CREATE"
            self._log("TRACE_EVENT_FLOW", {"step": "SYNC_DO_CREATE_RESPONSE", "response": result}, event_id=original_id, calendar_id=calendar_id)
        else:
            # Intentar UPDATE sobre el ID existente
            try:
                result = svc_cal.events().update(
                    calendarId=calendar_id,
                    eventId=original_id,
                    body=body
                ).execute()
                google_id = original_id
                operation = "UPDATE"
            except googleapiclient.errors.HttpError as e:
                if e.status_code == 404:
                    # No existe en Google, crear de nuevo y capturar nuevo ID
                    result = svc_cal.events().insert(calendarId=calendar_id, body=body).execute()
                    google_id = result.get("id")
                    operation = "CREATE"
                else:
                    raise

        now = _now_iso()
        # Actualizar evento: SUCCESS y limpiar flags.
        # IMPORTANTE: Preservamos el id local original, solo guardamos el google_event_id.
        with self.db._get_connection() as conn:
            conn.execute("""
                UPDATE eventos 
                SET google_event_id = ?, sync_status='SUCCESS', 
                    pending_sync=0, last_synced_at=?, updated_at=?, sync_error=NULL, last_sync_attempt=?
                WHERE id=? AND tecnico_nombre=?
            """, (google_id or original_id, now, now, now, original_id, tecnico))
            conn.commit()

        # Actualizar id del evento en cualquier grupo localmente si cambió
        if google_id:
            self.db.actualizar_event_id_en_grupos(original_id, google_id)

        self.db.update_queue_status(queue_id, "DONE")
        self.db.write_sync_log(original_id, tecnico, "TO_GOOGLE", operation, "OK")
        self._log("google_update_success", {"operation": operation, "google_id": google_id}, 
                 event_id=original_id, calendar_id=calendar_id)
        self._log("anti_loop_metadata_applied", {"source": "internal", "origin": "sync_worker"}, 
                 event_id=original_id)



    def _do_update(self, svc_cal, event: dict, calendar_id: str, 
                   queue_id: str, tecnico: str, original_calendar_id: str = None):
        """Actualiza el evento en Google Calendar via patch o recreación por movimiento."""
        body = map_evento_to_google(event)
        original_id = event["id"] # ID local
        google_id   = event.get("google_event_id") or original_id # ID para Google
        
        self._log("TRACE_EVENT_FLOW", {"step": "SYNC_DO_UPDATE_BODY", "body": body}, event_id=original_id, calendar_id=calendar_id)
        
        res = None
        moving = original_calendar_id and original_calendar_id != calendar_id
        
        if moving:
            self._log("move_detected", {
                "from": original_calendar_id,
                "to": calendar_id,
                "event_id": original_id,
                "google_id": google_id
            }, event_id=original_id, calendar_id=calendar_id, tag="LOGICAL_MOVE")
            
            # 1. Intentar borrar del calendario original usando el google_id
            try:
                svc_cal.events().delete(calendarId=original_calendar_id, eventId=google_id).execute()
                self._log("logical_identity_preserved", {"action": "delete_original"}, 
                         event_id=original_id, calendar_id=original_calendar_id, tag="LOGICAL_MOVE")
            except googleapiclient.errors.HttpError as e:
                if e.status_code == 404:
                    self._log("IDENTITY_MISMATCH_ON_MOVE", {"detail": "Evento no encontrado en origen durante movimiento."}, 
                             event_id=original_id, calendar_id=original_calendar_id, tag="LOGICAL_MOVE")
                else:
                    self._log("move_warning", {"detail": f"Error borrando original: {e}"}, 
                             event_id=original_id, calendar_id=original_calendar_id)
            except Exception as e:
                self._log("move_warning", {"detail": f"Error inesperado borrando original: {e}"}, 
                         event_id=original_id, calendar_id=original_calendar_id)
            
            # 2. Insertar en el nuevo calendario
            res = svc_cal.events().insert(calendarId=calendar_id, body=body).execute()
            self._log("google_recreate_required", {"status": "inserted_new"}, 
                     event_id=original_id, calendar_id=calendar_id, tag="LOGICAL_MOVE")
        else:
            try:
                res = svc_cal.events().patch(
                    calendarId=calendar_id,
                    eventId=google_id,
                    body=body
                ).execute()
                self._log("TRACE_EVENT_FLOW", {"step": "SYNC_DO_UPDATE_RESPONSE", "response": res}, event_id=original_id, calendar_id=calendar_id)
            except googleapiclient.errors.HttpError as e:
                if e.status_code == 404:
                    # El evento no existe en Google, crearlo
                    res = svc_cal.events().insert(calendarId=calendar_id, body=body).execute()
                elif e.status_code in (400, 403):
                    # Fallback: delete + insert
                    try:
                        svc_cal.events().delete(calendarId=calendar_id, eventId=google_id).execute()
                    except Exception: pass
                    res = svc_cal.events().insert(calendarId=calendar_id, body=body).execute()
                else:
                    raise

        new_google_id = res.get("id") if res else google_id
        now = _now_iso()
        
        # Actualizar evento: SUCCESS y limpiar flags.
        # IMPORTANTE: Preservamos el id local, solo actualizamos google_event_id.
        with self.db._get_connection() as conn:
            conn.execute("""
                UPDATE eventos 
                SET google_event_id = ?, sync_status='SUCCESS', 
                    pending_sync=0, last_synced_at=?, updated_at=?, sync_error=NULL, last_sync_attempt=?
                WHERE id=? AND tecnico_nombre=?
            """, (new_google_id, now, now, now, original_id, tecnico))
            conn.commit()

        self.db.update_queue_status(queue_id, "DONE")
        self.db.write_sync_log(original_id, tecnico, "TO_GOOGLE", "UPDATE", "OK")
        self._log("google_update_success", {"operation": "UPDATE_PATCH" if not moving else "UPDATE_MOVE", "google_id": new_google_id}, 
                 event_id=original_id, calendar_id=calendar_id)
        if moving:
            self._log("sync_completed", {"move": True}, event_id=original_id, calendar_id=calendar_id, tag="LOGICAL_MOVE")
        self._log("anti_loop_metadata_applied", {"source": "internal", "origin": "sync_worker"}, 
                 event_id=original_id)



    def _do_remote_reassignment(self, svc_cal, event: dict, calendar_id: str, queue_id: str, tecnico: str, original_calendar_id: str):
        """Ejecuta un movimiento cross-calendar explícito y controlado."""
        from utils import _now_iso
        import json
        import googleapiclient.errors
        
        original_id = event["id"]
        try:
            ext = json.loads(event.get("extended_props") or "{}")
            private_meta = ext.get("private", {})
        except Exception:
            private_meta = {}
            ext = {"private": {}}
            
        prev_google_id = private_meta.get("previous_google_event_id") or event.get("google_event_id") or original_id
        prev_cal_id = private_meta.get("previous_calendar_id") or original_calendar_id
        reassign_id = private_meta.get("reassignment_id", "UNKNOWN")
        
        print(f"[REASSIGN_TRACE:WORKER] INICIANDO REASSIGN local_id={original_id} reassign_id={reassign_id}")
        print(f"[REASSIGN_TRACE:WORKER] old_calendar_id={prev_cal_id}, new_calendar_id={calendar_id}, old_google_event_id={prev_google_id}")

        self._log("REMOTE_REASSIGNMENT", {"state": "REASSIGN_PENDING", "reassignment_id": reassign_id, "old_cal": prev_cal_id, "new_cal": calendar_id}, event_id=original_id)
        
        # 1. DELETE remoto
        try:
            print(f"[REASSIGN_TRACE:WORKER] DELETE REQUEST: calendarId={prev_cal_id}, eventId={prev_google_id}")
            svc_cal.events().delete(calendarId=prev_cal_id, eventId=prev_google_id).execute()
            print(f"[REASSIGN_TRACE:WORKER] DELETE RESPONSE: OK")
            self._log("REMOTE_REASSIGNMENT", {"state": "REASSIGN_REMOTE_DELETE_OK", "reassignment_id": reassign_id}, event_id=original_id)
        except googleapiclient.errors.HttpError as e:
            print(f"[REASSIGN_TRACE:WORKER] DELETE RESPONSE: FAILED status_code={e.status_code}")
            if e.status_code == 404:
                self._log("REMOTE_REASSIGNMENT", {"state": "REASSIGN_REMOTE_DELETE_SKIPPED", "reason": "Not found in old calendar"}, event_id=original_id)
            else:
                raise

        # 2. CREATE remoto
        body = map_evento_to_google(event)
        try:
            print(f"[REASSIGN_TRACE:WORKER] CREATE REQUEST: calendarId={calendar_id}, body={body}")
            res = svc_cal.events().insert(calendarId=calendar_id, body=body).execute()
            new_google_id = res["id"]
            print(f"[REASSIGN_TRACE:WORKER] CREATE RESPONSE: OK, new_google_id={new_google_id}")
            self._log("REMOTE_REASSIGNMENT", {"state": "REASSIGN_REMOTE_CREATE_OK", "new_google_id": new_google_id, "reassignment_id": reassign_id}, event_id=original_id)
        except googleapiclient.errors.HttpError as e:
            print(f"[REASSIGN_TRACE:WORKER] CREATE RESPONSE: FAILED error={str(e)}")
            self._log("REMOTE_REASSIGNMENT_FAILURE", {
                "reassignment_id": reassign_id,
                "old_calendar_id": prev_cal_id,
                "old_google_event_id": prev_google_id,
                "failure_reason": str(e)
            }, event_id=original_id)
            raise e

        # 3. Actualizar Identity Mapping Local (OBLIGATORIO usar el lifecycle)
        # Limpiar flag de en progreso
        if "reassignment_in_progress" in private_meta:
            del private_meta["reassignment_in_progress"]
            
        # Preparar data
        update_data = {
            "tecnico": tecnico,
            "evento": event.get("summary", ""),
            "inicio": event.get("inicio", ""),
            "fin": event.get("fin", ""),
            "ubicacion": event.get("ubicacion", ""),
            "descripcion": event.get("descripcion", ""),
            "extendedProperties": ext,
            "calendar_id": calendar_id,
            "sync_status": "REASSIGN_COMPLETED",
            "pending_sync": 0,
            "google_event_id": new_google_id
        }
        
        print(f"[REASSIGN_TRACE:IDENTITY] Mapeando: old_google_id={prev_google_id} -> new_google_id={new_google_id}")
        
        # Enviar a data manager para cumplir el lifecycle (version++, updated_at)
        self.db.actualizar_evento_individual(
            original_id, 
            calendar_id, 
            update_data, 
            base_version=event.get("version"),
            origin="sync_reassignment"
        )

        # Actualizar id del evento en cualquier grupo localmente tras reasignación
        if prev_google_id and new_google_id:
            self.db.actualizar_event_id_en_grupos(prev_google_id, new_google_id)
        
        self.db.update_queue_status(queue_id, "DONE")
        self.db.write_sync_log(original_id, tecnico, "TO_GOOGLE", "REMOTE_REASSIGNMENT", "OK", f"Reassigned: {new_google_id}")
        self._log("anti_loop_metadata_applied", {"source": "internal", "origin": "sync_worker"}, event_id=original_id)


    def _do_delete(self, svc_cal, event_id: str, calendar_id: str,
                   queue_id: str, tecnico: str):
        """Elimina el evento en Google Calendar."""
        # event_id ya es el google_event_id real (encolado por quitar_tecnico).
        # Solo hacemos fallback a DB si parece un local_id.
        google_id = event_id
        if event_id.startswith("local_"):
            try:
                with self.db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT google_event_id FROM eventos WHERE id = ?", (event_id,))
                    row = cursor.fetchone()
                    if row and row[0]:
                        google_id = row[0]
            except Exception as e:
                print(f"[SyncWorker] Advertencia: No se pudo obtener google_event_id para borrar {event_id}: {e}")

        print(f"[DELETE_TRACE] Borrando en Google: calendarId={calendar_id} eventId={google_id}")
        try:
            svc_cal.events().delete(
                calendarId=calendar_id,
                eventId=google_id
            ).execute()
        except googleapiclient.errors.HttpError as e:
            if e.status_code == 404:
                # Ya no existe en Google, dar por eliminado
                pass
            elif e.status_code == 410:
                # Gone — ya fue borrado
                pass
            else:
                raise

        self.db.update_queue_status(queue_id, "DONE")
        self.db.write_sync_log(event_id, tecnico, "TO_GOOGLE", "DELETE", "OK")
        
        # [OUTBOUND_MUTATION] mutation_synced -> Borrado físico final en SQLite
        # Buscar por id O por google_event_id para cubrir ambos casos
        with self.db._lock:
            with self.db._get_connection() as conn:
                conn.execute("DELETE FROM eventos WHERE id = ? OR google_event_id = ?", (event_id, event_id))
                conn.commit()

        self._log("google_update_success", {"operation": "DELETE", "final_cleanup": "physical_delete"}, 
                 event_id=event_id, calendar_id=calendar_id)


    # ── Helpers ────────────────────────────────────────────────

    def _get_event_from_db(self, event_id: str, tecnico: str) -> dict | None:
        """Lee un evento de la DB usando resolve_event para mayor robustez."""
        try:
            # resolve_event ya busca por id o google_event_id y retorna el dict correcto
            match = self.db.resolve_event(event_id)
            
            if match:
                # Validar que pertenezca al técnico (opcional pero recomendado)
                if match.get("tecnico") == tecnico or match.get("calendar_id") == tecnico:
                    return match
            return None
        except Exception as e:
            print(f"[SyncWorker] Error leyendo evento {event_id} de DB: {e}")
            return None


    def _schedule_retry(self, queue_id: str, current_attempts: int, error_msg: str):
        """Programa el próximo reintento con backoff exponencial."""
        next_try = _exponential_backoff(current_attempts)
        self.db.update_queue_retry(
            queue_id,
            next_try.isoformat(),
            current_attempts + 1,
            error_msg
        )
