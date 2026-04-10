import tkinter as tk
from tkinter import ttk, messagebox
import json
import datetime
import re
import os
import utils
import extractor

# Constantes visuales similares a app.py
COLOR_HEADER = "#2c3e50"
COLOR_BG = "#f4f4f4"
COLOR_BORDES = "#ddd"
COLOR_TEC = "#ecf0f1"
COLOR_DIA_FONDO = "#34495e"
COLOR_DIA_TEXTO = "white"
COLOR_OT = "#d1f2eb"
COLOR_CONFLICTO_BG = "#fadbd8"
COLOR_CONFLICTO_FG = "#c0392b"
COLOR_OK_FG = "#27ae60"

FONT_HEADER = ("Segoe UI", 11, "bold")
FONT_GRID = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")

IDX_OT = 1
IDX_TRAB = 5
IDX_PTS = 12



class ConflictosModule:
    def __init__(self, root, paquete_foco, tecnicos_info, tech_events, volver_fn, modo_semanal=False, fecha_ref=None, bd_ots=[]):
        self.root = root
        self.paquete_foco = paquete_foco
        self.tecnicos_info = tecnicos_info
        self.tech_events = tech_events
        self.volver_fn = volver_fn
        self.modo_semanal = modo_semanal
        self.bd_ots = bd_ots
        self.popup_activo = None
        
        # Determine the reference date for navigation
        self.fecha_ref = fecha_ref
        if not self.fecha_ref and self.paquete_foco and self.paquete_foco.get("eventos"):
            f_str = self.paquete_foco["eventos"][0]["Inicio"][:10]
            self.fecha_ref = datetime.datetime.strptime(f_str, "%Y-%m-%d").date()
        elif not self.fecha_ref:
            self.fecha_ref = datetime.date.today()
            
        self.contenedor = root.winfo_children()[0]
        self._cargar_bd_patrones()
        self._montar_datos_dinamicos()
        self._crear_interfaz()
        self._actualizar_todos_colores()

    def _cargar_bd_patrones(self):
        """Intenta cargar patrones desde cache local para velocidad."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, 'patrones_cache.json')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                self.bd_patrones = json.load(f)
        else:
            # Fallback a Sheets si no hay cache
            _, svc_sheets = extractor.get_google_services()
            self.bd_patrones = extractor.obtener_bd_patrones(svc_sheets)

    def _montar_datos_dinamicos(self):
        self.fechas = []
        fechas_set = set()
        if self.modo_semanal:
            start_date = self.fecha_ref - datetime.timedelta(days=self.fecha_ref.weekday())
            for i in range(7):
                fechas_set.add((start_date + datetime.timedelta(days=i)).strftime("%Y-%m-%d"))
        else:
            if self.paquete_foco and "eventos" in self.paquete_foco:
                for ev in self.paquete_foco["eventos"]:
                    fechas_set.add(ev["Inicio"][:10])
                    
        self.fechas = sorted(list(fechas_set))

        tecs = set()
        for t_name, dias in self.tech_events.items():
            for f in self.fechas:
                if dias.get(f): tecs.add(t_name)
        self.tecnicos_grid = sorted(list(tecs))

        self.vinc_patrones = {} 
        self.eventos_mapping = {} 
        
        for t in self.tecnicos_grid:
            for f in self.fechas:
                self.vinc_patrones[(t, f)] = {}
                evs = self.tech_events.get(t, {}).get(f, [])
                self.eventos_mapping[(t, f)] = evs
                for ev in evs:
                    props = ev.get("extendedProperties", {}).get("private", {})
                    p_str = props.get("app_patrones", "[]")
                    try:
                        p_list = json.loads(p_str)
                        for p in p_list:
                            self.vinc_patrones[(t, f)][p] = tk.BooleanVar(value=True)
                    except: pass

        self.ui_checkbuttons = {} 
        self.ui_boxes = {} 

    def _crear_interfaz(self):
        for w in self.contenedor.winfo_children(): w.destroy()
        self.ui_checkbuttons.clear()
        
        header = tk.Frame(self.contenedor, bg=COLOR_HEADER, height=55)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Button(header, text="← Volver", command=self.volver_fn, bg="#ecf0f1", fg=COLOR_HEADER, 
                  relief=tk.FLAT, font=FONT_BOLD, padx=15, cursor="hand2").pack(side=tk.LEFT, padx=10, pady=10)
        
        titulo = "SOLUCIONADOR GLOBAL DE CONFLICTOS" if self.modo_semanal else "SOLUCIONADOR DE PROYECTO"
        tk.Label(header, text=titulo, bg=COLOR_HEADER, fg="white", font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT, padx=20)

        if self.modo_semanal:
            nav_f = tk.Frame(header, bg=COLOR_HEADER)
            nav_f.pack(side=tk.RIGHT, padx=20)
            btn_sty = {"bg": "#ecf0f1", "fg": COLOR_HEADER, "relief": tk.FLAT, "font": FONT_BOLD, "cursor": "hand2", "padx": 10}
            tk.Button(nav_f, text="< Semana Anterior", command=lambda: self._cambiar_semana(-7), **btn_sty).pack(side=tk.LEFT, padx=5)
            tk.Button(nav_f, text="HOY", command=lambda: self._cambiar_semana(0), **btn_sty).pack(side=tk.LEFT, padx=5)
            tk.Button(nav_f, text="Semana Siguiente >", command=lambda: self._cambiar_semana(7), **btn_sty).pack(side=tk.LEFT, padx=5)

        self.main_frame = tk.Frame(self.contenedor, bg=COLOR_BORDES)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(self.main_frame, bg="white", highlightthickness=0)
        sb_y = ttk.Scrollbar(self.main_frame, orient="vertical", command=canvas.yview)
        sb_x = ttk.Scrollbar(self.main_frame, orient="horizontal", command=canvas.xview)
        self.grid_frame = tk.Frame(canvas, bg=COLOR_BORDES)
        
        self.grid_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_win = canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        canvas.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        
        sb_y.pack(side=tk.RIGHT, fill=tk.Y)
        sb_x.pack(side=tk.BOTTOM, fill=tk.X)
        canvas.pack(fill=tk.BOTH, expand=True)

        if not self.fechas:
            txt_vacio = "No hay programación en esta semana." if self.modo_semanal else "No hay fechas detectadas en el proyecto."
            tk.Label(self.grid_frame, text=txt_vacio, bg="white", fg="gray", font=("Segoe UI", 12, "italic")).pack(pady=50)
            return

        ANCHO_TEC = 150
        ANCHO_DIA = 200

        # Header fila
        tk.Label(self.grid_frame, text="TÉCNICOS", bg=COLOR_DIA_FONDO, fg="white", font=FONT_HEADER, width=15, height=2).grid(row=0, column=0, padx=1, pady=1, sticky="nsew")
        for c, f in enumerate(self.fechas, start=1):
            f_dt = datetime.datetime.strptime(f, "%Y-%m-%d")
            dias_nombres = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]
            f_lbl = f"{dias_nombres[f_dt.weekday()]}\n{f_dt.strftime('%d/%m')}"
            
            bg_col = "#27ae60" if f_dt.date() == datetime.date.today() else COLOR_DIA_FONDO
            tk.Label(self.grid_frame, text=f_lbl, bg=bg_col, fg="white", font=FONT_HEADER, width=25, height=2).grid(row=0, column=c, padx=1, pady=1, sticky="nsew")

        # Filas Técnicos
        for r, tech in enumerate(self.tecnicos_grid, start=1):
            f_t = tk.Frame(self.grid_frame, bg=COLOR_TEC, width=ANCHO_TEC)
            f_t.grid(row=r, column=0, padx=1, pady=1, sticky="nsew")
            tk.Label(f_t, text=tech, bg=COLOR_TEC, font=FONT_BOLD, anchor="w", padx=10, wraplength=ANCHO_TEC-20).pack(fill=tk.BOTH, expand=True)
            
            for c, f in enumerate(self.fechas, start=1):
                evs = self.eventos_mapping.get((tech, f), [])
                cell_bg = "white" if evs else "#f9f9f9"
                cell_f = tk.Frame(self.grid_frame, bg=cell_bg, width=ANCHO_DIA)
                cell_f.grid(row=r, column=c, padx=1, pady=1, sticky="nsew")
                
                if evs:
                    for ev in evs:
                        text_box = ev["text"]
                        bg_box = COLOR_OT if ev.get("es_ot") else "white"
                        lbl_ot = tk.Label(cell_f, text=text_box, bg=bg_box, fg="black", font=FONT_BOLD, 
                                          relief=tk.RAISED, bd=1, padx=3, pady=2, wraplength=ANCHO_DIA-10, cursor="hand2")
                        lbl_ot.pack(fill=tk.X, padx=2, pady=2)
                        lbl_ot.bind("<Button-1>", lambda e, t=tech, d=f, evs_dia=evs: self._mostrar_popup_partidas(e, t, d, evs_dia))
                        lbl_ot.bind("<Button-3>", lambda e, ev_single=ev: self._menu_contextual_conflicto(e, ev_single))
                    
                    box_pats = tk.Frame(cell_f, bg=cell_bg)
                    box_pats.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
                    self.ui_boxes[(tech, f)] = box_pats
                    self._dibujar_patrones_celda(tech, f, box_pats)
                else:
                    tk.Label(cell_f, text="", bg="#f9f9f9").pack(expand=True)

        footer = tk.Frame(self.contenedor, bg="#ecf0f1", pady=10)
        footer.pack(fill=tk.X)
        tk.Button(footer, text="💾 GUARDAR CAMBIOS EN GOOGLE CALENDAR", command=self._guardar, 
                  bg="#27ae60", fg="white", font=("Segoe UI", 11, "bold"), padx=30, pady=8, relief=tk.FLAT, cursor="hand2").pack()

    def _cambiar_semana(self, dias):
        if dias == 0:
            self.fecha_ref = datetime.date.today()
        else:
            self.fecha_ref = self.fecha_ref + datetime.timedelta(days=dias)
        self._montar_datos_dinamicos()
        self._crear_interfaz()
        self._actualizar_todos_colores()

    def _dibujar_patrones_celda(self, tech, f, parent_frame):
        for w in parent_frame.winfo_children(): w.destroy()
        
        pats_asignados = list(self.vinc_patrones.get((tech, f), {}).keys())
        cell_bg = parent_frame.cget("bg")
        
        for p in sorted(pats_asignados):
            var = self.vinc_patrones[(tech, f)][p]
            cb = tk.Checkbutton(parent_frame, text=p, variable=var, bg=cell_bg, activebackground=cell_bg, 
                                font=FONT_GRID, cursor="hand2", command=lambda f_=f, p_=p: self._actualizar_color(f_, p_))
            cb.pack(anchor="w", padx=10)
            self.ui_checkbuttons.setdefault((f, p), []).append((cb, var))
            
        btn_add = tk.Label(parent_frame, text="+ Agregar patrón", fg="#3498db", bg=cell_bg, font=("Segoe UI", 8, "underline"), cursor="hand2")
        btn_add.pack(anchor="w", padx=12, pady=(2,0))
        btn_add.bind("<Button-1>", lambda e, t=tech, d=f: self._abrir_selector(t, d))

    def _abrir_selector(self, tech, f):
        pop = tk.Toplevel(self.root)
        pop.title(f"Añadir Patrón - {tech}")
        pop.geometry("450x500")
        pop.configure(bg="white")
        pop.transient(self.root)
        pop.grab_set()

        h = tk.Frame(pop, bg=COLOR_HEADER, pady=10)
        h.pack(fill=tk.X)
        tk.Label(h, text=f"ASIGNAR EQUIPO A {tech}", fg="white", bg=COLOR_HEADER, font=FONT_BOLD).pack()

        f_busq = tk.Frame(pop, pady=10, bg="white")
        f_busq.pack(fill=tk.X)
        tk.Label(f_busq, text="🔍 Buscar:", bg="white", font=FONT_GRID).pack(side=tk.LEFT, padx=10)
        ent = ttk.Entry(f_busq, font=FONT_GRID)
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        ent.focus_set()
        
        style = ttk.Style()
        style.configure("Selector.Treeview", font=FONT_GRID, rowheight=25)
        t_lista = ttk.Treeview(pop, columns=("nom", "rango"), show="headings", style="Selector.Treeview")
        t_lista.heading("nom", text="ID / Patrón")
        t_lista.heading("rango", text="Rango / Detalles")
        t_lista.column("nom", width=150)
        t_lista.column("rango", width=250)
        t_lista.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        patrones_db_list = []
        if self.bd_patrones and len(self.bd_patrones) > 1:
            for p in self.bd_patrones[1:]: 
                if len(p) >= 1:
                    n = p[0]
                    r = p[13] if len(p) > 13 else ""
                    patrones_db_list.append((n, r))

        def _fill(q=""):
            for i in t_lista.get_children(): t_lista.delete(i)
            q = utils.normalizar_texto(q)
            for n, r in patrones_db_list:
                if q in utils.normalizar_texto(n) or q in utils.normalizar_texto(r):
                    t_lista.insert("", "end", iid=n, values=(n, r))

        _fill()
        ent.bind("<KeyRelease>", lambda e: _fill(ent.get()))

        def _confirmar(e=None):
            sel = t_lista.selection()
            if not sel: return
            nuevo = sel[0]
            if nuevo not in self.vinc_patrones[(tech, f)]:
                self.vinc_patrones[(tech, f)][nuevo] = tk.BooleanVar(value=True)
            else:
                self.vinc_patrones[(tech, f)][nuevo].set(True)
                
            self._dibujar_patrones_celda(tech, f, self.ui_boxes[(tech, f)])
            self._actualizar_color(f, nuevo)
            pop.destroy()

        t_lista.bind("<Double-1>", _confirmar)
        tk.Button(pop, text="ASIGNAR EQUIPO", command=_confirmar, bg="#3498db", fg="white", 
                  font=FONT_BOLD, relief=tk.FLAT, pady=10).pack(fill=tk.X, padx=10, pady=10)

    def _actualizar_todos_colores(self):
        vistos = set()
        for dicc in self.vinc_patrones.values():
            for p in dicc.keys(): vistos.add(p)
        for f in self.fechas:
            for p in vistos: self._actualizar_color(f, p)

    def _actualizar_color(self, f, p):
        # Lógica de Uso Compartido mejorada:
        # Cruza los técnicos que tienen el patrón activo y a qué OT pertenecen.
        ots_por_patron = {} # { tech_normalized: set_of_ot_numbers }
        
        # Primero poblamos el diccionario usando nombres normalizados
        for tech_name in self.tecnicos_grid:
            var = self.vinc_patrones.get((tech_name, f), {}).get(p)
            if var and var.get():
                evs = self.eventos_mapping.get((tech_name, f), [])
                nums_tech = set()
                for ev in evs:
                    summary = ev.get("original_text", "")
                    nums_tech.update(utils.extraer_ots(summary))
                
                # Usamos nombre normalizado como clave para agrupar duplicados de encoding
                t_norm = utils.normalizar_texto(tech_name)
                if t_norm not in ots_por_patron:
                    ots_por_patron[t_norm] = set()
                ots_por_patron[t_norm].update(nums_tech)

        color = "black"
        font_w = "normal"
        
        hay_conf, _ = utils.evaluar_conflicto(ots_por_patron)
        
        if hay_conf:
            color = COLOR_CONFLICTO_FG
            font_w = "bold"
        elif len(ots_por_patron) > 1:
            color = COLOR_OK_FG # Compartido
            font_w = "normal"
        else:
            color = "black" if len(ots_por_patron) == 1 else "gray"
            font_w = "normal"

        for cb, var in self.ui_checkbuttons.get((f, p), []):
            try:
                final_col = color if var.get() else "gray"
                cb.config(fg=final_col, font=("Segoe UI", 9, "bold" if final_col == COLOR_CONFLICTO_FG else "normal"))
            except: pass

    def _mostrar_popup_partidas(self, event, tech, date_key, eventos_dia):
        if self.popup_activo: self.popup_activo.destroy()
        
        numeros_ot = set()
        for ev in eventos_dia:
            summary = ev.get("original_text", "")
            numeros_ot.update(utils.extraer_ots(summary))

        conteo = {}
        for fila in self.bd_ots:
            if len(fila) > IDX_OT:
                ot_str = str(fila[IDX_OT]).strip()
                # Unir si la OT de la fila está contenida en los números encontrados
                if ot_str in numeros_ot:
                    trabajo = fila[IDX_TRAB].strip() if len(fila) > IDX_TRAB else ''
                    puntos = fila[IDX_PTS].strip() if len(fila) > IDX_PTS else ''
                    k = (trabajo, puntos)
                    conteo[k] = conteo.get(k, 0) + 1

        pop = tk.Toplevel(self.root)
        self.popup_activo = pop
        pop.overrideredirect(True)
        pop.configure(bg="white", highlightbackground=COLOR_HEADER, highlightthickness=1)
        
        inner = tk.Frame(pop, bg="white", padx=10, pady=10)
        inner.pack()
        
        f_dt = datetime.datetime.strptime(date_key, "%Y-%m-%d").date()
        tk.Label(inner, text=f"{tech} - {f_dt.strftime('%d/%m')}", bg=COLOR_HEADER, fg="white", font=FONT_BOLD).pack(fill=tk.X)
        tk.Label(inner, text=f"OTs detectadas: {', '.join(sorted(numeros_ot)) if numeros_ot else 'Ninguna'}", bg="#ecf0f1", font=FONT_GRID).pack(fill=tk.X, pady=2)
        
        if conteo:
            t_f = tk.Frame(inner, bg="white")
            t_f.pack(fill=tk.X, pady=5)
            tk.Label(t_f, text="Trabajo", bg="#34495e", fg="white", font=FONT_BOLD, width=30).grid(row=0, column=0)
            tk.Label(t_f, text="Pts", bg="#34495e", fg="white", font=FONT_BOLD, width=10).grid(row=0, column=1)
            tk.Label(t_f, text="Cant", bg="#34495e", fg="white", font=FONT_BOLD, width=5).grid(row=0, column=2)
            
            for i, ((trab, pts), cant) in enumerate(sorted(conteo.items()), 1):
                bg = "#f9f9f9" if i%2==0 else "white"
                tk.Label(t_f, text=trab, bg=bg, font=FONT_GRID, anchor="w").grid(row=i, column=0, sticky="ew")
                tk.Label(t_f, text=pts, bg=bg, font=FONT_GRID).grid(row=i, column=1, sticky="ew")
                tk.Label(t_f, text=cant, bg=bg, font=FONT_GRID).grid(row=i, column=2, sticky="ew")
        else:
            tk.Label(inner, text="No hay detalles de partidas.", bg="white", fg="gray", font=("Segoe UI", 9, "italic")).pack()

        pop.update_idletasks()
        pop.geometry(f"+{event.x_root+10}+{event.y_root+10}")
        pop.bind("<FocusOut>", lambda e: pop.destroy())
        pop.focus_set()

    def _guardar(self):
        parches = [] 
        
        for tech in self.tecnicos_grid:
            for f in self.fechas:
                evs = self.eventos_mapping.get((tech, f), [])
                if not evs: continue
                
                dict_celda = self.vinc_patrones.get((tech, f), {})
                pats_activos = [p for p, var in dict_celda.items() if var.get()]
                
                host_ev = evs[0]
                if not self.modo_semanal and self.paquete_foco:
                    ot_foco = self.paquete_foco.get("ots", "")
                    for e in evs:
                        if ot_foco in e.get("original_text", ""):
                            host_ev = e; break

                for ev in evs:
                    eid = ev.get("id")
                    cid = ev.get("calendar_id")
                    if not eid or not cid: continue
                    
                    props = ev.get("extendedProperties", {}).get("private", {})
                    if ev == host_ev:
                        props["app_patrones"] = json.dumps(pats_activos)
                        tags = pats_activos
                    else:
                        props["app_patrones"] = "[]"
                        tags = []
                        
                    old_desc = ev.get("description", "")
                    new_desc = re.sub(r'(?i)Patrones:.*(\r?\n)?', '', old_desc).strip()
                    if tags:
                        s = "Patrones: " + ", ".join(tags)
                        new_desc = f"{new_desc}\n\n{s}" if new_desc else s
                        
                    payload = {"extendedProperties": {"private": props}, "description": new_desc}
                    parches.append((cid, eid, payload))

        if not parches:
            messagebox.showinfo("Solucionador", "No hay cambios detectados para guardar.")
            return
            
        self._enviar_parches_batch(parches)

    def _enviar_parches_batch(self, parches):
        try:
            svc_cal, _ = extractor.get_google_services()
            batch = svc_cal.new_batch_http_request()
            for cid, eid, pay in parches:
                req = svc_cal.events().patch(calendarId=cid, eventId=eid, body=pay)
                batch.add(req)
            batch.execute()
            messagebox.showinfo("Éxito", "Cambios guardados. Sincroniza el calendario para ver los resultados.")
            self.volver_fn()
        except Exception as e:
            messagebox.showerror("Error", f"Fallo al guardar en Google: {e}")

    def _menu_contextual_conflicto(self, event, ev):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="🗑️ Eliminar este evento", command=lambda: self._eliminar_rapido(ev), foreground="red")
        menu.post(event.x_root, event.y_root)

    def _eliminar_rapido(self, ev):
        if messagebox.askyesno("Confirmar", "¿Eliminar este evento para resolver el conflicto?"):
            try:
                svc_cal, _ = extractor.get_google_services()
                svc_cal.events().delete(calendarId=ev['calendar_id'], eventId=ev['id']).execute()
                messagebox.showinfo("Éxito", "Evento eliminado. Cierre y vuelva a abrir para ver cambios.")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo eliminar: {e}")
