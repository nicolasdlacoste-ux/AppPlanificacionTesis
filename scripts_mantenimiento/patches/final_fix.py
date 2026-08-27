def final_fix():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Fix en if grupo de agregar_tecnico
    old = 'db.crear_o_actualizar_grupo({"grupo_id": grupo[\'grupo_id\'], "fecha": grupo[\'fecha\'], "event_ids": new_ids, "tecnico_nombres": new_nombres})'
    new = 'db.crear_o_actualizar_grupo({**grupo, "event_ids": new_ids, "tecnico_nombres": new_nombres})'
    content = content.replace(old, new)
    
    # Fix en quitar_tecnico
    old2 = 'db.crear_o_actualizar_grupo({"grupo_id": grupo_id, "fecha": grupo[\'fecha\'], "event_ids": new_event_ids, "tecnico_nombres": new_tecnico_nombres})'
    new2 = 'db.crear_o_actualizar_grupo({**grupo, "event_ids": new_event_ids, "tecnico_nombres": new_tecnico_nombres})'
    content = content.replace(old2, new2)

    # Fix en mover_evento
    old3 = 'db.crear_o_actualizar_grupo({"grupo_id": grupo[\'grupo_id\'], "fecha": grupo[\'fecha\'], "event_ids": new_event_ids, "tecnico_nombres": new_tecnico_nombres})'
    new3 = 'db.crear_o_actualizar_grupo({**grupo, "event_ids": new_event_ids, "tecnico_nombres": new_tecnico_nombres})'
    content = content.replace(old3, new3)

    with open('api_server.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Final fix completed.")

final_fix()
