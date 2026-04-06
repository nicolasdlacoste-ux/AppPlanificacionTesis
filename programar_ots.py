import os
import json
import math
import datetime
import itertools
import tkinter as tk
from tkinter import ttk, messagebox

import extractor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_OTS_PATH = os.path.join(BASE_DIR, 'bd_ots_cache.json')

IDX_ESTADO = 0   # Columna A  (Estatus Trabajos Campo)
IDX_OT    = 1   # Columna B
IDX_CLIE  = 3   # Columna D
IDX_TRAB  = 5   # Columna F
IDX_PTS   = 12  # Columna M
IDX_FECHA = 16  # Columna Q

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

        self._cargar_ots_unicas()
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
                    lbl.bind("<Button-1>", lambda e, n=[nro]: self._popup_partidas(e, n))

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

        main = tk.Frame(self.contenedor, bg="#f4f4f4")
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        # ── Panel Izquierdo: Resumen de Partidas ──
        lf_part = tk.LabelFrame(main, text="Resumen de Partidas", bg="#f4f4f4",
                                font=("Segoe UI", 10, "bold"), padx=6, pady=6)
        lf_part.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        filas = []
        for fila in self.bd_ots:
            if len(fila) > IDX_OT and str(fila[IDX_OT]).strip() in self.ots_seleccionadas:
                t = fila[IDX_TRAB].strip() if len(fila) > IDX_TRAB else ''
                p = fila[IDX_PTS].strip() if len(fila) > IDX_PTS else ''
                if t or p:
                    filas.append((t, p))
        conteo = {}
        for t, p in filas:
            k = (t, p); conteo[k] = conteo.get(k, 0) + 1

        t2 = ttk.Treeview(lf_part, columns=("trab","pts","cant"), show="headings", height=14)
        t2.heading("trab", text="Trabajo a Ejecutar")
        t2.heading("pts",  text="Puntos de Cal.")
        t2.heading("cant", text="Partidas")
        t2.column("trab", width=230)
        t2.column("pts",  width=120)
        t2.column("cant", width=70, anchor="center")
        for (t, p), c in sorted(conteo.items()):
            t2.insert("", "end", values=(t or "—", p or "—", c))
        sb2 = ttk.Scrollbar(lf_part, orient=tk.VERTICAL, command=t2.yview)
        t2.configure(yscrollcommand=sb2.set)
        sb2.pack(side=tk.RIGHT, fill=tk.Y)
        t2.pack(fill=tk.BOTH, expand=True)
        tk.Label(lf_part, text=f"Total: {sum(conteo.values())} partidas",
                 bg="#f4f4f4", fg="#2c3e50", font=("Segoe UI", 10, "bold"), anchor="e").pack(fill=tk.X, pady=4)

        # ── Panel Derecho: Formulario ──
        lf_form = tk.LabelFrame(main, text="Parámetros de Programación", bg="#f4f4f4",
                                font=("Segoe UI", 10, "bold"), padx=14, pady=12)
        lf_form.pack(side=tk.RIGHT, fill=tk.Y, ipadx=10)

        def row_lbl(text, r):
            tk.Label(lf_form, text=text, bg="#f4f4f4", font=("Segoe UI", 10),
                     anchor="w").grid(row=r, column=0, sticky="w", pady=8, padx=(0, 10))

        row_lbl("Jornadas requeridas:", 0)
        self.var_jornadas = tk.StringVar(value="1.0")
        self.lbl_desglose = tk.Label(lf_form, text="(1 día completo)", bg="#f4f4f4", 
                                     font=("Segoe UI", 9, "italic"), fg="#7f8c8d")
        self.lbl_desglose.grid(row=0, column=1, sticky="w", pady=(35, 0))
        
        def update_desglose(*args):
            try:
                val = float(self.var_jornadas.get())
                dias = int(val)
                horas = (val - dias) * 9
                txt = f"({dias} día{'s' if dias!=1 else ''} completo{'s' if dias!=1 else ''}"
                if horas > 0:
                    txt += f" + {horas:g} hs)"
                else:
                    txt += ")"
                self.lbl_desglose.config(text=txt)
            except: self.lbl_desglose.config(text="")
            
        self.var_jornadas.trace_add("write", update_desglose)
        
        ttk.Spinbox(lf_form, from_=0.5, to=30.0, increment=0.5,
                    textvariable=self.var_jornadas, width=10).grid(row=0, column=1, sticky="nw")

        row_lbl("Cantidad de técnicos:", 1)
        self.var_ntec = tk.IntVar(value=1)
        ttk.Spinbox(lf_form, from_=1, to=max(1, len(self.tecnicos_info)), increment=1,
                    textvariable=self.var_ntec, width=10).grid(row=1, column=1, sticky="w")

        row_lbl("Servicio abreviado:", 2)
        self.var_serv = tk.StringVar()
        ent = ttk.Entry(lf_form, textvariable=self.var_serv, width=16)
        ent.grid(row=2, column=1, sticky="w")
        self.var_serv.trace_add("write", lambda *_: self.var_serv.set(self.var_serv.get().upper()))

        row_lbl("Días consecutivos:", 3)
        self.var_cons  = tk.BooleanVar(value=False)
        self.var_viaje = tk.BooleanVar(value=False)
        tk.Checkbutton(lf_form, variable=self.var_cons, bg="#f4f4f4",
                       command=lambda: self.var_viaje.set(False) if not self.var_cons.get() else None
                       ).grid(row=3, column=1, sticky="w")

        row_lbl("Viaje:", 4)
        tk.Checkbutton(lf_form, variable=self.var_viaje, bg="#f4f4f4",
                       command=lambda: self.var_cons.set(True) if self.var_viaje.get() else None
                       ).grid(row=4, column=1, sticky="w")

        row_lbl("Descripción:", 5)
        self.txt_desc = tk.Text(lf_form, height=5, width=28, font=("Segoe UI", 9),
                                wrap=tk.WORD, relief=tk.SOLID, bd=1)
        self.txt_desc.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(2, 0))

        # Botones inferiores
        bottom2 = tk.Frame(self.contenedor, bg="#ecf0f1", height=50)
        bottom2.pack(fill=tk.X, side=tk.BOTTOM)
        bottom2.pack_propagate(False)
        
        tk.Button(bottom2, text="Manual ⚙", command=self._mostrar_vista_manual,
                  bg="#95a5a6", fg="white", font=("Segoe UI", 10, "bold"),
                  relief=tk.FLAT, padx=15, cursor="hand2").pack(side=tk.LEFT, padx=20, pady=8)

        tk.Button(bottom2, text="Buscar Disponibilidad →", command=self._ejecutar_busqueda,
                  bg="#2980b9", fg="white", font=("Segoe UI", 11, "bold"),
                  relief=tk.FLAT, padx=20, cursor="hand2").pack(side=tk.RIGHT, padx=20, pady=8)

    def _obtener_slots_ocupados(self, nombre, date_key, ignorar_no_ots=False):
        """Retorna (set_ocupados, lista_conflictos). Si ignorar_no_ots=True, los eventos no-OT se guardan como conflictos."""
        n_norm = str(nombre).strip()
        evs = self.tech_events.get(n_norm, {}).get(date_key, [])
        ocupados = set()
        conflictos = []
        
        for ev in evs:
            s_val = ev.get("sort", 0); e_val = ev.get("sort_end", 2400)
            s_h = s_val // 100 + (s_val % 100) / 60.0
            e_h = e_val // 100 + (e_val % 100) / 60.0
            
            es_ot = ev.get("es_ot", False)
            marcar_ocupado = True
            if ignorar_no_ots and not es_ot:
                marcar_ocupado = False

            for i in range(11): 
                h_i = 7.0 + i
                h_next = h_i + 1.0
                if s_h < h_next and e_h > h_i:
                    if marcar_ocupado:
                        ocupados.add(i)
                    else:
                        conflictos.append(f"{ev.get('original_text', ev.get('text'))}")
        
        return ocupados, list(set(conflictos))

    def _buscar_bloque_libre(self, nombres, date_key, horas_req, ignorar_no_ots=False):
        """Busca el primer slot disponible para un bloque de horas_req consecutivo."""
        slots_ocupados_total = set()
        conflictos_totales = []
        for nm in nombres:
            ocu, conf = self._obtener_slots_ocupados(nm, date_key, ignorar_no_ots)
            slots_ocupados_total.update(ocu)
            conflictos_totales.extend(conf)
        
        n_slots_nec = math.ceil(horas_req)
        for start_slot in range(11 - n_slots_nec + 1):
            bloque = range(start_slot, start_slot + n_slots_nec)
            if all(s not in slots_ocupados_total for s in bloque):
                # Si encontramos un hueco, los conflictos reales son solo los que solapan con ESTE bloque
                conflictos_reales = []
                if ignorar_no_ots:
                    # Re-verificamos conflictos específicos para este bloque seleccionado
                    for nm in nombres:
                        evs = self.tech_events.get(str(nm).strip(), {}).get(date_key, [])
                        for ev in evs:
                            if ev.get("es_ot"): continue
                            s_v = ev.get("sort", 0); e_v = ev.get("sort_end", 2400)
                            sh = s_v//100 + (s_v%100)/60.0; eh = e_v//100 + (e_v%100)/60.0
                            if sh < (7.0 + start_slot + n_slots_nec) and eh > (7.0 + start_slot):
                                conflictos_reales.append(f"{nm}: {ev.get('original_text')}")
                
                return 7.0 + start_slot, list(set(conflictos_reales))
        return None, []

    def _tech_libre(self, nombre, date_key):
        ocu, _ = self._obtener_slots_ocupados(nombre, date_key)
        return len(ocu) == 0

    def _son_consecutivos(self, fechas, viaje):
        for i in range(len(fechas) - 1):
            d1, d2 = fechas[i], fechas[i+1]
            diff = (d2 - d1).days
            if viaje:
                if diff != 1:
                    return False
            else:
                ok = (diff == 1) or (d1.weekday() == 4 and d2.weekday() == 0 and diff == 3)
                if not ok:
                    return False
        return True

    def _buscar_consecutivos_en(self, libres, n, viaje):
        for i in range(len(libres) - n + 1):
            v = libres[i:i+n]
            if self._son_consecutivos(v, viaje):
                return v
        return None

    def _buscar_en_ventana(self, libres, n):
        for i in range(len(libres)):
            lim = libres[i] + datetime.timedelta(days=30)
            bloque = [d for d in libres[i:] if d <= lim]
            if len(bloque) >= n:
                return bloque[:n]
        return None

    def _buscar_disponibilidad(self, n_tec, dias_nec, consecutivo, viaje, f_inicio, ventana, ignorar_no_ots=False):
        f_fin = f_inicio + datetime.timedelta(days=ventana)
        workdays = [f_inicio + datetime.timedelta(days=i) for i in range((f_fin - f_inicio).days + 1) if (f_inicio + datetime.timedelta(days=i)).weekday() < 5]

        n_full = int(dias_nec)
        h_resto = (dias_nec - n_full) * 9.0
        n_total_dias = math.ceil(dias_nec)

        candidatos = []
        for combo in itertools.combinations(self.tecnicos_info, n_tec):
            nombres = [t["nombre"] for t in combo]
            dias_validos = []
            for wd in workdays:
                dk = wd.strftime("%Y-%m-%d")
                h_start_9, conf9 = self._buscar_bloque_libre(nombres, dk, 9.0, ignorar_no_ots)
                h_req_resto = h_resto if h_resto > 0 else 9.0
                h_start_r, confr = self._buscar_bloque_libre(nombres, dk, h_req_resto, ignorar_no_ots)
                
                if h_start_9 is not None:
                    dias_validos.append({"date": wd, "h_start": h_start_9, "full": True, "conf": conf9})
                elif h_start_r is not None:
                    dias_validos.append({"date": wd, "h_start": h_start_r, "full": False, "conf": confr})

            if len(dias_validos) < n_total_dias:
                continue

            # Intentar formar una secuencia de n_total_dias
            # Para simplificar, buscamos subconjuntos de dias_validos que cumplan n_full dias completos
            # y 1 dia parcial si h_resto > 0.
            
            # Si es consecutivo, buscamos bloques seguidos en la lista de dias_validos
            for i in range(len(dias_validos) - n_total_dias + 1):
                ventana_dias = dias_validos[i : i + n_total_dias]
                fechas_puras = [dv["date"] for dv in ventana_dias]
                
                # Check consecutivo
                if consecutivo and not self._son_consecutivos(fechas_puras, viaje):
                    continue
                
                # Check si tenemos suficientes días "full"
                full_count = sum(1 for dv in ventana_dias if dv["full"])
                if full_count < n_full:
                    continue
                
                # Si llegamos aquí, tenemos una opción válida
                # Estructuramos la opción
                opcion_fechas = []
                for idx, dv in enumerate(ventana_dias):
                    h_dur = 9.0 if (idx < n_full) else h_resto
                    if h_dur == 0: h_dur = 9.0 # Caso jornadas enteras
                    opcion_fechas.append({
                        "date": dv["date"],
                        "h_start": dv["h_start"],
                        "h_dur": h_dur,
                        "conf": dv.get("conf", [])
                    })
                
                candidatos.append({
                    "tecnicos": list(combo),
                    "fechas": opcion_fechas,
                    "f0": fechas_puras[0]
                })

        candidatos.sort(key=lambda x: x["f0"])
        resultado, vistos = [], set()
        for c in candidatos:
            if len(resultado) >= 3: break
            key = (c["f0"], frozenset(t["nombre"] for t in c["tecnicos"]))
            if key not in vistos:
                vistos.add(key)
                resultado.append(c)
        return resultado

    def _ejecutar_busqueda(self):
        try:
            val_jornadas = float(self.var_jornadas.get())
            n_tec = self.var_ntec.get()
        except:
            messagebox.showerror("Error", "Jornadas o Técnicos inválidos"); return
            
        consecutivo = self.var_cons.get()
        viaje = self.var_viaje.get()
        serv = self.var_serv.get().strip()
        desc = self.txt_desc.get("1.0", tk.END).strip()
        
        if not serv:
            messagebox.showerror("Error", "Completá el campo Servicio Abreviado"); return
            
        f_inicio = datetime.date.today() + datetime.timedelta(days=1)
        
        # Doble búsqueda: Estricta y Flexible
        res_est = self._buscar_disponibilidad(n_tec, val_jornadas, consecutivo, viaje, f_inicio, 120, ignorar_no_ots=False)
        res_flex = self._buscar_disponibilidad(n_tec, val_jornadas, consecutivo, viaje, f_inicio, 120, ignorar_no_ots=True)
        
        if not res_est and not res_flex:
            messagebox.showwarning("Sin opciones", "No se encontraron opciones libres en los próximos 120 días.")
            return

        self._params = {"serv": serv, "desc": desc, "medio_dia_fin": (val_jornadas % 1 != 0)}
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
                
                if tiene_conf:
                    # Botón de info de conflictos
                    btn_conf = tk.Label(card, text="⚠️", bg=bg_color, fg="#e67e22", font=("Segoe UI", 12, "bold"), cursor="hand2")
                    btn_conf.pack(side=tk.RIGHT, padx=10)
                    btn_conf.bind("<Button-1>", lambda e, c=conflictos_totales: self._ver_conflictos(e, c))

        crear_lista(f_est, res_est, "est")
        crear_lista(f_flex, res_flex, "flex")

        bottom3 = tk.Frame(self.contenedor, bg="#ecf0f1", height=50)
        bottom3.pack(fill=tk.X, side=tk.BOTTOM)
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
        
        # Posicionamiento
        pop.update_idletasks()
        w, h = pop.winfo_reqwidth(), pop.winfo_reqheight()
        pop.geometry(f"+{event.x_root}+{event.y_root}")
        pop.bind("<FocusOut>", lambda e: pop.destroy())
        pop.focus_set()

    # ──────────────────────────────────────────────
    # CONFIRMACIÓN Y CREACIÓN DE EVENTOS
    # ──────────────────────────────────────────────
    def _agendar_final_logic(self, nombres, fechas_info, serv, desc_base):
        """Lógica centralizada para crear eventos en Google Calendar."""
        try:
            svc_cal, _ = extractor.get_google_services()
            ots_str = "/".join(self.ots_seleccionadas)
            cliente = self.ots_unicas[0]["cliente"] if self.ots_unicas else "Varios"
            
            error_count = 0
            for tech_nom in nombres:
                tech_obj = next((t for t in self.tecnicos_info if t["nombre"]==tech_nom), None)
                if not tech_obj: continue
                ini = tech_obj.get("iniciales", "??")
                
                for f_obj in fechas_info:
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
                        'description': desc_base,
                        'start': {'dateTime': dt_start.isoformat() + "-03:00", 'timeZone': 'America/Argentina/Buenos_Aires'},
                        'end': {'dateTime': dt_end.isoformat() + "-03:00", 'timeZone': 'America/Argentina/Buenos_Aires'}
                    }
                    try:
                        svc_cal.events().insert(calendarId=tech_obj["correo"], body=event).execute()
                    except: error_count += 1
            
            if error_count == 0:
                messagebox.showinfo("¡Éxito!", "Se agendaron todos los eventos correctamente.")
                self.volver_fn()
            else:
                messagebox.showwarning("Atención", f"Se crearon eventos pero hubo {error_count} errores.")
                self.volver_fn()
        except Exception as e:
            messagebox.showerror("Error Crítico", f"No se pudo conectar a Calendar: {e}")

    def _mostrar_vista_manual(self):
        self._limpiar()
        self._header("Programación Manual", "← Volver", self._mostrar_vista2)
        
        try:
            k = float(self.var_jornadas.get())
            n_tec = self.var_ntec.get()
        except: messagebox.showerror("Error", "Datos inválidos"); return

        main_manual = tk.Frame(self.contenedor, bg="#f4f4f4")
        main_manual.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # 1. Técnicos
        top = tk.LabelFrame(main_manual, text="1. Personal Asignado", bg="#f4f4f4", font=("Segoe UI", 10, "bold"), padx=10, pady=10)
        top.pack(fill=tk.X, pady=(0, 10))
        self.manual_tech_vars = []
        for i in range(n_tec):
            v = tk.StringVar()
            self.manual_tech_vars.append(v)
            ttk.Combobox(top, textvariable=v, values=[t["nombre"] for t in self.tecnicos_info], 
                         state="readonly", width=30).grid(row=i//2, column=i%2, padx=10, pady=5)

        # 2. Jornadas
        mid = tk.LabelFrame(main_manual, text="2. Cronograma de Trabajo", bg="#f4f4f4", font=("Segoe UI", 10, "bold"), padx=10, pady=10)
        mid.pack(fill=tk.BOTH, expand=True)

        n_dias = math.ceil(k)
        h_resto = (k - int(k)) * 9.0
        self.manual_rows = []
        headers = ["Jornada", "Fecha (AAAA-MM-DD)", "Inicio (HH:MM)", "Duración (hs)"]
        for c, h in enumerate(headers):
            tk.Label(mid, text=h, bg="#f4f4f4", font=("Segoe UI", 9, "bold")).grid(row=0, column=c, padx=5, pady=5)

        for i in range(n_dias):
            row = i + 1
            tk.Label(mid, text=f"Día {row}", bg="#f4f4f4").grid(row=row, column=0)
            vf = tk.StringVar(value=datetime.date.today().strftime("%Y-%m-%d"))
            tk.Entry(mid, textvariable=vf, width=15, justify="center").grid(row=row, column=1, padx=5)
            vh = tk.StringVar(value="07:00")
            tk.Entry(mid, textvariable=vh, width=10, justify="center").grid(row=row, column=2, padx=5)
            h_dur = 9.0 if (i < int(k) or h_resto == 0) else h_resto
            vd = tk.StringVar(value=f"{h_dur:g}")
            tk.Entry(mid, textvariable=vd, width=8, justify="center").grid(row=row, column=3, padx=5)
            self.manual_rows.append({"fecha": vf, "hora": vh, "dur": vd})

        bottom = tk.Frame(self.contenedor, bg="#ecf0f1", height=50)
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Button(bottom, text="✅ Confirmar y Agendar Todo", command=self._agendar_manual,
                  bg="#27ae60", fg="white", font=("Segoe UI", 11, "bold"),
                  relief=tk.FLAT, padx=20, cursor="hand2").pack(side=tk.RIGHT, padx=20, pady=8)

    def _agendar_manual(self):
        nombres = [v.get() for v in self.manual_tech_vars if v.get()]
        if len(nombres) < self.var_ntec.get():
            messagebox.showerror("Error", "Seleccioná todos los técnicos."); return
        
        serv = self.var_serv.get().strip(); desc = self.txt_desc.get("1.0", tk.END).strip()
        try:
            fechas_info = []
            for r in self.manual_rows:
                f = datetime.datetime.strptime(r["fecha"].get(), "%Y-%m-%d").date()
                hm = r["hora"].get().split(':')
                hi = int(hm[0]) + int(hm[1])/60.0
                hd = float(r["dur"].get())
                fechas_info.append({"date": f, "h_start": hi, "h_dur": hd})
        except: messagebox.showerror("Error", "Formato de fecha u hora incorrecto."); return

        if messagebox.askyesno("Confirmar", "¿Deseas agendar estos eventos manuales?"):
            self._agendar_final_logic(nombres, fechas_info, serv, desc)

    def _confirmar(self):
        val = self.var_seleccion_final.get() # Formato "tipo_index" (est_0, flex_1)
        try:
            tipo, idx_str = val.split('_')
            idx = int(idx_str)
            op = self._opciones_est[idx] if tipo == "est" else self._opciones_flex[idx]
            self._mostrar_vista_confirmacion(op)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo recuperar la opción seleccionada: {e}")

    def _mostrar_vista_confirmacion(self, op):
        self._limpiar()
        self._header("Confirmar Programación", "← Volver", lambda: self._mostrar_vista3(self._opciones_est, self._opciones_flex))
        
        main = tk.Frame(self.contenedor, bg="#f4f4f4")
        main.pack(fill=tk.BOTH, expand=True, padx=40, pady=20)
        
        # Resumen de Datos
        ots_str = "/".join(self.ots_seleccionadas)
        cliente = self.cliente_filtro or "Varios"
        
        tk.Label(main, text="Resumen de la Programación", bg="#f4f4f4", font=("Segoe UI", 14, "bold"), fg="#2c3e50").pack(pady=(0,20))
        
        info_f = tk.Frame(main, bg="white", relief=tk.RIDGE, bd=1, padx=25, pady=25)
        info_f.pack(fill=tk.X)
        
        tk.Label(info_f, text=f"OTs: {ots_str}", bg="white", font=("Segoe UI", 11, "bold"), anchor="w").pack(fill=tk.X)
        tk.Label(info_f, text=f"Cliente: {cliente}", bg="white", font=("Segoe UI", 11), anchor="w").pack(fill=tk.X)
        tk.Label(info_f, text=f"Servicio: {self._params['serv']}", bg="white", font=("Segoe UI", 11), anchor="w").pack(fill=tk.X, pady=(0,10))
        
        # Técnicos
        tec_names = [t["nombre"] for t in op["tecnicos"]]
        tk.Label(info_f, text=f"Técnicos ({len(tec_names)}):", bg="white", font=("Segoe UI", 10, "bold"), anchor="w").pack(fill=tk.X)
        tk.Label(info_f, text=" · ".join(tec_names), bg="white", font=("Segoe UI", 10), anchor="w", fg="#34495e").pack(fill=tk.X, pady=(0,10))
        
        # Cronograma
        tk.Label(info_f, text="Cronograma de Jornadas:", bg="white", font=("Segoe UI", 10, "bold"), anchor="w").pack(fill=tk.X)
        for i, f_obj in enumerate(op["fechas"]):
            h_ini = f_obj["h_start"]; h_dur = f_obj["h_dur"]
            h_fin = h_ini + h_dur
            turno = f"{int(h_ini):02d}:{int((h_ini%1)*60):02d} - {int(h_fin):02d}:{int((h_fin%1)*60):02d} ({h_dur:g} hs)"
            tk.Label(info_f, text=f"Día {i+1}: {self._fmt_fecha(f_obj)} | {turno}", bg="white", font=("Segoe UI", 10), anchor="w").pack(fill=tk.X, padx=10)

        # Botones
        btns = tk.Frame(self.contenedor, bg="#ecf0f1", height=70)
        btns.pack(fill=tk.X, side=tk.BOTTOM)
        
        tk.Button(btns, text="🚀 Finalizar y Agendar en Google Calendar", 
                  command=lambda: self._agendar_final_logic(tec_names, op["fechas"], self._params["serv"], self._params["desc"]),
                  bg="#27ae60", fg="white", font=("Segoe UI", 11, "bold"), relief=tk.FLAT, padx=25, cursor="hand2").pack(side=tk.RIGHT, padx=25, pady=15)
        
        tk.Button(btns, text="← Modificar", 
                  command=lambda: self._mostrar_vista3(self._opciones_est, self._opciones_flex),
                  bg="#95a5a6", fg="white", font=("Segoe UI", 11, "bold"), relief=tk.FLAT, padx=20, cursor="hand2").pack(side=tk.LEFT, padx=25, pady=15)
