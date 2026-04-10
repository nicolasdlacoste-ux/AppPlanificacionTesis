import extractor
import json
import os

def inspeccionar():
    print("--- Verificador de Metadatos de Agendamiento ---")
    svc_cal, _ = extractor.get_google_services()
    
    # Cargar técnicos desde caché
    cache_path = os.path.join(os.path.dirname(__file__), 'tecnicos_cache.json')
    if not os.path.exists(cache_path):
        print("Error: No se encontró tecnicos_cache.json. Sincroniza primero.")
        return
        
    with open(cache_path, 'r', encoding='utf-8') as f:
        tecnicos = json.load(f)

    for tech in tecnicos:
        print(f"\nRevisando calendario de: {tech['nombre']} ({tech['correo']})")
        try:
            events_result = svc_cal.events().list(
                calendarId=tech['correo'],
                maxResults=10,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            if not events:
                print("  (Sin eventos recientes)")
                continue

            for ev in events:
                summary = ev.get('summary', '(Sin título)')
                props = ev.get('extendedProperties', {}).get('private', {})
                
                if props:
                    print(f"\n  [ID Paquete: {props.get('app_pkg_id', 'N/A')}]")
                    print(f"  Evento: {summary}")
                    print(f"  - OTs: {props.get('app_ots', 'N/A')}")
                    print(f"  - Salesforce IDs: {props.get('app_sf_ids', 'N/A')}")
                    print(f"  - Jornada: {props.get('app_jornada', 'N/A')}")
                    print(f"  - Patrones: {props.get('app_patrones', 'N/A')}")
                    print(f"  - Cliente: {props.get('app_cliente', 'N/A')}")
                else:
                    print(f"  [Legacy] Evento: {summary} (Sin metadatos)")

        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    inspeccionar()
