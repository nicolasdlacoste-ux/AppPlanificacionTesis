import re

def fix_indentation():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Buscar cualquier bloque de Validacion Etapa 5 con mala indentacion
    pattern = r"(\s+)# Validaci\u00f3n Etapa 5.*?\n\s+# error_conflicto.*?\n\s+pass"
    
    # Reemplazar con 12 espacios uniformes
    def fix(match):
        return "            # Validaci\u00f3n Etapa 5 (Desactivado bloqueo seg\u00fan feedback usuario)\n            # error_conflicto = db.check_conflictos_negocio(...)\n            pass"

    new_content = re.sub(pattern, fix, content, flags=re.DOTALL)

    if content != new_content:
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Indentation fixed via regex.")
    else:
        print("Regex did not match.")

fix_indentation()
