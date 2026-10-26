# Two entry points share a single dependency directory; only the worker imports ML.
from pathlib import Path
root = Path(SPECPATH)
a = Analysis(
    [str(root / 'run.py')], pathex=[str(root)], binaries=[], datas=[],
    hiddenimports=['pystray._win32', 'PIL._tkinter_finder'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['pytest', 'psutil', 'torch', 'tensorflow', 'spacy', 'stanza', 'matplotlib', 'IPython'],
    noarchive=False,
)
pyz = PYZ(a.pure)
# The CPU-only product does not need the optional cuDNN dispatcher bundled by
# upstream Windows wheels. ctranslate2's directory glob loads only present DLLs.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() != 'cudnn64_9.dll']
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name='STM32Translate',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, icon=str(root / 'assets/app.ico'),
          version=str(root / 'assets/version.txt'))
worker = EXE(pyz, a.scripts, [], exclude_binaries=True, name='TranslateWorker',
             debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
             console=True, icon=str(root / 'assets/app.ico'))
coll = COLLECT(gui, worker, a.binaries, a.datas, strip=False, upx=False, name='STM32Translate')
