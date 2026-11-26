"""Change version metadata when preparing a new release or after your own edits."""
from __future__ import annotations
import pathlib
import re
import sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
if len(sys.argv)!=2 or sys.argv[1] not in ('major','minor','patch'):
    raise SystemExit('Usage: python3 scripts/bump_version.py major|minor|patch')
old=(ROOT/'VERSION').read_text().strip()
a,b,c=map(int,old.split('.'))
a,b,c= {'major':(a+1,0,0),'minor':(a,b+1,0),'patch':(a,b,c+1)}[sys.argv[1]]
new=f'{a}.{b}.{c}'
for path in [ROOT/'backend/circuit.py',ROOT/'frontend/index.html',ROOT/'frontend/app.js',ROOT/'README.md']:
    data=path.read_text()
    if path.name=='circuit.py':data=data.replace(f'VERSION = "{old}"',f'VERSION = "{new}"')
    else:data=data.replace(f'v{old}',f'v{new}')
    path.write_text(data)
(ROOT/'VERSION').write_text(new+'\n')
print(f'Version updated: {old} -> {new}. Review git diff and commit your changes.')
