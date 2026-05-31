
import re

def fix_api():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Standardize db calls to use tecnico without accent
    content = content.replace('db.obtener_técnicos()', 'db.obtener_tecnicos()')
    content = content.replace('db.obtener_t\u00e9cnicos()', 'db.obtener_tecnicos()')
    # Use a regex for the mangled ones
    content = re.sub(r'db\.obtener_t.*?cnicos\(\)', 'db.obtener_tecnicos()', content)
    
    # Also standardize variables if possible, but let's stick to methods first
    # to avoid breaking logic.

    with open('api_server.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("api_server.py method calls standardized.")

if __name__ == "__main__":
    fix_api()
