"""Install a Studio release ZIP in-place with a version-labelled FULL source snapshot.

The backup captures existing editable project files (including locally modified ones)
before any release files are installed. Git history and caches are not copied.
"""
from __future__ import annotations
import json
import os
import pathlib
import re
import shutil
import sys
import zipfile
from datetime import datetime

SCRIPT_ROOT = pathlib.Path(__file__).resolve().parents[1]
ROOT = pathlib.Path.cwd().resolve() if (pathlib.Path.cwd()/'server.py').is_file() else SCRIPT_ROOT
if len(sys.argv) != 2:
    raise SystemExit('Usage: sic-studio-update /path/to/sic-circuit-studio-vX.Y.Z.zip')
archive = pathlib.Path(sys.argv[1]).expanduser().resolve()
if not archive.is_file():
    raise SystemExit(f'ZIP not found: {archive}')
old_version = (ROOT/'VERSION').read_text().strip() if (ROOT/'VERSION').exists() else 'unknown'
version_pattern = re.compile(r'^\d+\.\d+\.\d+$')
def safe_version(s):
    return s if version_pattern.fullmatch(s) else 'unknown'
new_version = 'unknown'
allowed_roots = {'frontend', 'backend', 'tests', 'docs', 'scripts'}
allowed_top = {'server.py', 'desktop.py', 'README.md', 'VERSION', '.gitignore'}
items = []
with zipfile.ZipFile(archive) as z:
    names = set()
    for obj in z.infolist():
        if obj.is_dir(): continue
        parts = pathlib.PurePosixPath(obj.filename).parts
        if not parts or len(parts) < 2 or parts[0] != 'sic-circuit-studio':
            raise SystemExit(f'Unexpected ZIP layout: {obj.filename}')
        rel = pathlib.PurePosixPath(*parts[1:])
        if (rel.as_posix() in names or any(p in ('..', '.', '.git','__pycache__') for p in rel.parts)
                or rel.is_absolute() or rel.suffix in ('.cfg', '.env')):
            raise SystemExit(f'Unsafe or duplicate path: {rel}')
        names.add(rel.as_posix())
        if ((len(rel.parts) == 1 and rel.name not in allowed_top)
                or (len(rel.parts) > 1 and rel.parts[0] not in allowed_roots)):
            raise SystemExit(f'Unexpected file: {rel}')
        if len(rel.parts)>5 or obj.file_size>3_000_000:
            raise SystemExit(f'Unexpected size/path depth: {rel}')
        if (obj.external_attr >> 16) & 0o170000 == 0o120000:
            raise SystemExit(f'Symlink in ZIP rejected: {rel}')
        dest = ROOT.joinpath(*rel.parts)
        if dest.is_symlink() or any(part.is_symlink() for part in dest.parents if ROOT == part or ROOT in part.parents):
            raise SystemExit(f'Cannot update through symlink: {rel}')
        items.append((obj, rel))
    if not items: raise SystemExit('Empty update archive')
    if 'VERSION' in names:
        new_version = safe_version(z.read('sic-circuit-studio/VERSION').decode().strip())

    date_stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_dir = (ROOT.parent / (ROOT.name + '-backups') / safe_version(old_version)
                  / f'{date_stamp}_to_{new_version}')
    content_dir = backup_dir / 'project'
    ignore_dirs = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.idea', '.vscode'}
    def skip_source(rel):
        if any(part in ignore_dirs for part in rel.parts): return True
        if any(part.startswith('.') and part.endswith('.env') for part in rel.parts): return True
        if rel.name == '.env' or rel.suffix == '.cfg': return True
        if rel.suffix in ('.pyc', '.pyo', '.sqlite', '.db'): return True
        return False
    copied = []
    total_size = 0
    for dirname, subdirs, filenames in os.walk(ROOT):
        # Prune Git and caches before traversing to keep backups fast.
        subdirs[:] = [d for d in subdirs if d not in ignore_dirs and not pathlib.Path(dirname, d).is_symlink()]
        for filename in sorted(filenames):
            source = pathlib.Path(dirname, filename)
            rel = source.relative_to(ROOT)
            if skip_source(rel) or source.is_symlink() or not source.is_file(): continue
            size = source.stat().st_size
            if size > 8_000_000: continue
            total_size += size
            if total_size > 200_000_000:
                raise SystemExit('Backup source exceeds 200 MB; aborting update before any changes')
            backup_file = content_dir / rel
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, backup_file)
            copied.append(rel.as_posix())
    if not copied:
        raise SystemExit('No existing project files available for backup; update aborted')
    manifest = {
        'previous_version': old_version,
        'incoming_version': new_version,
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'source_project': str(ROOT),
        'archive_name': archive.name,
        'backed_up_files': copied,
        'updated_files': [rel.as_posix() for _, rel in items],
        'excluded': 'Git history, caches, virtual environments, .cfg/.env secrets, very large files',
    }
    (backup_dir/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    for obj, rel in items:
        dest = ROOT.joinpath(*rel.parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with z.open(obj) as f, dest.open('wb') as out:
            shutil.copyfileobj(f, out)
print(f'Updated {len(items)} release files: v{old_version} -> v{new_version}')
print(f'Complete source snapshot ({len(copied)} files): {content_dir}')
print('Your existing files not present in the release were left in place.')
print('Run: python3 -m unittest discover -s tests -v')
