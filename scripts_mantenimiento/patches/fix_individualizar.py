
import sys

with open("api_server.py", "r", encoding="utf-8") as f:
    js = f.read()

target = """        # 5. Crear nuevo evento con título reformulado
        new_ev_id = f"local_{uuid.uuid4().hex[:12]}"
        db.guardar_evento_individual({
            "id": new_ev_id,
            "calendar_id": tecnico_correo,
            "tecnico_nombre": nuevo_nombre,
            "summary": nuevo_titulo,
            "inicio": base_ev['inicio'],
            "fin": base_ev['fin'],
            "ubicacion": base_ev.get("ubicacion", ''),
            "descripcion": base_ev.get("descripcion", ''),
            "extended_props": base_ev.get('extended_props') or {},"""

replacement = """        # 5. Crear nuevo evento con título reformulado
        new_ev_id = f"local_{uuid.uuid4().hex[:12]}"
        
        # Limpiar is_complex flags al individualizar
        new_ext_props = base_ev.get('extended_props') or {}
        import copy
        new_ext_props = copy.deepcopy(new_ext_props)
        if 'private' in new_ext_props:
            new_ext_props['private'].pop('has_guests', None)
            
        db.guardar_evento_individual({
            "id": new_ev_id,
            "calendar_id": tecnico_correo,
            "tecnico_nombre": nuevo_nombre,
            "summary": nuevo_titulo,
            "inicio": base_ev['inicio'],
            "fin": base_ev['fin'],
            "ubicacion": base_ev.get("ubicacion", ''),
            "descripcion": base_ev.get("descripcion", ''),
            "extended_props": new_ext_props,"""

if target in js:
    js = js.replace(target, replacement)
    
    # Also in split_evento:
    target2 = """            # 3. Generar eventos individuales día a día
        current = d_start
        while current < d_end:
            target_day = current.strftime("%Y-%m-%d")"""
            
    replacement2 = """        # Limpiar is_complex flags al splittear
        import copy
        new_ext_props = copy.deepcopy(props_base)
        if 'private' in new_ext_props:
            new_ext_props['private'].pop('has_guests', None)

        # 3. Generar eventos individuales día a día
        current = d_start
        while current < d_end:
            target_day = current.strftime("%Y-%m-%d")"""
            
    if target2 in js:
        js = js.replace(target2, replacement2)

    with open("api_server.py", "w", encoding="utf-8") as f:
        f.write(js)
    print("Fixed individualizar and split event properties")
else:
    print("Target not found")

