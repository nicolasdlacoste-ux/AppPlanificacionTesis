import re

def clean_api_server_mess():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Patr\u00f3n para el bloque mal insertado
    # El bloque que insert\u00e9 err\u00f3neamente se repite muchas veces
    pattern = r"(\s+)# Auto-agrupaci\u00f3n si coincide con otra OT en el mismo d\u00eda\s+ots_actuales = list\(utils\.extraer_ots\(nuevo_titulo\)\)\s+if ots_actuales:\s+await _auto_agrupar_evento\(event_id, target_cal, tec_nombre, params\.nueva_fecha, ots_actuales\)"
    
    new_content = re.sub(pattern, "", content, flags=re.DOTALL)

    if content != new_content:
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("api_server.py cleaned from duplicated blocks.")
    else:
        print("Duplicated block pattern not found.")

clean_api_server_mess()
