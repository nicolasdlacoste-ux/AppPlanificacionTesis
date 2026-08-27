import os, re

text = open('api_server.py', encoding='utf-8').read()

old_line = r"h_end_val = params\.h_start \+ dur if params\.h_start is not None else None"
new_line = "h_end_val = params.h_start + (params.h_dur if params.h_dur is not None else 1.0) if params.h_start is not None else None"

if re.search(old_line, text):
    text = re.sub(old_line, new_line, text)
    open('api_server.py', 'w', encoding='utf-8').write(text)
    print("Patched api_server.py line 1960 successfully!")
else:
    print("Could not find the target line in api_server.py")
