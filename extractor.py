import os.path
import datetime
import pandas as pd
import json
import re
import uuid
import utils

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from data_manager import DataManager

# Configuración de Rutas base para PyInstaller
import sys

def get_base_path():
    if getattr(sys, 'frozen', False):
        # Si corre como .exe (PyInstaller)
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_path()

# Rutas por defecto (afuera del .exe para persistencia)
TOKEN_PATH_DEFAULT = os.path.join(BASE_DIR, 'token.json')
CREDENTIALS_PATH_DEFAULT = os.path.join(BASE_DIR, 'credentials.json')

# Si modificas estos rangos (SCOPES), borra el archivo token.json.
SCOPES = [
    'https://www.googleapis.com/auth/calendar',  # Lectura + Escritura en Calendar
    'https://www.googleapis.com/auth/spreadsheets'
]

SPREADSHEET_ID = '1LZA2cNq2bYgUP8z4INT9iDcT87cHKro2DtVuwibTtkI'
RANGE_NAME = 'Tecnicos'

SPREADSHEET_ID_OTS = '1P_-XkU4YqQTd08FQAgmofam0bPowf7dYD4IojSPi59M'
RANGE_NAME_OTS = 'OTs'

SPREADSHEET_ID_PATRONES = '1FV6mrF35GvLsckWC6W5I6YUm6MCfDTe3y5AK0HIyBF4'
RANGE_NAME_PATRONES = 'Patrones'
RANGE_NAME_VEHICULOS = 'Vehículos'

def get_google_services():
    """Muestra el flujo de autorización y crea los clientes de la API."""
    creds = None
    
    # 1. INTENTAR CARGAR TOKEN (Sesión de Usuario)
    env_token = os.environ.get('GOOGLE_TOKEN_JSON')
    if env_token:
        try:
            token_data = json.loads(env_token)
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        except Exception as e:
            print(f"Error cargando token desde Env Var: {e}")
    
    if not creds and os.path.exists(TOKEN_PATH_DEFAULT):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH_DEFAULT, SCOPES)
        
    # Si no hay credenciales válidas, le pide al usuario que inicie sesión.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # 2. INTENTAR CARGAR CREDENCIALES (App Secret)
            env_creds = os.environ.get('GOOGLE_CREDENTIALS_JSON')
            if env_creds:
                try:
                    creds_data = json.loads(env_creds)
                    flow = InstalledAppFlow.from_client_config(creds_data, SCOPES)
                except Exception as e:
                    print(f"Error cargando credentials desde Env Var: {e}")
                    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH_DEFAULT, SCOPES)
            else:
                if not os.path.exists(CREDENTIALS_PATH_DEFAULT):
                    msg = "No se encontró credentials.json ni variable de entorno GOOGLE_CREDENTIALS_JSON."
                    if getattr(sys, 'frozen', False):
                        msg += f"\n\nSOLUCIÓN: Copia el archivo 'credentials.json' a la misma carpeta donde está el ejecutable ({BASE_DIR})."
                    raise FileNotFoundError(msg)
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH_DEFAULT, SCOPES)
            
            creds = flow.run_local_server(port=0)
        
        # Intentar guardar el token actualizado (si se desea persistencia local fuera de Git)
        # Si no se define lo contrario, lo guardamos en el default (que ya está en .gitignore)
        try:
            with open(TOKEN_PATH_DEFAULT, 'w') as token_file:
                token_file.write(creds.to_json())
        except: pass

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

def crear_evento_calendar(service_calendar, correo, titulo, descripcion, fecha, jornada_completa=True, metadata=None):
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
    
    # Metadatos Privados para trazabilidad
    if metadata:
        event['extendedProperties'] = {
            'private': metadata
        }

    try:
        event_result = service_calendar.events().insert(calendarId=correo, body=event).execute()
        print(f"Evento creado: {event_result.get('htmlLink')}")
        return event_result
    except HttpError as error:
        print(f"Error creando evento: {error}")
        return None

def limpiar_calendar_fecha(service_calendar, correo, fecha):
    """Elimina eventos de tipo OT en una fecha específica para un técnico."""
    fecha_str = fecha.strftime("%Y-%m-%d")
    t_min = f"{fecha_str}T00:00:00Z"
    t_max = f"{fecha_str}T23:59:59Z"
    
    try:
        events_result = service_calendar.events().list(calendarId=correo, timeMin=t_min, timeMax=t_max,
                                                      singleEvents=True).execute()
        events = events_result.get('items', [])
        for ev in events:
            # Solo borrar si tiene nuestros metadatos o es sospechoso de ser una OT
            # Por ahora borramos todo lo que el usuario mande a limpiar en ese dia
            service_calendar.events().delete(calendarId=correo, eventId=ev['id']).execute()
            print(f"Evento borrado: {ev.get('summary')}")
    except Exception as e:
        print(f"Error limpiando calendario: {e}")

def actualizar_ots_desde_sheets(service_sheets):
    """Lee la planilla de OTs y retorna una lista de diccionarios."""
    try:
        sheet = service_sheets.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID_OTS,
                                    range=RANGE_NAME_OTS).execute()
        values = result.get('values', [])
        if not values: return [], []
        
        headers = values[0]
        data = []
        for row in values[1:]:
            obj = {}
            for i, h in enumerate(headers):
                if i < len(row):
                    obj[h] = row[i]
                else:
                    obj[h] = ""
            data.append(obj)
        return data, headers
    except Exception as e:
        print(f"Error leyendo OTs: {e}")
        return [], []

def actualizar_patrones_desde_sheets(service_sheets):
    """Lee la planilla de Patrones."""
    try:
        sheet = service_sheets.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID_PATRONES,
                                    range=RANGE_NAME_PATRONES).execute()
        values = result.get('values', [])
        if not values: return []
        
        # Estructura simple de patrones
        return values
    except Exception as e:
        print(f"Error leyendo Patrones: {e}")
        return []

def actualizar_vehiculos_desde_sheets(service_sheets):
    """Lee la planilla de Vehículos en el mismo ID de Patrones."""
    try:
        sheet = service_sheets.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID_PATRONES,
                                    range=RANGE_NAME_VEHICULOS).execute()
        values = result.get('values', [])
        if not values or len(values) < 2: return []
        
        # Estructura esperada: Nombre, Dominio, # Asientos
        # La primera fila son encabezados
        vehiculos = []
        for row in values[1:]:
            if len(row) > 0 and str(row[0]).strip() != "":
                 nombre = str(row[0]).strip()
                 asientos_str = str(row[2]).strip() if len(row) > 2 else "1"
                 try: asientos = int(asientos_str)
                 except: asientos = 1
                 vehiculos.append({"nombre": nombre, "asientos": asientos})
        return vehiculos
    except Exception as e:
        print(f"Error leyendo Vehículos: {e}")
        return []
