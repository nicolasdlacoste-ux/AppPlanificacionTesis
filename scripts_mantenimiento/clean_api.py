import re

def clean_file():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Patr\u00f3n para encontrar el desastre (comentario pegado a la l\u00ednea anterior o mal indentado)
    # Buscamos la l\u00ednea de patrones_val y lo que sigue
    pattern = r"(patrones_val = params\.patrones if params\.patrones is not None else pats_actuales).*?# Validaci\u00f3n Etapa 5.*?\n\s+# error_conflicto.*?\n\s+pass"
    
    # Reemplazamos por la l\u00ednea original limpia
    def fix(match):
        return match.group(1) + "\n"

    new_content = re.sub(pattern, fix, content, flags=re.DOTALL)

    if content != new_content:
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("api_server.py cleaned.")
    else:
        print("Clean pattern did not match.")

clean_file()
