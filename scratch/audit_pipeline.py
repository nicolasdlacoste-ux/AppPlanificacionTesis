import sqlite3, json, datetime
import data_manager
import api_server
import asyncio

async def audit():
    print('=== 1. SQLite Direct ===')
    conn = sqlite3.connect('planificacion.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM eventos')
    total = c.fetchone()[0]
    print(f'Total in DB: {total}')

    c.execute('SELECT COUNT(*) FROM eventos WHERE sync_status != "DELETED"')
    activos = c.fetchone()[0]
    print(f'Active in DB: {activos}')

    print('\\n=== 2. DataManager ===')
    db = data_manager.DataManager()
    eventos_dict = db.obtener_eventos_dict()
    print(f'db.obtener_eventos_dict() returned: {len(eventos_dict)}')
    
    if eventos_dict:
        print('Sample keys from first event:', list(eventos_dict[0].keys()))

    print('\\n=== 3. API Layer ===')
    # Run the endpoint function directly
    try:
        api_events = await api_server.obtener_eventos()
        count = sum(len(tech_events) for tech, dict_events in api_events.items() for date, tech_events in dict_events.items())
        print(f'API endpoint returned: {count} events across all techs and dates.')
        print('Keys in first event:', list(api_events[list(api_events.keys())[0]][list(api_events[list(api_events.keys())[0]].keys())[0]][0].keys()) if count > 0 else 'None')
    except Exception as e:
        print(f'API Error: {e}')

if __name__ == '__main__':
    asyncio.run(audit())
