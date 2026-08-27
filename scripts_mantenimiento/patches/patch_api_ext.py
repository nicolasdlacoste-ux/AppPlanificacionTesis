import re

api_py = open('api_server.py', encoding='utf-8').read()

old_func = '''def _build_tech_events():
    """Construye el diccionario tech_events que espera engine.py desde la DB."""
    eventos = db.obtener_eventos_dict()
    tech_events = {}'''

new_func = '''def _build_tech_events():
    """Construye el diccionario tech_events que espera engine.py desde la DB."""
    eventos = db.obtener_eventos_dict()
    # [BUGFIX] Integrar eventos externos invisibles para el motor de disponibilidad
    try:
        ext_evs = db.obtener_eventos_externos()
        eventos.extend(ext_evs)
    except Exception as e:
        print(f"Error cargando eventos externos: {e}")
        
    tech_events = {}'''

api_py = api_py.replace(old_func, new_func)

open('api_server.py', 'w', encoding='utf-8').write(api_py)
print("Patched api_server.py to include external events")
