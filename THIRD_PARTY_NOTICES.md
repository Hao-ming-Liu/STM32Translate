# Third-party sources and attribution

## Argos Translate inference code — MIT

Copyright (c) 2020 Argos Open Technologies, LLC.

Source: https://github.com/argosopentech/argos-translate
Revision: `17ed1a9b055c5ba1b51d76b683bbb0c64e2a4a88`.

`vendor/argos_core.py` adapts `argostranslate/tokenizer.py` and the inference/tokenization path of `apply_packaged_translation` in `argostranslate/translate.py`. Changes remove model management, online APIs, pivot languages, sentence-detector dependencies and alternate hypotheses; use CPU int8; add explicit length limits; preserve underscores in identifiers. Full MIT notice: `licenses/Argos-Translate-MIT.txt`.

## English → Chinese model — original OPUS model CC BY 4.0

Packaged model: Argos Translate `translate-en_zh-1_9.argosmodel`.

Authors: **Jörg Tiedemann and Santhosh Thottingal**.
Publication: **OPUS-MT — Building open translation services for the World**, Proceedings of EAMT, Lisbon, 2020.

Index: https://github.com/argosopentech/argospm-index/blob/main/index.json
Download: https://data.argosopentech.com/argospm/v1/translate-en_zh-1_9.argosmodel
Archive SHA-256: `433e7c4f034d87fbe2353161e05f18646d7999452f801a4e1f0378522b9850ab`.

The model archive's README explicitly states that the original OPUS model is licensed **CC BY 4.0**: https://creativecommons.org/licenses/by/4.0/ . That README is distributed unchanged in `models/en_zh/README.md`. We omit the unused Stanza sentence-tokenizer files; inference weights and SentencePiece files are unchanged. This application is not endorsed by the original authors. See `MODEL_INFO.json` for file checksums.

## Runtime dependencies

- CTranslate2: https://github.com/OpenNMT/CTranslate2
- SentencePiece: https://github.com/google/sentencepiece
- NumPy: https://numpy.org/
- PyYAML: https://pyyaml.org/
- Pillow: https://python-pillow.org/
- pystray: https://github.com/moses-palmer/pystray
- six: https://github.com/benjaminp/six
- Python: https://www.python.org/ — PSF and included third-party notices.
- Tcl/Tk 8.6: https://www.tcl.tk/ — notices in `licenses/Tcl-license.terms` and `licenses/Tk-license.terms`.
- PyInstaller: https://pyinstaller.org/ — bootloader distribution exception; notice included.

Exact runtime versions are in `requirements.txt`. Installed-wheel licenses and additional bundled-library notices are copied into `licenses/third_party` during the build. The Microsoft YaHei system font is used from Windows and is not redistributed.
