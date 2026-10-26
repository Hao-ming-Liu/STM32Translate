"""Inference adapted from Argos Translate (MIT).

Copyright (c) 2020 Argos Open Technologies, LLC.
Revision: 17ed1a9b055c5ba1b51d76b683bbb0c64e2a4a88
Sources: argostranslate/tokenizer.py and apply_packaged_translation in translate.py.
Full notice: licenses/Argos-Translate-MIT.txt.
Changes: CPU int8, single hypothesis, no manager/SBD/API, preserve underscores,
explicit length limits, whitespace cleanup. Source preprocessing lives separately.
"""
from pathlib import Path
import re
import ctranslate2
import sentencepiece as spm


class SentencePieceTokenizer:
    def __init__(self, model_file: Path):
        self.processor = spm.SentencePieceProcessor(model_file=str(model_file))

    def encode(self, sentence: str) -> list[str]:
        return self.processor.encode(sentence, out_type=str)

    def decode(self, tokens: list[str]) -> str:
        # Upstream underscore-to-space cleanup would corrupt code identifiers.
        return self.processor.decode_pieces(tokens).replace('▁', ' ')


class OfflineTranslator:
    def __init__(self, model_dir: Path):
        if not (model_dir / 'model/model.bin').is_file() or not (model_dir / 'sentencepiece.model').is_file():
            raise FileNotFoundError('缺少英中离线模型，请将完整包中的 models 文件夹放回程序旁边。')
        self.tokenizer = SentencePieceTokenizer(model_dir / 'sentencepiece.model')
        self.translator = ctranslate2.Translator(str(model_dir / 'model'), device='cpu', compute_type='int8', inter_threads=1, intra_threads=4)

    def translate_batch(self, sentences: list[str]) -> list[str]:
        batches = self.translator.translate_batch(
            [self.tokenizer.encode(s) for s in sentences], replace_unknowns=True,
            max_batch_size=512, batch_type='tokens', beam_size=4,
            num_hypotheses=1, length_penalty=0.2,
            max_input_length=0, max_decoding_length=512,
        )
        results = []
        for batch in batches:
            tokens = batch.hypotheses[0]
            if len(tokens) >= 512:
                raise ValueError('单段译文超过模型输出上限，请拆分后重试；未显示截断译文。')
            value = self.tokenizer.decode(tokens).strip()
            results.append(re.sub(r'(?<=[\u3400-\u9fff]) +(?=[\u3400-\u9fff])', '', value))
        return results
