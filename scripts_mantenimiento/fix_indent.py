import re

def fix_indentation():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Patr\u00f3n que caus\u00f3 el error de indentaci\u00f3n (8 espacios en lugar de 12)
    bad_pattern = r"# Validaci\u00f3n Etapa 5 \(Desactivado bloqueo seg\u00fan feedback usuario\)\n        # error_conflicto = db\.check_conflictos_negocio\(\.\.\.\)\n        pass"
    
    # Reemplazar por la versi\u00f3n con 12 espacios
    good_replacement = "            # Validaci\u00f3n Etapa 5 (Desactivado bloqueo seg\u00fan feedback usuario)\n            # error_conflicto = db.check_conflictos_negocio(...)\n            pass"
    
    new_content = content.replace(bad_pattern, good_replacement)

    if content != new_content:
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Indentation fixed.")
    else:
        print("Could not find the bad indentation pattern.")

fix_indentation()
