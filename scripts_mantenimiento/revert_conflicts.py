import re

def revert_conflict_blocking():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Patr\u00f3n para encontrar y eliminar el bloqueo por conflicto en mover_evento y mover_grupo
    pattern = r"error_conflicto = db\.check_conflictos_negocio\(.*?\)\s+if error_conflicto:\s+raise HTTPException\(status_code=409, detail=error_conflicto\)"
    
    # Usamos re.DOTALL para que el punto coincida con saltos de l\u00ednea si es necesario
    new_content = re.sub(pattern, "# Validaci\u00f3n Etapa 5 (Desactivado bloqueo seg\u00fan feedback usuario)\n        # error_conflicto = db.check_conflictos_negocio(...)\n        pass", content, flags=re.DOTALL)

    if content != new_content:
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Conflict blocking removed from api_server.py")
    else:
        print("Could not find conflict blocking pattern in api_server.py")

revert_conflict_blocking()
