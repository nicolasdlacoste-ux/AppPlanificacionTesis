
import sys

with open("api_server.py", "r", encoding="utf-8") as f:
    js = f.read()

target = """def _limpiar_cache_eventos():"""

replacement = """def _is_complex_event(ev: dict) -> bool:
    \"\"\"Determina si un evento es complejo (multidía o tiene invitados).\"\"\"
    # Chequear has_guests
    ext = ev.get('extendedProperties') or {}
    priv = ext.get('private') or {}
    if str(priv.get('has_guests', "false")).lower() == "true":
        return True
        
    # Chequear multidía
    inicio = ev.get('inicio', '')
    fin = ev.get('fin', '')
    
    # Eventos de día completo (yyyy-mm-dd)
    if inicio and fin and len(inicio) == 10 and len(fin) == 10:
        if inicio != fin:
            return True
            
    # Eventos con hora (yyyy-mm-ddThh:mm:ss...)
    if inicio and "T" in inicio and fin and "T" in fin:
        import datetime
        try:
            dt_s = datetime.datetime.fromisoformat(inicio.replace('Z', '+00:00'))
            dt_e = datetime.datetime.fromisoformat(fin.replace('Z', '+00:00'))
            if (dt_e - dt_s).total_seconds() > 24 * 3600:
                return True
        except:
            pass
            
    return False

def _limpiar_cache_eventos():"""

if target in js:
    js = js.replace(target, replacement)
    
    with open("api_server.py", "w", encoding="utf-8") as f:
        f.write(js)
    print("Added _is_complex_event")
else:
    print("target not found")

