import os
text=open('webapp/right-panel.js', encoding='utf-8').read()
text = text.replace('fecha: fdata.date,\n                            h_start: fdata.h_start,', 'fecha: fdata.date,\n                            fecha_fin: fdata.fecha_fin || null,\n                            h_start: fdata.h_start,')
open('webapp/right-panel.js', 'w', encoding='utf-8').write(text)
print('Replaced')

