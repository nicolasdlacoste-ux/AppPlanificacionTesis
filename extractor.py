import os.path
import datetime
import pandas as pd
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configuración de Rutas base para mayor seguridad sin importar desde dónde se corra
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, 'token.json')
CREDENTIALS_PATH = os.path.join(BASE_DIR, 'credentials.json')

# Si modificas estos rangos (SCOPES), borra el archivo token.json.
SCOPES = [
    'https://www.googleapis.com/auth/calendar',  # Lectura + Escritura en Calendar
    'https://www.googleapis.com/auth/spreadsheets'
]

SPREADSHEET_ID = '1LZA2cNq2bYgUP8z4INT9iDcT87cHKro2DtVuwibTtkI'
RANGE_NAME = 'Tecnicos'

SPREADSHEET_ID_OTS = '1P_-XkU4YqQTd08FQAgmofam0bPowf7dYD4IojSPi59M'
RANGE_NAME_OTS = 'OTs'

def get_google_services():
    """Muestra el flujo de autorización y crea los clientes de la API."""
    creds = None
    # El archivo token.json guarda los tokens de acceso y de actualización del usuario.
    # Se crea automáticamente cuando el flujo de autorización se completa por primera vez.
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        
    # Si no hay credenciales válidas, le pide al usuario que inicie sesión.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        # Guarda las credenciales para la próxima ejecución
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    # Construye y retorna los servicios
    service_calendar = build('calendar', 'v3', credentials=creds)
    service_sheets = build('sheets', 'v4', credentials=creds)
    
    return service_calendar, service_sheets

def obtener_tecnicos(service_sheets):
    """Lee el ID de la planilla y extrae Nombres y Correos."""
    try:
        sheet = service_sheets.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID,
                                    range=RANGE_NAME).execute()
        values = result.get('values', [])

        if not values:
            print('No se encontraron datos en la hoja Tecnicos.')
            return []

        # El primer elemento son los encabezados, los siguientes son los datos
        # Asumimos Columna A = Nombre, Columna B = Correo
        tecnicos = []
        for row in values[1:]: # Omitimos la fila 0 (encabezados)
            if len(row) >= 2:
                nombre = str(row[0]).strip()
                correo = str(row[1]).strip()
                iniciales = str(row[2]).strip() if len(row) > 2 else ''
                tecnicos.append({"nombre": nombre, "correo": correo, "iniciales": iniciales})
                
        return tecnicos

    except HttpError as err:
        print(f"Ocurrió un error conectando a Sheets: {err}")
        return []

def crear_evento_calendar(service_calendar, correo, titulo, descripcion, fecha, jornada_completa=True):
    """Crea un evento en el calendario de un técnico en una fecha específica."""
    fecha_str = fecha.strftime("%Y-%m-%d")
    hora_fin = "16:00:00" if jornada_completa else "11:30:00"
    
    event = {
        'summary': titulo,
        'description': descripcion,
        'start': {
            'dateTime': f"{fecha_str}T07:00:00-03:00",
            'timeZone': 'America/Argentina/Buenos_Aires',
        },
        'end': {
            'dateTime': f"{fecha_str}T{hora_fin}-03:00",
            'timeZone': 'America/Argentina/Buenos_Aires',
        },
    }
    try:
        creado = service_calendar.events().insert(calendarId=correo, body=event).execute()
        print(f"  Evento creado para {correo}: {creado.get('htmlLink')}")
        return True
    except HttpError as e:
        print(f"  Error creando evento para {correo}: {e}")
        return False

def obtener_bd_ots(service_sheets):
    """Descarga la tabla completa de la base de datos de OTs."""
    try:
        sheet = service_sheets.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID_OTS,
                                    range=RANGE_NAME_OTS).execute()
        return result.get('values', [])
    except HttpError as err:
        print(f"Ocurrió un error conectando a la BD de OTs: {err}")
        return []

def obtener_agendas(service_calendar, tecnicos):
    """Itera sobre la lista de técnicos y extrae los eventos recientes y próximos."""
    eventos_totales = []
    
    # Rango de tiempo: Desde 45 días atrás hasta 90 días adelante
    ahora = datetime.datetime.utcnow()
    inicio_busqueda = ahora - datetime.timedelta(days=45)
    fin_busqueda = ahora + datetime.timedelta(days=90)
    
    # Las APIs requieren formato ISO 8601 con 'Z' al final
    timeMin = inicio_busqueda.isoformat() + 'Z'  
    timeMax = fin_busqueda.isoformat() + 'Z'

    for tecnico in tecnicos:
        correo = tecnico['correo']
        nombre = tecnico['nombre']
        print(f"Consultando agenda de: {nombre} ({correo})")
        
        try:
            # Consultamos los eventos
            events_result = service_calendar.events().list(
                calendarId=correo, 
                timeMin=timeMin,
                timeMax=timeMax,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            if not events:
                print(f"  No se encontraron eventos próximos para {nombre}.")
            else:
                for event in events:
                    # 1. Ignorar eventos cancelados (o instancias borradas de una serie)
                    if event.get('status') == 'cancelled':
                        continue
                        
                    # 2. Ignorar si el técnico lo rechazó (declined)
                    rechazado = False
                    for asistente in event.get('attendees', []):
                        if asistente.get('email') == correo and asistente.get('responseStatus') == 'declined':
                            rechazado = True
                            break
                    if rechazado:
                        continue
                        
                    # 3. Ignorar avisos de "Lugar de Trabajo" (workingLocation) 
                    if event.get('eventType') == 'workingLocation':
                        continue

                    start = event['start'].get('dateTime', event['start'].get('date'))
                    end = event['end'].get('dateTime', event['end'].get('date'))
                    
                    eventos_totales.append({
                        "Técnico": nombre,
                        "Correo": correo,
                        "Evento": event.get('summary', '(Sin Título)'),
                        "Inicio": start,
                        "Fin": end,
                        "Ubicación": event.get('location', ''),
                        "Descripción": event.get('description', '')
                    })
        except HttpError as err:
            if err.resp.status == 404:
                print(f"  [!] No existe el calendario o no tienes permisos para el correo: {correo}")
            else:
                print(f"  [!] Error consultando a {correo}: {err}")
                
    return eventos_totales

def escribir_en_sheet(service_sheets, df):
    """Escribe el DataFrame de pandas directamente en la pestaña 'Agenda' de Google Sheets."""
    print("\nExportando a Google Sheets (pestaña 'Agenda')...")
    
    # Reemplazamos NaNs u otros valores vacíos por string vacío para evitar errores JSON
    df = df.fillna('')
    
    # Preparamos los datos: Fila 1 (Encabezados) + Resto de filas
    datos = [df.columns.values.tolist()] + df.values.tolist()
    
    body = {
        'values': datos
    }
    
    try:
        sheet = service_sheets.spreadsheets()
        # 1. Limpiar la hoja entera antes de escribir para no dejar datos viejos abajo
        sheet.values().clear(spreadsheetId=SPREADSHEET_ID, range='Agenda').execute()
        
        # 2. Escribir los nuevos datos desde A1
        result = sheet.values().update(
            spreadsheetId=SPREADSHEET_ID, 
            range='Agenda!A1',
            valueInputOption='USER_ENTERED', 
            body=body
        ).execute()
        
        print(f"¡Éxito! Se actualizaron {result.get('updatedCells')} celdas en el Google Sheet.")
    except HttpError as err:
        print(f"Ocurrió un error al escribir en Sheets: {err}")

def principal():
    print("Iniciando conexión con Google Cloud...")
    service_calendar, service_sheets = get_google_services()
    
    print("\n1. Obteniendo lista de técnicos desde Sheets...")
    tecnicos = obtener_tecnicos(service_sheets)
    print(f"Se encontraron {len(tecnicos)} técnicos válidos.")
    
    if not tecnicos:
        print("No hay técnicos para procesar. Saliendo.")
        return
    
    # Guardar lista de técnicos (con iniciales) en caché local
    tecnicos_cache_path = os.path.join(BASE_DIR, 'tecnicos_cache.json')
    with open(tecnicos_cache_path, 'w', encoding='utf-8') as f:
        json.dump(tecnicos, f, ensure_ascii=False, indent=2)

    print("\n2. Extrayendo calendarios (últimos 45 días hasta próximos 90 días)...")
    eventos = obtener_agendas(service_calendar, tecnicos)
    
    print(f"\n3. Se extrajeron {len(eventos)} eventos en total.")
    
    if eventos:
        # Guardar en caché local para la interfaz gráfica (UI rápida)
        cache_path = os.path.join(BASE_DIR, 'datos_cache.json')
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(eventos, f, ensure_ascii=False, indent=2)
            
        df = pd.DataFrame(eventos)
        
        # Limpieza y conversión a número de serie (formato de fechas numérico de Google Sheets)
        try:
            def procesar_fecha(val):
                if pd.isna(val) or val == '':
                    return pd.NaT
                dt = pd.to_datetime(val)
                # Removemos la zona horaria sin alterar la hora para conservar el horario local
                if dt.tzinfo is not None:
                    dt = dt.tz_localize(None)
                return dt

            inicio_dt = df['Inicio'].apply(procesar_fecha)
            fin_dt = df['Fin'].apply(procesar_fecha)
            
            # La fecha base o "Epoch" de Sheets y Excel es 30/12/1899
            epoch = pd.Timestamp('1899-12-30')
            
            # Calculamos la diferencia en días (fraccionales para incluir la hora)
            df['Inicio'] = (inicio_dt - epoch).dt.total_seconds() / 86400.0
            df['Fin'] = (fin_dt - epoch).dt.total_seconds() / 86400.0
        except Exception as e:
            print(f"Nota: No se pudieron convertir todas las fechas a numérico: {e}")
            
        escribir_en_sheet(service_sheets, df)
    else:
        print("No se encontraron eventos para guardar.")

    print("\n4. Actualizando Base de Datos de OTs...")
    bd_ots_datos = obtener_bd_ots(service_sheets)
    if bd_ots_datos:
        cache_ots_path = os.path.join(BASE_DIR, 'bd_ots_cache.json')
        with open(cache_ots_path, 'w', encoding='utf-8') as f:
            json.dump(bd_ots_datos, f, ensure_ascii=False)
        print(f"¡Éxito! Se sincronizaron {len(bd_ots_datos)} filas de OTs en caché rápido.")

if __name__ == '__main__':
    principal()
