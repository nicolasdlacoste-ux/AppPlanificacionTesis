def fix_keyerror():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Reemplazar el acceso inseguro a 'summary'
    old = "ev_ots = list(utils.extraer_ots(ev['summary'] or ev['Evento']))"
    new = "ev_ots = list(utils.extraer_ots(ev.get('summary') or ev.get('Evento') or ''))"
    
    content = content.replace(old, new)
    
    with open('api_server.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("KeyError: 'summary' fixed in api_server.py")

fix_keyerror()
