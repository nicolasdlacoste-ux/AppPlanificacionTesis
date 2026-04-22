import subprocess
import sys
import os
import shutil

def build():
    print("--- Iniciando proceso de compilación de Akrimet Planner ---")
    
    # 1. Verificar PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("Instalando PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 2. Definir comando
    # --onefile: Un solo ejecutable
    # --windowed: No abre consola de comandos (opcional, mejor para usuario final)
    # --add-data: Incluir la carpeta webapp dentro del ejecutable
    # --collect-all: Asegurar que uvicorn y fastapi tengan todas sus dependencias
    # --name: Nombre del archivo final
    
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed", 
        "--name", "AkrimetPlanner",
        "--add-data", "webapp;webapp",
        "--collect-all", "uvicorn",
        "--collect-all", "fastapi",
        "--collect-all", "googleapiclient",
        "--collect-all", "google_auth_oauthlib",
        "launcher.py"
    ]

    print(f"Ejecutando: {' '.join(cmd)}")
    
    try:
        subprocess.check_call(cmd)
        print("\n" + "="*40)
        print("¡COMPILACIÓN EXITOSA!")
        print(f"El ejecutable se encuentra en: {os.path.join(os.getcwd(), 'dist', 'AkrimetPlanner.exe')}")
        
        # 3. Copiar archivos de configuración necesarios al dist/
        print("Copiando configuración al directorio dist...")
        for f in ['credentials.json', 'token.json']:
            if os.path.exists(f):
                shutil.copy(f, "dist")
                print(f"  - {f} copiado.")
        
        print("="*40)
        
    except subprocess.CalledProcessError as e:
        print(f"Error durante la compilación: {e}")

if __name__ == "__main__":
    build()
