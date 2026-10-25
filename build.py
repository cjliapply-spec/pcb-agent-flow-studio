"""Rebuild the self-contained offline page using only Python standard library."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
p=ROOT/'app'
s=(p/'index.html').read_text(encoding='utf-8')
s=s.replace('<link rel="stylesheet" href="style.css">','<style>\n'+(p/'style.css').read_text(encoding='utf-8')+'\n</style>')
for name in ['engine','schematic','ui']:
    attrs=' id="engine-source"' if name=='engine' else ''
    s=s.replace(f'<script{attrs} src="{name}.js"></script>',f'<script{attrs}>\n'+(p/(name+'.js')).read_text(encoding='utf-8').replace('</script','<\\/script')+'\n</script>')
(ROOT/'OPEN_DEMO.html').write_text(s,encoding='utf-8')
print('Built:',ROOT/'OPEN_DEMO.html')
