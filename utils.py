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
