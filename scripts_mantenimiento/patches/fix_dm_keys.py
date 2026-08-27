
import re

def fix_dm_final():
    with open('data_manager.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Fix key mismatch in guardar_eventos
    content = content.replace('e.get("tecnico_nombre")', 'e.get("tecnico")')
    
    # Also ensure we fallback between 'summary' and 'evento'
    content = content.replace('e.get("evento")', 'e.get("summary") or e.get("evento")')
    content = content.replace('e.get("inicio")', 'e.get("start") or e.get("inicio")')
    content = content.replace('e.get("fin")', 'e.get("end") or e.get("fin")')
    content = content.replace('e.get("ubicacion")', 'e.get("location") or e.get("ubicacion")')
    content = content.replace('e.get("descripcion")', 'e.get("description") or e.get("descripcion")')

    with open('data_manager.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("data_manager.py fixed for key mismatches.")

if __name__ == "__main__":
    fix_dm_final()
