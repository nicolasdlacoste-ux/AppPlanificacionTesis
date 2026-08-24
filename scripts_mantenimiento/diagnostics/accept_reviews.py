import sqlite3
import json
from data_manager import DataManager

db = DataManager()
with db._get_connection() as conn:
    conn.row_factory = sqlite3.Row
    # Reset all ACCEPTED back to PENDING so accept_review works
    conn.execute("UPDATE poll_review_queue SET status='PENDING' WHERE status='ACCEPTED'")
    conn.commit()
    
    rows = conn.execute("SELECT * FROM poll_review_queue WHERE status = 'PENDING'").fetchall()

print(f"Encontrados {len(rows)} reviews para procesar")

for row in rows:
    try:
        r_dict = dict(row)
        review_id = r_dict["review_id"]
        db.accept_review(review_id=review_id)
    except Exception as e:
        print(f"Error procesando {review_id}: {e}")

print("Procesamiento terminado")
