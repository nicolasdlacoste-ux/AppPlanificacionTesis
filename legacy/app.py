import os
import json
import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import sys
import statistics
import calendar
import re

# Importar módulos
import extractor
import programar_ots as prog_ots
import gestion_proyectos as gest_proy
import utils
from data_manager import DataManager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, 'datos_cache.json')
CACHE_OTS_PATH = os.path.join(BASE_DIR, 'bd_ots_cache.json')
TECNICOS_CACHE_PATH = os.path.join(BASE_DIR, 'tecnicos_cache.json')

# --- CLASE TOOLTIP PARA UX MODERNA ---
class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text: return
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 25
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                      background="#34495e", foreground="white", relief=tk.SOLID, borderwidth=1,
                      font=("Segoe UI", 9), padx=10, pady=5)
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        tw = self.tip_window
        self.tip_window = None
        if tw: tw.destroy()

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
        self.db = DataManager()
        self.db.migrar_desde_json(BASE_DIR)
        
        self.popup_activo = None
        self.evento_seleccionado = None  # Almacena {ev, tech, date}
        self.celda_seleccionada_f = None # Referencia al widget resaltado
        self.var_solo_ots = tk.BooleanVar(value=True)
        
        self.crear_interfaz()
        # Iniciar carga asíncrona para no bloquear el inicio
        self.cargar_todo_async()

    def cargar_todo_async(self):
        """Inicia un hilo para cargar todos los datos de la DB sin congelar la UI."""
        self.lbl_rango_fechas.config(text="🔄 Cargando datos desde la base de datos...", fg="#e67e22")
        threading.Thread(target=self._hilo_carga_inicial, daemon=True).start()

    def _hilo_carga_inicial(self):
        try:
            self.cargar_tecnicos_cache()
            self.cargar_bd_ots()
            self.cargar_datos(sync_ui=False) # Cargar solo datos en memoria
            
            # Al terminar, refrescar la UI en el hilo principal
            self.root.after(0, self.dibujar_grilla)
        except Exception as e:
            msg = f"Error en carga inicial: {e}"
            self.root.after(0, lambda: messagebox.showerror("Error", msg))

    def mostrar_solucionador(self):
        # Crear un "pseudo-paquete" semanal dinámico basado en la vista actual
        fechas = [self.current_start_date + datetime.timedelta(days=i) for i in range(7)]
        eventos_semana = []
        for f in fechas: 
            eventos_semana.append({"Inicio": f.strftime("%Y-%m-%d")})
            
        paquete_semana = {"eventos": eventos_semana}

        import conflictos_ui
        conflictos_ui.ConflictosModule(self.root, paquete_semana, self.tecnicos_info, self.tech_events, 
                                       self.volver_desde_modulo, modo_semanal=True, 
                                       fecha_ref=self.current_start_date, bd_ots=self.bd_ots)

    def volver_desde_modulo(self):
        for w in self.contenedor.winfo_children(): w.destroy()
        self.crear_interfaz()
        self.dibujar_grilla()

    def crear_interfaz(self):
        # Limpiar contenedor para evitar solapamientos al volver de otros módulos
        for w in self.contenedor.winfo_children(): w.destroy()
        
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

        # Botón Gestión Proyectos (NUEVO)
        btn_gest = tk.Button(nav_frame, text="📁 Gestión Proyectos", command=self.mostrar_gestion_proyectos, 
                             bg="#3498db", fg="white", font=("Segoe UI", 10, "bold"), relief=tk.FLAT, padx=15, cursor="hand2")
        btn_gest.pack(side=tk.LEFT, padx=10)

        # Botón Solucionador Global
        btn_conf = tk.Button(nav_frame, text="🚨 Solucionador", command=self.mostrar_solucionador, 
                             bg="#e67e22", fg="white", font=("Segoe UI", 10, "bold"), relief=tk.FLAT, padx=15, cursor="hand2")
        btn_conf.pack(side=tk.LEFT, padx=10)

        # Filtro Solo OTs (NUEVO)
        chk_ots = tk.Checkbutton(nav_frame, text="🔍 Solo OTs", variable=self.var_solo_ots, 
                                 command=self.dibujar_grilla, bg="#2c3e50", fg="white", 
                                 selectcolor="#2c3e50", activebackground="#2c3e50", 
                                 activeforeground="white", font=("Segoe UI", 10, "bold"), cursor="hand2")
        chk_ots.pack(side=tk.LEFT, padx=10)
        
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
        
        # Vincular rueda del mouse globalmente con lógica de detección de contexto
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        
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
        self.tecnicos_info = self.db.obtener_tecnicos()

    def cargar_bd_ots(self):
        """Carga la base de datos local de OTs desde SQLite."""
        datos = self.db.obtener_bd_ots()
        if datos:
            self.bd_ots_headers = datos[0] # La primera fila guardada fueron los headers
            self.bd_ots = datos[1:]

    def cargar_datos(self, sync_ui=True):
        eventos = self.db.obtener_eventos_dict()
        if not eventos:
            if sync_ui:
                messagebox.showinfo("Sin Datos", "No hay datos en la base de datos. Haz clic en 'Sincronizar Cloud' para descargar.")
            self.tech_events = {}
            self.technicians_list = []
            if sync_ui: self.dibujar_grilla()
            return
            
        self.procesar_eventos(eventos)
        if sync_ui: self.dibujar_grilla()

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
                            "original_text": summary,
                            "extendedProperties": ev.get('extendedProperties', {}),
                            "id": ev.get("id"),
                            "calendar_id": ev.get("calendar_id", ev.get("Correo")),
                            "description": ev.get("description", "")
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
                            "original_text": summary,
                            "extendedProperties": ev.get('extendedProperties', {}),
                            "id": ev.get("id"),
                            "calendar_id": ev.get("calendar_id", ev.get("Correo")),
                            "description": ev.get("description", "")
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

        # Identificar Conflictos Globales de Patrones para la semana actual
        conflictos_por_dia = {} # { date_key: set(patrones_en_conflicto) }
        for fecha in fechas_semana:
            dk = fecha.strftime("%Y-%m-%d")
            patrones_asig = {} # { patron: { tech_normalized: set(ot_numbers) } }
            
            for t_name, dias_eventos in self.tech_events.items():
                for ev in dias_eventos.get(dk, []):
                    props = ev.get('extendedProperties', {}).get('private', {})
                    p_str = props.get('app_patrones', '[]')
                    try:
                        p_list = json.loads(p_str)
                        if not p_list: continue
                        
                        # Extraer OT numbers de TODO el día del técnico para este patrón
                        nums_tech = set()
                        for ev_all in dias_eventos.get(dk, []):
                            sum_txt = ev_all.get("original_text", "")
                            nums_tech.update(utils.extraer_ots(sum_txt))
                        
                        for p in p_list:
                            # Normalizamos el nombre del técnico para la comparacion interna
                            t_norm = utils.normalizar_texto(t_name)
                            patrones_asig.setdefault(p, {})[t_norm] = nums_tech
                    except: pass
            
            # Decidir conflicto por patrón usando la utilidad centralizada
            conf_hoy = set()
            for p, techs_dict in patrones_asig.items():
                hay_conf, _ = utils.evaluar_conflicto(techs_dict)
                if hay_conf:
                    conf_hoy.add(p)
            conflictos_por_dia[dk] = conf_hoy

        # Estilos Headers
        header_font = ("Segoe UI", 11, "bold")
        
        # --- DIMENSIONES FIJAS (Píxeles) ---
        ANCHO_TEC = 150
        ANCHO_DIA = 200
        ALTO_JORNADA = 105  # Altura reducida para que entren 6 técnicos en pantalla completa
        
        # -- DIBUJAR ENCABEZADOS (Fila 0) --
        # Esquina superior izquierda
        f_corner = tk.Frame(self.grid_frame, bg="#34495e", width=ANCHO_TEC, height=50)
        f_corner.grid(row=0, column=0, padx=1, pady=1, sticky="nsew")
        f_corner.grid_propagate(False)
        tk.Label(f_corner, text="Técnicos / Días", bg="#34495e", fg="white", font=header_font).pack(expand=True)
        
        dias_nombres = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]
        
        for col, (fecha, nombre_dia) in enumerate(zip(fechas_semana, dias_nombres), start=1):
            dia_str = fecha.strftime("%d/%m")
            texto_col = f"{nombre_dia}\n{dia_str}"
            
            is_weekend = fecha.weekday() >= 5
            bg_color = "#95a5a6" if is_weekend else "#34495e"
            if fecha == self.today: bg_color = "#27ae60"
            
            f_h = tk.Frame(self.grid_frame, bg=bg_color, width=ANCHO_DIA, height=50)
            f_h.grid(row=0, column=col, padx=1, pady=1, sticky="nsew")
            f_h.grid_propagate(False)
            tk.Label(f_h, text=texto_col, bg=bg_color, fg="white", font=header_font).pack(expand=True)

        # -- DIBUJAR FILAS DE TÉCNICOS --
        for row, tech in enumerate(self.technicians_list, start=1):
            # Nombre del técnico
            f_t = tk.Frame(self.grid_frame, bg="#ecf0f1", width=ANCHO_TEC, height=ALTO_JORNADA)
            f_t.grid(row=row, column=0, padx=1, pady=1, sticky="nsew")
            f_t.grid_propagate(False)
            tk.Label(f_t, text=tech, bg="#ecf0f1", fg="black", font=("Segoe UI", 10, "bold"), anchor="w", padx=10, wraplength=ANCHO_TEC-20).pack(fill=tk.BOTH, expand=True)
            
            for col, fecha in enumerate(fechas_semana, start=1):
                date_key = fecha.strftime("%Y-%m-%d")
                eventos_dia = self.tech_events.get(tech, {}).get(date_key, [])
                
                # Filtrar si solo queremos OTs
                if self.var_solo_ots.get():
                    eventos_dia = [ev for ev in eventos_dia if ev.get("es_ot")]
                
                is_weekend = fecha.weekday() >= 5
                
                # Color de fondo base de la celda
                if is_weekend:
                    bg_color = "#e0e0e0" if not eventos_dia else "#d5dbdb"
                else:
                    bg_color = "#ffffff" if not eventos_dia else "#e8f8f5"
                
                # Calcular alturas de eventos para determinar si la celda debe expandirse
                event_info = []
                total_ev_h = 0
                for ev in eventos_dia:
                    h_px = int((ev["horas"] / 9.0) * ALTO_JORNADA)
                    h_px = max(25, h_px) # Mínimo 25px para legibilidad
                    event_info.append((ev, h_px))
                    total_ev_h += h_px + 2 # +2 por padding vertical
                
                # Respetar el alto mínimo pero permitir expansión si hay saturación
                real_h = max(ALTO_JORNADA, total_ev_h)

                # Contenedor de la Celda Diaria
                cell_f = tk.Frame(self.grid_frame, bg=bg_color, width=ANCHO_DIA, height=real_h)
                cell_f.grid(row=row, column=col, padx=1, pady=1, sticky="nsew")
                cell_f.grid_propagate(False)
                
                if not eventos_dia:
                    pass
                else:
                    for ev, h_px in event_info:
                        try:
                            f_ev = tk.Frame(cell_f, bg=bg_color, height=h_px)
                            f_ev.pack(fill=tk.X, padx=1, pady=1)
                            f_ev.pack_propagate(False)
                            
                            text_box = ev.get("text", "Evento")
                            bg_box = "#d1f2eb" if ev.get("es_ot") else "#fdfefe"
                            fg_box = "black"
                            
                            # Comprobar conflictos de patrones
                            tiene_conflicto = False
                            props = ev.get('extendedProperties', {}).get('private', {})
                            p_str = props.get('app_patrones', '[]')
                            try:
                                p_list = json.loads(p_str)
                                conf_hoy = conflictos_por_dia.get(date_key, set())
                                if any(p in conf_hoy for p in p_list):
                                    tiene_conflicto = True
                            except: pass
                            
                            if tiene_conflicto:
                                text_box = f"⚠️ {text_box}"
                                bg_box = "#fadbd8" 
                                fg_box = "#c0392b"

                            lbl_ev = tk.Label(f_ev, text=text_box, bg=bg_box, fg=fg_box,
                                             font=("Segoe UI", 8, "bold" if tiene_conflicto else "normal"), 
                                             anchor="nw", justify="left", 
                                             wraplength=ANCHO_DIA-10, relief=tk.SOLID if tiene_conflicto else tk.RAISED, 
                                             bd=2 if tiene_conflicto else 1, padx=3, pady=2, cursor="hand2")
                            lbl_ev.pack(fill=tk.BOTH, expand=True)
                            
                            # Crear Tooltip detallado
                            tip_text = f"📋 {text_box}\n"
                            tip_text += f"📅 {ev.get('Inicio','')[11:16]} - {ev.get('Fin','')[11:16]}\n"
                            if p_str and p_str != "[]":
                                try: tip_text += f"🛠️ Patrones: {', '.join(json.loads(p_str))}\n"
                                except: pass
                            tip_text += "------------------\n💡 Click: Seleccionar/Mover\n💡 Der: Opciones"
                            Tooltip(lbl_ev, tip_text)
                            
                            lbl_ev.bind("<Button-1>", lambda e, t=tech, d=date_key, ev_single=ev, w=lbl_ev: self.seleccionar_evento_interactivo(e, t, d, ev_single, w))
                            lbl_ev.bind("<Button-3>", lambda e, t=tech, d=date_key, ev_single=ev: self.mostrar_menu_contextual(e, t, d, ev_single))
                        except Exception as e_draw:
                            print(f"Error dibujando cuadrito de evento: {e_draw}")
                
                # Clic en la celda vacía para mover el seleccionado
                cell_f.bind("<Button-1>", lambda e, t=tech, d=date_key: self.intentar_mover_a_celda(t, d))

        # Refrescar Métricas
        self.calcular_metricas(fechas_semana)

    def seleccionar_evento_interactivo(self, event, tech, date_key, ev, widget):
        if self.evento_seleccionado and self.evento_seleccionado['ev']['id'] == ev['id']:
            # Deseleccionar si se hace click en el mismo
            self.limpiar_seleccion()
            return
            
        self.limpiar_seleccion()
        self.evento_seleccionado = {"ev": ev, "tech": tech, "date": date_key}
        self.celda_seleccionada_f = widget
        widget.config(relief=tk.FLAT, bd=3, highlightbackground="#3498db", highlightthickness=2)
        
        # Opcional: Mostrar popup normal también si se prefiere
        # self.mostrar_popup_ots(event, tech, date_key, [ev])

    def limpiar_seleccion(self):
        if self.celda_seleccionada_f and self.celda_seleccionada_f.winfo_exists():
            self.celda_seleccionada_f.config(relief=tk.RAISED, bd=1, highlightthickness=0)
        self.evento_seleccionado = None
        self.celda_seleccionada_f = None

    def intentar_mover_a_celda(self, tech_dest, date_dest):
        if not self.evento_seleccionado:
            return
            
        ev = self.evento_seleccionado['ev']
        tech_orig = self.evento_seleccionado['tech']
        date_orig = self.evento_seleccionado['date']
        
        if tech_dest == tech_orig and date_dest == date_orig:
            self.limpiar_seleccion()
            return

        msg = f"¿Mover evento '{ev['text']}'?\nDe: {tech_orig} ({date_orig})\nA: {tech_dest} ({date_dest})"
        if not messagebox.askyesno("Confirmar Movimiento", msg):
            self.limpiar_seleccion()
            return

        # Proceder con el movimiento asíncrono
        threading.Thread(target=self._hilo_mover_evento, args=(ev, tech_dest, date_dest), daemon=True).start()
        self.limpiar_seleccion()
        self.lbl_rango_fechas.config(text="🔄 Procesando movimiento en Calendar...", fg="#e67e22")

    def _hilo_mover_evento(self, ev, tech_dest, date_dest):
        try:
            import extractor
            svc_cal, _ = extractor.get_google_services()
            
            # Buscar el correo del tecnico destino
            correo_dest = next((t['correo'] for t in self.tecnicos_info if t['nombre'] == tech_dest), None)
            if not correo_dest:
                raise Exception(f"No se encontró correo para el técnico {tech_dest}")

            # Calcular nuevas fechas preservando la hora
            # Manejar ISO con offset
            dt_ini = datetime.datetime.fromisoformat(ev['Inicio'].replace("Z", "+00:00"))
            dt_fin = datetime.datetime.fromisoformat(ev['Fin'].replace("Z", "+00:00"))
            
            nueva_f = datetime.datetime.strptime(date_dest, "%Y-%m-%d").date()
            delta = nueva_f - dt_ini.date()
            
            nuevo_dt_ini = dt_ini + datetime.timedelta(days=delta.days)
            nuevo_dt_fin = dt_fin + datetime.timedelta(days=delta.days)

            # 1. MOVER EL EVENTO (Patch)
            # Nota: Si el técnico cambia, es más complejo porque el evento pertenece a un calendario
            # Si el calendario es el mismo (calendar_id), solo cambiamos fechas.
            # Si el calendario es distinto, hay que ELIMINAR y CREAR o usar move()
            
            # Asumimos de momento que movemos dentro del "Pool" y actualizamos el tecnico en extendedProperties
            cal_id_orig = ev.get('calendar_id')
            
            # Si el tecnico cambia, el evento debe "viajar" al calendario del nuevo tecnico
            # Usando la API move()
            if correo_dest != cal_id_orig:
                svc_cal.events().move(
                    calendarId=cal_id_orig,
                    eventId=ev['id'],
                    destination=correo_dest
                ).execute()
                # El eventId puede cambiar al moverlo, pero usualmente se mantiene
            
            # 2. Update de fechas y metadatos
            # Actualizamos el Técnico en los metadatos privados
            props = ev.get('extendedProperties', {}).get('private', {})
            props['app_tecnico'] = tech_dest
            
            svc_cal.events().patch(
                calendarId=correo_dest,
                eventId=ev['id'],
                body={
                    'start': {'dateTime': nuevo_dt_ini.isoformat()},
                    'end': {'dateTime': nuevo_dt_fin.isoformat()},
                    'extendedProperties': {'private': props}
                }
            ).execute()

            # 3. Refrescar datos locales
            self.root.after(0, self.sincronizar_cloud)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error al mover", f"No se pudo completar el movimiento: {e}"))
            self.root.after(0, self.dibujar_grilla)

    def mostrar_menu_contextual(self, event, tech, date_key, ev):
        menu = tk.Menu(self.root, tearoff=0, font=("Segoe UI", 10))
        menu.add_command(label=f"📋 Ver Detalles", command=lambda: self.mostrar_popup_ots(event, tech, date_key, [ev]))
        menu.add_separator()
        
        # Acceso directo a Gestion
        pkg_id = ev.get('extendedProperties', {}).get('private', {}).get('app_pkg_id')
        if pkg_id:
            menu.add_command(label="📁 Ir a Gestión de Proyecto", command=lambda: self.mostrar_gestion_proyectos(preselect_id=pkg_id))
        
        menu.add_separator()
        menu.add_command(label="🗑️ Eliminar de Calendar", command=lambda: self.confirmar_eliminacion_rapida(ev), foreground="red")
        
        menu.post(event.x_root, event.y_root)

    def confirmar_eliminacion_rapida(self, ev):
        if messagebox.askyesno("Confirmar", f"¿Eliminar definitivamente '{ev['text']}' de Google Calendar?"):
            threading.Thread(target=self._hilo_eliminar_evento, args=(ev,), daemon=True).start()

    def _hilo_eliminar_evento(self, ev):
        try:
            import extractor
            svc_cal, _ = extractor.get_google_services()
            svc_cal.events().delete(calendarId=ev['calendar_id'], eventId=ev['id']).execute()
            self.root.after(0, self.sincronizar_cloud)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"No se pudo eliminar: {e}"))
        """Re-construye la interfaz y carga los datos para asegurar un refresco completo."""
        self.crear_interfaz()
        self.cargar_datos()

    def mostrar_gestion_proyectos(self, preselect_id=None):
        # Limpiar contenedor 
        for w in self.contenedor.winfo_children(): w.destroy()
        gest_proy.GestionProyectosModule(
            self.root, 
            self.contenedor, 
            self.tecnicos_info, 
            self.bd_ots, 
            self.tech_events, 
            self.regresar_a_esta_vista, # Usar el nuevo método de refresco
            preselect_id=preselect_id
        )

    def on_tecnico_click(self, tech_name, date_val):
        if not self.technicians_list:
            self.lbl_metrica_semana.config(text="Ocupación Semanal: N/A")
            self.lbl_metrica_mes.config(text="Ocupación Mensual: N/A")
            return

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
        # Lógica de "Toggle": si clickeamos el mismo evento con un popup ya abierto, lo cerramos y no lo volvemos a abrir
        widget = event.widget
        if getattr(self, 'popup_activo', None) and self.popup_activo.winfo_exists():
            self.popup_activo.destroy()
            if getattr(self, 'last_clicked_widget', None) == widget:
                self.last_clicked_widget = None
                return
        
        self.last_clicked_widget = widget
        
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
        
        # Usar índices desde utils
        try:
            idx_ot = utils.IDX_OT
            idx_trab = utils.IDX_TRAB
            idx_pts = utils.IDX_PTS
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
        
        inner_container = tk.Frame(outer, bg="#ffffff")
        inner_container.pack(fill=tk.BOTH, expand=True)
        
        # Canvas y Scrollbar para el popup (Tamaño dinámico con topes)
        pop_canvas = tk.Canvas(inner_container, bg="#ffffff", highlightthickness=0)
        popup.pop_canvas = pop_canvas # Guardar referencia para el scroll inteligente
        pop_vsb = ttk.Scrollbar(inner_container, orient="vertical", command=pop_canvas.yview)
        pop_canvas.configure(yscrollcommand=pop_vsb.set)
        
        pop_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        pop_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        inner = tk.Frame(pop_canvas, bg="#ffffff")
        pop_win = pop_canvas.create_window((0,0), window=inner, anchor="nw")
        
        def _resize_pop(e):
            # Calcular dimensiones basadas en el contenido
            pop_canvas.configure(scrollregion=pop_canvas.bbox("all"))
            
            # Ajustar el canvas al contenido pero con límites máximos
            req_w = min(850, inner.winfo_reqwidth() + 20)
            req_h = min(600, inner.winfo_reqheight())
            
            pop_canvas.config(width=req_w, height=req_h)
            pop_canvas.itemconfig(pop_win, width=req_w)
            
            # Ocultar scrollbar si no es necesaria
            if inner.winfo_reqheight() <= 600:
                pop_vsb.pack_forget()
            else:
                pop_vsb.pack(side=tk.RIGHT, fill=tk.Y)

        inner.bind("<Configure>", _resize_pop)

        # Ya no necesitamos bind_all aquí, _on_mousewheel se encargará de detectar el popup
        
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
        tabla_frame.pack(fill=tk.X, padx=10, pady=8)
        
        # Encabezados de la tabla
        enc_style = {"bg": "#34495e", "fg": "white", "font": ("Segoe UI", 9, "bold"), "pady": 4, "padx": 8}
        tk.Label(tabla_frame, text="Trabajo a Ejecutar", **enc_style).grid(row=0, column=0, sticky="ew", padx=1, pady=1)
        tabla_frame.grid_columnconfigure(0, weight=1) # Hacer que la columna de trabajo se expanda
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
        
        # --- NUEVO: Mostrar Patrones Asignados ---
        patrones_dia = set()
        for ev in eventos_dia:
            props = ev.get('extendedProperties', {}).get('private', {})
            p_str = props.get('app_patrones', '[]')
            try:
                plist = json.loads(p_str)
                for p in plist: patrones_dia.add(p)
            except: pass
            
        if patrones_dia:
            tk.Label(inner, text="🛠️ Patrones Asignados:", bg="#34495e", fg="white",
                     font=("Segoe UI", 9, "bold"), anchor="w", pady=4, padx=12).pack(fill=tk.X, pady=(10,0))
            
            p_frame = tk.Frame(inner, bg="#f9f9f9", padx=10, pady=5)
            p_frame.pack(fill=tk.X)
            for p in sorted(patrones_dia):
                tk.Label(p_frame, text=f"• {p}", bg="#f9f9f9", font=("Segoe UI", 8)).pack(anchor="w")

        # --- BOTÓN DE ATAJO A GESTIÓN ---
        # 1. Identificar pkg_id para este evento
        pkg_id = None
        for ev in eventos_dia:
            props = ev.get('extendedProperties', {}).get('private', {})
            if props.get('app_pkg_id'):
                pkg_id = props.get('app_pkg_id'); break
        
        # Si no hay metadatos, intentar construir el ID de Legacy para que el atajo funcione igual
        if not pkg_id:
            ots_norm = "/".join(sorted(list(numeros_ot)))
            # Sacamos el cliente del resumen si es legacy
            c_tmp = "Desconocido"
            import re
            m = re.search(r"\(([^)]+)\)", titulo_txt)
            if not m and eventos_dia:
                m = re.search(r"\(([^)]+)\)", eventos_dia[0].get('Evento', ''))
            if m: c_tmp = m.group(1).strip()
            pkg_id = f"legacy_{ots_norm}_{c_tmp}"

        def ir_a_gest():
            popup.destroy()
            self.mostrar_gestion_proyectos(preselect_id=pkg_id)

        btn_gest = tk.Button(inner, text="⚙️ Gestionar este Proyecto", command=ir_a_gest,
                             bg="#34495e", fg="white", font=("Segoe UI", 9, "bold"), 
                             relief=tk.FLAT, pady=6, cursor="hand2")
        btn_gest.pack(fill=tk.X)
        
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

    def _on_mousewheel(self, event):
        """Lógica de scroll inteligente que detecta si el mouse está sobre un popup o la grilla."""
        try:
            # 1. Si hay un popup activo y el mouse está dentro de él, scrollear el popup
            if self.popup_activo and self.popup_activo.winfo_exists():
                # Obtenemos el widget bajo el puntero
                w = self.root.winfo_containing(event.x_root, event.y_root)
                if w and str(w).startswith(str(self.popup_activo)):
                    # Buscar el canvas del popup (lo guardamos en el objeto popup para fácil acceso)
                    if hasattr(self.popup_activo, 'pop_canvas'):
                        self.popup_activo.pop_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                        return

            # 2. De lo contrario, scrollear el canvas principal
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        except:
            pass

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
        self.root.geometry("600x520")
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

        tk.Button(self.root, text="  📁 Gestión de Proyectos",
                   command=self._abrir_gestion,
                   bg="#34495e", fg="white", font=("Segoe UI", 14, "bold"),
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
        self.root.state('zoomed')   # Iniciar en pantalla completa (maximizado)
        self.root.resizable(True, True)
        self.root.configure(bg="#f4f4f4")
        contenedor = tk.Frame(self.root, bg="#f4f4f4")
        contenedor.pack(fill=tk.BOTH, expand=True)
        PlanificacionApp(self.root, contenedor, self._mostrar_menu)

    def _abrir_programar(self):
        db = DataManager()
        evs = db.obtener_eventos_dict()
        tecnicos_info = db.obtener_tecnicos()
        raw_ots = db.obtener_bd_ots()
        
        if not raw_ots:
            messagebox.showinfo("Sin Datos", "No hay datos en la DB. Sincroniza primero.")
            return

        # Procesar eventos para el formato tech_events que requiere el módulo
        # NOTA: En el futuro, el módulo de programación también debería usar la DB directamente
        tmp = PlanificacionApp.__new__(PlanificacionApp)
        tmp.db = db
        tmp.procesar_eventos(evs)
        tech_events = tmp.tech_events
        
        bd_ots_hdrs = raw_ots[0] if raw_ots else []
        bd_ots = raw_ots[1:] if len(raw_ots) > 1 else []

        self._limpiar()
        self.root.geometry("1400x850") # Un poco más grande
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

    def _abrir_gestion(self):
        db = DataManager()
        evs = db.obtener_eventos_dict()
        tecnicos_info = db.obtener_tecnicos()
        raw_ots = db.obtener_bd_ots()

        if not tecnicos_info:
            messagebox.showinfo("Sin Datos", "Sincroniza primero la agenda.")
            return

        tmp = PlanificacionApp.__new__(PlanificacionApp)
        tmp.db = db
        tmp.procesar_eventos(evs)
        tech_events = tmp.tech_events
        bd_ots = raw_ots[1:] if len(raw_ots) > 1 else []

        self._limpiar()
        self.root.geometry("1400x850")
        self.root.resizable(True, True)
        self.root.configure(bg="#f4f4f4")
        contenedor = tk.Frame(self.root, bg="#f4f4f4")
        contenedor.pack(fill=tk.BOTH, expand=True)

        gest_proy.GestionProyectosModule(
            self.root, 
            contenedor, 
            tecnicos_info, 
            bd_ots, 
            tech_events, 
            self._mostrar_menu
        )


if __name__ == "__main__":
    root = tk.Tk()
    MenuPrincipal(root)
    root.mainloop()
