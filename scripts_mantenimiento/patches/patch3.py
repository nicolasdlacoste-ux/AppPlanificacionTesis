import os
text=open('webapp/right-panel.js', encoding='utf-8').read()
old = "                nueva_fecha: newDate,\n                h_start: hStartF,"
new = "                nueva_fecha: newDate,\n                nueva_fecha_fin: newDateEnd || null,\n                h_start: hStartF,"
text = text.replace(old, new)
open('webapp/right-panel.js', 'w', encoding='utf-8').write(text)

