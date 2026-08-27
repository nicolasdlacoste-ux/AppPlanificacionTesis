import sys
sys.path.append('c:\\Users\\ndiaz_akrimet\\Git Proyect\\AppPlanificacion')
from data_manager import DataManager

db = DataManager()
queue = db.get_poll_review_queue(limit=10)
print(f"Encontrados {len(queue)} items en la cola.")

for item in queue:
    print(f"\nIntentando aceptar review: {item['review_id']} - {item['conflict_type']}")
    try:
        res = db.accept_review(item['review_id'])
        print(f"Éxito: {res}")
    except Exception as e:
        print(f"Error: {e}")

