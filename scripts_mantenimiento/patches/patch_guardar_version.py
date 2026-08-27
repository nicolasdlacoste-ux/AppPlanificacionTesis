import os, re

text = open('data_manager.py', encoding='utf-8').read()

old_str = "current_v = row[0] if row else 1"
new_str = "current_v = row[0] if (row and row[0] is not None) else 1"

if old_str in text:
    text = text.replace(old_str, new_str)
    open('data_manager.py', 'w', encoding='utf-8').write(text)
    print("Patched current_v!")
else:
    print("Could not find the string.")
