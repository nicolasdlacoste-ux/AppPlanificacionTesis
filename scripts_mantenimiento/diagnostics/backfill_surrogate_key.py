"""
backfill_surrogate_key.py
─────────────────────────
Script de ejecución única para migrar el sistema al modelo de Llave Sustituta.

Acciones:
  1. Marca como LEGACY los registros REMOTE_CREATE en poll_review_queue
     (ya no son relevantes bajo el nuevo modelo).
  2. Identifica eventos 'internal' en la tabla eventos que NO tienen
     tarea_id_local en sus extended_props.
  3. Para cada uno de esos eventos, encolá un UPDATE en sync_queue para
     que el SyncWorker les inyecte la llave sustituta en Google Calendar.

Uso:
    cd "c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion"
    python scripts_mantenimiento\\backfill_surrogate_key.py
"""

import sys
import os
import json
import datetime

# Asegurar que el path raíz esté disponible
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_manager import DataManager

def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

def run_backfill():
    db = DataManager()
    print("=" * 60)
    print("  BACKFILL: Llave Sustituta (tarea_id_local)")
    print("=" * 60)

    # ─── PASO 1: Limpiar cola de revisión ────────────────────────
    print("\n[1/3] Marcando registros REMOTE_CREATE como LEGACY...")
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE poll_review_queue
            SET status = 'LEGACY'
            WHERE conflict_type = 'REMOTE_CREATE'
              AND status IN ('PENDING', 'IGNORED')
        """)
        legacy_count = cursor.rowcount
        conn.commit()
    print(f"      → {legacy_count} registros marcados como LEGACY.")

    # ─── PASO 2: Identificar eventos sin tarea_id_local ──────────
    print("\n[2/3] Identificando eventos sin tarea_id_local...")
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, google_event_id, calendar_id, tecnico_nombre, extended_props
            FROM eventos
            WHERE source = 'internal'
              AND (
                extended_props IS NULL
                OR extended_props NOT LIKE '%tarea_id_local%'
              )
        """)
        rows = cursor.fetchall()

    orphans = []
    for row in rows:
        event_id, gid, cal_id, tec, ext_raw = row
        try:
            ext = json.loads(ext_raw or "{}")
        except Exception:
            ext = {}
        # Doble-check: el LIKE puede dar falso positivo, verificar la clave exacta
        priv = ext.get("private", {})
        if not priv.get("tarea_id_local"):
            orphans.append({
                "id": event_id,
                "google_event_id": gid,
                "calendar_id": cal_id,
                "tecnico_nombre": tec,
                "extended_props": ext
            })

    print(f"      → {len(orphans)} eventos internos sin tarea_id_local.")

    if not orphans:
        print("\n✅ Todos los eventos ya tienen llave sustituta. Nada que hacer.")
        return

    # ─── PASO 3: Encolar UPDATE en sync_queue ────────────────────
    print(f"\n[3/3] Encolando {len(orphans)} eventos para inyección de llave sustituta...")
    enqueued = 0
    errors   = 0

    with db._get_connection() as conn:
        cursor = conn.cursor()
        for ev in orphans:
            event_id = ev["id"]
            cal_id   = ev["calendar_id"]
            tec      = ev["tecnico_nombre"]
            ext      = ev["extended_props"]

            # Inyectar tarea_id_local en los extended_props del registro local
            if "private" not in ext:
                ext["private"] = {}
            ext["private"]["tarea_id_local"] = event_id

            try:
                # Actualizar extended_props en DB local
                cursor.execute("""
                    UPDATE eventos
                    SET extended_props = ?,
                        updated_at     = ?,
                        pending_sync   = 1,
                        sync_status    = 'PENDING'
                    WHERE id = ? AND tecnico_nombre = ?
                """, (json.dumps(ext, ensure_ascii=False), now_iso(), event_id, tec))

                # Encolar UPDATE en sync_queue para que SyncWorker lo suba a Google Calendar
                cursor.execute("""
                    INSERT OR IGNORE INTO sync_queue
                        (queue_id, event_id, calendar_id, tecnico, operation, status, created_at, attempts)
                    VALUES
                        (?, ?, ?, ?, 'UPDATE', 'PENDING', ?, 0)
                """, (
                    f"backfill_{event_id[:20]}",
                    event_id, cal_id, tec, now_iso()
                ))
                enqueued += 1
            except Exception as e:
                print(f"      ⚠ Error encolando {event_id}: {e}")
                errors += 1

        conn.commit()

    print(f"      → {enqueued} eventos encolados exitosamente.")
    if errors:
        print(f"      → {errors} eventos con error (ver detalles arriba).")

    print("\n" + "=" * 60)
    print("  BACKFILL COMPLETADO")
    print(f"  LEGACY marcados:   {legacy_count}")
    print(f"  Eventos encolados: {enqueued}")
    print(f"  Errores:           {errors}")
    print("=" * 60)
    print("\n  El SyncWorker inyectará la llave en Google Calendar")
    print("  en el próximo ciclo (máx. 30 segundos).")
    print("  Luego podés verificar con el check del Polling Manager.")


if __name__ == "__main__":
    run_backfill()
