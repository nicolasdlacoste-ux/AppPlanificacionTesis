
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

class BatchEditarParams(BaseModel):
    event_ids: List[str]
    delta_dias: Optional[int] = None
    correo_destino: Optional[str] = None
    patrones: Optional[List[str]] = None
    ots: Optional[List[str]] = None
    vehiculo: Optional[str] = None

# This patch file just holds the definition so we can use multi_replace_file_content safely later.

