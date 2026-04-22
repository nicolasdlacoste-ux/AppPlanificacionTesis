import os
import threading
import time
import subprocess
import webbrowser
import socket
import sys

# Redirigir stdout/stderr si no hay consola (evita crash en uvicorn)
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def wait_for_server(port, timeout=15):
    """Espera hasta que el puerto esté abierto o se agote el tiempo."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) == 0:
                return True
        time.sleep(0.5)
    return False

def run_server(port):
    try:
        import uvicorn
        from api_server import app
        # log_level error para evitar spam, pero capturamos excepciones
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")
    except Exception as e:
        with open("error_log.txt", "a") as f:
            f.write(f"[{time.ctime()}] ERROR EN EL SERVIDOR: {str(e)}\n")
            import traceback
            traceback.print_exc(file=f)

def start_app():
    try:
        port = find_free_port()
        
        # 1. Iniciar FastAPI en un hilo separado
        server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
        server_thread.start()
        
        # 2. Espera Inteligente (hasta 15 segundos)
        print(f"Esperando que el servidor responda en puerto {port}...")
        if not wait_for_server(port):
            with open("error_log.txt", "a") as f:
                f.write(f"[{time.ctime()}] El servidor no inició a tiempo en puerto {port}\n")
            # Podemos intentar abrir igual por si acaso, o dar un mensaje
        
        url = f"http://localhost:{port}"
        print(f"Abriendo interfaz en {url}")
        
        # 3. Intentar abrir en "Modo App" de Chrome
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
        ]
        
        opened = False
        for path in chrome_paths:
            if os.path.exists(path):
                try:
                    subprocess.Popen([path, f"--app={url}", "--start-maximized"])
                    opened = True
                    break
                except:
                    continue
        
        if not opened:
            webbrowser.open(url)

        # 4. Mantener vivo
        while True:
            time.sleep(1)
            if not server_thread.is_alive():
                break
                
    except Exception as e:
        with open("error_log.txt", "a") as f:
            f.write(f"[{time.ctime()}] ERROR EN START_APP: {str(e)}\n")

if __name__ == "__main__":
    start_app()
