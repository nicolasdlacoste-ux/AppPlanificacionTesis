# Fase A — Operational Inventory

> **Modo:** auditoría read-only del código actual (mayo 2026).  
> **Propósito:** inventario de operaciones funcionales reales, no comportamiento ideal.

## Leyenda

| Columna | Valores |
|---------|---------|
| **Estado** | `estable` · `parcial` · `frágil` · `legacy` · `desconocido` |
| **Riesgo** | `bajo` · `medio` · `alto` · `crítico` |
| **Tipo** | `local_only` · `sync_outbound` · `sync_inbound` · `distributed` · `arbitration` · `group_operation` |

---

## Resumen ejecutivo (prioridad alta)

| Operación | Estado | Riesgo | Tipo | Componentes principales |
|-----------|--------|--------|------|-------------------------|
| Reasignar técnico (move + cambio calendario) | parcial | **crítico** | distributed | `app.js`, `scheduler.js`, `api_server.mover_evento`, `data_manager`, `sync_manager._do_remote_reassignment`, `poll_manager` |
| Mover grupo (fecha) | estable | medio | group_operation + sync_outbound | `mover_grupo`, `data_manager`, `sync_manager` |
| Reasignar técnico en grupo (drag) | **frágil** | **crítico** | distributed | `app.js` → endpoint **`reasignar_tecnico_grupo` inexistente** |
| Polling / reconciliación inbound | parcial | alto | sync_inbound + arbitration | `poll_manager`, `field_ownership`, `data_manager.enqueue_review` |
| Accept / Reject review | parcial | alto | arbitration | `poll.js`, `data_manager.accept_review/reject_review` |
| Split / individualizar multidía | parcial | alto | distributed + group_operation | `split`, `individualizar`, múltiples CREATE+DELETE |
| Delete / quitar técnico | parcial | alto | distributed | `quitar_tecnico`, `eliminar_evento` (alias), `sync_manager._do_delete` |
| Crear evento | parcial | **alto** | sync_outbound | `crear_evento` encola op **`INSERT`** (no manejada por worker) |
| Sync cloud (carga masiva) | legacy | medio | sync_inbound | `sync_cloud`, `extractor` |
| Batch editar | parcial | alto | distributed | `batch_editar`, expansión de grupos |

---

## Inventario completo

### 1. Carga y lectura (sin mutación remota directa)

| Operación | Estado | Riesgo | Tipo | Componentes | Side effects conocidos |
|-----------|--------|--------|------|-------------|------------------------|
| Boot / refresh datos | estable | bajo | local_only | `app.js`, `api_server` GETs | Pobla `_eventos`, `_tecnicos`, OTs, patrones; `Scheduler.render` |
| GET `/api/eventos` | estable | bajo | local_only | `data_manager.obtener_eventos_dict` | Normalización vía `EventAdapter` en respuesta |
| GET `/api/ots/pendientes` | estable | bajo | local_only | `extractor`, Sheets | Cache en memoria frontend |
| Engine buscar slot | estable | bajo | local_only | `engine.py`, `api_server` | No persiste |
| Tarjeta de salida | estable | bajo | local_only | `right-panel`, `grupos/tarjeta_salida` | Solo lectura por fecha |
| Heartbeat / auth | estable | bajo | local_only | `api_server`, `launcher` | Watchdog cierre servidor |
| Dashboard ocupación | estable | bajo | local_only | `api_server`, `indicadores` | Ocupación consolidada por técnico/servicio |
| Trace cliente | parcial | bajo | local_only | `POST /api/trace` | Logs en DB vía `log_trace` |

### 2. Creación y duplicación

| Operación | Estado | Riesgo | Tipo | Componentes | Side effects conocidos |
|-----------|--------|--------|------|-------------|------------------------|
| Crear evento | parcial | **alto** | sync_outbound | `right-panel`, `crear_evento` | SQLite `local_*`; `_auto_agrupar_evento`; **`enqueue_sync(..., "INSERT")`** — worker solo entiende `CREATE` |
| Crear desde backlog / quick create | parcial | alto | sync_outbound | `backlog.js`, `right-panel` | Igual pipeline que crear |
| Duplicar evento | parcial | medio | sync_outbound | `POST duplicar` | Clon local + cola sync |
| Registrar grupo manual | parcial | medio | group_operation | `POST grupos/registrar` | Tabla `grupos` + metadata `grupo_id` |

### 3. Movimiento y reasignación (prioridad 1)

| Operación | Estado | Riesgo | Tipo | Componentes | Side effects conocidos |
|-----------|--------|--------|------|-------------|------------------------|
| Mover evento individual (fecha/hora/metadata) | parcial | alto | distributed | `PATCH mover` → si hay grupo redirige a `mover_grupo` | Recalcula título si OT; propaga vehículo/patrones al grupo; optimistic UI |
| Reasignar técnico (mismo endpoint `mover`) | parcial | **crítico** | distributed | `mover_evento` detecta `is_reassignment` | Flags `reassignment_in_progress`, `REASSIGN_PENDING`, cola `REMOTE_REASSIGNMENT`; reformula/disuelve grupo |
| Mover grupo (solo fecha) | estable | medio | group_operation | `mover_grupo` | Itera miembros; `UPDATE` en cola; `_auto_agrupar_evento` post-move |
| Reasignar técnico grupo (drag) | **frágil** | **crítico** | distributed | `app.js` → `PATCH .../reasignar_tecnico_grupo` | **404 — endpoint no existe en API** |
| Batch editar (delta días / técnico) | parcial | alto | distributed | `batch/editar` | Expande grupos; múltiples `REMOTE_REASSIGNMENT` posibles |
| Drag & drop scheduler | parcial | alto | distributed | `scheduler.js` → `App.moveEvent` | Optimistic update; bloqueo `_globalSyncing` |
| Editar en panel (save) | parcial | alto | distributed | `right-panel.saveEventEdit` | `mover` / `mover_grupo` / metadata batch |

### 4. Ciclo de vida de grupo (prioridad 2)

| Operación | Estado | Riesgo | Tipo | Componentes | Side effects conocidos |
|-----------|--------|--------|------|-------------|------------------------|
| Agregar técnico al grupo | parcial | alto | group_operation | `agregar_tecnico` | Nuevo `local_*`; reformula títulos; `update_group_title` |
| Quitar técnico / delete individual | parcial | alto | distributed | `quitar_tecnico`, `DELETE eventos` (alias) | DELETE Google; disuelve grupo si ≤1 miembro; limpia tag iniciales |
| Eliminar grupo completo | parcial | alto | group_operation | `DELETE grupos/{id}` | DELETE por miembro; **código post-delete intenta UPDATE sobre eventos ya borrados** (orden defectuoso) |
| Individualizar (salir del grupo) | parcial | medio | group_operation | `individualizar` | Limpia título OT base; reformula o disuelve grupo |
| Split multidía | parcial | **alto** | distributed | `split` | N×CREATE por día; DELETE originales; grupos día a día; disuelve grupo original |
| Auto-agrupar por OT/fecha | parcial | medio | group_operation | `_auto_agrupar_evento` | Fusiona eventos misma OT; `update_group_title` |
| Update group title | parcial | medio | group_operation | `update_group_title` | Sincroniza summary con iniciales en todos los calendarios del grupo |

### 5. Metadata y OTs

| Operación | Estado | Riesgo | Tipo | Componentes | Side effects conocidos |
|-----------|--------|--------|------|-------------|------------------------|
| Add / remove OT (panel) | parcial | medio | sync_outbound | `right-panel` PATCH campos | `app_ots`, título, descripción enriquecida |
| Add / remove patrón | parcial | medio | sync_outbound | idem | `app_patrones` JSON |
| Add vehículo | parcial | medio | sync_outbound | idem + propagación grupo en `mover` | `app_vehiculo`; `generar_descripcion_enriquecida` |
| Batch OT partidas | estable | bajo | local_only | `ots/batch/partidas` | Lectura Sheets |
| Hidratación OT (create/move) | parcial | medio | local_only | `hydration_service`, `hydrator` | Rellena patrones/vehículo desde repo OT |

### 6. Sync outbound (prioridad 3)

| Operación | Estado | Riesgo | Tipo | Componentes | Side effects conocidos |
|-----------|--------|--------|------|-------------|------------------------|
| Encolar sync | estable | medio | sync_outbound | `data_manager.enqueue_sync` | `sync_queue` PENDING |
| Sync worker procesar cola | parcial | alto | sync_outbound | `sync_manager` thread | CREATE/UPDATE/DELETE/REMOTE_REASSIGNMENT; retry exponencial |
| REMOTE_REASSIGNMENT | parcial | **crítico** | distributed | `_do_remote_reassignment` | DELETE calendario origen → INSERT destino → nuevo `google_event_id`; `actualizar_event_id_en_grupos` |
| GET sync status | estable | bajo | local_only | `/api/sync/status` | Métricas cola + logs |
| Sync cloud masivo | legacy | medio | sync_inbound | `GET /api/sync` | Descarga calendarios → SQLite; puede pisar estado local antiguo |

### 7. Polling y arbitraje (prioridad 3)

| Operación | Estado | Riesgo | Tipo | Componentes | Side effects conocidos |
|-----------|--------|--------|------|-------------|------------------------|
| Poll start/stop/trigger | parcial | medio | sync_inbound | `poll_manager`, `api_server` | Checklist pre-poll; ciclo por calendario |
| Procesar evento inbound | parcial | alto | sync_inbound | `_process_incoming_event` | Anti-loop `source=internal`; ownership filter |
| Implicit Group Creation | estable | medio | arbitration | `data_manager`, `google_event_id` | Agrupa eventos inbound automáticamente |
| Auto-apply SHARED_SAFE | parcial | medio | sync_inbound | `apply_poll_safe_changes` | SQLite sin review |
| Inbound Routing (AUTO/INBOX) | estable | alto | arbitration | `poll_routing_config` | Auto-aplica o encola según reglas | parcial | alto | arbitration | `enqueue_review` | `poll_review_queue` PENDING |
| Accept review | parcial | alto | arbitration | `accept_review` | Mutación SQLite; idempotencia status |
| Reject review | parcial | alto | arbitration | `reject_review` | Encola UPDATE/CREATE outbound |
| Defer review | estable | bajo | arbitration | `defer_review` | No muta evento |
| Legacy resolve review | legacy | medio | arbitration | `PATCH poll/review_queue/.../resolve` | Solo cambia status — **no aplicar diff** |
| Hydration en poll | parcial | medio | sync_inbound | `hydration_service` en poll | Merge incremental `extended_props` |

### 8. Restricciones y guards

| Operación | Estado | Riesgo | Tipo | Componentes | Side effects conocidos |
|-----------|--------|--------|------|-------------|------------------------|
| Bloqueo evento complejo | estable | medio | local_only | `_is_complex_event` | HTTP 400 en move/delete/agregar si multidía o `has_guests` |
| Optimistic lock (version) | parcial | medio | distributed | `base_version` en mover | HTTP 409 si versión DB > base |
| Anti-loop polling | estable | medio | sync_inbound | `_is_internal_change` | Ignora eventos con metadata internal |
| Race reassignment | parcial | alto | sync_inbound | `reassignment_in_progress` | Poll ignora evento hasta completar worker |

### 9. Admin / observabilidad

| Operación | Estado | Riesgo | Tipo | Componentes | Side effects conocidos |
|-----------|--------|--------|------|-------------|------------------------|
| Drift report | parcial | bajo | local_only | `sync_observatory.get_full_drift_report` | Solo lectura diagnóstico |
| Admin timeline | parcial | bajo | local_only | `get_event_timeline` | Agrega poll_log + sync_log |
| Admin HTML | legacy | bajo | local_only | `webapp/admin.html` | UI diagnóstico |

---

## Duplicación lógica detectada

| Área | Ubicaciones | Notas |
|------|-------------|-------|
| Mover vs mover_grupo | `mover_evento` redirige si hay grupo; lógica de disolución también en `mover` post-move | Dos caminos con reglas similares no idénticas |
| Delete | `eliminar_evento` → `quitar_tecnico` | Mismo pipeline |
| Normalización eventos | `utils.EventAdapter`, keys legacy `evento`/`summary`, `extendedProperties`/`extended_props` | Coexistencia canonical + legacy en DB y API |
| Resolución ID | `resolve_event`, `google_event_id`, `local_*` | Crítico en reassignment y arbitration |
| Operaciones cola | `CREATE` vs `INSERT` en enqueue | **Inconsistencia real** en `crear_evento` |

---

## Mapa de componentes por capa

```
UI:        app.js, scheduler.js, right-panel.js, backlog.js, poll.js, config.js
API:       api_server.py (monolito ~2876 líneas)
Persist:   data_manager.py, planificacion.db
Outbound:  sync_manager.py, sync_queue, extractor.py
Inbound:   poll_manager.py, polling_service.py (wrapper)
Ownership: field_ownership.py
Hydration: hydration_service.py, historical_hydrator.py
Obs:       sync_observatory.py, trace logs, poll_log, sync_log
```

---

## Clasificación global de riesgo operacional

| Nivel | Operaciones |
|-------|-------------|
| **Crítico** | Reasignación individual, drag grupo→`reasignar_tecnico_grupo`, CREATE con op INSERT, reassignment race con poll |
| **Alto** | Split, batch editar, accept review lookup miss, eliminar_grupo orden, polling reopen |
| **Medio** | Group move, agregar técnico, sync_cloud, títulos stale |
| **Bajo** | Lecturas, engine, config, defer review |

---

*Generado por auditoría estática del repositorio AppPlanificacion. No modifica código.*
