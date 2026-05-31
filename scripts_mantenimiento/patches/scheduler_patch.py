
import sys

with open("webapp/scheduler.js", "r", encoding="utf-8") as f:
    js = f.read()

target1 = """block.dataset.jobKey = jk;"""
replacement1 = """block.dataset.jobKey = jk;
        if (window.App && App.isBatchMode && App.isBatchMode() && App.isEventSelected(ev.google_event_id)) {
            block.classList.add("batch-selected");
        }"""

js = js.replace(target1, replacement1)

target2 = """card.className = 'res-card' + (ev._syncing ? ' syncing' : '');"""
replacement2 = """card.className = 'res-card' + (ev._syncing ? ' syncing' : '');
        if (window.App && App.isBatchMode && App.isBatchMode() && App.isEventSelected(ev.google_event_id)) {
            card.classList.add("batch-selected");
        }"""
js = js.replace(target2, replacement2)

with open("webapp/scheduler.js", "w", encoding="utf-8") as f:
    f.write(js)
print("scheduler.js patched.")

