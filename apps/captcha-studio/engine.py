"""G1 studio adapter: reuse S53 mechanics without editing the frozen corpus.

Studio recipe `g1-studio-v1` is distinct from frozen S53: selectable arms and
custom labels; combined effects rotate last. The original generator, S53 tool,
and shipping OCR files stay byte-for-byte unchanged. Ground truth is never
passed to the reader, not even as a family hint.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time
import zipfile

APP = Path(__file__).resolve().parent
ROOT = APP.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]

import numpy as np
import PIL
from PIL import Image, features
import generator as G
import gen_hard_corpus as S53

RECIPE = 'g1-studio-v1'
MAX_COUNT = 32
MAX_TEXT = 48
# Preserve the canonical face order, but supply our own verified font assets.
FONT_NAMES = tuple(Path(p).name for p in G._FONT_CANDIDATES)
FONT_DIR = APP / 'fonts'
FAMILIES = {
    'control': ('none',),
    'corrosion': tuple(S53.CORROSION_PITS),
    'rotation': tuple(S53.ROTATION_DEG),
    'spiderweb': ('light', 'heavy'),
    'cross-shadow': ('light', 'heavy'),
    'strippy': ('light', 'heavy'),
    'darts': ('light', 'heavy'),
    'combined': ('mixed',),
    'sampler': ('mixed',),
}
CORE_FILES = ('generator.py', 'baseline.py', 'reader.py', 'preclassify.py',
              'tools/gen_hard_corpus.py', 'tools/lex_projection.py', 'tools/reader_lex.py',
              'models/glyphcnn-v2.npz')


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_fonts() -> dict:
    expected = json.loads((FONT_DIR / 'SHA256SUMS.json').read_text())
    if set(expected) != set(FONT_NAMES):
        raise RuntimeError('Bundled font inventory differs from the original eight faces')
    for name in FONT_NAMES:
        p = FONT_DIR / name
        if not p.is_file() or sha256(p.read_bytes()) != expected[name]:
            raise RuntimeError('Missing or changed bundled font: ' + name)
    G._FONT_CANDIDATES = [str(FONT_DIR / name) for name in FONT_NAMES]
    return expected


FONT_HASHES = verify_fonts()


def build_info() -> dict:
    p = ROOT / 'studio-build.json'
    info = json.loads(p.read_text()) if p.is_file() else {'revision': 'working-tree', 'release': False}
    return {**info, 'recipe': RECIPE, 'python': sys.version.split()[0],
            'pillow': PIL.__version__, 'numpy': np.__version__,
            'freetype': features.version_module('freetype2'),
            'zlib': features.version_codec('zlib'),
            'fonts': len(FONT_NAMES), 'font_policy': 'bundled eight faces in original order',
            'font_sha256': FONT_HASHES,
            'core_sha256': {name: sha256((ROOT / name).read_bytes()) for name in CORE_FILES},
            'ocr_route': 'baseline.read_text(image, None) + lex_projection.fix_line',
            'accuracy_target_met': False}


def integer(value, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f'{name} must be an integer from {low} to {high}')
    return value


def validate_request(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError('Expected a JSON object')
    if set(payload) - {'family', 'severity', 'seed', 'count', 'text', 'start_index'}:
        raise ValueError('Unknown generator setting')
    family = payload.get('family', 'corrosion')
    if not isinstance(family, str) or family not in FAMILIES:
        raise ValueError('Unknown degradation family')
    severity = payload.get('severity', FAMILIES[family][0])
    if severity not in FAMILIES[family]:
        raise ValueError('Severity does not belong to the selected family')
    text = payload.get('text', '')
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise ValueError(f'Custom text must be at most {MAX_TEXT} characters')
    if text and (not re.fullmatch(r'[A-Za-z0-9 ]+', text) or text != text.strip()):
        raise ValueError('Use ASCII letters, digits and spaces, without leading/trailing spaces')
    return {'family': family, 'severity': severity,
            'seed': integer(payload.get('seed', 53), 'seed', 0, 2147483647),
            'count': integer(payload.get('count', 6), 'count', 1, MAX_COUNT),
            'start_index': integer(payload.get('start_index', 0), 'start_index', 0, 1000000),
            'text': text}


def render(config: dict, index: int) -> tuple[bytes, dict]:
    """One bounded studio sample. All rendering/effects come from S53 helpers."""
    rng = S53.corpus_rng(RECIPE, config['seed'], index)
    family, severity = config['family'], config['severity']
    if family == 'sampler':
        family, severity = S53.ARMS[index % len(S53.ARMS)]
        if family == 'overlay':
            family, severity = severity.split(':')
    label = config['text'] or G.make_label(rng)
    image, font, x, y = S53.base_render(rng, label)
    boxes = S53.advance_char_boxes(image, label, font, x, y)
    angle = 0.0
    effects = []
    if family == 'combined':
        selected = rng.sample(['corrosion', 'rotation', *S53.OVERLAY_FAMS], rng.randint(2, 3))
        # Studio-specific recipe: rotate after effects defined in base coordinates.
        selected.sort(key=lambda name: name == 'rotation')
        for effect in selected:
            levels = (tuple(S53.CORROSION_PITS) if effect == 'corrosion'
                      else tuple(S53.ROTATION_DEG) if effect == 'rotation'
                      else ('light', 'heavy'))
            effects.append((effect, rng.choice(levels)))
    elif family != 'control':
        effects = [(family, severity)]
    for effect, level in effects:
        if effect == 'corrosion':
            image = S53.apply_corrosion(image, rng, level)
        elif effect == 'rotation':
            before = image.size
            image, angle = S53.apply_rotation(image, rng, level)
            boxes = S53.transform_boxes(boxes, angle, before, image.size)
        else:
            image = S53.apply_overlay(image, rng, effect, level)
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    png = buf.getvalue()
    recipe = {**config, 'count': 1, 'start_index': index}
    identifier = sha256(png + json.dumps(recipe, sort_keys=True).encode())[:24]
    row = {'id': identifier, 'image': f'images/{identifier}.png',
           'label': label, 'family': family, 'severity': severity,
           'seed': config['seed'], 'index': index, 'recipe': RECIPE,
           'tags': ['studio', 'synthetic', f'seed={config["seed"]}'],
           'degradation_type': '+'.join(e[0] for e in effects) or 'control',
           'effects': [{'type': e, 'severity': s} for e, s in effects],
           'rotation_deg': round(angle, 6), 'char_boxes': boxes,
           'box_semantics': 'oracle ink boxes, [x0,x1,y0,y1], spaces omitted',
           'width': image.width, 'height': image.height, 'sha256': sha256(png)}
    return png, row


def generate(payload: dict) -> tuple[dict, list[tuple[bytes, dict]]]:
    config = validate_request(payload)
    images = [render(config, i) for i in range(config['start_index'],
               config['start_index'] + config['count'])]
    return config, images


def export_zip(items: list[tuple[bytes, dict]]) -> bytes:
    """A label-bearing export, never passed to OCR. Fixed ZIP times for replay."""
    if not items or len(items) > MAX_COUNT:
        raise ValueError(f'Export requires 1–{MAX_COUNT} images')
    if len({row['id'] for _, row in items}) != len(items):
        raise ValueError('Duplicate image identifiers in export')
    info = build_info()
    provenance = {k: info[k] for k in ['recipe', 'revision', 'pillow', 'numpy', 'freetype', 'zlib',
                                      'font_sha256', 'core_sha256', 'ocr_route']}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        def add(name, body):
            item = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, body)
        for png, row in items:
            add(row['image'], png)
        add('manifest.jsonl', ''.join(json.dumps(row, sort_keys=True) + '\n'
                                     for _, row in items))
        add('provenance.json', json.dumps(provenance, indent=2, sort_keys=True) + '\n')
        add('README.txt', 'Synthetic studio export. Labels are exact and case-sensitive.\n'
            'The studio recipe is separate from frozen S53 and canonical evaluation suites.\n'
            'Oracle boxes are not reader output. Reproducibility is scoped to these font, '
            'Pillow/FreeType and NumPy versions. This is not a 98/95 accuracy certificate.\n')
    return buf.getvalue()


def recognize(png: bytes) -> dict:
    """ONLY image bytes enter this function: no label, family hint or oracle boxes."""
    # Pin the ordinary shipping route, not an inherited experimental piece policy.
    os.environ['SUPEROCR_PIECE_CNN'] = '0'
    import baseline as B
    from lex_projection import fix_line
    B.PIECE_CNN = False
    started = time.perf_counter()
    image = Image.open(io.BytesIO(png)).convert('RGB')
    # The existing trained tie-break model resolves its relative path from cwd.
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError('Start the studio server from its project/bundle root')
    raw, confidence = B.read_text(image, None)
    result = fix_line(raw)
    return {'text': result, 'raw_text': raw, 'route': 'floor+lex',
            'milliseconds': round((time.perf_counter() - started) * 1000, 1),
            'glyph_confidences': [round(float(c), 4) for c in confidence],
            'note': 'Confidence is a matcher score, not a calibrated probability.'}


def compare_result(result: dict, label: str) -> dict:
    # Comparison happens AFTER recognition. No stripping/case folding/fuzzy credit.
    return {**result, 'expected': label, 'exact_match': result['text'] == label,
            'comparison': 'exact, case-sensitive; no whitespace normalization'}


def selftest(with_ocr: bool = False) -> dict:
    verify_fonts()
    config = {'family': 'sampler', 'severity': 'mixed', 'count': len(S53.ARMS), 'seed': 53}
    _, first = generate(config)
    _, second = generate(config)
    if first != second:
        raise RuntimeError('Determinism selftest failed')
    if any(row['width'] <= 0 or not row['label'] for _, row in first):
        raise RuntimeError('Invalid generated sample')
    export = export_zip(first)
    with zipfile.ZipFile(io.BytesIO(export)) as archive:
        if len(archive.namelist()) != len(first) + 3:
            raise RuntimeError('Export selftest failed')
    report = {'selftest': 'PASS', 'font_faces': len(FONT_NAMES),
              'arms': len(first), 'deterministic': True, 'export': 'PASS',
              'accuracy_claim': False}
    if with_ocr:
        _, sample = generate({'family': 'control', 'severity': 'none',
                              'count': 1, 'seed': 7, 'text': 'amber'})
        report['ocr_smoke'] = compare_result(recognize(sample[0][0]), sample[0][1]['label'])
    return report
