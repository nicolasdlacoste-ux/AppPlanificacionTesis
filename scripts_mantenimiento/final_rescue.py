import re

def final_rescue(filename):
    with open(filename, 'rb') as f:
        data = f.read()

    # Patr\u00f3n: Cualquier cosa seguida de "cnico"
    # Vamos a reemplazar por la secuencia de bytes para "T\u00e9cnico" en UTF-8
    # "T" = 0x54, "\u00e9" = 0xc3a9, "cnico" = 0x636e69636f
    
    # Buscamos 0x636e69636f y retrocedemos unos bytes para capturar el prefijo corrupto
    pattern = rb'.{1,6}636e69636f' # No, esto es hex. 
    
    # Mejor: buscar la cadena "cnico" y reemplazar los 1-3 bytes anteriores si no son 'e'
    # Pero es m\u00e1s f\u00e1cil:
    import re
    # Reemplazar cualquier secuencia que termine en "cnico" y tenga prefijos raros
    # Buscamos bytes que no son ASCII est\u00e1ndar seguidos de "cnico"
    data = re.sub(rb'[\x80-\xff]+cnico', b'\xc3\xa9cnico', data)
    
    # Y asegurar la T
    data = data.replace(b'T\xc3\xa9cnico', b'T\xc3\xa9cnico') # Ya est\u00e1 bien
    
    # Tambi\u00e9n Ubicaci\u00f3n y Descripci\u00f3n
    data = re.sub(rb'Ubicaci[\x80-\xff]+n', b'Ubicaci\xc3\xb3n', data)
    data = re.sub(rb'Descripci[\x80-\xff]+n', b'Descripci\xc3\xb3n', data)
    
    # Y el desastre de "ALTER TABLE"
    data = data.replace(b'ALT\xc3\xa9cnicos', b'ALTER TABLE tecnicos')

    with open(filename, 'wb') as f:
        f.write(data)

final_rescue('api_server.py')
final_rescue('data_manager.py')
