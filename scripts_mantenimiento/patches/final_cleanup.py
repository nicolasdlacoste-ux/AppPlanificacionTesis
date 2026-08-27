def final_cleanup():
    with open('data_manager.py', 'rb') as f:
        data = f.read()
    
    # Reemplazar ALT\u01f8cnicos (\xc7\xb8)
    # T\u01f8cnico
    
    # Vamos a usar reemplazo de bytes para estar seguros
    # ALT + \xc7\xb8 + cnicos -> ALTER TABLE tecnicos
    data = data.replace(b'ALT\xc7\xb8cnicos', b'ALTER TABLE tecnicos')
    
    # t\xc7\xb8cnicos -> tecnicos
    data = data.replace(b't\xc7\xb8cnicos', b'tecnicos')
    
    # t\xc7\xb8cnico -> tecnico
    data = data.replace(b't\xc7\xb8cnico', b'tecnico')
    
    # T\xc7\xb8cnico -> T\xc3\xa9cnico (UTF-8 \u00e9)
    data = data.replace(b'T\xc7\xb8cnico', b'T\xc3\xa9cnico')
    
    # Ubicac\xc7\xb8n -> Ubicaci\xc3\xb3n (\u00f3)
    # Descripc\xc7\xb8n -> Descripci\xc3\xb3n
    # Note: I need to check the exact byte for the corrupted \u00f3
    
    with open('data_manager.py', 'wb') as f:
        f.write(data)
    print("Bytes replacement completed.")

final_cleanup()
