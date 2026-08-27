def literal_fix():
    with open('data_manager.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Usar el caracter exacto que veo en el log
    content = content.replace('T\u01f8cnico', 'T\u00e9cnico')
    content = content.replace('Ubicaci\u00f3n', 'Ubicaci\u00f3n') # Ya est\u00e1 bien?
    
    with open('data_manager.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Literal fix completed.")

literal_fix()
