import os, re

text = open('api_server.py', encoding='utf-8').read()

old_complex = r'''def _is_complex_event\(ev: dict\) -> bool:
    """Determina si un evento es complejo \(multidia o tiene invitados\)\."""
    ext = ev\.get\('extendedProperties'\) or \{\}
    priv = ext\.get\('private'\) or \{\}
    if str\(priv\.get\('has_guests', "false"\)\)\.lower\(\) == "true":
        return True
        
    inicio = ev\.get\('inicio', ''\)
    fin = ev\.get\('fin', ''\)
    
    if inicio and fin and len\(inicio\) == 10 and len\(fin\) == 10:
        if inicio != fin:
            return True
            
    if inicio and "T" in inicio and fin and "T" in fin:
        import datetime
        try:
            dt_s = datetime\.datetime\.fromisoformat\(inicio\.replace\('Z', '\+00:00'\)\)
            dt_e = datetime\.datetime\.fromisoformat\(fin\.replace\('Z', '\+00:00'\)\)
            if \(dt_e - dt_s\)\.total_seconds\(\) > 24 \* 3600:
                return True
        except:
            pass
            
    return False'''

new_complex = '''def _is_complex_event(ev: dict) -> bool:
    """Determina si un evento tiene invitados externos (ya no bloquea multidía)."""
    ext = ev.get('extendedProperties') or {}
    priv = ext.get('private') or {}
    if str(priv.get('has_guests', "false")).lower() == "true":
        return True
    return False'''

if re.search(old_complex, text):
    text = re.sub(old_complex, new_complex, text)
    open('api_server.py', 'w', encoding='utf-8').write(text)
    print("Patched _is_complex_event!")
else:
    print("Could not find _is_complex_event!")
