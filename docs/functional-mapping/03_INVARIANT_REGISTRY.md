# Fase C — Invariant Registry

> Reglas que el sistema **intenta** mantener. La columna **Estado** indica si hay validación efectiva hoy.

**Estado de validación:** `SQL` · `API` · `frontend` · `runtime` · `ownership` · `no validado` · `parcial`

---

## Resumen

| Invariant | Riesgo si se rompe | Operaciones afectadas | Estado validación |
|-----------|-------------------|----------------------|-------------------|
| [G1] GROUP_MIN_MEMBERS | orphan metadata, títulos incorrectos | delete, quitar, individualize, reassignment | parcial (API) |
| [G2] GROUP_MOVE_ATOMIC_DATE | miembros en fechas distintas | mover_grupo, drag grupo | API |
| [G3] NO_FECHA_TECNICO_GRUPO | 400 / toast error | drag grupo, mover_grupo | API + frontend |
| [S1] GOOGLE_ID_UNIQUENESS | duplicate rows, wrong updates | sync, poll, reassignment | SQL (drift report) |
| [S2] SYNC_NO_DUPLICATE_CREATE | eventos duplicados en Google | retry CREATE, 404→insert | runtime (worker) |
| [S3] REASSIGN_SINGLE_IDENTITY | jump técnico, lookup miss | reassignment, poll | parcial (flags) |
| [M1] METADATA_NEVER_NULL_WIPE | pérdida OT/patrones | poll, accept, update | ownership + parcial |
| [M2] PLANNER_OWNED_NO_INBOUND_OVERWRITE | drift silencioso | polling | ownership |
| [A1] ACCEPT_MUTATES_SQLITE | false convergence | accept review | API + fail-fast |
| [A2] REJECT_NO_SQLITE_MUTATION | pérdida cambios locales | reject review | API |
| [A3] REVIEW_IDEMPOTENCY | double apply | accept/reject | API |
| [A4] RESOLVED_REVIEW_NO_REOPEN | review fantasmas | polling enqueue | parcial |
| [U1] COMPLEX_EVENT_BLOCKED | corrupción multidía | move, delete, agregar | API |
| [U2] OPTIMISTIC_VERSION | lost updates | mover, batch | API |
| [Q1] QUEUE_OP_CANONICAL | eventos nunca en Google | crear_evento | **no validado** |

---

## Grupo (GROUP)

### G1 — GROUP_MIN_MEMBERS

| Atributo | Valor |
|----------|-------|
| **Descripción** | Un `grupo_id` activo debe tener ≥2 `event_ids` o el grupo debe eliminarse y los títulos deben perder el tag de iniciales. |
| **Componentes** | `data_manager` grupos, `quitar_tecnico`, `individualizar`, `mover_evento` post-hooks |
| **Operaciones** | quitar técnico, delete, individualize, reassignment (sale del grupo) |
| **Validación** | API: lógica `len(remaining) <= 1 → eliminar_grupo` en varios endpoints |
| **Riesgo** | `orphan_events` en drift report: metadata `grupo_id` sin fila en `grupos` |
| **Estado** | parcial |

### G2 — GROUP_MOVE_ATOMIC_DATE

| Atributo | Valor |
|----------|-------|
| **Descripción** | Al mover un grupo, todos los miembros reciben el mismo delta de fecha (mismo `nueva_fecha` aplicado por miembro). |
| **Componentes** | `mover_grupo` loop |
| **Operaciones** | mover_grupo, drag fecha en grupo |
| **Validación** | API loop |
| **Riesgo** | split drift: miembros en distintos días tras error parcial |
| **Estado** | API |

### G3 — NO_FECHA_TECNICO_GRUPO_SIMULTANEO

| Atributo | Valor |
|----------|-------|
| **Descripción** | No se puede cambiar fecha y técnico en la misma operación sobre un evento agrupado. |
| **Componentes** | `mover_grupo`, `app.js moveEvent` |
| **Validación** | HTTP 400 servidor; toast cliente |
| **Riesgo** | Estados divergentes entre calendarios si se forzara la API |
| **Estado** | API + frontend |

### G4 — GROUP_TITLE_TAG_CONSISTENCY

| Atributo | Valor |
|----------|-------|
| **Descripción** | Todos los miembros de un grupo comparten el mismo `summary` con sufijo `- INI1/INI2`. |
| **Componentes** | `update_group_title`, `format_group_summary` |
| **Operaciones** | agregar técnico, quitar, auto-agrupar |
| **Validación** | runtime al llamar `update_group_title` (no transaccional global) |
| **Riesgo** | stale titles si sync falla en un miembro |
| **Estado** | parcial |

---

## Sync (S)

### S1 — GOOGLE_ID_UNIQUENESS

| Atributo | Valor |
|----------|-------|
| **Descripción** | Como máximo una fila `eventos` por `google_event_id` real (excluyendo `local_*`). |
| **Validación** | `sync_observatory` indicador `duplicate_events` |
| **Riesgo** | Updates aplicados a fila equivocada; arbitration lookup miss |
| **Estado** | SQL (detección, no prevención) |

### S2 — SYNC_RETRY_NO_DUPLICATE

| Atributo | Valor |
|----------|-------|
| **Descripción** | Reintentos UPDATE/CREATE no deben dejar dos eventos visibles para la misma intención lógica. |
| **Componentes** | `sync_manager._do_create` (404 → insert una vez) |
| **Validación** | runtime |
| **Riesgo** | duplicated sync en Google |
| **Estado** | parcial |

### S3 — REASSIGN_SINGLE_IDENTITY

| Atributo | Valor |
|----------|-------|
| **Descripción** | Durante reassignment existe exactamente un evento remoto activo: viejo borrado, nuevo creado; local mapea `previous_google_event_id` → nuevo id. |
| **Componentes** | `_do_remote_reassignment`, `actualizar_event_id_en_grupos` |
| **Validación** | flags `reassignment_in_progress`; poll ignore |
| **Riesgo** | REASSIGNMENT_JUMP, evento vuelve al técnico anterior |
| **Estado** | parcial |

### S4 — OUTBOUND_BEFORE_INBOUND_WIN

| Atributo | Valor |
|----------|-------|
| **Descripción** | Si `pending_sync=1` o `local_updated` más reciente, polling no debe aplicar cambios críticos sin review. |
| **Validación** | timestamp compare `g_updated <= local_updated` → NO_OP_STALE |
| **Riesgo** | overwrite de mutación local en curso |
| **Estado** | runtime (parcial: no considera pending_sync explícitamente) |

### S5 — INTERNAL_SOURCE_ANTI_LOOP

| Atributo | Valor |
|----------|-------|
| **Descripción** | Eventos escritos por el worker con metadata `source=internal` no deben re-entrar como conflictos. |
| **Validación** | `_is_internal_change` en poll |
| **Estado** | runtime |

---

## Metadata (M)

### M1 — APP_OTS_PRESERVED

| Atributo | Valor |
|----------|-------|
| **Descripción** | `app_ots` / `app_ot` en `extendedProperties.private` no deben borrarse por merge inbound ni accept parcial. |
| **Validación** | `FieldOwnership.PLANNER_OWNED`; `assert_metadata_integrity` post-accept |
| **Riesgo** | metadata wipe, OT invisible en planner |
| **Estado** | ownership + parcial |

### M2 — APP_PATRONES_VEHICULO_PRESERVED

| Atributo | Valor |
|----------|-------|
| **Descripción** | `app_patrones`, `app_vehiculo` solo cambian por mutación Planner o accept explícito. |
| **Validación** | ownership registry |
| **Estado** | ownership |

### M3 — LINEAGE_KEYS_NO_NULL_OVERWRITE

| Atributo | Valor |
|----------|-------|
| **Descripción** | Claves de lineage (`version`, `sync_origin`, `reassignment_id`, etc.) no se sobrescriben con null desde Google. |
| **Validación** | classify_extended_props_diff filtra planner_owned |
| **Estado** | ownership |

### M4 — GRUPO_ID_STABLE_IN_GROUP_OPS

| Atributo | Valor |
|----------|-------|
| **Descripción** | Operaciones de grupo preservan `grupo_id` en metadata de cada miembro durante `mover_grupo`. |
| **Validación** | `mover_grupo` asigna `metadata["grupo_id"]` |
| **Estado** | API |

---

## Arbitration (A)

### A1 — ACCEPT_MUTATES_SQLITE

| Atributo | Valor |
|----------|-------|
| **Descripción** | `accept_review` debe producir cambio persistido o HTTP 422 (no false-200). |
| **Validación** | `new_ver is None` → ValueError → 422 |
| **Estado** | API |

### A2 — REJECT_PRESERVES_LOCAL

| Atributo | Valor |
|----------|-------|
| **Descripción** | `reject_review` no aplica snapshot remoto a SQLite; encola resync outbound. |
| **Validación** | código `reject_review` |
| **Estado** | API |

### A3 — REVIEW_SINGLE_RESOLUTION

| Atributo | Valor |
|----------|-------|
| **Descripción** | Un review en estado distinto de `PENDING` no puede accept/reject de nuevo. |
| **Validación** | API ValueError |
| **Estado** | API |

### A4 — NO_REOPEN_RESOLVED_REVIEWS

| Atributo | Valor |
|----------|-------|
| **Descripción** | Polling no debe recrear review PENDING para el mismo cambio ya resuelto. |
| **Validación** | `enqueue_review` debería deduplicar — indicador `reopened_reviews` en observatory |
| **Riesgo** | polling reopen, fatiga operador |
| **Estado** | parcial |

### A5 — REMOTE_DELETE_ACCEPT_CANCELS_LOCAL

| Atributo | Valor |
|----------|-------|
| **Descripción** | Accept de `REMOTE_DELETE` marca `CANCELLED_IN_GOOGLE` sin borrar fila inmediatamente (soft). |
| **Validación** | accept_review branch |
| **Estado** | API |

---

## UI (U)

### U1 — COMPLEX_EVENT_EDIT_BLOCKED

| Atributo | Valor |
|----------|-------|
| **Descripción** | Eventos multidía o con `has_guests=true` no son editables/movibles hasta individualizar (split). |
| **Validación** | `_is_complex_event` → HTTP 400 |
| **Estado** | API |

### U2 — OPTIMISTIC_LOCK_VERSION

| Atributo | Valor |
|----------|-------|
| **Descripción** | Si `base_version` < versión DB, rechazar con 409. |
| **Validación** | `mover_evento`, `mover_grupo` |
| **Estado** | API (frontend no siempre envía `base_version`) |

### U3 — DRAG_GROUP_SCOPE

| Atributo | Valor |
|----------|-------|
| **Descripción** | Drag en evento con grupo aplica mutación a todos los `event_ids` en optimista. |
| **Validación** | frontend solo |
| **Riesgo** | UI muestra grupo movido pero API falló (endpoint missing) |
| **Estado** | frontend |

---

## Cola y operaciones (Q)

### Q1 — QUEUE_OPERATION_CANONICAL

| Atributo | Valor |
|----------|-------|
| **Descripción** | Toda entrada en `sync_queue.operation` debe ser ∈ {`CREATE`,`UPDATE`,`DELETE`,`REMOTE_REASSIGNMENT`}. |
| **Violación observada** | `crear_evento` usa `INSERT` |
| **Validación** | **no validado** |
| **Riesgo** | eventos permanecen `local_*` / PENDING forever |
| **Estado** | no validado |

### Q2 — SQLITE_GOOGLE_PARITY_AFTER_SUCCESS

| Atributo | Valor |
|----------|-------|
| **Descripción** | Tras `sync_status=SUCCESS`, campos mapeados por `map_evento_to_google` son equivalentes en Google. |
| **Validación** | no validado automáticamente (drift manual) |
| **Estado** | no validado |

---

## Identidad (I)

### I1 — RESOLVE_EVENT_ALIASES

| Atributo | Valor |
|----------|-------|
| **Descripción** | `resolve_event(id)` resuelve `id`, `google_event_id`, y aliases legacy. |
| **Validación** | runtime + LOOKUP_MISS logs |
| **Riesgo** | arbitration 422, reassignment jump |
| **Estado** | runtime |

### I2 — REVIEW_EVENT_ID_MATCHES_SQLITE

| Atributo | Valor |
|----------|-------|
| **Descripción** | `poll_review_queue.event_id` debe ser resoluble vía `resolve_event` al accept. |
| **Riesgo** | lookup miss en accept |
| **Estado** | parcial |

---

## Matriz operación → invariantes

| Operación | Invariantes críticos |
|-----------|---------------------|
| Reassignment | S3, S1, G1, M1, I1, S5 |
| mover_grupo | G2, G3, G4, M4 |
| Split | G1, S2, U1 |
| Polling | M2, A4, S4, S5, M1 |
| Accept review | A1, M1, I2 |
| Reject review | A2, S2 |
| Crear evento | Q1, S2 |
| Delete grupo | G1, S2 (orden ejecución) |

---

*Los invariantes con estado `ownership` se enforced en `poll_manager` vía `FieldOwnershipRegistry`, no en sync outbound.*
