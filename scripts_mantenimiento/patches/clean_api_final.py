import re

def clean_api_server():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Eliminar el bloque duplicado
    pattern = r"(\s+raise HTTPException\(status_code=500, detail=str\(e\)\))\s+\}\s+except Exception as e:\s+import traceback; print\(traceback\.format_exc\(\)\)\s+raise HTTPException\(status_code=500, detail=str\(e\)\)"
    
    new_content = re.sub(pattern, r"\1", content, flags=re.DOTALL)

    if content != new_content:
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("api_server.py cleaned.")
    else:
        print("Duplication pattern not found.")

clean_api_server()
