import re

def fix_grupo_calls():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. En agregar_tecnico_a_grupo (cuando hay grupo previo)
    pattern1 = r'db\.crear_o_actualizar_grupo\(\{"grupo_id": grupo\[\'grupo_id\'\], "fecha": grupo\[\'fecha\'\], "event_ids": new_ids, "tecnico_nombres": new_nombres\}\)'
    replacement1 = r'db.crear_o_actualizar_grupo({**grupo, "event_ids": new_ids, "tecnico_nombres": new_nombres})'
    content = content.replace(pattern1, replacement1)

    # 2. En agregar_tecnico_a_grupo (cuando es grupo nuevo)
    pattern2 = r'# Crear grupo nuevo con ambos\s+nuevo_grupo_id = str\(uuid\.uuid4\(\)\)\s+new_ids = \[event_id, new_ev_id\]\s+new_nombres = \[base_ev\[\'TǸcnico\'\], nuevo_nombre\]\s+db\.crear_o_actualizar_grupo\(\{"grupo_id": nuevo_grupo_id, "fecha": base_ev\[\'Inicio\'\]\[:10\], "event_ids": new_ids, "tecnico_nombres": new_nombres\}\)'
    
    # Usar regex m\u00e1s flexible para capturar las variables
    pattern2_regex = r'# Crear grupo nuevo con ambos\s+nuevo_grupo_id = str\(uuid\.uuid4\(\)\)\s+new_ids = \[event_id, new_ev_id\]\s+new_nombres = \[base_ev\[\'T\u00e9cnico\'\], nuevo_nombre\]\s+db\.crear_o_actualizar_grupo\(\{"grupo_id": nuevo_grupo_id, "fecha": base_ev\[\'Inicio\'\]\[:10\], "event_ids": new_ids, "tecnico_nombres": new_nombres\}\)'
    
    replacement2 = '''# Crear grupo nuevo con ambos
            nuevo_grupo_id = str(uuid.uuid4())
            new_ids = [event_id, new_ev_id]
            new_nombres = [base_ev['T\u00e9cnico'], nuevo_nombre]
            ots_extraidas = list(utils.extraer_ots(base_ev['Evento']))
            ot_nro = ots_extraidas[0] if ots_extraidas else "N/A"
            db.crear_o_actualizar_grupo({
                "grupo_id": nuevo_grupo_id, 
                "fecha": base_ev['Inicio'][:10], 
                "event_ids": new_ids, 
                "tecnico_nombres": new_nombres,
                "ot_nro": ot_nro
            })'''
    
    content = re.sub(pattern2_regex, replacement2, content, flags=re.DOTALL)

    # 3. En mover_evento
    pattern3 = r'db\.crear_o_actualizar_grupo\(\{"grupo_id": grupo\[\'grupo_id\'\], "fecha": grupo\[\'fecha\'\], "event_ids": new_event_ids, "tecnico_nombres": new_tecnico_nombres\}\)'
    replacement3 = r'db.crear_o_actualizar_grupo({**grupo, "event_ids": new_event_ids, "tecnico_nombres": new_tecnico_nombres})'
    content = content.replace(pattern3, replacement3)

    # 4. En mover_grupo
    pattern4 = r'db\.crear_o_actualizar_grupo\(\{"grupo_id":\s+new_grupo_data\[\'grupo_id\'\], "fecha": new_grupo_data\[\'fecha\'\], "event_ids": new_grupo_data\[\'event_ids\'\], "tecnico_nombres": new_grupo_data\[\'tecnico_nombres\'\]\s+\}\)'
    replacement4 = r'db.crear_o_actualizar_grupo(new_grupo_data)'
    content = re.sub(pattern4, replacement4, content, flags=re.DOTALL)

    # 5. En quitar_tecnico
    pattern5 = r'db\.crear_o_actualizar_grupo\(\{"grupo_id": grupo_id, "fecha": grupo\[\'fecha\'\], "event_ids": new_event_ids, "tecnico_nombres": new_tecnico_nombres\}\)'
    replacement5 = r'db.crear_o_actualizar_grupo({**grupo, "event_ids": new_event_ids, "tecnico_nombres": new_tecnico_nombres})'
    content = content.replace(pattern5, replacement5)

    with open('api_server.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("All group calls fixed.")

fix_grupo_calls()
