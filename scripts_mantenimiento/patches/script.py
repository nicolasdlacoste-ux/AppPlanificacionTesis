with open('webapp/app.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    
start = -1
end = -1
for i, line in enumerate(lines):
    if 'async function loadAll()' in line:
        start = i
    if start != -1 and line.strip() == '}' and i > start + 30:
        end = i
        break
        
for i in range(start, end+1):
    print(f"{i+1}: {lines[i]}", end='')
