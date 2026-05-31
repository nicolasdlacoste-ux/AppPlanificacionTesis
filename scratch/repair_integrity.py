import sqlite3
import datetime
from data_manager import DataManager

def repair():
    print("Iniciando reparación de integridad operacional...")
    db = DataManager("planificacion.db") # Esto dispara _init_db con las nuevas columnas
    
    with db._get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Reparar updated_at usando last_synced_at si está disponible
        cursor.execute("""
            UPDATE eventos 
            SET updated_at = last_synced_at 
            WHERE updated_at IS NULL AND last_synced_at IS NOT NULL
        """)
        print(f"Reparados {cursor.rowcount} eventos usando last_synced_at.")
        
        # 2. Reparar updated_at restantes con el timestamp actual
        now = datetime.datetime.now().isoformat()
        cursor.execute("""
            UPDATE eventos 
            SET updated_at = ? 
            WHERE updated_at IS NULL
        """, (now,))
        print(f"Reparados {cursor.rowcount} eventos con timestamp actual.")
        
        # 3. Asegurar google_event_id = id si está NULL (para eventos antiguos que no se sincronizaron)
        # Pero solo si id NO parece un UUID local
        cursor.execute("""
            UPDATE eventos 
            SET google_event_id = id 
            WHERE google_event_id IS NULL AND id NOT LIKE 'local_%'
        """)
        print(f"Reparados {cursor.rowcount} google_event_ids.")
        
        # 4. Asegurar source='internal' por defecto
        cursor.execute("UPDATE eventos SET source = 'internal' WHERE source IS NULL")
        print(f"Reparados {cursor.rowcount} campos source.")
        
        conn.commit()

    print("Reparación finalizada.")

if __name__ == "__main__":
    repair()
