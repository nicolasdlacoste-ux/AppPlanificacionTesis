import sys

def add_eliminar_evento():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    if 'async def eliminar_evento' in content:
        print("eliminar_evento already exists.")
        return

    code_to_add = '''
@app.delete("/api/eventos/{event_id}")
async def eliminar_evento(event_id: str, calendar_id: str = Query(...)):
    await check_authorization()
    """Elimina un evento individual o lo quita del grupo."""
    return await quitar_tecnico(event_id, calendar_id)
'''
    
    # Insertar antes de ARCHIVOS EST\u00c1TICOS
    anchor = "# \u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?\u00bf?"
    # Since anchors with special chars are hard, I'll just use "webapp_path ="
    anchor2 = "webapp_path = get_resource_path"
    
    if anchor2 in content:
        parts = content.split(anchor2)
        new_content = parts[0] + code_to_add + "\n\n" + anchor2 + parts[1]
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("eliminar_evento added back.")
    else:
        print("Could not find anchor to add eliminar_evento.")

add_eliminar_evento()
