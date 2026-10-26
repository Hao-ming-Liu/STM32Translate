"""Developer-only reproducible model acquisition. The application never imports this."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SHA256 = '433e7c4f034d87fbe2353161e05f18646d7999452f801a4e1f0378522b9850ab'
URLS = [
    'https://data.argosopentech.com/argospm/v1/translate-en_zh-1_9.argosmodel',
    'https://argos-net.com/v1/translate-en_zh-1_9.argosmodel',
    'https://huggingface.co/TiberiuCristianLeon/Argostranslate/resolve/9dc7a2c8f29ac18e020c93f8208476d1e3fe9a9f/translate-en_zh-1_9.argosmodel',
]


def main():
    archive = ROOT / 'downloads/translate-en_zh-1_9.argosmodel'
    archive.parent.mkdir(exist_ok=True)
    source_url = URLS[0]
    if not archive.exists() or hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest() != SHA256:
        for url in URLS:
            part = archive.with_suffix('.part')
            try:
                with urllib.request.urlopen(url, timeout=60) as src, part.open('wb') as out:
                    shutil.copyfileobj(src, out)
                with part.open('rb') as file:
                    if hashlib.file_digest(file, 'sha256').hexdigest() != SHA256:
                        raise ValueError('模型校验失败，拒绝使用')
                part.replace(archive)
                source_url = url
                break
            except Exception as exc:
                part.unlink(missing_ok=True)
                print(f'{url}: {exc}', flush=True)
        else:
            raise RuntimeError('无法下载经过校验的英中模型')
    root = ROOT / 'models/en_zh'
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            path = PurePosixPath(item.filename)
            if item.is_dir() or 'stanza' in path.parts:
                continue
            if path.is_absolute() or '..' in path.parts or path.parts[0] != 'translate-en_zh-1_9':
                raise ValueError('模型包含非预期路径')
            dest = root.joinpath(*path.parts[1:])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(item))
    info = {
        'model': 'Argos Translate English–Chinese 1.9', 'language_pair': 'en -> zh (simplified)',
        'index': 'https://github.com/argosopentech/argospm-index/blob/main/index.json',
        'download': source_url, 'archive_sha256': SHA256, 'archive_bytes': archive.stat().st_size,
        'authors': ['Jörg Tiedemann', 'Santhosh Thottingal'],
        'paper': 'OPUS-MT — Building open translation services for the World (EAMT 2020)',
        'license': 'CC-BY-4.0 (original OPUS model, per bundled README.md)',
        'changes': 'Stanza tokenizer files omitted; CTranslate2 inference model and SentencePiece unchanged.',
    }
    info['files_sha256'] = {}
    for file in root.rglob('*'):
        if file.is_file() and file.name != 'SOURCE.json':
            with file.open('rb') as f:
                info['files_sha256'][file.relative_to(root).as_posix()] = hashlib.file_digest(f, 'sha256').hexdigest()
    (root / 'SOURCE.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
