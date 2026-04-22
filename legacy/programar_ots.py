import os
import json
import math
import datetime
import itertools
import uuid
import tkinter as tk
from tkinter import ttk, messagebox

from data_manager import DataManager

import extractor
import engine
import utils

IDX_ESTADO = utils.IDX_ESTADO
IDX_OT    = utils.IDX_OT
IDX_CLIE  = utils.IDX_CLIE
IDX_TRAB  = utils.IDX_TRAB
IDX_ID    = utils.IDX_ID
IDX_MODELO = utils.IDX_MODELO
IDX_MARCA = utils.IDX_MARCA
IDX_SERIE = utils.IDX_SERIE
IDX_PTS   = utils.IDX_PTS
IDX_FECHA = utils.IDX_FECHA
IDX_SF    = utils.IDX_SF

IDX_PATRON_NOMBRE = utils.IDX_PATRON_NOMBRE
IDX_PATRON_TRABAJOS = utils.IDX_PATRON_TRABAJOS
IDX_PATRON_RANGO = utils.IDX_PATRON_RANGO

ESTADOS_PROGRAMABLES = {"Nueva", "Reprogramar"}

DIAS_SEM = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
MESES    = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
            "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]


class ProgramarOTsModule:
    def __init__(self, root, contenedor, tech_events, tecnicos_info, bd_ots, bd_ots_headers, volver_fn):
        self.root = root
        self.contenedor = contenedor
        self.tech_events = tech_events         # {nombre: {date_key: [events]}}
        self.tecnicos_info = tecnicos_info     # [{nombre, correo, iniciales}]
        self.bd_ots = bd_ots
        self.bd_ots_headers = bd_ots_headers
        self.volver_fn = volver_fn

        self.ots_seleccionadas = []
        self.cliente_filtro = None
        self.ots_unicas = []
        self._params = {}
        self._opciones = []
        self.patrones_db = self._cargar_patrones_db()

        self._cargar_ots_unicas()
        
        # Inicializar variables de persistencia para Vista 2
        self.var_jornadas = tk.StringVar(value="1.0")
        self.var_ntec = tk.IntVar(value=1)
        self.var_serv = tk.StringVar()
        self.var_cons = tk.BooleanVar(value=False)
        self.var_viaje = tk.BooleanVar(value=False)
        self._desc_cached = ""
        self._pivot_date = None
        self._opciones_est = []
        self._opciones_flex = []
        
        self._mostrar_vista1()

    # ──────────────────────────────────────────────
    # Utilidades
    # ──────────────────────────────────────────────
    def _limpiar(self):
        for w in self.contenedor.winfo_children():
            w.destroy()

    def _header(self, titulo, btn_texto, btn_cmd):
        h = tk.Frame(self.contenedor, bg="#2c3e50", height=55)
        h.pack(fill=tk.X)
        h.pack_propagate(False)
        tk.Label(h, text=titulo, fg="white", bg="#2c3e50",
                 font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT, padx=20, pady=12)
        tk.Button(h, text=btn_texto, command=btn_cmd,
                  bg="#ecf0f1", fg="#2c3e50", font=("Segoe UI", 10, "bold"),
                   relief=tk.FLAT, padx=10, cursor="hand2").pack(side=tk.RIGHT, padx=20)
        return h

    def _cargar_patrones_db(self):
        db = DataManager()
        return db.obtener_patrones()

    def _popup_partidas(self, event, numeros_ot):
        filas = []
        for fila in self.bd_ots:
            if len(fila) > IDX_OT and str(fila[IDX_OT]).strip() in numeros_ot:
                t = fila[IDX_TRAB].strip() if len(fila) > IDX_TRAB else ''
                p = fila[IDX_PTS].strip() if len(fila) > IDX_PTS else ''
                if t or p:
                    filas.append((t, p))
        conteo = {}
        for t, p in filas:
            k = (t, p); conteo[k] = conteo.get(k, 0) + 1

        pop = tk.Toplevel(self.root)
        pop.overrideredirect(True)
        pop.attributes('-topmost', True)
        x, y = event.x_root + 10, event.y_root + 10
        outer = tk.Frame(pop, bg="#2c3e50", padx=1, pady=1); outer.pack(fill=tk.BOTH, expand=True)
        inner = tk.Frame(outer, bg="#fff"); inner.pack(fill=tk.BOTH, expand=True)
        tk.Label(inner, text=f"OTs: {', '.join(numeros_ot)}", bg="#2c3e50", fg="white",
                 font=("Segoe UI", 10, "bold"), pady=8, padx=12, anchor="w").pack(fill=tk.X)
        tf = tk.Frame(inner, bg="#fff"); tf.pack(fill=tk.BOTH, padx=10, pady=8)
        es = {"bg":"#34495e","fg":"white","font":("Segoe UI",9,"bold"),"pady":4,"padx":8}
        tk.Label(tf, text="Trabajo a Ejecutar", **es).grid(row=0, column=0, sticky="ew", padx=1, pady=1)
        tk.Label(tf, text="Puntos de Cal.", **es).grid(row=0, column=1, sticky="ew", padx=1, pady=1)
        tk.Label(tf, text="Cant.", **es).grid(row=0, column=2, sticky="ew", padx=1, pady=1)
        for i, ((t, p), c) in enumerate(sorted(conteo.items()), 1):
            bg = "#f9f9f9" if i % 2 == 0 else "#fff"
            fs = {"bg":bg,"font":("Segoe UI",9),"pady":3,"padx":8}
            tk.Label(tf, text=t or "—", anchor="w", **fs).grid(row=i, column=0, sticky="ew", padx=1, pady=1)
            tk.Label(tf, text=p or "—", **fs).grid(row=i, column=1, sticky="ew", padx=1, pady=1)
            tk.Label(tf, text=str(c), **fs).grid(row=i, column=2, sticky="ew", padx=1, pady=1)
        tk.Label(inner, text=f"Total: {sum(conteo.values())} partidas",
                 bg="#ecf0f1", fg="#2c3e50", font=("Segoe UI",9,"bold"),
                 pady=6, padx=12, anchor="e").pack(fill=tk.X)
                 
        # --- NUEVO: Mostrar eventos de Calendar vinculados ---
        eventos_rel = []
        for t_nom, dias_dict in self.tech_events.items():
            for fecha, evs in dias_dict.items():
                for ev in evs:
                    props = ev.get('extendedProperties', {}).get('private', {})
                    ev_ots_str = props.get('app_ots', '')
                    # Comprobar intersección de OTs
                    if any(num in ev_ots_str for num in numeros_ot):
                        eventos_rel.append((fecha, t_nom, ev.get('text', '')))
        
        if eventos_rel:
            tk.Label(inner, text="📅 Eventos en Calendar:", bg="#34495e", fg="white", 
                     font=("Segoe UI", 9, "bold"), anchor="w", pady=4, padx=12).pack(fill=tk.X, pady=(10,0))
            
            ev_frame = tk.Frame(inner, bg="#f9f9f9", padx=10, pady=5)
            ev_frame.pack(fill=tk.X)
            
            # Limitar a máximo 5 para no desbordar el popup
            for i, (fecha, t_nom, ev_text) in enumerate(sorted(eventos_rel, key=lambda x: x[0])):
                if i >= 5:
                    tk.Label(ev_frame, text=f"...y {len(eventos_rel)-5} más", bg="#f9f9f9", font=("Segoe UI", 8, "italic")).pack(anchor="w")
                    break
                # Formatear la fecha
                formato_f = datetime.datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m")
                tk.Label(ev_frame, text=f"• {formato_f} | {t_nom[:15]}... | {ev_text[:30]}", bg="#f9f9f9", font=("Segoe UI", 8)).pack(anchor="w")

        pop.update_idletasks()
        pw, ph = pop.winfo_reqwidth(), pop.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        if x + pw > sw - 10: x = event.x_root - pw - 10
        if y + ph > sh - 40: y = event.y_root - ph - 10
        pop.geometry(f"+{max(5,x)}+{max(5,y)}")
        pop.bind("<FocusOut>", lambda e: pop.destroy() if pop.winfo_exists() else None)
        pop.focus_set()

    # ──────────────────────────────────────────────
    # VISTA 1: Tabla de selección de OTs
    # ──────────────────────────────────────────────
    def _cargar_ots_unicas(self):
        seen = {}
        for fila in self.bd_ots:
            if len(fila) > IDX_OT:
                # Filtrar solo estados programables
                estado = fila[IDX_ESTADO].strip() if len(fila) > IDX_ESTADO else ''
                if estado not in ESTADOS_PROGRAMABLES:
                    continue
                nro = str(fila[IDX_OT]).strip()
                if nro and nro not in seen:
                    clie = fila[IDX_CLIE].strip() if len(fila) > IDX_CLIE else ''
                    fecha = fila[IDX_FECHA].strip() if len(fila) > IDX_FECHA else ''
                    seen[nro] = {"nro": nro, "cliente": clie, "fecha": fecha, "estado": estado}
        # Ordenar ascendente por fecha de creacion
        self.ots_unicas = sorted(seen.values(), key=lambda x: x["fecha"])

    def _mostrar_vista1(self):
        self._limpiar()
        self.ots_seleccionadas = []
        self.cliente_filtro = None

        self._header("Programar OTs — Selección de OTs", "← Volver al Menú", self.volver_fn)

        self.lbl_filtro = tk.Label(self.contenedor,
            text="Seleccioná las OTs a programar (deben ser del mismo cliente).",
            bg="#f4f4f4", fg="#555", font=("Segoe UI", 10), pady=6)
        self.lbl_filtro.pack(fill=tk.X, padx=20)

        # Contenedor para la tabla con scroll
        self.table_container = tk.Frame(self.contenedor, bg="#f4f4f4")
        self.table_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 5))

        self.canvas_ot = tk.Canvas(self.table_container, bg="#ffffff", highlightthickness=0)
        self.vsb_ot = ttk.Scrollbar(self.table_container, orient="vertical", command=self.canvas_ot.yview)
        self.canvas_ot.configure(yscrollcommand=self.vsb_ot.set)

        self.vsb_ot.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas_ot.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.grid_ots = tk.Frame(self.canvas_ot, bg="#bdc3c7") # Color de las líneas de la grilla
        self.canvas_window_ot = self.canvas_ot.create_window((0, 0), window=self.grid_ots, anchor="nw")
        
        self.grid_ots.bind("<Configure>", lambda e: self.canvas_ot.configure(scrollregion=self.canvas_ot.bbox("all")))
        self.canvas_ot.bind("<Configure>", lambda e: self.canvas_ot.itemconfig(self.canvas_window_ot, width=e.width))

        self._refrescar_tabla()

        # Botones inferiores
        bottom = tk.Frame(self.contenedor, bg="#ecf0f1", height=50)
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        bottom.pack_propagate(False)
        self.lbl_sel = tk.Label(bottom, text="0 OTs seleccionadas",
                                bg="#ecf0f1", fg="#2c3e50", font=("Segoe UI", 10))
        self.lbl_sel.pack(side=tk.LEFT, padx=20)
        self.btn_sig = tk.Button(bottom, text="Siguiente →", command=self._mostrar_vista2,
                                  bg="#27ae60", fg="white", font=("Segoe UI", 11, "bold"),
                                  relief=tk.FLAT, padx=20, state=tk.DISABLED, cursor="hand2")
        self.btn_sig.pack(side=tk.RIGHT, padx=20, pady=8)

    def _refrescar_tabla(self):
        for w in self.grid_ots.winfo_children():
            w.destroy()

        headers = ["✓", "Estado", "N° OT", "Cliente", "Fecha Creación"]
        widths = [4, 15, 12, 45, 18]
        
        # Dibujar Encabezados
        for col, (h, w) in enumerate(zip(headers, widths)):
            tk.Label(self.grid_ots, text=h, bg="#34495e", fg="white", 
                     font=("Segoe UI", 10, "bold"), width=w, pady=8).grid(row=0, column=col, sticky="nsew", padx=1, pady=1)

        # Dibujar Filas
        for row_idx, ot in enumerate(self.ots_unicas, 1):
            nro = ot["nro"]
            sel = nro in self.ots_seleccionadas
            bloq = (self.cliente_filtro and ot["cliente"] != self.cliente_filtro and not sel)
            
            marca = "☑" if sel else "☐"
            bg_color = "#d5f5e3" if sel else ("#f9f9f9" if row_idx % 2 == 0 else "#ffffff")
            fg_color = "#bbb" if bloq else "black"
            
            # 1. Columna Check
            lbl_check = tk.Label(self.grid_ots, text=marca, bg=bg_color, fg=fg_color, font=("Segoe UI", 12), width=widths[0], cursor="hand2")
            lbl_check.grid(row=row_idx, column=0, sticky="nsew", padx=1, pady=1)
            lbl_check.bind("<Button-1>", lambda e, n=nro, o=ot: self._toggle_ot(n, o))

            # Columnas de Datos (Nombres de campos para el bucle)
            campos = [ot["estado"], nro, ot["cliente"], ot["fecha"]]
            
            for col_idx, (val, width) in enumerate(zip(campos, widths[1:]), 1):
                lbl = tk.Label(self.grid_ots, text=val, bg=bg_color, fg=fg_color, 
                               font=("Segoe UI", 10), width=width, anchor="w" if col_idx == 3 else "center", 
                               padx=10, pady=6, cursor="hand2")
                lbl.grid(row=row_idx, column=col_idx, sticky="nsew", padx=1, pady=1)
                
                # Clic simple abre el resumen (excepto si está bloqueada por cliente distinto)
                if not bloq:
                    def cmd_popup(e, n=[nro], root=self.root):
                        # Destruir cualquier otro Toplevel hijo antes de abrir uno nuevo
                        for child in root.winfo_children():
                            if isinstance(child, tk.Toplevel): child.destroy()
                        self._popup_partidas(e, n)
                    
                    lbl.bind("<Button-1>", cmd_popup)

    def _toggle_ot(self, nro, ot):
        if self.cliente_filtro and ot["cliente"] != self.cliente_filtro and nro not in self.ots_seleccionadas:
            messagebox.showwarning("Cliente distinto",
                f"Solo podés seleccionar OTs del mismo cliente.\nCliente actual: {self.cliente_filtro}")
            return
        if nro in self.ots_seleccionadas:
            self.ots_seleccionadas.remove(nro)
        else:
            self.ots_seleccionadas.append(nro)
        self.cliente_filtro = (
            next((o["cliente"] for o in self.ots_unicas if o["nro"] == self.ots_seleccionadas[0]), None)
            if self.ots_seleccionadas else None
        )
        self._refrescar_tabla()
        n = len(self.ots_seleccionadas)
        self.lbl_sel.config(text=f"{n} OT{'s' if n != 1 else ''} seleccionada{'s' if n != 1 else ''}")
        self.btn_sig.config(state=tk.NORMAL if n > 0 else tk.DISABLED)

    # ──────────────────────────────────────────────
    # VISTA 2: Parámetros + Resumen de Partidas
    # ──────────────────────────────────────────────
    def _mostrar_vista2(self):
        self._limpiar()
        ot_str = " / ".join(self.ots_seleccionadas)
        clie   = self.cliente_filtro or ""

        self._header(f"Programar: {ot_str}  ({clie})", "← Volver", self._mostrar_vista1)

        # ── Botones inferiores (se empacan primero para que no los tape el main) ──
        bottom2 = tk.Frame(self.contenedor, bg="#ecf0f1", height=55)
        bottom2.pack(fill=tk.X, side=tk.BOTTOM)
        bottom2.pack_propagate(False)
        
        tk.Button(bottom2, text="Manual ⚙", command=lambda: save_desc_and_call(self._mostrar_vista_manual),
                  bg="#95a5a6", fg="white", font=("Segoe UI", 10, "bold"),
                  relief=tk.FLAT, padx=15, cursor="hand2").pack(side=tk.LEFT, padx=20, pady=8)

        tk.Button(bottom2, text="Buscar Disponibilidad →", command=lambda: save_desc_and_call(self._ejecutar_busqueda),
                  bg="#2980b9", fg="white", font=("Segoe UI", 11, "bold"),
                  relief=tk.FLAT, padx=20, cursor="hand2").pack(side=tk.RIGHT, padx=20, pady=8)

        main = tk.Frame(self.contenedor, bg="#f4f4f4")
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        # ── Panel Izquierdo: Contenedor de Tablas ──
        left_p = tk.Frame(main, bg="#f4f4f4")
        left_p.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        # 1. Resumen de Partidas
        lf_part = tk.LabelFrame(left_p, text="Resumen de Partidas (Agrupado)", bg="#f4f4f4",
                                font=("Segoe UI", 10, "bold"), padx=6, pady=6)
        lf_part.pack(fill=tk.X, pady=(0, 10))

        filas_data = []
        for fila in self.bd_ots:
            if len(fila) > IDX_OT and str(fila[IDX_OT]).strip() in self.ots_seleccionadas:
                filas_data.append(fila)

        conteo = {}
        for f in filas_data:
            t = f[IDX_TRAB].strip() if len(f) > IDX_TRAB else ''
            p = f[IDX_PTS].strip() if len(f) > IDX_PTS else ''
            if t or p:
                k = (t, p); conteo[k] = conteo.get(k, 0) + 1

        t2 = ttk.Treeview(lf_part, columns=("trab","pts","cant"), show="headings", height=6)
        t2.heading("trab", text="Trabajo a Ejecutar")
        t2.heading("pts",  text="Puntos de Cal.")
        t2.heading("cant", text="Cant.")
        t2.column("trab", width=250)
        t2.column("pts",  width=150)
        t2.column("cant", width=50, anchor="center")
        for (t, p), c in sorted(conteo.items()):
            t2.insert("", "end", values=(t or "—", p or "—", c))
        sb2 = ttk.Scrollbar(lf_part, orient=tk.VERTICAL, command=t2.yview)
        t2.configure(yscrollcommand=sb2.set)
        sb2.pack(side=tk.RIGHT, fill=tk.Y)
        t2.pack(fill=tk.BOTH, expand=True)
        tk.Label(lf_part, text=f"Total: {sum(conteo.values())} partidas",
                 bg="#f4f4f4", fg="#2c3e50", font=("Segoe UI", 10, "bold"), anchor="e").pack(fill=tk.X, pady=4)

        # 2. Detalle de OTs (Tabla Nueva)
        lf_det = tk.LabelFrame(left_p, text="Detalle de Equipos / Partidas", bg="#f4f4f4",
                               font=("Segoe UI", 10, "bold"), padx=6, pady=6)
        lf_det.pack(fill=tk.BOTH, expand=True)
        
        cols_det = ("id", "serie", "marca", "modelo", "trab", "pts")
        t_det = ttk.Treeview(lf_det, columns=cols_det, show="headings", height=10)
        t_det.heading("id", text="ID")
        t_det.heading("serie", text="Serie")
        t_det.heading("marca", text="Marca")
        t_det.heading("modelo", text="Modelo")
        t_det.heading("trab", text="Trabajo")
        t_det.heading("pts", text="Puntos")
        
        t_det.column("id", width=80)
        t_det.column("serie", width=100)
        t_det.column("marca", width=100)
        t_det.column("modelo", width=120)
        t_det.column("trab", width=180)
        t_det.column("pts", width=120)
        
        for f in filas_data:
            vals = (
                f[IDX_ID] if len(f) > IDX_ID else "",
                f[IDX_SERIE] if len(f) > IDX_SERIE else "",
                f[IDX_MARCA] if len(f) > IDX_MARCA else "",
                f[IDX_MODELO] if len(f) > IDX_MODELO else "",
                f[IDX_TRAB] if len(f) > IDX_TRAB else "",
                f[IDX_PTS] if len(f) > IDX_PTS else ""
            )
            t_det.insert("", "end", values=vals)
            
        sb_det = ttk.Scrollbar(lf_det, orient=tk.VERTICAL, command=t_det.yview)
        t_det.configure(yscrollcommand=sb_det.set)
        sb_det.pack(side=tk.RIGHT, fill=tk.Y)
        t_det.pack(fill=tk.BOTH, expand=True)

        # ── Panel Derecho: Formulario (ANCHO FIJO) ──
        lf_form = tk.LabelFrame(main, text="Parámetros de Programación", bg="#f4f4f4",
                                font=("Segoe UI", 10, "bold"), padx=14, pady=12, width=360)
        lf_form.grid_propagate(False) # Importante: evita que el grid interno cambie el tamaño del LabelFrame
        lf_form.pack(side=tk.RIGHT, fill=tk.Y)

        def row_lbl(text, r):
            tk.Label(lf_form, text=text, bg="#f4f4f4", font=("Segoe UI", 10),
                     anchor="w").grid(row=r, column=0, sticky="w", pady=8, padx=(0, 10))

        row_lbl("Jornadas requeridas:", 0)
        self.lbl_desglose = tk.Label(lf_form, text="(1 día completo)", bg="#f4f4f4", 
                                     font=("Segoe UI", 9, "italic"), fg="#7f8c8d")
        self.lbl_desglose.grid(row=0, column=1, sticky="w", pady=(35, 0))
        
        def update_desglose(*args):
            try:
                val = float(self.var_jornadas.get())
                dias = int(val)
                horas = (val - dias) * 9
                txt = f"({dias} día{'s' if dias!=1 else ''}"
                if horas > 0:
                    txt += f" + {horas:g} hs)"
                else:
                    txt += f" completo{'s' if dias!=1 else ''})"
                self.lbl_desglose.config(text=txt)
            except: self.lbl_desglose.config(text="")
            
        # Limpiar trazas anteriores si existen (opcional, pero StringVar.trace es persistente)
        # Para evitar duplicados, usaremos un flag de inicialización
        if not hasattr(self, '_trace_jornadas_set'):
            self.var_jornadas.trace_add("write", update_desglose)
            self._trace_jornadas_set = True
        update_desglose() # Ejecutar una vez al cargar
        
        ttk.Spinbox(lf_form, from_=0.5, to=30.0, increment=0.5,
                    textvariable=self.var_jornadas, width=10).grid(row=0, column=1, sticky="nw")

        row_lbl("Cantidad de técnicos:", 1)
        ttk.Spinbox(lf_form, from_=1, to=max(1, len(self.tecnicos_info)), increment=1,
                    textvariable=self.var_ntec, width=10).grid(row=1, column=1, sticky="w")

        row_lbl("Servicio abreviado:", 2)
        ent = ttk.Entry(lf_form, textvariable=self.var_serv, width=16)
        ent.grid(row=2, column=1, sticky="w")
        if not hasattr(self, '_trace_serv_set'):
            self.var_serv.trace_add("write", lambda *_: self.var_serv.set(self.var_serv.get().upper()))
            self._trace_serv_set = True

        row_lbl("Días consecutivos:", 3)
        tk.Checkbutton(lf_form, variable=self.var_cons, bg="#f4f4f4",
                       command=lambda: self.var_viaje.set(False) if not self.var_cons.get() else None
                       ).grid(row=3, column=1, sticky="w")

        row_lbl("Viaje:", 4)
        tk.Checkbutton(lf_form, variable=self.var_viaje, bg="#f4f4f4",
                       command=lambda: self.var_cons.set(True) if self.var_viaje.get() else None
                       ).grid(row=4, column=1, sticky="w")

        row_lbl("Descripción:", 5)
        self.txt_desc = tk.Text(lf_form, height=5, width=32, font=("Segoe UI", 9),
                                wrap=tk.WORD, relief=tk.SOLID, bd=1)
        self.txt_desc.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(2, 0))
        if self._desc_cached:
            self.txt_desc.insert("1.0", self._desc_cached)

        def save_desc_and_call(fn, *args):
            self._desc_cached = self.txt_desc.get("1.0", "end-1c")
            fn(*args)

        # Contenedor para botones de patrones y checks
        pats_frame = tk.Frame(lf_form, bg="#f4f4f4")
        pats_frame.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(15, 5))
        
        btn_pat = tk.Button(pats_frame, text="🛠️ Seleccionar Patrones", 
                  command=lambda: save_desc_and_call(self._mostrar_vista_patrones),
                  bg="#34495e", fg="white", font=("Segoe UI", 9, "bold"),
                  relief=tk.RAISED, cursor="hand2", pady=5)
        btn_pat.pack(side=tk.LEFT, expand=True, fill=tk.X)
        
        btn_ojo = tk.Label(pats_frame, text="👁️", bg="#f4f4f4", font=("Segoe UI", 14), cursor="hand2")
        btn_ojo.pack(side=tk.LEFT, padx=5)
        btn_ojo.bind("<Button-1>", self._popup_ver_patrones)
        
        # Checkbox Filtrar conflictos de patrones
        if not hasattr(self, 'var_filtro_pats'):
            self.var_filtro_pats = tk.BooleanVar(value=False)
        tk.Checkbutton(lf_form, text="Excluir conflictos de patrones", variable=self.var_filtro_pats, bg="#f4f4f4", font=("Segoe UI", 8)).grid(row=8, column=0, columnspan=2, sticky="w")

    def _popup_ver_patrones(self, event):
        pats = set()
        if hasattr(self, '_patrones_preseleccionados'):
            for dlist in self._patrones_preseleccionados.values():
                for p in dlist:
                    pats.add(p)
                    
        txt = "Patrones seleccionados:\n\n" + ("\n".join(f"• {p}" for p in sorted(pats)) if pats else "(Ninguno)")
        
        pop = tk.Toplevel(self.root)
        pop.overrideredirect(True)
        pop.configure(bg="#fef9e7", highlightbackground="#f1c40f", highlightthickness=1)
        tk.Label(pop, text=txt, bg="#fef9e7", font=("Segoe UI", 9), justify="left", padx=15, pady=10).pack()
        
        pop.update_idletasks()
        pw, ph = pop.winfo_reqwidth(), pop.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        # Ajustar para que no salga del monitor
        x = min(event.x_root + 15, sw - pw - 5)
        y = min(event.y_root, sh - ph - 40)
        pop.geometry(f"+{x}+{y}")
        
        pop.bind("<FocusOut>", lambda e: pop.destroy())
        pop.focus_set()

    def _ejecutar_busqueda(self):
        try:
            val_jornadas = float(self.var_jornadas.get())
            # Forzamos n_tec a ser entero y lo actualizamos en la UI
            n_tec = int(round(float(self.var_ntec.get())))
            self.var_ntec.set(n_tec)
        except:
            messagebox.showerror("Error", "Jornadas o Técnicos inválidos"); return
            
        consecutivo = self.var_cons.get()
        viaje = self.var_viaje.get()
        serv = self.var_serv.get().strip()
        desc = self.txt_desc.get("1.0", tk.END).strip()
        
        if not serv:
            messagebox.showerror("Error", "Completá el campo Servicio Abreviado"); return
            
        # Recopilar patrones seleccionados para detección de conflictos
        pats_req = []
        if hasattr(self, '_patrones_preseleccionados'):
            for dlist in self._patrones_preseleccionados.values():
                for p in dlist:
                    if p not in pats_req: pats_req.append(p)
        
        f_inicio = datetime.date.today() + datetime.timedelta(days=1)
        
        # Doble búsqueda usando el motor externo (con exclusión automática ligada al check)
        excluir_conf = self.var_filtro_pats.get()
        
        res_est = engine.buscar_disponibilidad(self.tech_events, self.tecnicos_info, n_tec, val_jornadas, 
                                               consecutivo, viaje, f_inicio, 120, ignorar_no_ots=False,
                                               patrones_requeridos=pats_req, excluir_conflictos_pats=excluir_conf,
                                               ots_objetivo=self.ots_seleccionadas)
        res_flex = engine.buscar_disponibilidad(self.tech_events, self.tecnicos_info, n_tec, val_jornadas, 
                                                consecutivo, viaje, f_inicio, 120, ignorar_no_ots=True,
                                                patrones_requeridos=pats_req, excluir_conflictos_pats=excluir_conf,
                                                ots_objetivo=self.ots_seleccionadas)
        
        if not res_est and not res_flex:
            messagebox.showwarning("Sin opciones", "No se encontraron opciones libres en los próximos 120 días.")
            return

        self._params = {"serv": serv, "desc": desc, "medio_dia_fin": (val_jornadas % 1 != 0), "viaje": viaje}
        
        # Obtener IDs de Salesforce de las OTs seleccionadas
        sf_ids = []
        for f in self.bd_ots:
            if len(f) > IDX_OT and str(f[IDX_OT]).strip() in self.ots_seleccionadas:
                if len(f) > IDX_SF:
                    sf_id = str(f[IDX_SF]).strip()
                    if sf_id and sf_id not in sf_ids:
                        sf_ids.append(sf_id)
        self._params["sf_ids"] = sf_ids
        
        self._pivot_date = f_inicio
        self._mostrar_vista3(res_est, res_flex)

    def _buscar_siguiente_3(self):
        # 1. Determinar el nuevo pivot (fecha posterior a todas las opciones actuales)
        max_f = self._pivot_date
        todas = self._opciones_est + self._opciones_flex
        for op in todas:
            f0 = op["fechas"][0]["date"]
            if f0 > max_f: max_f = f0
        
        self._pivot_date = max_f + datetime.timedelta(days=1)
        
        val_jornadas = float(self.var_jornadas.get())
        n_tec = self.var_ntec.get()
        consecutivo = self.var_cons.get()
        viaje = self.var_viaje.get()
        
        # Patrones para búsqueda secuencial
        pats_req = []
        if hasattr(self, '_patrones_preseleccionados'):
            for dlist in self._patrones_preseleccionados.values():
                for p in dlist:
                    if p not in pats_req: pats_req.append(p)

        # Nueva búsqueda
        excluir_conf = getattr(self, 'var_filtro_pats', tk.BooleanVar(value=True)).get()
        res_est = engine.buscar_disponibilidad(self.tech_events, self.tecnicos_info, n_tec, val_jornadas, 
                                               consecutivo, viaje, self._pivot_date, 120, ignorar_no_ots=False,
                                               patrones_requeridos=pats_req, excluir_conflictos_pats=excluir_conf,
                                               ots_objetivo=self.ots_seleccionadas)
        res_flex = engine.buscar_disponibilidad(self.tech_events, self.tecnicos_info, n_tec, val_jornadas, 
                                                consecutivo, viaje, self._pivot_date, 120, ignorar_no_ots=True,
                                                patrones_requeridos=pats_req, excluir_conflictos_pats=excluir_conf,
                                                ots_objetivo=self.ots_seleccionadas)
        
        if not res_est and not res_flex:
            messagebox.showinfo("Fin de Calendario", "No se encontraron más opciones en los próximos 120 días.")
            return

        # Actualizar vista (reemplazar)
        self._mostrar_vista3(res_est, res_flex)

    # ──────────────────────────────────────────────
    # VISTA 3: Selección de Opción
    # ──────────────────────────────────────────────
    def _fmt_fecha(self, f_obj):
        # Si f_obj es un objeto {date, h_start, h_dur}
        if isinstance(f_obj, dict):
            f = f_obj["date"]
            h = f_obj["h_start"]
            return f"{DIAS_SEM[f.weekday()]} {f.day:02d}/{f.month:02d}/{f.year} @ {int(h):02d}:{int((h%1)*60):02d}"
        # Si es solo datetime.date
        return f"{DIAS_SEM[f_obj.weekday()]} {f_obj.day:02d}/{f_obj.month:02d}/{f_obj.year}"

    def _mostrar_vista3(self, res_est, res_flex):
        self._limpiar()
        # Guardamos ambas listas para recuperarlas al confirmar
        # Usamos un identificador para saber de qué lista es la selección
        self._opciones_est = res_est
        self._opciones_flex = res_flex

        self._header("Opciones de Disponibilidad", "← Reformular", self._mostrar_vista2)
        
        # Frame principal dividido en 2 columnas
        cols = tk.Frame(self.contenedor, bg="#f4f4f4")
        cols.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Columna Estricta
        f_est = tk.Frame(cols, bg="#f4f4f4")
        f_est.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        tk.Label(f_est, text="🛡️ OPCIONES ESTRICTAS\n(Sin conflictos)", bg="#f4f4f4", fg="#2c3e50", font=("Segoe UI", 10, "bold")).pack(pady=5)
        
        # Columna Flexible
        f_flex = tk.Frame(cols, bg="#f4f4f4")
        f_flex.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        tk.Label(f_flex, text="⚖️ OPCIONES FLEXIBLES\n(Ignoran bloqueos no-OT)", bg="#f4f4f4", fg="#2c3e50", font=("Segoe UI", 10, "bold")).pack(pady=5)

        # Variable única para toda la vista, valor: "tipo_indice" (ej: "est_0", "flex_2")
        self.var_seleccion_final = tk.StringVar(value="est_0")

        def crear_lista(parent, opciones, tipo_lista):
            cont = tk.Frame(parent, bg="#f4f4f4")
            cont.pack(fill=tk.BOTH, expand=True)
            
            canvas = tk.Canvas(cont, bg="#f4f4f4", highlightthickness=0)
            vsb = ttk.Scrollbar(cont, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=vsb.set)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            scroll_f = tk.Frame(canvas, bg="#f4f4f4")
            win = canvas.create_window((0,0), window=scroll_f, anchor="nw")
            scroll_f.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))

            if not opciones:
                tk.Label(scroll_f, text="No se encontraron\nopciones adicionales.", bg="#f4f4f4", fg="gray", font=("Segoe UI", 9, "italic")).pack(pady=20)
                return

            for i, op in enumerate(opciones):
                # Determinar si hay conflictos reales en modo flexible
                conflictos_totales = []
                for fecha_data in op["fechas"]:
                    conflictos_totales.extend(fecha_data.get("conf", []))
                
                tiene_conf = len(conflictos_totales) > 0
                bg_color = "white"
                # Color naranja muy suave si tiene conflictos en modo flexible
                if tipo_lista == "flex" and tiene_conf:
                    bg_color = "#fff3e0" 

                card = tk.Frame(scroll_f, bg=bg_color, relief=tk.RIDGE, bd=2)
                card.pack(fill=tk.X, pady=4, padx=2)

                val_radio = f"{tipo_lista}_{i}"
                rb = tk.Radiobutton(card, variable=self.var_seleccion_final, value=val_radio,
                                    bg=bg_color, activebackground=bg_color)
                rb.pack(side=tk.LEFT, padx=5)

                def sel(ev, v=val_radio): 
                    self.var_seleccion_final.set(v)

                info = tk.Frame(card, bg=bg_color)
                info.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=5)
                info.bind("<Button-1>", sel)

                tec_s = " · ".join([f"{t['nombre']} [{t['iniciales']}]" for t in op["tecnicos"]])
                tk.Label(info, text=tec_s, bg=bg_color, font=("Segoe UI", 9, "bold"), anchor="w").pack(fill=tk.X)

                for f_obj in op["fechas"]:
                    h_ini = f_obj["h_start"]; h_fin = h_ini + f_obj["h_dur"]
                    turno = f"{int(h_ini):02d}:{int((h_ini%1)*60):02d} - {int(h_fin):02d}:{int((h_fin%1)*60):02d}"
                    lbl_f = tk.Label(info, text=f"{self._fmt_fecha(f_obj)} ({turno})", bg=bg_color, font=("Segoe UI", 8), anchor="w")
                    lbl_f.pack(fill=tk.X)
                    lbl_f.bind("<Button-1>", lambda e, v=val_radio: self.var_seleccion_final.set(v))
                
                # Determinar si hay conflictos de patrones
                conflictos_patrones = []
                for fecha_data in op["fechas"]:
                    conflictos_patrones.extend(fecha_data.get("conf_patrones", []))
                
                tiene_conf_p = len(conflictos_patrones) > 0

                if tiene_conf:
                    # Botón de info de conflictos de tiempo
                    btn_conf = tk.Label(card, text="⚠️", bg=bg_color, fg="#e67e22", font=("Segoe UI", 12, "bold"), cursor="hand2")
                    btn_conf.pack(side=tk.RIGHT, padx=5)
                    btn_conf.bind("<Button-1>", lambda e, c=conflictos_totales: self._ver_conflictos(e, c))
                
                if tiene_conf_p:
                    # Botón de info de conflictos de patrones
                    btn_p = tk.Label(card, text="🛠️⚠️", bg=bg_color, fg="#c0392b", font=("Segoe UI", 10, "bold"), cursor="hand2")
                    btn_p.pack(side=tk.RIGHT, padx=5)
                    btn_p.bind("<Button-1>", lambda e, c=conflictos_patrones: self._ver_conflictos_patrones(e, c))

        crear_lista(f_est, res_est, "est")
        crear_lista(f_flex, res_flex, "flex")

        # --- PANELES INFERIORES DE DETALLE ---
        detail_f = tk.Frame(self.contenedor, bg="#f4f4f4", height=150)
        detail_f.pack(fill=tk.X, padx=15, pady=(5, 10))
        detail_f.pack_propagate(False)

        # 1. Resumen de Partidas
        lf_partidas = tk.LabelFrame(detail_f, text="📦 Resumen de Partidas involucradas", bg="#f4f4f4", font=("Segoe UI", 9, "bold"))
        lf_partidas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        t_part = ttk.Treeview(lf_partidas, columns=("trab", "pts", "cant"), show="headings", height=4)
        t_part.heading("trab", text="Trabajo")
        t_part.heading("pts", text="Puntos")
        t_part.heading("cant", text="Cant.")
        t_part.column("trab", width=220); t_part.column("pts", width=120); t_part.column("cant", width=50, anchor="center")
        
        # Calcular conteo
        conteo = {}
        for fila in self.bd_ots:
            if len(fila) > IDX_OT and str(fila[IDX_OT]).strip() in self.ots_seleccionadas:
                t = fila[IDX_TRAB].strip() if len(fila) > IDX_TRAB else ''
                p = fila[IDX_PTS].strip() if len(fila) > IDX_PTS else ''
                if t or p:
                    k = (t, p); conteo[k] = conteo.get(k, 0) + 1
        for (t, p), c in sorted(conteo.items()):
            t_part.insert("", "end", values=(t or "—", p or "—", c))
        
        sb_p = ttk.Scrollbar(lf_partidas, orient="vertical", command=t_part.yview)
        t_part.configure(yscrollcommand=sb_p.set)
        sb_p.pack(side=tk.RIGHT, fill=tk.Y)
        t_part.pack(fill=tk.BOTH, expand=True)

        # 2. Patrones Seleccionados
        lf_patrones = tk.LabelFrame(detail_f, text="🛠️ Patrones", bg="#f4f4f4", font=("Segoe UI", 9, "bold"))
        lf_patrones.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        txt_pats = tk.Text(lf_patrones, bg="white", font=("Segoe UI", 9), height=4, state=tk.DISABLED, relief=tk.FLAT)
        sb_pat = ttk.Scrollbar(lf_patrones, orient="vertical", command=txt_pats.yview)
        txt_pats.configure(yscrollcommand=sb_pat.set)
        sb_pat.pack(side=tk.RIGHT, fill=tk.Y)
        txt_pats.pack(fill=tk.BOTH, expand=True)
        
        # Obtener lista de patrones (agregando los de todos los días seleccionados)
        pats_display = "No se especificaron patrones."
        all_pats = set()
        if hasattr(self, '_patrones_preseleccionados') and self._patrones_preseleccionados:
            for day_list in self._patrones_preseleccionados.values():
                for p in day_list:
                    all_pats.add(p)
        
        if all_pats:
            pats_display = "\n".join([f"• {p}" for p in sorted(list(all_pats))])
        
        txt_pats.config(state=tk.NORMAL); txt_pats.insert("1.0", pats_display); txt_pats.config(state=tk.DISABLED)

        bottom3 = tk.Frame(self.contenedor, bg="#ecf0f1", height=50)
        bottom3.pack(fill=tk.X, side=tk.BOTTOM)
        
        tk.Button(bottom3, text="Manual ⚙", command=self._mostrar_vista_manual,
                  bg="#95a5a6", fg="white", font=("Segoe UI", 10, "bold"),
                  relief=tk.FLAT, padx=15, cursor="hand2").pack(side=tk.LEFT, padx=20, pady=8)

        tk.Button(bottom3, text="🔍 Buscar siguientes 3 opciones", command=self._buscar_siguiente_3,
                  bg="#34495e", fg="white", font=("Segoe UI", 10, "bold"),
                  relief=tk.FLAT, padx=15, cursor="hand2").pack(side=tk.LEFT, padx=5, pady=8)

        tk.Button(bottom3, text="Continuar →", command=self._confirmar,
                  bg="#2980b9", fg="white", font=("Segoe UI", 11, "bold"),
                  relief=tk.FLAT, padx=20, cursor="hand2").pack(side=tk.RIGHT, padx=20, pady=8)

    def _ver_conflictos(self, event, conflictos):
        pop = tk.Toplevel(self.root)
        pop.overrideredirect(True)
        pop.configure(bg="#fff3e0", highlightbackground="#e67e22", highlightthickness=1)
        
        tk.Label(pop, text="Eventos que se ignorarán:", bg="#fff3e0", font=("Segoe UI", 9, "bold")).pack(padx=10, pady=(10,5))
        for c in list(set(conflictos)):
            tk.Label(pop, text=f"• {c}", bg="#fff3e0", font=("Segoe UI", 9), anchor="w", justify=tk.LEFT).pack(fill=tk.X, padx=20)
        
        tk.Label(pop, text="(Haz clic fuera para cerrar)", bg="#fff3e0", fg="gray", font=("Segoe UI", 8, "italic")).pack(pady=5)
        
        # Posicionamiento inteligente
        pop.update_idletasks()
        w, h = pop.winfo_reqwidth(), pop.winfo_reqheight()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        
        x, y = event.x_root + 10, event.y_root + 10
        if x + w > sw - 10: x = event.x_root - w - 10
        if y + h > sh - 40: y = event.y_root - h - 10
        
        pop.geometry(f"+{max(5, x)}+{max(5, y)}")
        pop.bind("<FocusOut>", lambda e: pop.destroy() if pop.winfo_exists() else None)
        pop.focus_set()

    # ──────────────────────────────────────────────
    # CONFIRMACIÓN Y CREACIÓN DE EVENTOS
    # ──────────────────────────────────────────────
    def _agendar_final_logic(self, fechas_info, serv, desc_base):
        """Lógica centralizada para crear eventos en Google Calendar."""
        try:
            svc_cal, _ = extractor.get_google_services()
            ots_str = "/".join(self.ots_seleccionadas)
            cliente = self.cliente_filtro or "Varios"
            
            # Generar ID de paquete único para este agendamiento completo
            pkg_id = str(uuid.uuid4())
            sf_ids_str = ", ".join(self._params.get("sf_ids", []))
            total_j = len(fechas_info)

            error_count = 0
            for f_idx, f_obj in enumerate(fechas_info):
                # Construir descripción con patrones
                pats = f_obj.get("patrones_seleccionados", [])
                
                # Si no tiene patrones (ej: vinieron de pre-selección), buscamos en caché temporal
                if not pats and hasattr(self, '_patrones_preseleccionados'):
                    pats = self._patrones_preseleccionados.get(f_idx, [])

                desc_pats = ""
                if pats:
                    desc_pats = "\n\n--------------------------------\n\nPatrones asignados:\n- " + "\n- ".join(pats)
                
                full_desc = desc_base + desc_pats
                
                tecs_del_dia = f_obj.get("tecnicos", [])
                for tech_nom in tecs_del_dia:
                    tech_obj = next((t for t in self.tecnicos_info if t["nombre"] == tech_nom), None)
                    if not tech_obj: continue
                    ini = tech_obj.get("iniciales", "??")
                    
                    titulo = f"{ots_str} ({cliente}) - {serv} - {ini}"
                    h_start = f_obj["h_start"]
                    h_dur = f_obj["h_dur"]
                    h_end = h_start + h_dur
                    
                    dt_start = datetime.datetime.combine(f_obj["date"], 
                                datetime.time(hour=int(h_start), minute=int(round((h_start%1)*60))))
                    
                    # Para el fin, si se pasa de las 23:59 lo limitamos
                    h_fin_int = int(h_end)
                    m_fin_int = int(round((h_end%1)*60))
                    if h_fin_int >= 24: h_fin_int = 23; m_fin_int = 59
                    
                    dt_end = datetime.datetime.combine(f_obj["date"], 
                                datetime.time(hour=h_fin_int, minute=m_fin_int))
                    
                    event = {
                        'summary': titulo,
                        'description': full_desc,
                        'start': {'dateTime': dt_start.isoformat() + "-03:00", 'timeZone': 'America/Argentina/Buenos_Aires'},
                        'end': {'dateTime': dt_end.isoformat() + "-03:00", 'timeZone': 'America/Argentina/Buenos_Aires'},
                        'extendedProperties': {
                            'private': {
                                'app_pkg_id': pkg_id,
                                'app_ots': ots_str,
                                'app_sf_ids': sf_ids_str,
                                'app_patrones': json.dumps(pats, ensure_ascii=False),
                                'app_jornada': f"{f_idx + 1}/{total_j}",
                                'app_cliente': cliente,
                                'app_servicio': serv
                            }
                        }
                    }
                    try:
                        svc_cal.events().insert(calendarId=tech_obj["correo"], body=event).execute()
                    except: 
                        error_count += 1
            
            if error_count == 0:
                messagebox.showinfo("¡Éxito!", "Se agendaron todos los eventos correctamente.")
                self.volver_fn()
            else:
                messagebox.showwarning("Atención", f"Se crearon eventos pero hubo {error_count} errores.")
                self.volver_fn()
        except Exception as e:
            messagebox.showerror("Error Crítico", f"No se pudo conectar a Calendar: {e}")

    def _popup_seleccionar_tecnicos(self, event, current_list, callback):
        """Muestra un popup con checkboxes para la selección múltiple de técnicos."""
        pop = tk.Toplevel(self.root)
        pop.overrideredirect(True)
        pop.attributes("-topmost", True)
        pop.configure(bg="#2c3e50", padx=1, pady=1)
        
        inner = tk.Frame(pop, bg="white")
        inner.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(inner, text="Asignar Técnicos", bg="#34495e", fg="white", font=("Segoe UI", 9, "bold")).pack(fill=tk.X)
        
        def al_cambiar(*args):
            seleccionados = [n for n, v in vars_dict.items() if v.get()]
            callback(seleccionados)
            
        vars_dict = {}
        for t in self.tecnicos_info:
            nom = t["nombre"]
            var = tk.BooleanVar(value=(nom in current_list))
            var.trace_add("write", al_cambiar)
            vars_dict[nom] = var
            tk.Checkbutton(inner, text=nom, variable=var, bg="white", anchor="w", font=("Segoe UI", 9)).pack(fill=tk.X, padx=10, pady=2)
        
        tk.Label(inner, text="(Para cerrar, haz clic fuera)", bg="#f4f4f4", fg="gray", font=("Segoe UI", 8, "italic")).pack(pady=5)
        
        # Posicionamiento
        pop.update_idletasks()
        pw, ph = pop.winfo_reqwidth(), pop.winfo_reqheight()
        pop.geometry(f"+{event.x_root}+{event.y_root}")
        pop.bind("<FocusOut>", lambda e: pop.destroy())
        pop.focus_set()

    def _mostrar_vista_manual(self):
        self._limpiar()
        self._header("Programación Manual", "← Volver", self._mostrar_vista2)
        
        try:
            k = float(self.var_jornadas.get())
        except: 
            messagebox.showerror("Error", "Datos de jornadas inválidos"); return

        main_manual = tk.Frame(self.contenedor, bg="#f4f4f4")
        main_manual.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Tabla de jornadas
        table_f = tk.LabelFrame(main_manual, text="Detalle de Jornadas", bg="#f4f4f4", font=("Segoe UI", 10, "bold"), padx=10, pady=10)
        table_f.pack(fill=tk.BOTH, expand=True)
        
        # Canvas con scroll para la tabla
        canvas = tk.Canvas(table_f, bg="#f4f4f4", highlightthickness=0)
        vsb = ttk.Scrollbar(table_f, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.manual_rows_frame = tk.Frame(canvas, bg="#f4f4f4")
        canvas.create_window((0,0), window=self.manual_rows_frame, anchor="nw")
        self.manual_rows_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        headers = ["Jornada", "Fecha (AAAA-MM-DD)", "Inicio (HH:MM)", "Duración (hs)", "Técnicos Asignados"]
        for c, h in enumerate(headers):
            tk.Label(self.manual_rows_frame, text=h, bg="#f4f4f4", font=("Segoe UI", 9, "bold")).grid(row=0, column=c, padx=10, pady=5)

        self.manual_data_rows = []
        
        def agregar_fila(fecha=None, hora="07:00", dur=None, tecnicos=None):
            idx = len(self.manual_data_rows)
            row_idx = idx + 1
            
            if fecha is None: fecha = datetime.date.today().strftime("%Y-%m-%d")
            if dur is None: dur = "9.0"
            if tecnicos is None: tecnicos = []
            
            tk.Label(self.manual_rows_frame, text=f"Día {row_idx}", bg="#f4f4f4").grid(row=row_idx, column=0)
            
            vf = tk.StringVar(value=fecha)
            tk.Entry(self.manual_rows_frame, textvariable=vf, width=15, justify="center").grid(row=row_idx, column=1, padx=5, pady=2)
            
            vh = tk.StringVar(value=hora)
            tk.Entry(self.manual_rows_frame, textvariable=vh, width=10, justify="center").grid(row=row_idx, column=2, padx=5, pady=2)
            
            vd = tk.StringVar(value=dur)
            tk.Entry(self.manual_rows_frame, textvariable=vd, width=8, justify="center").grid(row=row_idx, column=3, padx=5, pady=2)
            
            btn_tec_text = tk.StringVar(value=f"{len(tecnicos)} técnicos" if tecnicos else "Seleccionar...")
            btn_tec = tk.Button(self.manual_rows_frame, textvariable=btn_tec_text, width=25, bg="white", relief=tk.GROOVE)
            btn_tec.grid(row=row_idx, column=4, padx=10, pady=2)
            
            row_data = {"fecha": vf, "hora": vh, "dur": vd, "tecnicos": tecnicos, "btn_text": btn_tec_text}
            
            def open_picker(e, rd=row_data):
                def update_tecs(new_list):
                    rd["tecnicos"] = new_list
                    rd["btn_text"].set(f"{len(new_list)} técnicos: " + ", ".join([t[:2] for t in new_list]))
                self._popup_seleccionar_tecnicos(e, rd["tecnicos"], update_tecs)
                
            btn_tec.bind("<Button-1>", open_picker)
            self.manual_data_rows.append(row_data)

        # Cargar jornadas iniciales
        n_ini = math.ceil(k)
        h_resto = (k - int(k)) * 9.0
        for i in range(n_ini):
            h_d = 9.0 if (i < int(k) or h_resto == 0) else h_resto
            agregar_fila(dur=f"{h_d:g}")

        # Botón agregar
        tk.Button(main_manual, text="+ Agregar Jornada", command=agregar_fila, bg="#3498db", fg="white", font=("Segoe UI", 9, "bold")).pack(pady=10)

        bottom = tk.Frame(self.contenedor, bg="#ecf0f1", height=50)
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Button(bottom, text="✅ Revisar y Confirmar", command=self._agendar_manual,
                  bg="#27ae60", fg="white", font=("Segoe UI", 11, "bold"),
                  relief=tk.FLAT, padx=20, cursor="hand2").pack(side=tk.RIGHT, padx=20, pady=8)

    def _agendar_manual(self):
        try:
            fechas_info = []
            for r in self.manual_data_rows:
                if not r["tecnicos"]:
                    messagebox.showerror("Error", f"Fila {self.manual_data_rows.index(r)+1}: Seleccioná al menos un técnico."); return
                
                f = datetime.datetime.strptime(r["fecha"].get(), "%Y-%m-%d").date()
                hm = r["hora"].get().split(':')
                hi = int(hm[0]) + int(hm[1])/60.0
                hd = float(r["dur"].get())
                fechas_info.append({
                    "date": f, 
                    "h_start": hi, 
                    "h_dur": hd, 
                    "tecnicos": r["tecnicos"]
                })
        except Exception as e:
            messagebox.showerror("Error", f"Formato de fecha u hora incorrecto: {e}"); return

        op_manual = {
            "fechas": fechas_info,
            "es_manual": True
        }
        self._mostrar_vista_patrones(op_manual)

    def _confirmar(self):
        val = self.var_seleccion_final.get() # Formato "tipo_index" (est_0, flex_1)
        try:
            tipo, idx_str = val.split('_')
            idx = int(idx_str)
            op = self._opciones_est[idx] if tipo == "est" else self._opciones_flex[idx]
            self._mostrar_vista_confirmacion(op)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo recuperar la opción seleccionada: {e}")

    def _mostrar_vista_patrones(self, op=None):
        self._limpiar()
        
        volver_fn = self._mostrar_vista2
        if op:
            volver_fn = self._mostrar_vista_manual if op.get("es_manual") else lambda: self._mostrar_vista3(self._opciones_est, self._opciones_flex)

        self._header("Selección de Patrones", "← Volver", volver_fn)
        
        main = tk.Frame(self.contenedor, bg="#f4f4f4")
        main.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # 1. Filtrar patrones disponibles
        trabajos_ots = set()
        for f in self.bd_ots:
            if len(f) > IDX_OT and str(f[IDX_OT]).strip() in self.ots_seleccionadas:
                trabajos_ots.add(f[IDX_TRAB].strip())
        
        patrones_filtrados = []
        for p in self.patrones_db[1:]: # Omitir cabecera
            if len(p) >= 2:
                nombre = p[IDX_PATRON_NOMBRE]
                rango  = p[IDX_PATRON_RANGO] if len(p) > IDX_PATRON_RANGO else ""
                try: 
                    compatibles = json.loads(p[IDX_PATRON_TRABAJOS]) 
                except: 
                    compatibles = []
                
                if any(t in trabajos_ots for t in compatibles):
                    patrones_filtrados.append({"nom": nombre, "rango": rango})

        # Ordenar por Nombre (ID) ascendente
        patrones_filtrados.sort(key=lambda x: x["nom"])

        if not patrones_filtrados:
            messagebox.showinfo("Patrones", "No se encontraron patrones compatibles con los trabajos de estas OTs.")
            if op: self._mostrar_vista_confirmacion(op)
            else: self._mostrar_vista2()
            return

        # 2. UI Selección
        top = tk.Frame(main, bg="#f4f4f4")
        top.pack(fill=tk.X, pady=5)
        
        viaje = self._params.get("viaje", False) if op else self.var_viaje.get()
        self.var_fijar_pats = tk.BooleanVar(value=viaje)
        chk_fijar = tk.Checkbutton(top, text="Fijar Patrones (mismos para todos los días)", 
                                   variable=self.var_fijar_pats, bg="#f4f4f4", font=("Segoe UI", 10, "bold"))
        chk_fijar.pack(side=tk.LEFT)
        if viaje: chk_fijar.config(state=tk.DISABLED)

        # Determinar cantidad de días
        if op:
            n_dias = len(op["fechas"])
            textos_dias = [f"Día {i+1}: {self._fmt_fecha(f_obj)}" for i, f_obj in enumerate(op["fechas"])]
        else:
            try: val_j = float(self.var_jornadas.get())
            except: val_j = 1.0
            n_dias = math.ceil(val_j)
            textos_dias = [f"Día {i+1}" for i in range(n_dias)]

        # Contenedor para la tabla con scroll
        table_container = tk.Frame(main, bg="#f4f4f4")
        table_container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(table_container, bg="white", highlightthickness=0)
        vsb = ttk.Scrollbar(table_container, orient="vertical", command=canvas.yview)
        hsb = ttk.Scrollbar(table_container, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        inner_table = tk.Frame(canvas, bg="#dfe6e9")
        canvas.create_window((0,0), window=inner_table, anchor="nw")
        
        def _update_scrollregion(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner_table.bind("<Configure>", _update_scrollregion)

        # Headers
        h_style = {"bg": "#2d3436", "fg": "white", "font": ("Segoe UI", 9, "bold"), "padx": 10, "pady": 5}
        tk.Label(inner_table, text="Patrón (Rango)", width=35, **h_style).grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        for j in range(n_dias):
            tk.Label(inner_table, text=textos_dias[j], width=18, **h_style).grid(row=0, column=j+1, sticky="nsew", padx=1, pady=1)

        self.patrones_vars_per_day = [{} for _ in range(n_dias)] # Al revés para facilitar guardado: n_dias diccionarios {nom: Var}
        self.rows_vars = [] # Para facilitar la sincronización: [{nom, vars: [Var1, Var2...]}]

        if not hasattr(self, '_patrones_preseleccionados'):
            self._patrones_preseleccionados = {}

        def sync_row(pat_nom, val, source_day_idx):
            if self.var_fijar_pats.get():
                row_data = next((r for r in self.rows_vars if r["nom"] == pat_nom), None)
                if row_data:
                    for v in row_data["vars"]:
                        v.set(val)

        for i, p_info in enumerate(patrones_filtrados):
            p_nom = p_info["nom"]
            p_ran = p_info["rango"]
            display_name = f"{p_nom} ({p_ran})" if p_ran else p_nom
            
            row_bg = "white" if i % 2 == 0 else "#f8f9fa"
            tk.Label(inner_table, text=display_name, bg=row_bg, anchor="w", font=("Segoe UI", 9), padx=10).grid(row=i+1, column=0, sticky="nsew", padx=1, pady=1)
            
            row_var_list = []
            for j in range(n_dias):
                already = p_nom in self._patrones_preseleccionados.get(j, [])
                v = tk.BooleanVar(value=already)
                self.patrones_vars_per_day[j][p_nom] = v
                row_var_list.append(v)
                
                cb = tk.Checkbutton(inner_table, variable=v, bg=row_bg, activebackground=row_bg)
                cb.grid(row=i+1, column=j+1, sticky="nsew", padx=1, pady=1)
                
                # Trace para sincronización
                v.trace_add("write", lambda *args, pn=p_nom, var=v, dj=j: sync_row(pn, var.get(), dj))

            self.rows_vars.append({"nom": p_nom, "vars": row_var_list})

        def on_fijar_change(*args):
            if self.var_fijar_pats.get():
                # Al activar, sincronizamos todo con el Día 1
                for row in self.rows_vars:
                    val1 = row["vars"][0].get()
                    for v in row["vars"][1:]:
                        v.set(val1)

        self.var_fijar_pats.trace_add("write", on_fijar_change)

        # 3. Resumen Agrupado de OTs (en la parte inferior)
        lf_res = tk.LabelFrame(main, text="Resumen de Partidas Seleccionadas", bg="#f4f4f4",
                                font=("Segoe UI", 10, "bold"), padx=10, pady=5)
        lf_res.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))
        
        conteo = {}
        for f in self.bd_ots:
            if len(f) > IDX_OT and str(f[IDX_OT]).strip() in self.ots_seleccionadas:
                t = f[IDX_TRAB].strip() if len(f) > IDX_TRAB else ''
                p = f[IDX_PTS].strip() if len(f) > IDX_PTS else ''
                if t or p:
                    k = (t, p); conteo[k] = conteo.get(k, 0) + 1
        
        t_res = ttk.Treeview(lf_res, columns=("trab","pts","cant"), show="headings", height=4)
        t_res.heading("trab", text="Trabajo a Ejecutar")
        t_res.heading("pts",  text="Puntos de Cal.")
        t_res.heading("cant", text="Cant.")
        t_res.column("trab", width=350)
        t_res.column("pts",  width=200)
        t_res.column("cant", width=60, anchor="center")
        
        for (t, p), c in sorted(conteo.items()):
            t_res.insert("", "end", values=(t or "—", p or "—", c))
            
        sb_res = ttk.Scrollbar(lf_res, orient=tk.VERTICAL, command=t_res.yview)
        t_res.configure(yscrollcommand=sb_res.set)
        sb_res.pack(side=tk.RIGHT, fill=tk.Y)
        t_res.pack(fill=tk.BOTH, expand=True)

        bottom = tk.Frame(self.contenedor, bg="#ecf0f1", height=50)
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        
        def guardar_y_continuar():
            self._patrones_preseleccionados = {}
            for j in range(n_dias):
                sel = [n for n, v in self.patrones_vars_per_day[j].items() if v.get()]
                self._patrones_preseleccionados[j] = sel
                if op: op["fechas"][j]["patrones_seleccionados"] = sel
            
            if op: self._mostrar_vista_confirmacion(op)
            else: self._mostrar_vista2()

        btn_txt = "Confirmar Selección" if not op else "Siguiente →"
        tk.Button(bottom, text=btn_txt, command=guardar_y_continuar,
                  bg="#2980b9", fg="white", font=("Segoe UI", 11, "bold"),
                  relief=tk.FLAT, padx=20, cursor="hand2").pack(side=tk.RIGHT, padx=20, pady=8)

    def _ver_conflictos_patrones(self, event, conflictos):
        pop = tk.Toplevel(self.root)
        pop.overrideredirect(True)
        pop.configure(bg="#fdedec", highlightbackground="#c0392b", highlightthickness=1)
        
        tk.Label(pop, text="⚠️ Conflictos de Patrones detectados:", bg="#fdedec", font=("Segoe UI", 9, "bold"), fg="#c0392b").pack(padx=10, pady=(10,5))
        
        # Agrupar por patrón para que no se repitan tanto
        agrupados = {}
        for c in conflictos:
            k = c["patron"]
            if k not in agrupados: agrupados[k] = []
            agrupados[k].append(f"{c['tecnico']} en {c['donde']}")
        
        for pat, lugares in agrupados.items():
            tk.Label(pop, text=f"• Patrón {pat} ya está en:", bg="#fdedec", font=("Segoe UI", 9, "bold"), anchor="w").pack(fill=tk.X, padx=15)
            for lug in list(set(lugares)):
                tk.Label(pop, text=f"  - {lug}", bg="#fdedec", font=("Segoe UI", 8), anchor="w").pack(fill=tk.X, padx=25)
        
        tk.Label(pop, text="(Haz clic fuera para cerrar)", bg="#fdedec", fg="gray", font=("Segoe UI", 8, "italic")).pack(pady=5, padx=10)
        
        pop.update_idletasks()
        pop.geometry(f"+{event.x_root}+{event.y_root}")
        pop.bind("<FocusOut>", lambda e: pop.destroy())
        pop.focus_set()

    def _mostrar_vista_confirmacion(self, op):
        # Asegurarse de que los patrones pre-seleccionados se inyecten si no existen
        if hasattr(self, '_patrones_preseleccionados'):
            for i, f_obj in enumerate(op["fechas"]):
                if "patrones_seleccionados" not in f_obj:
                    f_obj["patrones_seleccionados"] = self._patrones_preseleccionados.get(i, [])

        self._limpiar()
        
        # Volver al paso anterior según el origen
        if op.get("es_manual"):
            back_fn = self._mostrar_vista_manual
        else:
            back_fn = lambda: self._mostrar_vista3(self._opciones_est, self._opciones_flex)
            
        self._header("Resumen Final de Programación", "← Volver", back_fn)
        
        main = tk.Frame(self.contenedor, bg="#f4f4f4")
        main.pack(fill=tk.BOTH, expand=True, padx=40, pady=20)
        
        ots_str = "/".join(self.ots_seleccionadas)
        cliente = self.cliente_filtro or "Varios"
        
        tk.Label(main, text="Verificá los datos antes de agendar", bg="#f4f4f4", font=("Segoe UI", 12), fg="#555").pack(pady=(0,15))
        
        # Card de Info General
        info_f = tk.Frame(main, bg="white", relief=tk.RIDGE, bd=1, padx=25, pady=20)
        info_f.pack(fill=tk.X)
        
        tk.Label(info_f, text=f"CLIENTE: {cliente}", bg="white", font=("Segoe UI", 11, "bold"), fg="#2c3e50").pack(anchor="w")
        tk.Label(info_f, text=f"OTs: {ots_str}", bg="white", font=("Segoe UI", 10), fg="#34495e").pack(anchor="w", pady=(2,10))
        
        tk.Label(info_f, text=f"SERVICIO: {self._params.get('serv', 'N/A')}", bg="white", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        if self._params.get('desc'):
            tk.Label(info_f, text=f"Descripción: {self._params['desc']}", bg="white", font=("Segoe UI", 9, "italic"), fg="#7f8c8d", wraplength=800, justify="left").pack(anchor="w")

        # Tabla de Cronograma detallado
        tk.Label(main, text="Cronograma Detallado:", bg="#f4f4f4", font=("Segoe UI", 10, "bold"), pady=10).pack(anchor="w")
        
        # Frame scrollable para las jornadas si son muchas
        table_f = tk.Frame(main, bg="white", relief=tk.RIDGE, bd=1)
        table_f.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(table_f, bg="white", highlightthickness=0)
        vsb = ttk.Scrollbar(table_f, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        rows_f = tk.Frame(canvas, bg="white")
        canvas.create_window((0,0), window=rows_f, anchor="nw")
        rows_f.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # Headers tabla resumen
        h_style = {"bg": "#34495e", "fg": "white", "font": ("Segoe UI", 9, "bold"), "pady": 5}
        tk.Label(rows_f, text="Día", width=8, **h_style).grid(row=0, column=0, padx=1, pady=1)
        tk.Label(rows_f, text="Fecha", width=15, **h_style).grid(row=0, column=1, padx=1, pady=1)
        tk.Label(rows_f, text="Horario", width=20, **h_style).grid(row=0, column=2, padx=1, pady=1)
        tk.Label(rows_f, text="Técnicos", width=60, **h_style).grid(row=0, column=3, padx=1, pady=1)

        for i, f_obj in enumerate(op["fechas"]):
            bg = "#f9f9f9" if i % 2 == 0 else "white"
            h_ini = f_obj["h_start"]; h_dur = f_obj["h_dur"]
            turno = f"{int(h_ini):02d}:{int((h_ini%1)*60):02d} - {int(h_ini+h_dur):02d}:{int(((h_ini+h_dur)%1)*60):02d}"
            tecs = ", ".join(f_obj.get("tecnicos", []))
            
            c_style = {"bg": bg, "font": ("Segoe UI", 9), "pady": 5}
            tk.Label(rows_f, text=f"Día {i+1}", **c_style).grid(row=i+1, column=0, sticky="nsew", padx=1, pady=1)
            tk.Label(rows_f, text=self._fmt_fecha(f_obj), **c_style).grid(row=i+1, column=1, sticky="nsew", padx=1, pady=1)
            tk.Label(rows_f, text=turno, **c_style).grid(row=i+1, column=2, sticky="nsew", padx=1, pady=1)
            tk.Label(rows_f, text=tecs, anchor="w", padx=10, **c_style).grid(row=i+1, column=3, sticky="nsew", padx=1, pady=1)

        # Botón Final
        btns = tk.Frame(self.contenedor, bg="#ecf0f1", height=70)
        btns.pack(fill=tk.X, side=tk.BOTTOM)
        
        tk.Button(btns, text="🚀 Finalizar y Agendar en Google Calendar", 
                  command=lambda: self._agendar_final_logic(op["fechas"], self._params.get('serv'), self._params.get('desc')),
                  bg="#27ae60", fg="white", font=("Segoe UI", 11, "bold"), relief=tk.FLAT, padx=25, cursor="hand2").pack(side=tk.RIGHT, padx=25, pady=15)
        
        tk.Button(btns, text="← Modificar", 
                  command=back_fn,
                  bg="#95a5a6", fg="white", font=("Segoe UI", 11, "bold"), relief=tk.FLAT, padx=20, cursor="hand2").pack(side=tk.LEFT, padx=25, pady=15)
