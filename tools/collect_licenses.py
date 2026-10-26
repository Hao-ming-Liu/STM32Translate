from pathlib import Path
import importlib.metadata as md
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ['ctranslate2', 'sentencepiece', 'numpy', 'PyYAML', 'Pillow', 'pystray', 'six', 'pyinstaller']


def main():
    target = ROOT / 'licenses/third_party'
    target.mkdir(parents=True, exist_ok=True)
    for package in PACKAGES:
        dist = md.distribution(package)
        out = target / f'{dist.metadata["Name"]}-{dist.version}'
        found = []
        for entry in dist.files or []:
            name = Path(str(entry)).name.lower()
            if name.startswith(('license', 'copying', 'copyright', 'notice')) and dist.locate_file(entry).is_file():
                out.mkdir(exist_ok=True)
                dest = out / str(entry).replace('/', '__').replace('\\', '__')
                shutil.copyfile(dist.locate_file(entry), dest)
                found.append(dest.name)
        if not found:
            fallback = {'ctranslate2': 'CTranslate2-LICENSE.txt', 'sentencepiece': 'SentencePiece-LICENSE.txt'}.get(package)
            if not fallback or not (ROOT / 'licenses' / fallback).exists():
                raise RuntimeError(f'缺少 {package} 的许可证文件')
            out.mkdir(exist_ok=True)
            shutil.copyfile(ROOT / 'licenses' / fallback, out / fallback)
    base = Path(sys.base_prefix)
    for candidate in (base / 'LICENSE.txt', base / 'LICENSE'):
        if candidate.exists():
            shutil.copyfile(candidate, target / 'Python-LICENSE.txt')
            break
    else:
        raise RuntimeError('缺少 Python 许可证文件')
    print('Collected runtime and bundler licenses into', target)


if __name__ == '__main__':
    main()
