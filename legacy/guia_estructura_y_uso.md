# Guía de Estructura y Uso: App Planificación Akrimet

Este documento describe la arquitectura técnica del software y el flujo de trabajo para la gestión de agendas detallando los componentes clave del sistema.

---

## 1. Estructura de Archivos y Componentes

El proyecto se organiza en tres módulos principales de Python y archivos de soporte para datos y credenciales:

### Módulos de Código
- **[app.py](file:///c:/Users/ndiaz_akrimet/Git%20Proyect/AppPlanificacion/app.py):** Punto de entrada principal. Gestiona el menú de navegación y la vista de **Planificación Semanal**. Se encarga de la visualización de la grilla de técnicos y el cálculo de métricas de ocupación.
- **[programar_ots.py](file:///c:/Users/ndiaz_akrimet/Git%20Proyect/AppPlanificacion/programar_ots.py):** Motor de lógica para la asignación de Órdenes de Trabajo (OTs). Contiene el asistente (wizard) de programación y los algoritmos de búsqueda de disponibilidad.
- **[extractor.py](file:///c:/Users/ndiaz_akrimet/Git%20Proyect/AppPlanificacion/extractor.py):** Capa de integración con Google Cloud. Maneja las peticiones a Google Sheets (para obtener técnicos y OTs) y a Google Calendar (para leer y escribir eventos).

### Archivos de Datos y Configuración
- **`credentials.json`:** Archivo de configuración descargado de Google Cloud Console (ID de cliente OAuth).
- **`token.json`:** Autenticación persistente del usuario (generado automáticamente tras el primer inicio de sesión).
- **`datos_cache.json`:** Caché local de todos los eventos de calendario de todos los técnicos.
- **`bd_ots_cache.json`:** Copia local de la base de datos de OTs de Google Sheets para consultas rápidas.
- **`tecnicos_cache.json`:** Lista de técnicos con sus correos e iniciales.
- **`requirements.txt`:** Lista de librerías necesarias (`pandas`, `google-api-python-client`, etc.).

---

## 2. Flujo de Datos

El sistema minimiza las latencias de la red mediante un sistema de caché local:

1.  **Sincronización:** Al presionar "Sincronizar Cloud", `extractor.py` descarga los eventos y la base de datos de OTs, guardándolos en los archivos `.json` locales.
2.  **Carga:** La aplicación lee estos archivos JSON al iniciar o al cambiar de vista, permitiendo una interfaz fluida.
3.  **Escritura:** Solo cuando se confirma una programación de OT, el sistema escribe directamente en Google Calendar.

---

## 3. Guía de Uso Paso a Paso

### Paso 1: Sincronización Inicial
Al abrir el programa, lo primero es verificar si los datos están actualizados.
- En el menú principal o en la barra superior, haz clic en **"Sincronizar Cloud  ⟳"**.
- Esto actualizará la agenda de todos los técnicos (+90 días a futuro) y la base de datos de OTs pendientes.

### Paso 2: Planificación Semanal (Vista de Grilla)
- Accede a **"Planificación Semanal"**.
- Puedes navegar entre semanas con los botones de flechas o volver a hoy.
- **Métricas:** En la parte inferior verás la ocupación total y la ocupación específica de OTs para la semana y el mes.
- **Detalle de OT:** Al hacer clic en un bloque de OT en la grilla, aparecerá un **popup** con el desglose de "Trabajo a ejecutar", "Puntos de calibración" y cantidad de partidas asociadas.

### Paso 3: Programación de Nuevas OTs
Este es el flujo principal para asignar trabajo:
1.  **Selección:** En la lista de OTs, selecciona las que deseas programar. El sistema te obligará a que todas pertenezcan al **mismo cliente**.
2.  **Parámetros:** Define cuántas jornadas requiere el trabajo, cuántos técnicos asignar, si requiere viaje y añade una descripción breve.
3.  **Búsqueda:** Haz clic en **"Buscar Disponibilidad"**. Aparecerán dos columnas:
    - **Opciones Estrictas:** Huecos 100% libres en el calendario.
    - **Opciones Flexibles:** Ignora bloqueos que no sean OTs (como trámites o reuniones internas), marcándolos con un icono de advertencia `⚠️`.
4.  **Confirmación:** Elige la mejor opción y confirma. El sistema creará automáticamente los eventos en los calendarios de Google de los técnicos seleccionados.

---

## 4. Referencia de Estructuras para Cambios Futuros

> [!TIP]
> Si deseas modificar la lógica de negocio, ten en cuenta estos puntos:

- **Estructura de OTs:** Si cambias las columnas en el Excel de Google Sheets, deberás actualizar las constantes `IDX_...` al inicio de `programar_ots.py`.
- **Cálculo de Ocupación:** La lógica reside en el método `calcular_metricas` dentro de `app.py`. Actualmente considera una jornada de 9 horas (07:00 a 16:00).
- **Colores de la Grilla:** Se gestionan en el método `dibujar_grilla` en `app.py`. Puedes ajustar los códigos HEX para cambiar la estética.
- **Algoritmo de Búsqueda:** La función central es `_buscar_disponibilidad` en `programar_ots.py`.

---

> [!IMPORTANT]
> **Seguridad de Archivos:** Nunca borres `credentials.json` a menos que necesites cambiar la App de Google Cloud. Si borras `token.json`, el programa simplemente te pedirá loguearte de nuevo en el navegador.
