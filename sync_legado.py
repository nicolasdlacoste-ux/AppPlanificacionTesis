import extractor
import json
import os

def ejecutar_upgrade():
    print("Iniciando Sincronización de Metadatos para Eventos Legados...\n")
    svc_cal, svc_sheets = extractor.get_google_services()
    
    # 1. Cargar Técnicos
    cache_tech = os.path.join(os.path.dirname(__file__), 'tecnicos_cache.json')
    if not os.path.exists(cache_tech):
        print("Error: Sincroniza los técnicos primero.")
        return
    with open(cache_tech, 'r', encoding='utf-8') as f:
        tecnicos = json.load(f)

    # 2. Obtener Agendas (Raw)
    print("Extrayendo eventos del calendario...")
    eventos_raw = extractor.obtener_agendas(svc_cal, tecnicos)
    
    # 3. Clasificar (Heurísticas)
    print("Analizando eventos para identificar paquetes potenciales...")
    paquetes = extractor.clasificar_agendas_en_paquetes(eventos_raw)
    
    paquetes_virtuales = [p for p in paquetes if p["tipo"] == "virtual"]
    
    if not paquetes_virtuales:
        print("No se encontraron eventos legados para upgrado.")
        return

    print(f"Se detectaron {len(paquetes_virtuales)} proyectos antiguos sin metadatos.")
    
    # 4. Cargar BD OTs para buscar IDs de Salesforce
    cache_ots = os.path.join(os.path.dirname(__file__), 'bd_ots_cache.json')
    if not os.path.exists(cache_ots):
        print("Error: No se encontró bd_ots_cache.json.")
        return
    with open(cache_ots, 'r', encoding='utf-8') as f:
        bd_ots = json.load(f)

    # 5. Ejecutar Upgrade
    confirm = input(f"\n¿Deseas escribir los metadatos de vuelta en {len(paquetes_virtuales)} grupos de Google Calendar? (s/n): ")
    if confirm.lower() == 's':
        total = extractor.sincronizar_metadatos_legado(svc_cal, paquetes_virtuales, bd_ots)
        print(f"\n¡Proceso terminado! Se actualizaron {total} eventos individuales.")
    else:
        print("Operación cancelada.")

if __name__ == "__main__":
    ejecutar_upgrade()
