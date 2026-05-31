# Roadmap — Akrimet Planner v2.0

## ✅ Implementado (v2.0)
- Arquitectura híbrida Python/FastAPI + Interfaz Web
- Sincronización en dos niveles: carga rápida local (SQLite) + sync en segundo plano (Google)
- Gestión de Grupos de Trabajo: creación, desasignación e integridad de títulos con iniciales
- Integración del Backlog con la lógica de grupos al programar OTs
- Tarjeta de Salida: generación de reporte imprimible por grupo
- Compilación a ejecutable independiente (.exe) con PyInstaller
- Smart Wait: el lanzador espera activamente a que el servidor esté listo
- Logging de errores a `error_log.txt` en modo compilado

## 🔄 En Proceso (Sprint Actual)
- [x] **Lock en SQLite**: `threading.Lock` en `DataManager` para evitar errores de concurrencia
- [x] **Rollback en grupos**: transacción atómica con rollback en `quitar_tecnico`
- [x] **Token auto-refresh**: manejo de `google.auth.exceptions.TransportError` en `extractor.py`
- [x] **Confirmación en desasignación**: `confirm()` antes de quitar técnico desde el panel
- [x] **Identidad de usuario**: chip en el header que muestra el email y las iniciales de la cuenta Google autenticada
- [x] **Logout**: endpoint `POST /api/auth/logout` que elimina `token.json` y limpia el caché del perfil
- [x] **Caché de perfil**: guardado en SQLite (`metadatos`) para carga instantánea sin round-trip a Google

---

## 🗓️ Próxima Versión (v2.1)

### UX/UI
- [ ] **Ícono personalizado para el .exe**: agregar `--icon=icono.ico` al `build_exe.py`
- [ ] **Splash screen de carga**: página intermedia mientras el servidor desempaqueta (~5-10s)
- [ ] **Indicador visual de sync en curso**: ícono girando en el footer durante background sync

### Configuración (confirmado por usuario)
- [ ] **Menú de Configuración**: panel que lista todos los calendarios de Google Workspace donde el usuario tiene permisos de edición (`accessRole = writer|owner`). El usuario selecciona cuáles se muestran como técnicos en el planificador.
  - OTs y Patrones **siguen viviendo en Google Sheets** (sin cambios)
  - Solo la **lista de técnicos** migra de Sheets a Calendar
  - Endpoint futuro: `GET /api/auth/calendars`
  - Config guardada en SQLite: `metadatos['calendarios_seleccionados']`
- [ ] **Variables de entorno para IDs de Spreadsheet**: mover los `SPREADSHEET_ID` hardcodeados en `extractor.py` a un `config.json` externo

---

## 📋 Backlog (Versiones Futuras)

### Mantenibilidad
- [ ] **Modularizar `api_server.py`**: extraer endpoints de grupos a `routers/grupos.py` usando `APIRouter` de FastAPI (actualmente 1.286 líneas)
- [ ] **Logging estructurado**: reemplazar `print()` dispersos por `logging.Logger` configurable con niveles DEBUG/INFO/ERROR

### Funcionalidades
- [ ] **Historial de cambios por OT**: registrar en SQLite cada vez que se crea, mueve o elimina un evento de una OT
- [ ] **Búsqueda de disponibilidad multi-OT**: buscar el próximo slot libre para varias OTs simultáneamente
- [ ] **Notificaciones de conflicto en tiempo real**: alertar al usuario si otro técnico programa algo que genera conflicto de patrón mientras la app está abierta
- [ ] **Panel de reportes**: vista semanal/mensual de ocupación por técnico exportable a PDF

### Infraestructura
- [ ] **Modo servidor**: opción para desplegar en red local y que múltiples usuarios (planificadores) accedan simultáneamente desde sus propios navegadores
- [ ] **Backup automático de la DB**: copia diaria de `planificacion.db` a una carpeta configurable

---

> [!NOTE]  
> Este documento se mantiene actualizado manualmente. Las fechas de versión son orientativas y dependen de la prioridad del negocio.
