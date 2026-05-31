def inspect_keys():
    with open('data_manager.py', 'r', encoding='utf-8') as f:
        dm_content = f.read()
    
    with open('api_server.py', 'r', encoding='utf-8') as f:
        api_content = f.read()

    import re
    # Buscar el bloque de dict en obtener_eventos_dict
    dm_match = re.search(r'"(T.*?cnico)": r\[2\]', dm_content)
    api_match = re.search(r'"resourceId": ev\["(T.*?cnico)"\]', api_content)

    if dm_match:
        print(f"DM Key: {repr(dm_match.group(1))}")
    if api_match:
        print(f"API Key: {repr(api_match.group(1))}")

inspect_keys()
