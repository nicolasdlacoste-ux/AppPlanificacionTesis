
import sys

with open("webapp/index.html", "r", encoding="utf-8") as f:
    html = f.read()

# 1. Insert Button in header-left
header_left_target = """<span class="header-title">Akrimet <em>Planner</em></span>
    </div>"""
header_left_replacement = """<span class="header-title">Akrimet <em>Planner</em></span>
        <button id="btn-batch-mode" class="nav-btn" style="margin-left: 15px; border-radius: 4px;" title="Activar/Desactivar Modo Batch">
            <i class="fa-solid fa-list-check"></i>
        </button>
    </div>"""

html = html.replace(header_left_target, header_left_replacement)

# 2. Insert ctx-batch view
ctx_batch_html = """
        <!-- Context: BATCH MODE -->
        <div id="ctx-batch" class="ctx-view">
            <div class="ctx-header">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span class="ctx-title"><i class="fa-solid fa-list-check"></i> Modo Batch</span>
                </div>
                <span class="ctx-subtitle" id="batch-selected-count">0 eventos seleccionados</span>
            </div>
            <div class="ctx-body">
                <div class="param-grid">
                    <label>Técnico (Opcional)</label>
                    <select id="batch-tec" class="param-input">
                        <option value="">-- Mantener Técnico Actual --</option>
                    </select>
                    <label>Fecha de Inicio Base</label>
                    <input type="date" id="batch-fecha" class="param-input">
                    <label>OTs</label>
                    <input type="text" id="batch-ots" class="param-input" placeholder="Ej: 1234, 5678">
                    <label>Patrones</label>
                    <input type="text" id="batch-patrones" class="param-input" placeholder="Ej: PAT-1, PAT-2">
                    <label>Vehículo</label>
                    <select id="batch-vehiculo" class="param-input">
                        <option value="">-- Sin Vehículo --</option>
                    </select>
                </div>
            </div>
            <div class="ctx-footer" style="flex-direction: column; gap: 8px;">
                <button id="btn-batch-apply" class="btn-primary w-full">Aplicar Cambios</button>
                <button id="btn-batch-exit" class="btn-secondary w-full">Salir del Modo Batch</button>
            </div>
        </div>
"""

# Insert before ctx-empty
html = html.replace("""<div id="ctx-empty" class="ctx-view active">""", ctx_batch_html + """\n        <div id="ctx-empty" class="ctx-view active">""")

with open("webapp/index.html", "w", encoding="utf-8") as f:
    f.write(html)
print("index.html patched.")

