with open('data_manager.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re
# Encontrar todas las palabras que terminen en cnic...
matches = re.findall(r'.{1}cnico', content)
print(f"Found matches: {[repr(m) for m in matches]}")

# Reemplazar todas por T\u00e9cnico
new_content = re.sub(r'.{1}cnico', 'T\u00e9cnico', content)

with open('data_manager.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
