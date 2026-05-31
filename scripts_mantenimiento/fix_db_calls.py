import re

def fix_db_calls():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Patr\u00f3n para: db.crear_o_actualizar_grupo(grupo_id, fecha, event_ids, tec_names)
    # Reemplazar por: db.crear_o_actualizar_grupo({"grupo_id": grupo_id, "fecha": fecha, "event_ids": event_ids, "tecnico_nombres": tec_names})
    
    pattern1 = r"db\.crear_o_actualizar_grupo\(([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,\)]+)\)"
    def sub1(m):
        return f'db.crear_o_actualizar_grupo({{"grupo_id": {m.group(1)}, "fecha": {m.group(2)}, "event_ids": {m.group(3)}, "tecnico_nombres": {m.group(4)}}})'
    
    content = re.sub(pattern1, sub1, content)
    
    # Tambi\u00e9n hab\u00eda uno con 3 argumentos en alg\u00fan lado? No, parece que la mayor\u00eda eran 4.
    # En mover_grupo us\u00e9: db.crear_o_actualizar_grupo(new_grupo_data['grupo_id'], new_grupo_data['fecha'], ...)
    
    with open('api_server.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("db.crear_o_actualizar_grupo calls fixed.")

fix_db_calls()
