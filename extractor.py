import os.path
import datetime
import pandas as pd
import json
import re
import uuid
import utils
import threading

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import google.auth.exceptions
from data_manager import DataManager

# Configuración de Rutas base para PyInstaller
import sys

def get_base_path():
    if getattr(sys, 'frozen', False):
        # Directorio donde está el .exe (para archivos persistentes como token.json)
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_internal_path():
    if getattr(sys, 'frozen', False):
        # Directorio temporal interno de PyInstaller (para archivos empaquetados)
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_user_data_path():
    r"""
    Retorna la ruta para archivos de datos persistentes del usuario (perfil local).
    En Windows usa %LOCALAPPDATA%\AkrimetPlanner.
    """
    if os.name == 'nt': # Windows
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~\\AppData\\Local')
        path = os.path.join(base, 'AkrimetPlanner')
    else: # Otros (Linux/Mac)
        path = os.path.expanduser('~/.akrimetplanner')
    
    try:
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
    except Exception as e:
        print(f"Error creando directorio de datos de usuario: {e}")
        # Fallback al directorio actual si falla la creación (poco probable)
        return get_base_path()
        
    return path

BASE_DIR = get_base_path()
INTERNAL_DIR = get_internal_path()
USER_DATA_DIR = get_user_data_path()

# Archivo de sesión (persiste en el perfil del usuario, fuera del directorio del exe)
TOKEN_PATH_DEFAULT = os.path.join(USER_DATA_DIR, 'token.json')
# Secreto de la app (empaquetado adentro del exe)
CREDENTIALS_PATH_DEFAULT = os.path.join(INTERNAL_DIR, 'credentials.json')

# Si modificas estos rangos (SCOPES), borra el archivo token.json.
SCOPES = [
    'https://www.googleapis.com/auth/calendar',  # Lectura + Escritura en Calendar
    'https://www.googleapis.com/auth/spreadsheets'
]

# Lock para evitar que múltiples hilos disparen el flujo OAuth simultáneamente
_auth_lock = threading.Lock()

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
    
    token_candidates = [
        TOKEN_PATH_DEFAULT,
        os.path.join(BASE_DIR, 'token.json'),
        os.path.join(os.getcwd(), 'token.json')
    ]
    
    if not creds:
        for t_path in token_candidates:
            if os.path.exists(t_path):
                try:
                    creds = Credentials.from_authorized_user_file(t_path, SCOPES)
                    if creds:
                        print(f"[Auth] Token cargado exitosamente desde: {t_path}")
                        break
                except Exception as t_err:
                    print(f"[Auth] Error al leer token desde {t_path}: {t_err}")
        
    # Si no hay credenciales válidas, le pide al usuario que inicie sesión.
    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except Exception as re_err:
                print(f"[Auth] Error al refrescar token: {re_err}. Re-autenticando...")
                creds = None
                
        if not refreshed:
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
                    raise FileNotFoundError("Error de compilación: No se empaquetó el credentials.json en el ejecutable.")
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH_DEFAULT, SCOPES)
            
            with _auth_lock:
                # Re-chequeo del token dentro del lock por si otro hilo ya lo generó
                if os.path.exists(TOKEN_PATH_DEFAULT):
                    try:
                        creds = Credentials.from_authorized_user_file(TOKEN_PATH_DEFAULT, SCOPES)
                        if creds and creds.valid:
                            pass # Usar estas credenciales
                        else:
                            creds = flow.run_local_server(port=0)
                    except:
                        creds = flow.run_local_server(port=0)
                else:
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

def _safe_get_google_services():
    """Wrapper con auto-refresco de token. Si falla por TransportError, reintenta una vez."""
    try:
        return get_google_services()
    except google.auth.exceptions.TransportError as e:
        print(f"[Auth] TransportError detectado, reintentando refresco de token: {e}")
        try:
            if os.path.exists(TOKEN_PATH_DEFAULT):
                os.remove(TOKEN_PATH_DEFAULT)
            return get_google_services()
        except Exception as retry_err:
            raise RuntimeError(f"No se pudo reconectar con Google: {retry_err}")

def get_current_user_profile(svc_cal):
    """
    Obtiene el perfil del usuario autenticado usando el calendario primario.
    No requiere scopes adicionales (ya tenemos 'calendar').
    Retorna: { "email": ..., "nombre": ... }
    """
    try:
        primary = svc_cal.calendars().get(calendarId='primary').execute()
        return {
            "email": primary.get('id', ''),
            "nombre": primary.get('summary', primary.get('id', 'Usuario'))
        }
    except Exception as e:
        print(f"[Auth] No se pudo obtener perfil de usuario: {e}")
        return {"email": "", "nombre": "Usuario desconocido"}

def obtener_email_usuario(svc_cal):
    """Obtiene el email del usuario autenticado consultando el ID del calendario principal."""
    try:
        cal = svc_cal.calendars().get(calendarId='primary').execute()
        return cal.get('id', '')
    except Exception as e:
        print(f"[Auth] Error al obtener email de usuario: {e}")
        return ""

def obtener_calendarios_usuario(svc_cal):
    """
    Obtiene todos los calendarios accesibles por el usuario autenticado.
    Filtra solo aquellos donde el usuario tiene permisos de escritura (writer u owner).
    """
    try:
        calendars = []
        page_token = None
        while True:
            calendar_list = svc_cal.calendarList().list(pageToken=page_token).execute()
            for entry in calendar_list.get('items', []):
                summary = entry.get('summary', '')
                cal_id = entry.get('id', '')
                
                # Filtrar calendarios de sistema o no deseados
                if "Cumpleaños" in summary or "Birthdays" in summary:
                    continue
                if "#contacts@group.v.calendar.google.com" in cal_id:
                    continue
                if "holiday@group.v.calendar.google.com" in cal_id:
                    continue

                role = entry.get('accessRole', '')
                if role in ['writer', 'owner']:
                    calendars.append({
                        "id": cal_id,
                        "summary": summary,
                        "color": entry.get('backgroundColor', '#000000')
                    })
            page_token = calendar_list.get('nextPageToken')
            if not page_token:
                break
        return calendars
    except Exception as e:
        print(f"[Auth] Error al obtener lista de calendarios: {e}")
        return []

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
