
import re

def fix_dm():
    with open('data_manager.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Fix the 'TEXT' key issue in dictionaries
    content = content.replace('"TEXT": r[2]', '"Técnico": r[2]')
    
    # 2. Fix the e.get("TEXT") / data.get("TEXT") issue
    content = content.replace('e.get("TEXT")', 'e.get("tecnico_nombre")')
    content = content.replace('data.get("TEXT")', 'data.get("tecnico_nombre")')
    
    # 3. Fix the corrupted UPDATE statement
    content = content.replace('UPDAttecnico_nombre', 'UPDATE eventos SET tecnico_nombre')
    
    # 4. Fix double 't' in column names
    content = content.replace('ttecnico_nombre', 'tecnico_nombre')
    
    # 5. Fix the method name standardization
    # api_server.py uses db.obtener_tecnicos() and db.obtener_técnicos()
    # Let's ensure both are available or standardize to one.
    # Actually, it's safer to have both if we're not sure, but let's check api_server.py first.

    with open('data_manager.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("data_manager.py cleaned up.")

if __name__ == "__main__":
    fix_dm()
