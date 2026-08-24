import sys

def patch_eliminar_evento():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    start_idx = -1
    end_idx = -1
    for i, line in enumerate(lines):
        if line.startswith('@app.delete("/api/eventos/{event_id}")'):
            start_idx = i
        if start_idx != -1 and i > start_idx + 1 and line.startswith('    return {'):
            end_idx = i + 1
            break

    if start_idx != -1 and end_idx != -1:
        new_content = '''@app.delete("/api/eventos/{event_id}")
async def eliminar_evento(event_id: str, calendar_id: str = Query(...)):
    await check_authorization()
    try:
        # LOCAL-ONLY: Eliminar solo de SQLite
        db.eliminar_evento_individual(event_id)
        
        # TambiǸn limpiar del grupo si pertenece a uno
        grupo = db.obtener_grupo_de_evento(event_id)
        if grupo:
            new_ids = [eid for eid in grupo['event_ids'] if eid != event_id]
            if not new_ids or len(new_ids) <= 1:
                db.eliminar_grupo(grupo['grupo_id'])
            else:
                # Actualizar el grupo eliminando este tǸcnico/evento
                idx_rem = -1
                try: idx_rem = grupo['event_ids'].index(event_id)
                except: pass
                
                new_tecnicos = list(grupo['tecnico_nombres'])
                if idx_rem != -1 and idx_rem < len(new_tecnicos):
                    new_tecnicos.pop(idx_rem)
                
                db.crear_o_actualizar_grupo(grupo['grupo_id'], grupo['fecha'], new_ids, new_tecnicos)

        db.update_last_sync()
        return {"status": "ok"}
    except Exception as e:
        print("Error en eliminar_evento:", e)
        raise HTTPException(status_code=500, detail=str(e))
'''
        lines = lines[:start_idx] + [new_content] + lines[end_idx:]
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("eliminar_evento replaced successfully.")
    else:
        print(f"Could not find bounds for eliminar_evento: start={start_idx}, end={end_idx}")

patch_eliminar_evento()
