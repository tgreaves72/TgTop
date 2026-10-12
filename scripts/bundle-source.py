"""Package application source using an allowlist, never local runtime/account data."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
files = [root / name for name in (
    '.dockerignore', '.env.example', '.gitignore', 'Dockerfile',
    'package.json', 'package-lock.json', 'requirements.txt',
    'requirements.lock.txt', 'run.py', 'README.md', 'SECURITY.md', 'railway.json',
)]
for directory in ('app', 'web', 'desktop', 'deploy', 'integrations', 'scripts', 'tests'):
    files.extend(path for path in (root / directory).rglob('*')
                 if path.is_file() and '__pycache__' not in path.parts
                 and path.suffix not in ('.pyc', '.log') and path.name != '.env')
files.extend(path for path in (root / 'docs').glob('*.md'))
destination = root / 'release' / 'TgTop-source.zip'
destination.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(set(files)):
        if path.exists():
            archive.write(path, path.relative_to(root).as_posix())
print(f'Saved {destination}')
