import unicodedata
import re

def normalizar_texto(s):
    """
    Elimina acentos, convierte a minúsculas y limpia espacios.
    Útil para comparaciones de nombres de técnicos y búsqueda de strings.
    """
    if not s: return ""
    s = str(s).lower().strip()
    # Eliminar acentos usando normalización NFD
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return s

def extraer_ots(texto):
    """
    Extrae todos los números de 3 o más dígitos de un texto.
    Ignora P1, P2 (puntos de calibración) pero atrapa 8131, 8598, etc.
    """
    if not texto: return set()
    return set(re.findall(r'\d{3,}', str(texto)))

def evaluar_conflicto(ots_por_tecnico):
    """
    Decide si un grupo de técnicos tiene un conflicto de patrones.
    Recibe: { t_name_norm: set(ot_numbers) }
    Retorna: (hay_conflicto, o_compartida) 
    - hay_conflicto: True si no comparten OT común.
    - o_compartida: Set de OTs comunes (si existe).
    """
    if len(ots_por_tecnico) <= 1:
        return False, set()

    tech_sets = list(ots_por_tecnico.values())
    
    # Intersección de TODOS los técnicos
    interseccion = tech_sets[0]
    for s in tech_sets[1:]:
        interseccion = interseccion.intersection(s)
    
    if interseccion:
        # Tienen al menos una OT común -> Uso compartido legítimo
        return False, interseccion
    else:
        # No hay OT común entre todos -> Conflicto de duplicación
        return True, set()

# --- ÍNDICES DE COLUMNAS DE LA BD DE OTS (SPREADSHEET) ---
IDX_ESTADO = 0   # Columna A (Estatus Trabajos Campo)
IDX_OT    = 1    # Columna B
IDX_CLIE  = 3    # Columna D
IDX_TRAB  = 5    # Columna F
IDX_ID    = 8    # Columna I
IDX_MODELO = 9   # Columna J
IDX_MARCA = 10   # Columna K
IDX_SERIE = 11   # Columna L
IDX_PTS   = 12   # Columna M
IDX_FECHA = 16   # Columna Q
IDX_DIRECCION = 17 # Columna R

# --- ÍNDICES DE COLUMNAS DE LA BD DE PATRONES ---
IDX_PATRON_NOMBRE = 0
IDX_PATRON_TRABAJOS = 1
IDX_PATRON_CLASE = 10  # Columna K
IDX_PATRON_RANGO = 13
