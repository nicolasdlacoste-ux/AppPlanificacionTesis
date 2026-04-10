import os
import json
import datetime
import uuid
import tkinter as tk
from tkinter import ttk, messagebox
import extractor
import engine

DIAS_SEM = ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"]
IDX_OT = 1
IDX_TRAB = 5
IDX_PTS = 12

class GestionProyectosModule:
    def __init__(self, root, contenedor, tecnicos_info, bd_ots, tech_events, volver_fn, preselect_id=None):
        self.root = root
        self.contenedor = contenedor
        self.tecnicos_info = tecnicos_info
        self.bd_ots = bd_ots
        self.tech_events = tech_events
        self.volver_fn = volver_fn
        self.preselect_id = preselect_id
        
        self.paquetes = []
        self.paquete_seleccionado = None
        
        self._pivot_date = None
        self._opciones_est = []
        self._opciones_flex = []
        self._params_busqueda = {} # Para repetir la búsqueda
        
        self._mostrar_cargando()
        # Iniciar carga en hilo para no congelar la UI
        import threading
        threading.Thread(target=self._cargar_datos, daemon=True).start()

    def _mostrar_cargando(self):
        self._limpiar()
        tk.Label(self.contenedor, text="Cargando Proyectos desde Google Calendar...", 
                 font=("Segoe UI", 12), bg="#f4f4f4").pack(expand=True)

    def _limpiar(self):
        for w in self.contenedor.winfo_children():
            w.destroy()

    def _cargar_datos(self):
        try:
            svc_cal, _ = extractor.get_google_services()
            # Rango amplio para gestión: -15 días a +120 días
            eventos = extractor.obtener_agendas(svc_cal, self.tecnicos_info)
            todos = extractor.clasificar_agendas_en_paquetes(eventos)
            
            # FILTRO: Solo mostrar proyectos que tengan OTs (real o virtual)
            self.paquetes = [p for p in todos if p["tipo"] in ("real", "virtual")]
            
            # Ordenar por fecha de inicio (primer evento de cada paquete)
            for p in self.paquetes:
                p["fecha_min"] = min([e["Inicio"] for e in p["eventos"]]) if p["eventos"] else "9999-99-99"
            
            self.paquetes.sort(key=lambda x: x["fecha_min"], reverse=True)
            self.root.after(0, self._crear_interfaz)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"No se pudieron cargar los proyectos: {e}"))

    def _aplicar_preseleccion(self):
        if self.tree.exists(self.preselect_id):
            self.tree.selection_set(self.preselect_id)
            self.tree.see(self.preselect_id)
            self._on_seleccionar(None)

    def _crear_interfaz(self):
        self._limpiar()
        
        # Header
        header = tk.Frame(self.contenedor, bg="#2c3e50", height=50)
        header.pack(fill=tk.X)
        tk.Button(header, text="← Volver", command=self.volver_fn, bg="#34495e", fg="white", relief=tk.FLAT).pack(side=tk.LEFT, padx=10, pady=10)
        tk.Label(header, text="GESTIÓN DE PROYECTOS (OTs PROGRAMADAS)", bg="#2c3e50", fg="white", font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT, padx=20)

        main = tk.PanedWindow(self.contenedor, orient=tk.HORIZONTAL, bg="#ddd", sashwidth=4)
        main.pack(fill=tk.BOTH, expand=True)

        # --- Panel Izquierdo: Lista ---
        left = tk.Frame(main, bg="white")
        main.add(left, width=450)
        
        tk.Label(left, text="Proyectos Activos", bg="#ecf0f1", font=("Segoe UI", 10, "bold"), pady=5).pack(fill=tk.X)
        
        # Buscadores
        f_busq = tk.Frame(left, bg="white", pady=5)
        f_busq.pack(fill=tk.X)
        
        tk.Label(f_busq, text="🔍 OT:", bg="white", font=("Segoe UI", 9)).grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.ent_ot = ttk.Entry(f_busq, width=20)
        self.ent_ot.grid(row=0, column=1, padx=5, pady=2, sticky="we")
        self.ent_ot.bind("<KeyRelease>", lambda e: self._filtrar_lista())

        tk.Label(f_busq, text="👤 Cliente:", bg="white", font=("Segoe UI", 9)).grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.ent_cl = ttk.Entry(f_busq, width=20)
        self.ent_cl.grid(row=1, column=1, padx=5, pady=2, sticky="we")
        self.ent_cl.bind("<KeyRelease>", lambda e: self._filtrar_lista())

        cols = ("ots", "cliente", "inicio", "tipo")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("ots", text="OTs")
        self.tree.heading("cliente", text="Cliente")
        self.tree.heading("inicio", text="Inicio")
        self.tree.heading("tipo", text="Estado")
        
        self.tree.column("ots", width=120)
        self.tree.column("cliente", width=150)
        self.tree.column("inicio", width=90)
        self.tree.column("tipo", width=70)
        
        sb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_seleccionar)

        # --- Panel Derecho: Detalle ---
        self.right = tk.Frame(main, bg="#f4f4f4")
        main.add(self.right)
        
        self._llenar_lista(self.paquetes)
        
        # Si hay una pre-selección, dispararla ahora que la lista está llena
        if self.preselect_id:
            self.root.after(100, self._aplicar_preseleccion)

    def _llenar_lista(self, lista):
        for i in self.tree.get_children(): self.tree.delete(i)
        for p in lista:
            tag = "Legacy" if p["tipo"] == "virtual" else "Cargado"
            f = p["fecha_min"][:10] if isinstance(p["fecha_min"], str) else p["fecha_min"]
            self.tree.insert("", "end", iid=p["id"], values=(p["ots"], p["cliente"], f, tag))

    def _filtrar_lista(self):
        q_ot = self.ent_ot.get().lower().strip()
        q_cl = self.ent_cl.get().lower().strip()
        
        filtrados = self.paquetes
        
        if q_ot:
            filtrados = [p for p in filtrados if q_ot in str(p["ots"]).lower()]
            
        if q_cl:
            # Traer proyectos que "aún no han finalizado" = Su fecha de fin teórica es >= hoy, y coincide el cliente
            hoy_iso = datetime.datetime.now().isoformat()
            cl_filtrados = []
            for p in filtrados:
                if q_cl in str(p["cliente"]).lower():
                    # Check if not finished (has events in the future)
                    if p.get("eventos") and max([e["Fin"] for e in p["eventos"]]) >= hoy_iso:
                        cl_filtrados.append(p)
            filtrados = cl_filtrados
            
        self._llenar_lista(filtrados)

    def _mostrar_vacio(self):
        for w in self.right.winfo_children(): w.destroy()
        tk.Label(self.right, text="Selecciona un proyecto de la lista\npara ver detalles y acciones.", 
                 fg="gray", bg="#f4f4f4", font=("Segoe UI", 11, "italic")).pack(expand=True)

    def _on_seleccionar(self, event):
        sel = self.tree.selection()
        if not sel: return
        p_id = sel[0]
        pkg = next((p for p in self.paquetes if p["id"] == p_id), None)
        if pkg:
            self.paquete_seleccionado = pkg
            self._ver_detalle(pkg)

    def _ver_detalle(self, pkg):
        for w in self.right.winfo_children(): w.destroy()
        
        # Título del Proyecto
        title_f = tk.Frame(self.right, bg="#34495e", pady=10)
        title_f.pack(fill=tk.X)
        tk.Label(title_f, text=f"PROYECTO: {pkg['ots']}", bg="#34495e", fg="white", font=("Segoe UI", 12, "bold")).pack()
        tk.Label(title_f, text=pkg["cliente"], bg="#34495e", fg="#bdc3c7", font=("Segoe UI", 10)).pack()

        # Botones de Acción
        btn_f = tk.Frame(self.right, bg="#ecf0f1", pady=10)
        btn_f.pack(fill=tk.X)
        
        # Estilo botones
        b_sty = {"font": ("Segoe UI", 9, "bold"), "padx": 10, "pady": 5, "cursor": "hand2", "relief": tk.GROOVE}
        
        tk.Button(btn_f, text="📅 Reprogramar (Manual)", bg="#2980b9", fg="white", **b_sty, command=self._reprogramar_manual).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_f, text="🔍 Mejor Fecha", bg="#27ae60", fg="white", **b_sty, command=self._reprogramar_inteligente).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_f, text="🚨 Solucionar Conflictos", bg="#f39c12", fg="white", **b_sty, command=self._abrir_solucionador).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_f, text="🗑️", bg="#c0392b", fg="white", **b_sty, command=self._eliminar_con_confirmacion).pack(side=tk.RIGHT, padx=10)
        
        # Info Detallada
        info_f = tk.Frame(self.right, bg="white", padx=20, pady=20)
        info_f.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Desglose de jornadas
        tk.Label(info_f, text="Jornadas Agendadas", font=("Segoe UI", 10, "bold"), bg="white").pack(anchor="w")
        
        t_jor = ttk.Treeview(info_f, columns=("fecha", "inicio", "fin", "tecnico"), show="headings", height=8)
        t_jor.heading("fecha", text="Fecha")
        t_jor.heading("inicio", text="Inicio")
        t_jor.heading("fin", text="Fin")
        t_jor.heading("tecnico", text="Técnico")
        t_jor.column("fecha", width=100)
        t_jor.column("inicio", width=80)
        t_jor.column("fin", width=80)
        t_jor.column("tecnico", width=150)
        t_jor.pack(fill=tk.X, pady=10)
        
        # Patrones (si hay metadatos)
        # Buscar el primer evento que tenga patrones grabados
        pats_str = "No especificados"
        for ev in pkg["eventos"]:
            props = ev.get('extendedProperties', {}).get('private', {})
            p = props.get('app_patrones')
            if p and p != "[]":
                try: pats_str = ", ".join(json.loads(p))
                except: pats_str = p
                break
        
        tk.Label(info_f, text=f"Patrones: {pats_str}", bg="white", font=("Segoe UI", 9, "italic"), fg="gray", wraplength=400, justify="left").pack(anchor="w", pady=5)
        
        for ev in pkg["eventos"]:
            t_jor.insert("", "end", values=(ev["Inicio"][:10], ev["Inicio"][11:16], ev["Fin"][11:16], ev["Técnico"]))

    def _abrir_solucionador(self):
        import conflictos_ui
        conflictos_ui.ConflictosModule(self.root, self.paquete_seleccionado, self.tecnicos_info, self.tech_events, self.volver_fn, bd_ots=self.bd_ots)

    def _reprogramar_manual(self):
        if not self.paquete_seleccionado: return
        
        # Diálogo para pedir nueva fecha
        pop = tk.Toplevel(self.root)
        pop.title("Nueva Fecha de Inicio")
        pop.geometry("300x150")
        pop.transient(self.root)
        pop.grab_set()
        
        tk.Label(pop, text=f"Mover proyecto {self.paquete_seleccionado['ots']}\na una nueva fecha de inicio:", pady=10).pack()
        ent = ttk.Entry(pop)
        ent.insert(0, datetime.date.today().strftime("%Y-%m-%d"))
        ent.pack(pady=5)
        
        def confirmar():
            try:
                nueva_f = datetime.datetime.strptime(ent.get(), "%Y-%m-%d").date()
                pop.destroy()
                self._ejecutar_reprogramacion_manual(nueva_f)
            except: 
                messagebox.showerror("Error", "Formato inválido (AAAA-MM-DD)")

        tk.Button(pop, text="Confirmar Movimiento", command=confirmar, bg="#2980b9", fg="white", font=("Segoe UI", 9, "bold")).pack(pady=10)

    def _ejecutar_reprogramacion_manual(self, nueva_f_inicio):
        pkg = self.paquete_seleccionado
        orig_f_inicio = pkg["fecha_min"]
        if isinstance(orig_f_inicio, str):
            orig_f_inicio = datetime.datetime.fromisoformat(orig_f_inicio).date()
        
        delta = nueva_f_inicio - orig_f_inicio
        print(f"Desplazando proyecto {pkg['ots']} por {delta.days} días...")
        
        svc_cal, _ = extractor.get_google_services()
        exito = 0
        total = len(pkg["eventos"])
        
        for ev in pkg["eventos"]:
            try:
                # 1. Parsear fechas originales
                # Manejar formatos ISO (con o sin T)
                inicio_str = ev["Inicio"]
                fin_str = ev["Fin"]
                
                dt_ini = datetime.datetime.fromisoformat(inicio_str.replace("Z", "+00:00"))
                dt_fin = datetime.datetime.fromisoformat(fin_str.replace("Z", "+00:00"))
                
                # 2. Aplicar Delta
                new_dt_ini = dt_ini + delta
                new_dt_fin = dt_fin + delta
                
                # 3. Patch en Calendar
                # Preservamos los extendedProperties originales
                svc_cal.events().patch(
                    calendarId=ev["calendar_id"],
                    eventId=ev["id"],
                    body={
                        'start': {'dateTime': new_dt_ini.isoformat()},
                        'end': {'dateTime': new_dt_fin.isoformat()}
                    }
                ).execute()
                exito += 1
            except Exception as e:
                print(f"Error moviendo evento {ev['id']}: {e}")

        messagebox.showinfo("Proceso Terminado", f"Se movieron {exito} de {total} eventos.")
        self._cargar_datos() # Recargar lista

    def _reprogramar_inteligente(self):
        if not self.paquete_seleccionado: return
        pkg = self.paquete_seleccionado
        
        # 1. Determinar métricas originales
        ncs = [len(set([e["Técnico"] for e in pkg["eventos"] if e["Inicio"][:10] == d])) 
               for d in set([e["Inicio"][:10] for e in pkg["eventos"]])]
        n_tec_req = max(ncs) if ncs else 1
        
        total_hs = 0
        for ev in pkg["eventos"]:
            try:
                ini = datetime.datetime.fromisoformat(ev["Inicio"].replace("Z", "+00:00"))
                fin = datetime.datetime.fromisoformat(ev["Fin"].replace("Z", "+00:00"))
                total_hs += (fin - ini).total_seconds() / 3600.0
            except: pass
        val_jornadas = total_hs / 9.0 / n_tec_req
        consecutivo = True
        viaje = any("viaje" in str(ev.get('description','')).lower() for ev in pkg["eventos"])
        
        # Guardar parámetros para repetición
        self._params_busqueda = {
            "n_tec": n_tec_req,
            "dias": val_jornadas,
            "cons": consecutivo,
            "viaje": viaje
        }
        
        f_inicio = datetime.date.today() + datetime.timedelta(days=1)
        self._pivot_date = f_inicio
        
        # Obtener patrones del proyecto para detección de conflictos
        pats_req = []
        for ev_p in pkg["eventos"]:
            p = ev_p.get('extendedProperties', {}).get('private', {}).get('app_patrones')
            if p:
                try: 
                    plist = json.loads(p)
                    for item in plist:
                        if item not in pats_req: pats_req.append(item)
                except: pass

        # Busqueda inicial
        res_est = engine.buscar_disponibilidad(self.tech_events, self.tecnicos_info, n_tec_req, val_jornadas, 
                                               consecutivo, viaje, f_inicio, 120, ignorar_no_ots=False,
                                               patrones_requeridos=pats_req)
        res_flex = engine.buscar_disponibilidad(self.tech_events, self.tecnicos_info, n_tec_req, val_jornadas, 
                                                consecutivo, viaje, f_inicio, 120, ignorar_no_ots=True,
                                                patrones_requeridos=pats_req)
        
        if not res_est and not res_flex:
            messagebox.showwarning("Sin Opciones", "No se encontraron fechas libres en los próximos 120 días.")
            return

        self._mostrar_vista_busqueda(res_est, res_flex)

    def _buscar_siguiente_3(self):
        # Avanzar el pivot
        max_f = self._pivot_date
        todas = self._opciones_est + self._opciones_flex
        for op in todas:
            f0 = op["fechas"][0]["date"]
            if f0 > max_f: max_f = f0
        
        self._pivot_date = max_f + datetime.timedelta(days=1)
        
        p = self._params_busqueda
        
        # Patrones para búsqueda secuencial
        pats_req = []
        for ev_p in self.paquete_seleccionado["eventos"]:
            p_str = ev_p.get('extendedProperties', {}).get('private', {}).get('app_patrones')
            if p_str:
                try: 
                    plist = json.loads(p_str)
                    for item in plist:
                        if item not in pats_req: pats_req.append(item)
                except: pass

        res_est = engine.buscar_disponibilidad(self.tech_events, self.tecnicos_info, p["n_tec"], p["dias"], 
                                               p["cons"], p["viaje"], self._pivot_date, 120, ignorar_no_ots=False,
                                               patrones_requeridos=pats_req)
        res_flex = engine.buscar_disponibilidad(self.tech_events, self.tecnicos_info, p["n_tec"], p["dias"], 
                                                p["cons"], p["viaje"], self._pivot_date, 120, ignorar_no_ots=True,
                                                patrones_requeridos=pats_req)
        
        if not res_est and not res_flex:
            messagebox.showinfo("Fin de Calendario", "No hay más opciones disponibles.")
            return
            
        self._mostrar_vista_busqueda(res_est, res_flex)

    def _fmt_fecha(self, f_obj):
        if isinstance(f_obj, dict):
            f = f_obj["date"]
            h = f_obj["h_start"]
            return f"{DIAS_SEM[f.weekday()]} {f.day:02d}/{f.month:02d}/{f.year} @ {int(h):02d}:{int((h%1)*60):02d}"
        return f"{DIAS_SEM[f_obj.weekday()]} {f_obj.day:02d}/{f_obj.month:02d}/{f_obj.year}"

    def _mostrar_vista_busqueda(self, res_est, res_flex):
        # Esta vista reemplaza el panel de detalle temporalmente
        for w in self.right.winfo_children(): w.destroy()
        self._opciones_est = res_est
        self._opciones_flex = res_flex

        tk.Label(self.right, text="Opciones de Disponibilidad Detectadas", bg="#2c3e50", fg="white", 
                 font=("Segoe UI", 11, "bold"), pady=10).pack(fill=tk.X)
        
        cols_f = tk.Frame(self.right, bg="#f4f4f4")
        cols_f.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        f_est = tk.Frame(cols_f, bg="#f4f4f4")
        f_est.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        tk.Label(f_est, text="🛡️ ESTRICTA", bg="#f4f4f4", font=("Segoe UI", 9, "bold")).pack()
        
        f_flex = tk.Frame(cols_f, bg="#f4f4f4")
        f_flex.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        tk.Label(f_flex, text="⚖️ FLEXIBLE", bg="#f4f4f4", font=("Segoe UI", 9, "bold")).pack()

        self.var_sel = tk.StringVar(value="none")

        def crear_lista(parent, opciones, tipo):
            canvas = tk.Canvas(parent, bg="#f4f4f4", highlightthickness=0)
            vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=vsb.set)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            scroll_f = tk.Frame(canvas, bg="#f4f4f4")
            canvas.create_window((0,0), window=scroll_f, anchor="nw")
            scroll_f.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

            if not opciones:
                tk.Label(scroll_f, text="No hay opciones.", bg="#f4f4f4", fg="gray").pack(pady=20)
                return

            for i, op in enumerate(opciones):
                card = tk.Frame(scroll_f, bg="white", relief=tk.RIDGE, bd=2)
                card.pack(fill=tk.X, pady=3, padx=2)
                
                rb = tk.Radiobutton(card, variable=self.var_sel, value=f"{tipo}_{i}", bg="white")
                rb.pack(side=tk.LEFT, padx=5)
                
                txt = f"Inicio: {self._fmt_fecha(op['fechas'][0])}"
                tk.Label(card, text=txt, bg="white", font=("Segoe UI", 9, "bold"), anchor="w").pack(fill=tk.X, pady=5)

                # Conflictos de Patrones
                conflictos_p = []
                for fd in op["fechas"]:
                    conflictos_p.extend(fd.get("conf_patrones", []))
                
                if conflictos_p:
                    btn_p = tk.Label(card, text="🛠️⚠️", bg="white", fg="#c0392b", font=("Segoe UI", 10, "bold"), cursor="hand2")
                    btn_p.pack(side=tk.RIGHT, padx=10)
                    btn_p.bind("<Button-1>", lambda e, c=conflictos_p: self._ver_conflictos_patrones(e, c))

        crear_lista(f_est, res_est, "est")
        crear_lista(f_flex, res_flex, "flex")

        # --- PANELES INFERIORES DE DETALLE ---
        detail_f = tk.Frame(self.right, bg="#f4f4f4", height=150)
        detail_f.pack(fill=tk.X, padx=15, pady=(5, 10))
        detail_f.pack_propagate(False)

        # 1. Resumen de Partidas
        lf_partidas = tk.LabelFrame(detail_f, text="📦 Resumen de Partidas", bg="#f4f4f4", font=("Segoe UI", 9, "bold"))
        lf_partidas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        t_part = ttk.Treeview(lf_partidas, columns=("trab", "pts", "cant"), show="headings", height=4)
        t_part.heading("trab", text="Trabajo")
        t_part.heading("pts", text="Puntos")
        t_part.heading("cant", text="Cant.")
        t_part.column("trab", width=220); t_part.column("pts", width=120); t_part.column("cant", width=50, anchor="center")
        
        # Calcular conteo de partidas para las OTs del proyecto
        ots_lista = str(self.paquete_seleccionado["ots"]).split(" / ")
        conteo = {}
        for fila in self.bd_ots:
            if len(fila) > IDX_OT and str(fila[IDX_OT]).strip() in ots_lista:
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
        
        # Obtener patrones de metadatos privados de los eventos
        pats_list = []
        for ev in self.paquete_seleccionado["eventos"]:
            p = ev.get('extendedProperties', {}).get('private', {}).get('app_patrones')
            if p:
                try: 
                    plist = json.loads(p)
                    for item in plist:
                        if item not in pats_list: pats_list.append(item)
                except: pass
        
        pats_display = "\n".join([f"• {p}" for p in pats_list]) if pats_list else "No se detectaron patrones en los metadatos."
        txt_pats.config(state=tk.NORMAL); txt_pats.insert("1.0", pats_display); txt_pats.config(state=tk.DISABLED)

        btn_f = tk.Frame(self.right, bg="#ecf0f1", pady=10)
        btn_f.pack(fill=tk.X, side=tk.BOTTOM)
        
        tk.Button(btn_f, text="← Cancelar", command=lambda: self._ver_detalle(self.paquete_seleccionado), bg="#95a5a6", fg="white").pack(side=tk.LEFT, padx=20)
        tk.Button(btn_f, text="🔍 Buscar siguientes 3", command=self._buscar_siguiente_3, bg="#34495e", fg="white").pack(side=tk.LEFT, padx=5)
        
        def aplicar():
            val = self.var_sel.get()
            if val == "none": return
            tipo, idx = val.split("_")
            lista = self._opciones_est if tipo == "est" else self._opciones_flex
            nueva_f = lista[int(idx)]["fechas"][0]["date"]
            self._ejecutar_reprogramacion_manual(nueva_f)

        tk.Button(btn_f, text="Aplicar Fecha →", command=aplicar, bg="#27ae60", fg="white", font=("Segoe UI", 10, "bold")).pack(side=tk.RIGHT, padx=20)

    def _eliminar_con_confirmacion(self):
        if not self.paquete_seleccionado: return
        pkg = self.paquete_seleccionado
        
        preg = messagebox.askyesno("Confirmar Eliminación", 
                                   f"¿Estás seguro de eliminar el proyecto {pkg['ots']}?\n\n"
                                   f"Se borrarán todos los eventos en Google Calendar de todos los técnicos involucrados.\n\n"
                                   "(Se guardará una copia en la Papelera de Reciclaje local)")
        if not preg: return

        # 1. Guardar en Papelera (Recycle Bin)
        self._guardar_en_papelera(pkg)

        # 2. Borrar en Google Calendar
        svc_cal, _ = extractor.get_google_services()
        exito = 0
        for ev in pkg["eventos"]:
            try:
                svc_cal.events().delete(calendarId=ev["calendar_id"], eventId=ev["id"]).execute()
                exito += 1
            except Exception as e:
                print(f"Error borrando {ev['id']}: {e}")

        messagebox.showinfo("Eliminado", f"Se han eliminado {exito} eventos. El proyecto fue movido a la Papelera.")
        self._cargar_datos()

    def _guardar_en_papelera(self, pkg):
        papelera_path = os.path.join(os.path.dirname(__file__), 'papelera_proyectos.json')
        datos = []
        if os.path.exists(papelera_path):
            with open(papelera_path, 'r', encoding='utf-8') as f:
                try: datos = json.load(f)
                except: datos = []
        
        # Añadir timestamp de borrado
        pkg["fecha_borrado"] = datetime.datetime.now().isoformat()
        datos.append(pkg)
        
        with open(papelera_path, 'w', encoding='utf-8') as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)

    def _ver_conflictos_patrones(self, event, conflictos):
        pop = tk.Toplevel(self.root)
        pop.overrideredirect(True)
        pop.configure(bg="#fdedec", highlightbackground="#c0392b", highlightthickness=1)
        tk.Label(pop, text="⚠️ Conflictos de Patrones:", bg="#fdedec", font=("Segoe UI", 9, "bold"), fg="#c0392b").pack(padx=10, pady=5)
        
        agrupados = {}
        for c in conflictos:
            k = c["patron"]
            if k not in agrupados: agrupados[k] = []
            agrupados[k].append(f"{c['tecnico']} en {c['donde']}")
        
        for pat, lugares in agrupados.items():
            tk.Label(pop, text=f"• {pat} ya está en:", bg="#fdedec", font=("Segoe UI", 8, "bold"), anchor="w").pack(fill=tk.X, padx=15)
            for lug in list(set(lugares)):
                tk.Label(pop, text=f"  - {lug}", bg="#fdedec", font=("Segoe UI", 8), anchor="w").pack(fill=tk.X, padx=25)
        
        tk.Label(pop, text="(Haz clic fuera para cerrar)", bg="#fdedec", fg="gray", font=("Segoe UI", 8, "italic")).pack(pady=5, padx=10)
        
        pop.update_idletasks()
        pop.geometry(f"+{event.x_root}+{event.y_root}")
        pop.bind("<FocusOut>", lambda e: pop.destroy())
        pop.focus_set()
