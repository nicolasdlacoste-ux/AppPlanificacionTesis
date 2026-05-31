"""
migrate_review_ids.py — Asigna UUIDs a los reviews con review_id = NULL.

Ejecutar UNA VEZ desde AppPlanificacion/:
    python scratch/migrate_review_ids.py

Esto permite arbitrar los conflictos pre-existentes de forma individual.
"""
import sqlite3
import uuid
import datetime

DB_PATH = "planificacion.db"

def run():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Auto-migrar columnas nuevas si faltan
    cursor.execute("PRAGMA table_info(poll_review_queue)")
    existing_cols = {r[1] for r in cursor.fetchall()}
    new_cols = {
        "conflict_type":      "TEXT DEFAULT 'FIELD_CHANGE'",
        "google_event_id":    "TEXT",
        "local_snapshot":     "TEXT",
        "remote_snapshot":    "TEXT",
        "recommended_action": "TEXT",
        "resolved_at":        "TEXT",
    }
    for col, spec in new_cols.items():
        if col not in existing_cols:
            print(f"  Migrando columna: {col}")
            cursor.execute(f"ALTER TABLE poll_review_queue ADD COLUMN {col} {spec}")

    # 2. Contar NULLs
    cursor.execute("SELECT COUNT(*) FROM poll_review_queue WHERE review_id IS NULL")
    count = cursor.fetchone()[0]
    print(f"\nEncontrados {count} reviews con review_id = NULL")

    if count == 0:
        print("Nada que migrar.")
        conn.close()
        return

    # 3. Asignar UUIDs
    cursor.execute("SELECT rowid FROM poll_review_queue WHERE review_id IS NULL")
    rows = cursor.fetchall()
    for (rowid,) in rows:
        new_id = str(uuid.uuid4())
        cursor.execute(
            "UPDATE poll_review_queue SET review_id = ?, conflict_type = COALESCE(conflict_type, 'FIELD_CHANGE') WHERE rowid = ?",
            (new_id, rowid)
        )

    conn.commit()
    conn.close()
    print(f"OK: {count} reviews actualizados con UUIDs únicos.")
    print("Ahora pueden ser arbitrados individualmente via /api/review/{id}/accept|reject|defer")

if __name__ == "__main__":
    run()
