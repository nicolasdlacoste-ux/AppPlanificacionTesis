# Functional System Mapping — Akrimet Planner

Documentación funcional y operacional generada por **auditoría read-only** del código (sin modificaciones de lógica).

## Documentos

| # | Archivo | Contenido |
|---|---------|-----------|
| A | [01_OPERATIONAL_INVENTORY.md](./01_OPERATIONAL_INVENTORY.md) | Inventario de operaciones, estado, riesgo, componentes, side effects |
| B | [02_FLOW_MAPPING.md](./02_FLOW_MAPPING.md) | Entry points, sequence flows, ownership, convergencia |
| C | [03_INVARIANT_REGISTRY.md](./03_INVARIANT_REGISTRY.md) | Reglas que no deben romperse + estado de validación |
| D | [04_FAILURE_MATRIX.md](./04_FAILURE_MATRIX.md) | Fallos conocidos, síntomas, root cause, severidad |
| E | [05_FUNCTIONAL_OBSERVATORY_SPEC.md](./05_FUNCTIONAL_OBSERVATORY_SPEC.md) | Spec del observatorio funcional (no implementado) |

## Prioridad de lectura (áreas de mayor riesgo)

1. Reassignment — `02` §1, `04` REASSIGNMENT_JUMP, GROUP_REASSIGN_404
2. Group lifecycle — `02` §2, invariantes G1–G4
3. Sync / polling / arbitration — `02` §4, invariantes S/A
4. Metadata lineage — `03` M1–M3, `field_ownership.py`
5. Delete lifecycle — `02` §2b, `04` GROUP_DELETE_ORDER
6. Drag & drop — `02` §6
7. Individualize / split — `02` §2d

## Hallazgos críticos (resumen)

- **`reasignar_tecnico_grupo`**: el frontend lo invoca; no existe en la API → drag de grupo entre técnicos falla con 404.
- **`INSERT` en sync_queue**: `crear_evento` encola operación no procesada por `sync_manager` (espera `CREATE`).
- **Reassignment**: pipeline DELETE+INSERT con protección poll por `reassignment_in_progress`; riesgo residual de jump/drift.

## Alcance de la auditoría

- Backend: `api_server.py`, `data_manager.py`, `sync_manager.py`, `poll_manager.py`, `field_ownership.py`, `sync_observatory.py`, `utils.py`
- Frontend: `webapp/app.js`, `scheduler.js`, `right-panel.js`, `poll.js`
- Excluido: scripts `scripts_mantenimiento/`, patches sueltos en raíz (no son runtime principal)

## Mantenimiento

Actualizar estos documentos cuando cambien contratos de API, operaciones de cola, o reglas de ownership. No sustituyen `project_architecture.md` (visión técnica histórica).
