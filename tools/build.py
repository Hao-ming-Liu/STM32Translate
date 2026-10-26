"""Build an entirely local, self-contained portable folder; never installs globally."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.environ['PYTHONUTF8'] = '1'
    parser = argparse.ArgumentParser()
    parser.add_argument('--package-only', action='store_true', help='refresh documents and ZIP without rebuilding binaries')
    args = parser.parse_args()
    if not args.package_only:
        subprocess.run([sys.executable, str(ROOT / 'tools/fetch_model.py')], check=True)
        subprocess.run([sys.executable, str(ROOT / 'tools/collect_licenses.py')], check=True)
        sys.path.insert(0, str(ROOT))
        from stm32translate.resources import make_icon
        (ROOT / 'assets').mkdir(exist_ok=True)
        make_icon().save(ROOT / 'assets/app.ico', sizes=[(16,16), (32,32), (48,48), (64,64)])
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', str(ROOT / 'STM32Translate.spec')], cwd=ROOT, check=True)
    folder = ROOT / 'dist/STM32Translate'
    shutil.copytree(ROOT / 'models/en_zh', folder / 'models/en_zh', dirs_exist_ok=True)
    shutil.copytree(ROOT / 'licenses', folder / 'licenses', dirs_exist_ok=True)
    for name in ['README.md', 'THIRD_PARTY_NOTICES.md', 'LICENSE', 'requirements.txt', 'requirements-lock.txt']:
        shutil.copyfile(ROOT / name, folder / name)
    if (ROOT / 'docs/verification.md').exists():
        (folder / 'docs').mkdir(exist_ok=True)
        shutil.copyfile(ROOT / 'docs/verification.md', folder / 'docs/verification.md')
    shutil.copyfile(ROOT / 'README.md', folder / '使用说明.txt')
    shutil.copyfile(ROOT / 'models/en_zh/SOURCE.json', folder / 'MODEL_INFO.json')
    # Clipboard, cache, saved terms and test data never ship in the portable archive.
    archive = ROOT / 'dist/STM32Translate-1.0.0-win64-full.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(folder.rglob('*')):
            rel = path.relative_to(folder)
            if path.is_file() and rel.parts[0] not in ('data', '__pycache__'):
                z.write(path, str(Path(folder.name) / rel))
    print(json.dumps({'folder':str(folder), 'zip':str(archive), 'zip_mib':archive.stat().st_size / 1048576}, indent=2))


if __name__ == '__main__':
    main()
