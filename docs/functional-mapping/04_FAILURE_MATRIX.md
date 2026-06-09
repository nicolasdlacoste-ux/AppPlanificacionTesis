# Fase D — Failure Matrix

> Fallos **observados o deducibles** del código y tests/scratch. No lista bugs hipotéticos sin anclaje.

---

## Matriz principal

| Failure | Síntoma visible | Root cause conocida | Componentes | Detección | Severidad | Estado |
|---------|-----------------|---------------------|-------------|-----------|-----------|--------|
| **REASSIGNMENT_JUMP** | Evento vuelve al técnico/calendario original tras refresh | Poll aplica diff antes de completar worker; alias/`resolve_event` usa id viejo; falta `base_version` en UI | `sync_manager`, `poll_manager`, `app.js`, `data_manager` | Visual jump; `[REASSIGN_TRACE:*]` logs | **crítica** | mitigado (Move Correlation buffer eliminado, ruteo inbound auto-aplica reassignment o bloquea) |
| **GROUP_REASSIGN_404** | Toast error al arrastrar grupo a otro técnico | Frontend llama `PATCH .../reasignar_tecnico_grupo` — **endpoint no definido** en `api_server.py` | `app.js`, `right-panel.js` | HTTP 404; Network tab | **crítica** | **pendiente** |
| **CREATE_INSERT_NOOP** | Eventos nuevos quedan `local_*`, nunca aparecen en Google | `crear_evento` encola `INSERT`; `sync_manager` solo maneja `CREATE`/`UPDATE`/`DELETE`/`REMOTE_REASSIGNMENT` | `api_server`, `sync_manager` | `events_without_google_id` drift; cola atascada | **crítica** | **pendiente** |
| **ARBITRATION_LOOKUP_MISS** | Accept review → HTTP 422 SQLITE_MUTATION_FAILED | `review.event_id` no resuelve en SQLite (google_id vs local_id, calendar mismatch) | `data_manager.accept_review`, `resolve_event` | HTTP 422; `SQLITE_LOOKUP_MISS` trace | **alta** | mitigado (fail-fast 422) |
| **POLLING_REOPEN** | Mismo conflicto reaparece en badge tras resolver | Review `PENDING` con `resolved_at` no nulo; dedup incompleto en `enqueue_review` | `poll_manager`, `poll_review_queue` | `reopened_reviews` en drift report | **alta** | intermitente |
| **DUPLICATE_GOOGLE_ID** | Dos tarjetas mismo evento / updates erráticos | Reassignment + poll CREATE; retry 404→insert sin dedup local | `sync_manager`, `data_manager` | `duplicate_events` drift | **alta** | intermitente |
| **METADATA_WIPE** | OTs/patrones desaparecen del panel | Merge inbound legacy; diff JSON completo antes de ownership | `poll_manager` (pre-ownership paths) | `assert_metadata_integrity` logs | **alta** | mitigado (ownership) |
| **STALE_GROUP_TITLE** | Un miembro con tag `- ND/LR` distinto al resto | `update_group_title` no ejecutado o UPDATE sync falló para un miembro | `update_group_title`, `sync_queue` | Inspección visual; sync FAILED logs | **media** | intermitente |
| **ORPHAN_GROUP_ID** | Metadata con `grupo_id` pero sin fila en `grupos` | Crash entre `actualizar_evento` y `crear_o_actualizar_grupo`; split parcial | `data_manager`, split | `orphan_events` drift | **media** | pendiente |
| **GROUP_DELETE_ORDER** | Títulos sin limpiar / UPDATE sobre evento borrado | `eliminar_grupo_completo` borra SQLite antes de intentar `resolve_event` + UPDATE | `api_server` eliminar_grupo | Logs error; miembro restante con tag | **media** | pendiente |
| **SPLIT_DRIFT** | Días faltantes o duplicados post-split | Loop split + DELETE async; grupo día no creado si un CREATE falla | `split`, `sync_manager` | Conteo días vs Google | **alta** | intermitente |
| **MULTIDAY_CORRUPTION** | Edición mueve solo un día o bloquea todo | `_is_complex_event` detecta multidía; usuario no split | `api_server`, UI warning | HTTP 400 o warning panel | **media** | mitigado (bloqueo) |
| **REASSIGNMENT_LOOP** | Cola REASSIGN_PENDING repetida | Worker falla CREATE; retry sin limpiar flags | `sync_manager`, cola | `REASSIGN_REMOTE_CREATE_FAILED`; queue FAILED | **alta** | intermitente |
| **GOOGLE_OWNERSHIP_CONFLICT** | Cambio en Google UI reaparece como review eterno | Campo SHARED_CRITICAL cambiado en app Google nativa | `poll_manager`, ownership | Review queue FIELD_CHANGE | **media** | esperado (by design) |
| **POLLING_LAG** | Cambios en Google tardan >12 min | Worker detenido; checklist falló; intervalo largo | `poll_manager` | `polling_lag` drift | **media** | operacional |
| **SYNC_CLOUD_STALE** | Refresh masivo pisa cambios locales recientes | `GET /api/sync` upsert sin merge arbitration | `sync_cloud`, extractor | Drift tras sync manual | **alta** | legacy / pendiente |
| **FALSE_200_ACCEPT** (histórico) | Accept OK pero SQLite sin cambio | `actualizar_evento_individual` retornaba None silencioso | `accept_review` | Ya no: ahora 422 | **alta** | **resuelto** |
| **BATCH_PARTIAL_REASSIGN** | Algunos miembros del batch en técnico viejo | `batch_editar` no reformula grupos; solo encola por evento | `batch_editar` | Inspección grupo tras batch | **alta** | pendiente |
| **FRONTEND_OPTIMISTIC_DRIFT** | UI muestra técnico X, refresh muestra Y | Optimistic update no revertido si API OK pero sync lento | `app.js` | Tras `refreshEvents` | **media** | esperado corto plazo |
| **LEGACY_RESOLVE_REVIEW** | Review marcado RESOLVED sin cambio datos | `PATCH poll/review_queue/.../resolve` solo UPDATE status | `api_server` legacy endpoint | Estado DB vs Google | **media** | legacy |
| **ALIAS_CALENDAR_MISMATCH** | Técnico mal asignado | `target_cal` resuelto por nombre/correo ambiguo en `obtener_tecnicos` | `mover_evento`, config alias | Trace REASSIGN target_cal | **media** | intermitente |
| **CANCELLED_VISIBLE** | Evento cancelado sigue en planner | Accept REMOTE_DELETE soft; no purge UI filter | `data_manager`, scheduler | `cancelled_visible` drift | **baja** | mitigado |

---

## Detalle por categoría (prioridad documentada)

### Reassignment

```
Trigger: correo_destino ≠ calendar_id en mover / batch
Failure chain:
  1. SQLite actualiza calendar_id antes de Google
  2. Poll lee evento viejo en calendario origen (si flag falla)
  3. UI optimista muestra destino; refresh lee origen
Mitigations presentes:
  - reassignment_in_progress → poll IGNORE
  - REMOTE_REASSIGNMENT DELETE+INSERT atómico en worker
Gaps:
  - Grupo drag usa endpoint inexistente
  - actualizar_event_id_en_grupos puede no cubrir todos los alias
```

### Polling / arbitration

```
Trigger: cambio externo en Google
Failures:
  - REOPEN: mismo diff re-encolado
  - LOOKUP_MISS: accept no encuentra fila
  - SAFE_APPLY overwrite si clasificación errónea
Detect:
  - /api/review/pending count
  - /api/admin/drift_report
  - poll_log FIELD_OWNERSHIP / REVIEW_REQUIRED
```

### Group lifecycle

```
Failures:
  - ORPHAN grupo_id
  - STALE_TITLE miembro desincronizado
  - DELETE_ORDER en eliminar_grupo_completo
Detect:
  - GET /api/grupos/evento/{id} vs metadata
  - visual: iniciales inconsistentes
```

### Sync queue

```
Failures:
  - INSERT no procesado
  - FAILED permanente 403/400
  - DUPLICATE en 404→insert path
Detect:
  - GET /api/sync/status
  - sync_log TO_GOOGLE ERROR
  - admin/sync_queue
```

### Metadata

```
Failures:
  - Wipe app_ots (histórico JSON diff)
  - Patrones vacíos tras accept parcial
Detect:
  - METADATA_INTEGRITY logs post-accept
  - right-panel muestra OT vacía
```

---

## Severidad y acción recomendada (solo documentación)

| Severidad | Criterio | Ejemplos |
|-----------|----------|----------|
| crítica | Pérdida de datos o operación rota en flujo principal | GROUP_REASSIGN_404, CREATE_INSERT_NOOP |
| alta | Drift persistente o requiere intervención manual | LOOKUP_MISS, SPLIT_DRIFT, DUPLICATE |
| media | Inconsistencia visual o recuperable con refresh/sync | STALE_TITLE, OPTIMISTIC_DRIFT |
| baja | Cosmético o filtrable | CANCELLED_VISIBLE |

---

## Estado actual — leyenda

| Estado | Significado |
|--------|-------------|
| **resuelto** | Fix verificado en código actual |
| **mitigado** | Guard parcial; puede reaparecer en edge cases |
| **pendiente** | Sin fix conocido en código auditado |
| **intermitente** | Depende de timing/red/operador |
| **legacy** | Ruta antigua aún expuesta |
| **esperado** | Comportamiento por diseño (conflictos humanos) |

---

## Correlación con tests/scratch

| Failure | Artefacto en repo |
|---------|------------------|
| LOOKUP_MISS | `scratch/test_field_ownership.py`, accept 422 en `api_server` |
| Drift indicators | `sync_observatory.py`, `scratch/drift_validation.py` |
| Polling | `tests/test_polling.py`, `scratch/trigger_poll.py` |
| Reassignment | logs `[REASSIGN_TRACE:*]` en api/sync/poll |
| Operational matrix | `tests/test_operational_matrix.py` |

---

*Matriz viva: actualizar cuando se corrijan endpoints o operaciones de cola.*
