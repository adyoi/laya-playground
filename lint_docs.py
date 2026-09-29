import pathlib
import re
import sys

# Kata camelCase yang sah di prosa/komentar. Sisanya = mencurigakan.
ALLOW = {
    # Merek / nama library
    'GitHub', 'JetBrains', 'GitLab',
    # Atribut SVG (camelCase diwajibkan spesifikasi)
    'viewBox', 'currentColor', 'strokeWidth', 'strokeLinecap', 'strokeLinejoin',
    'fillRule', 'clipRule', 'preserveAspectRatio',
    # Identifier JS yang sah
    'textContent', 'className', 'getElementById', 'innerHTML', 'lastJson', 'rawOn',
    'curlView', 'watchLoading', 'buildBody', 'setMode', 'useSchema', 'distRows',
    'parseState', 'parseJson', 'parseQuestions', 'renderAnswer', 'renderStructured',
    'renderGuardrail', 'showJson', 'showCurl', 'paintCurl', 'hideJsonCard',
    'hideCurlCard', 'curlFor', 'copyText', 'null', 'true', 'false', 'redactKinds',
    'parseInt', 'parseFloat', 'startsWith', 'createElement', 'appendChild',
    'insertBefore', 'firstChild', 'setInterval', 'clearInterval', 'reqBody',
    'setAttribute', 'classList', 'setTimeout', 'writeText', 'forEach', 'ctrlKey',
    'preventDefault', 'closeEnough', 'syncTabEdges', 'centerTab', 'setOpen',
    'querySelector', 'querySelectorAll', 'closest', 'addEventListener',
    'IntersectionObserver', 'classList', 'toLowerCase', 'join', 'map', 'filter',
    'getBoundingClientRect', 'offsetWidth', 'clientWidth', 'scrollWidth',
    'scrollIntoView', 'scrollTo', 'slice', 'toggle', 'contains', 'push', 'at',
}

# Token yang sengaja ada di kedua file walau dipakai di salah satu saja.
#onedemo = token bersama tema, bukan token yang terlupa.
SHARED_ONLY = {'--red-soft', '--warn', '--warn-soft', '--ring', '--line-2'}

FILES = ['docs/index.html', 'static/index.html']
bad = []
roots = {}

TITLE = 'Laya Playground &middot; typed decisions engine'

for path in FILES:
    text = pathlib.Path(path).read_text(encoding='utf-8')
    prose = text.split('<script>')[0]

    # 1. Karakter CJK / mojibake yang tidak sengaja tertinggal di teks.
    for lineno, line in enumerate(text.splitlines(), 1):
        for ch in line:
            cp = ord(ch)
            if (0x3040 <= cp <= 0x30FF or 0x4E00 <= cp <= 0x9FFF
                    or 0xAC00 <= cp <= 0xD7AF or 0xFF00 <= cp <= 0xFFEF):
                bad.append((path, lineno, 'CJK %r' % ch, line.strip()[:80]))
                break

    # 2. Kata camelCase di prosa yang bukan nama sendiri.
    for m in re.finditer(r'\b([A-Za-z]{3,}[A-Z][a-z]{2,})\b', prose):
        w = m.group(1)
        if w in ALLOW or w.startswith('--') or w.startswith('http'):
            continue
        bad.append((path, prose[:m.start()].count('\n') + 1, 'prose camel %r' % w, ''))

    # 3. Variabel CSS: semua var() harus terdefinisi.
    style = text.split('<style>')[1].split('</style>')[0]
    defined = set(re.findall(r'(--[\w-]+)\s*:', style))
    used = set(re.findall(r'var\((--[\w-]+)\)', text))
    for v in sorted(used - defined):
        bad.append((path, 0, 'undefined var %s' % v, ''))
    # Token tak terpakai hanya relevan kalau BUKAN token bersama.
    for v in sorted(defined - used - SHARED_ONLY):
        bad.append((path, 0, 'unused var %s' % v, ''))

    # 4. Simpan blok :root untuk dibandingkan antar file.
    m = re.search(r':root\{(.*?)\n\}', style, re.S)
    if not m:
        bad.append((path, 0, 'blok :root tidak ditemukan', ''))
    else:
        roots[path] = re.sub(r'\s+', ' ', m.group(1)).strip()

    # 5. Keseimbangan tag.
    for tag in ['section', 'div', 'pre', 'table', 'nav', 'header', 'footer',
                'style', 'script', 'button', 'span']:
        o = len(re.findall(r'<%s[\s>]' % tag, text))
        c = len(re.findall(r'</%s>' % tag, text))
        if o != c:
            bad.append((path, 0, 'tag %s %d/%d' % (tag, o, c), ''))

    # 6. Judul harus konsisten.
    t = re.search(r'<title>(.*?)</title>', text, re.S)
    if not t:
        bad.append((path, 0, 'tidak ada <title>', ''))
    elif t.group(1).strip() != TITLE:
        bad.append((path, 0, 'title %r != %r' % (t.group(1).strip(), TITLE), ''))

    print('%-22s %6d bytes' % (path, len(text.encode('utf-8'))))

# 7. Syarat "satu tema": blok :root di kedua file harus identik persis.
if len(roots) == 2:
    a, b = (roots[f] for f in FILES)
    if a != b:
        ta, tb = set(re.findall(r'(--[\w-]+)\s*:', a)), set(re.findall(r'(--[\w-]+)\s*:', b))
        bad.append(('THEME', 0,
                    'token :root tidak sama: hanya di docs=%s hanya di static=%s'
                    % (sorted(ta - tb), sorted(tb - ta)), ''))
        for va in sorted(ta & tb):
            da = re.search(r'%s:\s*([^;]+)' % re.escape(va), a)
            db = re.search(r'%s:\s*([^;]+)' % re.escape(va), b)
            if da and db and da.group(1).strip() != db.group(1).strip():
                bad.append(('THEME', 0, '%s beda: docs=%s static=%s'
                            % (va, da.group(1).strip(), db.group(1).strip()), ''))
    else:
        print('theme tokens        identical across both files (%d tokens)'
              % len(re.findall(r'--[\w-]+\s*:', a)))

print()
if bad:
    for item in bad:
        print('PROBLEM %s:%s %s | %s' % item)
    sys.exit(1)
print('clean')
