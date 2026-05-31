import sys, asyncio, json
sys.path.append('.')
import api_server
from sync_manager import map_evento_to_google

async def test():
    event_obj = {
        'id': 'local_test123',
        'google_event_id': 'local_test123',
        'calendar_id': 'ldiaz@akrimet.com',
        'tecnico_nombre': 'Luis Diaz',
        'summary': 'Auditoria Payload',
        'inicio': '2026-05-15T10:00:00-03:00',
        'fin': '2026-05-15T12:00:00-03:00',
        'ubicacion': '123 Main St',
        'descripcion': 'Test audit',
        'extendedProperties': {'private': {'app_ots': '["12345"]', 'app_vehiculo': 'Hilux'}},
        'version': 1,
        'sync_status': 'PENDING'
    }

    print('Calling map_evento_to_google...')
    payload = map_evento_to_google(event_obj)

asyncio.run(test())
