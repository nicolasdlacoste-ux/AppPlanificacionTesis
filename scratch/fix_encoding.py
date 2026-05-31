import os

def fix_encoding(filename):
    with open(filename, 'rb') as f:
        content = f.read()
    
    # Intentar decodificar como latin-1 y recodificar como utf-8
    try:
        decoded = content.decode('latin-1')
        # Reemplazar los caracteres raros que vi en la salida anterior
        decoded = decoded.replace('', 'u') # ltimos -> ultimos
        # También vi un estǭ -> está
        decoded = decoded.replace('estǭ', 'está')
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(decoded)
        print(f"Fixed encoding for {filename}")
    except Exception as e:
        print(f"Error fixing {filename}: {e}")

if __name__ == "__main__":
    fix_encoding('data_manager.py')
