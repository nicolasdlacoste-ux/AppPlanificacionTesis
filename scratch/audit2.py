import sys, asyncio, json
sys.path.append('.')
import data_manager
import api_server
from utils import CanonicalEventAdapter

async def audit():
    print('=== 1. SQLite Direct ===')
    db = data_manager.DataManager()
    with db._get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM eventos")
        total = c.fetchone()[0]
        print(f"Total in DB: {total}")

        c.execute("SELECT COUNT(*) FROM eventos WHERE sync_status != 'DELETED'")
        activos = c.fetchone()[0]
        print(f"Active in DB: {activos}")

    print('\\n=== 2. DataManager ===')
    eventos_dict = db.obtener_eventos_dict()
    print(f"db.obtener_eventos_dict() returned: {len(eventos_dict)}")
    
    print('\\n=== 3. CanonicalAdapter ===')
    canonical_events = []
    failed = 0
    discarded_no_id = 0
    for ev in eventos_dict:
        try:
            c_ev = CanonicalEventAdapter.to_canonical(ev)
            if not c_ev.get("id"):
                discarded_no_id += 1
            canonical_events.append(c_ev)
        except Exception as e:
            failed += 1
    
    print(f"Successfully adapted: {len(canonical_events)}")
    print(f"Failed to adapt: {failed}")
    print(f"Adapted but no ID: {discarded_no_id}")

    print('\\n=== 4. API Layer ===')
    try:
        api_events = await api_server.get_eventos()
        print(f"API endpoint returned: {len(api_events)} events")
        if len(api_events) > 0:
            print(f"Sample ID: {api_events[0].get('id')}")
    except Exception as e:
        print(f"API Error: {e}")

asyncio.run(audit())
