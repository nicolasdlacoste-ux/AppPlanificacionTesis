import os, re

text = open('api_server.py', encoding='utf-8').read()

old_block = '''        else:
            nuevo_s = TimeNormalizationService.normalize_to_utc_z(nueva_f)
            nuevo_e = TimeNormalizationService.normalize_to_utc_z(nueva_f + datetime.timedelta(days=1))'''

new_block = '''        else:
            if hasattr(params, "nueva_fecha_fin") and params.nueva_fecha_fin:
                nueva_f_fin = datetime.date.fromisoformat(params.nueva_fecha_fin)
                nuevo_s = nueva_f.isoformat()
                nuevo_e = (nueva_f_fin + datetime.timedelta(days=1)).isoformat()
            else:
                d_start = datetime.date.fromisoformat(start_orig[:10])
                d_end = datetime.date.fromisoformat(end_orig[:10])
                delta_days = (d_end - d_start).days
                if delta_days == 0: delta_days = 1
                nuevo_s = nueva_f.isoformat()
                nuevo_e = (nueva_f + datetime.timedelta(days=delta_days)).isoformat()'''

if old_block in text:
    text = text.replace(old_block, new_block)
    open('api_server.py', 'w', encoding='utf-8').write(text)
    print("Patched mover_evento dates!")
else:
    print("Could not find the block.")
