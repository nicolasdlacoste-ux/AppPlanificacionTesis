
import sys

with open("webapp/index.css", "a", encoding="utf-8") as f:
    f.write("\n\n/* BATCH MODE SELECTED STATE */\n.ev-block.batch-selected, .res-card.batch-selected {\n    border: 3px solid var(--accent) !important;\n    box-shadow: 0 0 10px rgba(0, 161, 224, 0.5) !important;\n    opacity: 1 !important;\n    z-index: 100 !important;\n}\n")
print("index.css patched.")

