import sys

def patch_quitar_tecnico():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    start_idx = -1
    end_idx = -1
    for i, line in enumerate(lines):
        if line.startswith('@app.post("/api/eventos/{event_id}/quitar_tecnico")'):
            start_idx = i
        if start_idx != -1 and i > start_idx + 1 and line.startswith('    except Exception as e:'):
            # Find the end of this function
            for j in range(i, len(lines)):
                if lines[j].startswith("    return "):
                    end_idx = j + 1
                    break
            break

    if start_idx != -1 and end_idx != -1:
        new_content = '''@app.post("/api/eventos/{event_id}/quitar_tecnico")
async def quitar_tecnico(event_id: str, calendar_id: str = Query(...)):
    await check_authorization()
    """Elimina a un técnico de un grupo y actualiza los títulos de los demás localmente."""
    try:
        # 1. Identificar el grupo
        grupo = db.obtener_grupo_de_evento(event_id)
        if not grupo:
            # Sin grupo: Borrado simple local
            db.eliminar_evento_individual(event_id)
            return {"status": "ok"}

        grupo_id = grupo['grupo_id']

        # 2. Borrar el evento del técnico solicitado localmente
        db.eliminar_evento_individual(event_id)
        
        # 3. Calcular nueva composición
        new_event_ids = [eid for eid in grupo['event_ids'] if eid != event_id]
        
        try:
            idx_removed = grupo['event_ids'].index(event_id)
            new_tecnico_nombres = [n for i, n in enumerate(grupo['tecnico_nombres']) if i != idx_removed]
        except ValueError:
            new_tecnico_nombres = list(grupo['tecnico_nombres'])

        # 4. Actualizar o disolver grupo
        if not new_event_ids or len(new_event_ids) <= 1:
            db.eliminar_grupo(grupo_id)
        else:
            db.crear_o_actualizar_grupo(grupo_id, grupo['fecha'], new_event_ids, new_tecnico_nombres)
            # Deshabilitado: await sync_group_events(grupo_id)

        db.update_last_sync()
        return {"status": "ok"}
    except Exception as e:
        print("Error en quitar_tecnico:", e)
        raise HTTPException(status_code=500, detail=str(e))
'''
        lines = lines[:start_idx] + [new_content] + lines[end_idx:]
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("quitar_tecnico replaced successfully.")
    else:
        print(f"Could not find bounds for quitar_tecnico: start={start_idx}, end={end_idx}")

patch_quitar_tecnico()
