import os
import json
import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import sys
import statistics
import calendar

# Importar módulos
import extractor
import programar_ots as prog_ots

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, 'datos_cache.json')
CACHE_OTS_PATH = os.path.join(BASE_DIR, 'bd_ots_cache.json')
TECNICOS_CACHE_PATH = os.path.join(BASE_DIR, 'tecnicos_cache.json')

class PlanificacionApp:
    def __init__(self, root, contenedor, on_volver):
        self.root = root
        self.contenedor = contenedor
        self.on_volver = on_volver
        self.today = datetime.date.today()
        self.current_start_date = self.today - datetime.timedelta(days=self.today.weekday())
        
        self.tech_events = {}
        self.technicians_list = []
        self.bd_ots = []
        self.bd_ots_headers = []
        self.tecnicos_info = []
        self.popup_activo = None
        
        self.crear_interfaz()
        self.cargar_tecnicos_cache()
        self.cargar_bd_ots()
        self.cargar_datos()

    def crear_interfaz(self):
        # --- TOP HEADER BAR ---
        self.header_frame = tk.Frame(self.contenedor, bg="#2c3e50", height=60)
        self.header_frame.pack(fill=tk.X, side=tk.TOP)
        self.header_frame.pack_propagate(False)
        
        # Título
        title_lbl = tk.Label(self.header_frame, text="Planificación Semanal", fg="white", bg="#2c3e50", font=("Sege UI", 16, "bold"))
        title_lbl.pack(side=tk.LEFT, padx=20)
        
        # Botones Centrales de Navegación
        nav_frame = tk.Frame(self.header_frame, bg="#2c3e50")
        nav_frame.pack(side=tk.LEFT, padx=50, expand=True)

        btn_style = {"bg": "#ecf0f1", "fg": "#2c3e50", "font": ("Segoe UI", 10, "bold"), "relief": tk.FLAT, "padx": 10, "cursor": "hand2"}

        btn_prev = tk.Button(nav_frame, text="< Semana Anterior", command=lambda: self.cambiar_semana(-7), **btn_style)
        btn_prev.pack(side=tk.LEFT, padx=5)

        btn_hoy = tk.Button(nav_frame, text="HOY", command=self.ir_a_hoy, **btn_style)
        btn_hoy.pack(side=tk.LEFT, padx=5)

        btn_next = tk.Button(nav_frame, text="Semana Siguiente >", command=lambda: self.cambiar_semana(7), **btn_style)
        btn_next.pack(side=tk.LEFT, padx=5)
        
        # Boton volver al menu (antes del sync, a la derecha)
        tk.Button(self.header_frame, text="<- Menu", command=self.on_volver,
                  bg="#7f8c8d", fg="white", font=("Segoe UI", 10, "bold"),
                  relief=tk.FLAT, padx=10, cursor="hand2").pack(side=tk.RIGHT, padx=4, pady=10)

        # Boton Sincronizar a la derecha
        sync_style = {"bg": "#e74c3c", "fg": "white", "font": ("Segoe UI", 10, "bold"), "relief": tk.FLAT, "padx": 15, "cursor": "hand2"}
        self.btn_sync = tk.Button(self.header_frame, text="Sincronizar Cloud", command=self.sincronizar_cloud, **sync_style)
        self.btn_sync.pack(side=tk.RIGHT, padx=8)
        
        # Label de fechas
        self.lbl_rango_fechas = tk.Label(self.contenedor, text="", bg="#f4f4f4", font=("Segoe UI", 12, "bold"), pady=10)
        self.lbl_rango_fechas.pack()

        # --- DATA GRID (Scrollable Canvas) ---
        self.center_frame = tk.Frame(self.contenedor, bg="#f4f4f4")
        self.center_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.center_frame, bg="#ffffff", highlightthickness=0)
        
        # Scrollbars
        self.vsb = ttk.Scrollbar(self.center_frame, orient="vertical", command=self.canvas.yview)
        self.hsb = ttk.Scrollbar(self.center_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        
        self.hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=20, pady=(0,20))
        
        # Frame interno que contiene la grilla de verdad
        self.grid_frame = tk.Frame(self.canvas, bg="#ddd")
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        # --- FOOTER METRICS BAR ---
        self.footer_frame = tk.Frame(self.contenedor, bg="#ecf0f1", height=40)
        self.footer_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.lbl_metrica_semana = tk.Label(self.footer_frame, text="", bg="#ecf0f1", fg="#2c3e50", font=("Segoe UI", 11, "bold"))
        self.lbl_metrica_semana.pack(side=tk.LEFT, padx=30, pady=10)
        
        self.lbl_metrica_mes = tk.Label(self.footer_frame, text="", bg="#ecf0f1", fg="#2c3e50", font=("Segoe UI", 11, "bold"))
        self.lbl_metrica_mes.pack(side=tk.RIGHT, padx=30, pady=10)

    def cargar_tecnicos_cache(self):
        if os.path.exists(TECNICOS_CACHE_PATH):
            with open(TECNICOS_CACHE_PATH, 'r', encoding='utf-8') as f:
                self.tecnicos_info = json.load(f)

    def cargar_bd_ots(self):
        """Carga la base de datos local de OTs desde el cache JSON."""
        if not os.path.exists(CACHE_OTS_PATH):
            return
        with open(CACHE_OTS_PATH, 'r', encoding='utf-8') as f:
            datos = json.load(f)
        if datos:
            self.bd_ots_headers = datos[0]
            self.bd_ots = datos[1:]

    def cargar_datos(self):
        if not os.path.exists(CACHE_PATH):
            messagebox.showinfo("Sin Datos", "No se encontró caché local. Haz clic en 'Sincronizar Cloud' para descargar los datos por primera vez.")
            self.tech_events = {}
            self.technicians_list = []
            self.dibujar_grilla()
            return
            
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            eventos = json.load(f)
            
        self.procesar_eventos(eventos)
        self.dibujar_grilla()

    def procesar_eventos(self, eventos):
        self.tech_events = {}
        todos_tecnicos = set()
        
        for ev in eventos:
            tech = str(ev.get("Técnico", "Desconocido")).strip()
            todos_tecnicos.add(tech)
            if tech not in self.tech_events:
                self.tech_events[tech] = {}
                
            start_str = ev.get("Inicio", "")
            end_str = ev.get("Fin", "")
            summary = ev.get("Evento", "")
            
            if not start_str or not end_str:
                continue
                
            # Extraer OT y Cliente (corta hasta el primer paréntesis de cierre para ignorar guiones en el nombre)
            idx_parentesis = summary.find(')')
            if idx_parentesis != -1:
                ot = summary[:idx_parentesis+1].strip()
            else:
                ot = summary.split('-')[0].strip()
                
            if not ot:
                ot = summary.strip() # Por si queda vacío
                
            # Check si es todo el día (sin hora) o si tiene hora (ISO 8601 con 'T')
            es_todo_el_dia = "T" not in start_str
            
            try:
                if es_todo_el_dia:
                    start_date = datetime.datetime.strptime(start_str, "%Y-%m-%d").date()
                    end_date = datetime.datetime.strptime(end_str, "%Y-%m-%d").date()
                    
                    # Google Calendar All-Day end date es *exclusivo* (el día final no se incluye, marca el límite)
                    dias_duracion = (end_date - start_date).days
                    if dias_duracion <= 0: dias_duracion = 1
                    
                    for i in range(dias_duracion):
                        d = start_date + datetime.timedelta(days=i)
                        date_key = d.strftime("%Y-%m-%d")
                        # Para todo el día, asumimos jornada laboral de 9h, si es fin de semana suma 0
                        is_weekend = d.weekday() >= 5
                        horas_dia = 0.0 if is_weekend else 9.0
                        desc = f"07:00-16:00 | {ot}"
                        # Todo el día: inicio 07:00 (700), fin 16:00 (1600)
                        # Identificar OT
                        es_ot = (ot and ot[0].isdigit()) or "RESERVA" in summary.upper()

                        self.tech_events[tech].setdefault(date_key, []).append({
                            "sort": 700, 
                            "sort_end": 1600, 
                            "text": desc, 
                            "horas": horas_dia,
                            "es_ot": es_ot,
                            "original_text": summary
                        })
                        
                else:
                    # Evento con hora (ej: 2026-02-18T07:00:00-03:00)
                    start_dt = datetime.datetime.fromisoformat(start_str)
                    end_dt = datetime.datetime.fromisoformat(end_str)
                    start_date = start_dt.date()
                    end_date = end_dt.date()
                    
                    dias_duracion = (end_date - start_date).days
                    
                    for i in range(dias_duracion + 1):
                        d = start_date + datetime.timedelta(days=i)
                        date_key = d.strftime("%Y-%m-%d")
                        is_weekend = d.weekday() >= 5
                        
                        horas_dia = 0.0
                        
                        if i == 0 and dias_duracion == 0:
                            # Mismo día
                            t1 = start_dt.strftime("%H:%M")
                            t2 = end_dt.strftime("%H:%M")
                            desc = f"{t1}-{t2} | {ot}"
                            sort_val = int(start_dt.strftime("%H%M"))
                            sort_end_val = int(end_dt.strftime("%H%M"))
                            if not is_weekend:
                                h_s = start_dt.hour + start_dt.minute/60.0
                                h_e = end_dt.hour + end_dt.minute/60.0
                                lower = max(7.0, h_s)
                                upper = min(16.0, h_e)
                                horas_dia = max(0.0, upper - lower)
                                
                        elif i == 0:
                            t1 = start_dt.strftime("%H:%M")
                            desc = f"{t1}-... | {ot}"
                            sort_val = int(start_dt.strftime("%H%M"))
                            sort_end_val = 2359  # Continúa, tratar como el último del día
                            if not is_weekend:
                                h_s = start_dt.hour + start_dt.minute/60.0
                                lower = max(7.0, h_s)
                                horas_dia = max(0.0, 16.0 - lower)
                                
                        elif i == dias_duracion:
                            t2 = end_dt.strftime("%H:%M")
                            desc = f"...-{t2} | {ot}"
                            sort_val = 0
                            sort_end_val = int(end_dt.strftime("%H%M"))
                            if not is_weekend:
                                h_e = end_dt.hour + end_dt.minute/60.0
                                upper = min(16.0, h_e)
                                horas_dia = max(0.0, upper - 7.0)
                        else:
                            desc = f"Día entero | {ot}"
                            sort_val = 0
                            sort_end_val = 2359
                            if not is_weekend: horas_dia = 9.0
                            
                        # Identificar si es OT: empieza con número o contiene "RESERVA"
                        es_ot = (ot and ot[0].isdigit()) or "RESERVA" in summary.upper()

                        self.tech_events[tech].setdefault(date_key, []).append({
                            "sort": sort_val, 
                            "sort_end": sort_end_val, 
                            "text": desc, 
                            "horas": horas_dia,
                            "es_ot": es_ot,
                            "original_text": summary
                        })
                        
            except Exception as e:
                print(f"Error procesando evento {summary}: {e}")
                
        # Ordenamos la lista de técnicos y los eventos de cada día por hora inicio, desempatando por hora fin
        self.technicians_list = sorted(list(todos_tecnicos))
        for t in self.tech_events:
            for d in self.tech_events[t]:
                self.tech_events[t][d].sort(key=lambda x: (x["sort"], x.get("sort_end", 9999)))

    def dibujar_grilla(self):
        # Limpiar frame
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        # Días de la semana
        fechas_semana = [self.current_start_date + datetime.timedelta(days=i) for i in range(7)]
        
        # Etiqueta de rango
        d1 = fechas_semana[0].strftime("%d/%m")
        d2 = fechas_semana[6].strftime("%d/%m/%Y")
        self.lbl_rango_fechas.config(text=f"Semana del {d1} al {d2}")

        # Estilos Headers
        header_font = ("Segoe UI", 11, "bold")
        
        # -- DIBUJAR ENCABEZADOS (Fila 0) --
        # Esquina superior izquierda (vacío)
        tk.Label(self.grid_frame, text="Técnicos / Días", bg="#34495e", fg="white", font=header_font, width=20, height=2).grid(row=0, column=0, padx=1, pady=1, sticky="nsew")
        
        dias_nombres = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]
        
        for col, (fecha, nombre_dia) in enumerate(zip(fechas_semana, dias_nombres), start=1):
            dia_str = fecha.strftime("%d/%m")
            texto_col = f"{nombre_dia}\n{dia_str}"
            
            # Sábado (5) y Domingo (6) en gris más oscuro
            is_weekend = fecha.weekday() >= 5
            bg_color = "#95a5a6" if is_weekend else "#34495e"
            if fecha == self.today:
                bg_color = "#27ae60" # Color verde si es HOY
                
            tk.Label(self.grid_frame, text=texto_col, bg=bg_color, fg="white", font=header_font, width=22).grid(row=0, column=col, padx=1, pady=1, sticky="nsew")

        # -- DIBUJAR FILAS DE TÉCNICOS --
        for row, tech in enumerate(self.technicians_list, start=1):
            # Nombre del técnico
            tk.Label(self.grid_frame, text=tech, bg="#ecf0f1", fg="black", font=("Segoe UI", 10, "bold"), anchor="w", padx=10).grid(row=row, column=0, padx=1, pady=1, sticky="nsew")
            
            for col, fecha in enumerate(fechas_semana, start=1):
                date_key = fecha.strftime("%Y-%m-%d")
                eventos_dia = self.tech_events.get(tech, {}).get(date_key, [])
                
                is_weekend = fecha.weekday() >= 5
                
                # Texto
                text_lines = [ev["text"] for ev in eventos_dia]
                display_text = "\n\n".join(text_lines) if text_lines else ""
                
                # Color de fondo (gris para fin de semana o celda con datos vs vacía)
                if is_weekend:
                    bg_color = "#e0e0e0" # Gris de fin de semana
                    if display_text:
                        bg_color = "#d5dbdb" # Un poco menos gris si hay actividad
                else:
                    bg_color = "#ffffff"
                    if display_text:
                        bg_color = "#e8f8f5" # Ligero tono verde agua si hay actividad
                        
                cursor_style = "hand2" if display_text else "arrow"
                lbl = tk.Label(self.grid_frame, text=display_text, bg=bg_color, font=("Segoe UI", 9), anchor="nw", justify="left", wraplength=180, pady=5, padx=5, cursor=cursor_style)
                lbl.grid(row=row, column=col, padx=1, pady=1, sticky="nsew")
                
                if display_text:
                    # Capturamos variables en el closure para que no se sobreescriban
                    lbl.bind("<Button-1>", lambda e, t=tech, d=date_key, ev=eventos_dia: self.mostrar_popup_ots(e, t, d, ev))

        # Refrescar Métricas
        self.calcular_metricas(fechas_semana)

    def calcular_metricas(self, fechas_semana):
        if not self.technicians_list:
            self.lbl_metrica_semana.config(text="Ocupación Semanal: N/A")
            self.lbl_metrica_mes.config(text="Ocupación Mensual: N/A")
            return

        # 1. Determinar el "mes objetivo" basado en los días hábiles de la semana vista
        fechas_habiles = fechas_semana[:5]
        ym_list = [(f.year, f.month) for f in fechas_habiles]
        target_year, target_month = statistics.mode(ym_list)
        
        # 2. Capacidad Semanal
        capacidad_semana = len(self.technicians_list) * 5 * 9.0
        
        # 3. Capacidad Mensual
        p_month = calendar.monthcalendar(target_year, target_month)
        work_days_month = sum(1 for week in p_month for d_dia in week[:5] if d_dia != 0)
        capacidad_mes = len(self.technicians_list) * work_days_month * 9.0
        
        # 4. Calcular Ocupación de la Semana Vista
        horas_us_sem = 0.0
        horas_ot_sem = 0.0
        for tech in self.technicians_list:
            for f in fechas_habiles:
                dk = f.strftime("%Y-%m-%d")
                evs = self.tech_events.get(tech, {}).get(dk, [])
                h_dia = sum(e.get("horas", 0.0) for e in evs)
                h_ot = sum(e.get("horas", 0.0) for e in evs if e.get("es_ot"))
                horas_us_sem += min(h_dia, 9.0)
                horas_ot_sem += min(h_ot, 9.0)
                
        pct_sem = (horas_us_sem / capacidad_semana * 100) if capacidad_semana > 0 else 0
        pct_ot_sem = (horas_ot_sem / capacidad_semana * 100) if capacidad_semana > 0 else 0

        # 5. Calcular Ocupación del Mes Objetivo Total
        horas_us_mes = 0.0
        horas_ot_mes = 0.0
        for tech in self.technicians_list:
            for dk, evs in self.tech_events.get(tech, {}).items():
                dt = datetime.datetime.strptime(dk, "%Y-%m-%d").date()
                if dt.year == target_year and dt.month == target_month and dt.weekday() < 5:
                    h_dia = sum(e.get("horas", 0.0) for e in evs)
                    h_ot = sum(e.get("horas", 0.0) for e in evs if e.get("es_ot"))
                    horas_us_mes += min(h_dia, 9.0)
                    horas_ot_mes += min(h_ot, 9.0)
                    
        pct_mes = (horas_us_mes / capacidad_mes * 100) if capacidad_mes > 0 else 0
        pct_ot_mes = (horas_ot_mes / capacidad_mes * 100) if capacidad_mes > 0 else 0
        
        # Actualizar Labels
        meses_nombres = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        nombre_mes = meses_nombres[target_month - 1]
        
        self.lbl_metrica_semana.config(text=f"Ocupación Semanal Total: {pct_sem:.1f}% (Solo OTs: {pct_ot_sem:.1f}%)")
        self.lbl_metrica_mes.config(text=f"Ocupación de {nombre_mes} Total: {pct_mes:.1f}% (Solo OTs: {pct_ot_mes:.1f}%)")

    def mostrar_popup_ots(self, event, tech, date_key, eventos_dia):
        """Muestra un popup flotante con el resumen de partidas de las OTs del día."""
        # Cerrar popup previo si existe
        if self.popup_activo and self.popup_activo.winfo_exists():
            self.popup_activo.destroy()
        
        # 1. Extraer todos los números de OT del día (considerando múltiples OTs con /)
        numeros_ot = set()
        for ev in eventos_dia:
            texto = ev.get("text", "")
            # Extraer la parte de la OT (después del '| ')
            if '|' in texto:
                ot_parte = texto.split('|', 1)[1].strip()
            else:
                ot_parte = texto
            
            # Limpiar el texto: quitar lo que está entre paréntesis para quedarnos sólo con N°s
            # Formato esperado: "NNNNN (CLIENTE) / MMMMM (CLIENTE)"
            # Extraemos solo la parte numérica antes del primer paréntesis de cada segmento
            segmentos = ot_parte.split('/')
            for seg in segmentos:
                num = seg.strip().split('(')[0].strip()
                if num.isdigit():
                    numeros_ot.add(num)
        
        if not numeros_ot:
            return  # No hay OTs reconocibles, no mostramos nada
        
        # 2. Buscar en la BD de OTs
        if not self.bd_ots or not self.bd_ots_headers:
            messagebox.showinfo("Sin BD", "No hay BD de OTs en caché. Sincronicé primero con el botón 'Sincronizar Cloud'.")
            return
        
        # Detectar el índice de las columnas que necesitamos (B=1, F=5, M=12)
        try:
            header = self.bd_ots_headers
            idx_ot = 1      # Columna B: N° OT
            idx_trab = 5    # Columna F: Trabajo a Ejecutar
            idx_pts = 12    # Columna M: Puntos de Calibración
        except Exception:
            return
        
        # Filtrar filas que pertenecen a las OTs del día
        filas_coincidentes = []
        for fila in self.bd_ots:
            if len(fila) > idx_ot:
                nro = str(fila[idx_ot]).strip()
                if nro in numeros_ot:
                    trabajo = fila[idx_trab].strip() if len(fila) > idx_trab else ''
                    puntos = fila[idx_pts].strip() if len(fila) > idx_pts else ''
                    if trabajo or puntos:  # Solo incluir si tiene al menos uno
                        filas_coincidentes.append((trabajo, puntos))
        
        # 3. Agrupar por Trabajo + Puntos y contar partidas
        conteo = {}
        for trabajo, puntos in filas_coincidentes:
            clave = (trabajo, puntos)
            conteo[clave] = conteo.get(clave, 0) + 1
        
        # 4. Construir el popup
        popup = tk.Toplevel(self.root)
        self.popup_activo = popup
        popup.overrideredirect(True)   # Sin barra de título de Windows
        popup.attributes('-topmost', True)
        
        # Posicionar junto al mouse
        x = event.x_root + 10
        y = event.y_root + 10
        
        # Frame principal con borde visual
        outer = tk.Frame(popup, bg="#2c3e50", padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)
        
        inner = tk.Frame(outer, bg="#ffffff")
        inner.pack(fill=tk.BOTH, expand=True)
        
        # Título del popup
        fecha_dt = datetime.datetime.strptime(date_key, "%Y-%m-%d").date()
        titulo_txt = f"{tech}  ·  {fecha_dt.strftime('%A %d/%m').capitalize()}"
        tk.Label(inner, text=titulo_txt, bg="#2c3e50", fg="white",
                 font=("Segoe UI", 10, "bold"), pady=8, padx=12, anchor="w").pack(fill=tk.X)
        
        ot_lista = ", ".join(sorted(numeros_ot))
        tk.Label(inner, text=f"OTs: {ot_lista}", bg="#ecf0f1", fg="#555",
                 font=("Segoe UI", 9), pady=4, padx=12, anchor="w").pack(fill=tk.X)
        
        # Tabla de partidas
        tabla_frame = tk.Frame(inner, bg="#ffffff")
        tabla_frame.pack(fill=tk.BOTH, padx=10, pady=8)
        
        # Encabezados de la tabla
        enc_style = {"bg": "#34495e", "fg": "white", "font": ("Segoe UI", 9, "bold"), "pady": 4, "padx": 8}
        tk.Label(tabla_frame, text="Trabajo a Ejecutar", **enc_style).grid(row=0, column=0, sticky="ew", padx=1, pady=1)
        tk.Label(tabla_frame, text="Puntos de Cal.", **enc_style).grid(row=0, column=1, sticky="ew", padx=1, pady=1)
        tk.Label(tabla_frame, text="Partidas", **enc_style).grid(row=0, column=2, sticky="ew", padx=1, pady=1)
        
        if conteo:
            for i, ((trabajo, puntos), cantidad) in enumerate(sorted(conteo.items()), start=1):
                bg = "#f9f9f9" if i % 2 == 0 else "#ffffff"
                fila_style = {"bg": bg, "font": ("Segoe UI", 9), "pady": 3, "padx": 8}
                tk.Label(tabla_frame, text=trabajo or "—", anchor="w", **fila_style).grid(row=i, column=0, sticky="ew", padx=1, pady=1)
                tk.Label(tabla_frame, text=puntos or "—", **fila_style).grid(row=i, column=1, sticky="ew", padx=1, pady=1)
                tk.Label(tabla_frame, text=str(cantidad), **fila_style).grid(row=i, column=2, sticky="ew", padx=1, pady=1)
        else:
            tk.Label(inner, text="Sin partidas en la BD para estas OTs.", bg="#ffffff",
                     fg="#888", font=("Segoe UI", 9, "italic"), pady=6, padx=12).pack()
        
        # Total general
        total = sum(conteo.values())
        tk.Label(inner, text=f"Total de partidas: {total}", bg="#ecf0f1", fg="#2c3e50",
                 font=("Segoe UI", 9, "bold"), pady=6, padx=12, anchor="e").pack(fill=tk.X)
        
        # Calcular posición inteligente: evitar que el popup se salga de la pantalla
        popup.update_idletasks()
        popup_w = popup.winfo_reqwidth()
        popup_h = popup.winfo_reqheight()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        
        # Ajustar X: si no cabe a la derecha, lo ponemos a la izquierda del cursor
        if x + popup_w > screen_w - 10:
            x = event.x_root - popup_w - 10
        # Ajustar Y: si no cabe abajo, lo ponemos arriba del cursor
        if y + popup_h > screen_h - 40:  # -40 por barra de tareas de Windows
            y = event.y_root - popup_h - 10
        # Asegurar que no se vaya fuera del borde superior/izquierdo
        x = max(5, x)
        y = max(5, y)
        
        popup.geometry(f"+{x}+{y}")
        
        # Cerrar al perder foco
        popup.bind("<FocusOut>", lambda e: popup.destroy() if popup.winfo_exists() else None)
        popup.focus_set()

    def cambiar_semana(self, dias):
        self.current_start_date += datetime.timedelta(days=dias)
        self.dibujar_grilla()

    def ir_a_hoy(self):
        self.current_start_date = self.today - datetime.timedelta(days=self.today.weekday())
        self.dibujar_grilla()

    def sincronizar_cloud(self):
        self.btn_sync.config(text="Sincronizando...", state=tk.DISABLED)
        # Usamos un Thread para no congelar la ventana mientras se conecta a Google
        threading.Thread(target=self._hilo_sincronizacion).start()

    def _hilo_sincronizacion(self):
        try:
            # Llama a todo el proceso original del extractor
            extractor.principal()
            
            # Forzamos refresco gráfico desde el hilo principal
            self.root.after(0, self._al_terminar_sync)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Fallo en la sincronización conectando a Google: {e}"))
            self.root.after(0, lambda: self.btn_sync.config(text="Sincronizar Cloud  ⟳", state=tk.NORMAL))

    def _al_terminar_sync(self):
        self.btn_sync.config(text="Sincronizar Cloud", state=tk.NORMAL)
        self.cargar_bd_ots()
        self.cargar_tecnicos_cache()
        self.cargar_datos()
        # Notificación eliminada por petición del usuario


# =====================================================
# MENU PRINCIPAL
# =====================================================
class MenuPrincipal:
    def __init__(self, root):
        self.root = root
        self.root.title("App Planificacion Akrimet")
        self.root.resizable(False, False)
        self._mostrar_menu()

    def _limpiar(self):
        for w in self.root.winfo_children():
            w.destroy()

    def _mostrar_menu(self):
        self._limpiar()
        self.root.geometry("600x420")
        self.root.resizable(False, False)
        self.root.configure(bg="#2c3e50")

        tk.Label(self.root, text="App Planificacion", bg="#2c3e50", fg="white",
                 font=("Segoe UI", 28, "bold")).pack(pady=(45, 6))
        tk.Label(self.root, text="Sistema de Gestion de Agenda Tecnica",
                 bg="#2c3e50", fg="#95a5a6",
                 font=("Segoe UI", 12)).pack(pady=(0, 40))

        tk.Button(self.root, text="  Planificacion Semanal",
                  command=self._abrir_planificacion,
                  bg="#3498db", fg="white", font=("Segoe UI", 14, "bold"),
                  relief=tk.FLAT, cursor="hand2", width=30, pady=12).pack(pady=8)

        tk.Button(self.root, text="  Programar OTs",
                  command=self._abrir_programar,
                  bg="#27ae60", fg="white", font=("Segoe UI", 14, "bold"),
                  relief=tk.FLAT, cursor="hand2", width=30, pady=12).pack(pady=8)

        self.btn_sync_menu = tk.Button(self.root, text="  Sincronizar Cloud  ⟳",
                  command=self.sincronizar_cloud,
                  bg="#e74c3c", fg="white", font=("Segoe UI", 13, "bold"),
                  relief=tk.FLAT, cursor="hand2", width=30, pady=10)
        self.btn_sync_menu.pack(pady=(20, 8))

    def sincronizar_cloud(self):
        self.btn_sync_menu.config(text="Sincronizando...", state=tk.DISABLED)
        threading.Thread(target=self._hilo_sync).start()

    def _hilo_sync(self):
        try:
            extractor.principal()
            self.root.after(0, lambda: self.btn_sync_menu.config(text="  Sincronizar Cloud  ⟳", state=tk.NORMAL))
        except Exception as e:
            msg = f"Error en la sincronización: {e}"
            self.root.after(0, lambda: messagebox.showerror("Error", msg))
            self.root.after(0, lambda: self.btn_sync_menu.config(text="  Sincronizar Cloud  ⟳", state=tk.NORMAL))

    def _abrir_planificacion(self):
        self._limpiar()
        self.root.geometry("1400x800")
        self.root.resizable(True, True)
        self.root.configure(bg="#f4f4f4")
        contenedor = tk.Frame(self.root, bg="#f4f4f4")
        contenedor.pack(fill=tk.BOTH, expand=True)
        PlanificacionApp(self.root, contenedor, self._mostrar_menu)

    def _abrir_programar(self):
        tech_events, tecnicos_info, bd_ots, bd_ots_hdrs = {}, [], [], []

        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                evs = json.load(f)
            # Reusar procesar_eventos sin lanzar la UI completa
            tmp = PlanificacionApp.__new__(PlanificacionApp)
            tmp.root = self.root
            tmp.today = datetime.date.today()
            tmp.current_start_date = tmp.today - datetime.timedelta(days=tmp.today.weekday())
            tmp.tech_events, tmp.technicians_list = {}, []
            tmp.bd_ots, tmp.bd_ots_headers, tmp.tecnicos_info = [], [], []
            tmp.popup_activo = None
            tmp.procesar_eventos(evs)
            tech_events = tmp.tech_events

        if os.path.exists(CACHE_OTS_PATH):
            with open(CACHE_OTS_PATH, 'r', encoding='utf-8') as f:
                datos = json.load(f)
            bd_ots_hdrs = datos[0] if datos else []
            bd_ots = datos[1:] if len(datos) > 1 else []

        if os.path.exists(TECNICOS_CACHE_PATH):
            with open(TECNICOS_CACHE_PATH, 'r', encoding='utf-8') as f:
                tecnicos_info = json.load(f)

        if not bd_ots:
            messagebox.showinfo("Sin Datos",
                "No hay datos de OTs en cache. Sincroniza primero desde Planificacion Semanal.")
            return

        self._limpiar()
        self.root.geometry("1200x750")
        self.root.resizable(True, True)
        self.root.configure(bg="#f4f4f4")
        contenedor = tk.Frame(self.root, bg="#f4f4f4")
        contenedor.pack(fill=tk.BOTH, expand=True)
        prog_ots.ProgramarOTsModule(
            self.root, contenedor,
            tech_events, tecnicos_info,
            bd_ots, bd_ots_hdrs,
            self._mostrar_menu
        )


if __name__ == "__main__":
    root = tk.Tk()
    MenuPrincipal(root)
    root.mainloop()
