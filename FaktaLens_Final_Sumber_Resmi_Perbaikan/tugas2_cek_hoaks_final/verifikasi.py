import re
import unicodedata

import requests

WIKIPEDIA_API = 'https://id.wikipedia.org/w/api.php'
UA = 'FaktaLens/2.0 (aplikasi pembelajaran; fact checking demo)'
STOP = set('yang dan atau dari untuk dengan pada dalam bahwa telah akan karena agar dapat adalah sebagai menjadi kepada kami anda mereka sebuah tersebut seperti ini itu di ke oleh para sebuah jika ketika serta soal terkait mengatakan berita kabar disebut diduga viral heboh terbaru resmi informasi menurut sebuah terjadi sudah apa siapa bagaimana mengapa bisa ada'.split())
NOISE = re.compile(r'(?:diteruskan berkali-kali|forwarded many times|ketik pesan|mohon dibagikan|bagikan ke keluarga|share ke grup|baca selengkapnya|pesan diteruskan)', re.I)
NEG = re.compile(r'\b(?:tidak|bukan|tak|nggak|belum|never|not|no)\b', re.I)
MONTH = '(?:januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)'
DATE = re.compile(r'\b(\d{1,2})\s+(' + MONTH + r')\s+(\d{4})\b', re.I)
ALIASES = {'mikrocip':'microchip', 'microchips':'microchip', 'cip':'microchip', 'chip':'microchip',
           'covid19':'covid', 'covid-19':'covid', 'korona':'corona', 'nggak':'tidak',
           'hoax':'hoaks', 'bohong':'hoaks'}


def normalize(value):
    value = unicodedata.normalize('NFKC', str(value or '')).lower()
    value = value.replace('covid-19', 'covid19')
    return re.sub(r'\s+', ' ', value).strip()


def tokens(value):
    result = []
    for raw in re.findall(r'(?u)\b[\w]+\b', normalize(value)):
        word = ALIASES.get(raw, raw)
        if (len(word) > 2 or word.isdigit()) and word not in STOP:
            result.append(word)
    return result


def clean_text(value):
    lines = []
    for line in str(value or '').splitlines():
        line = NOISE.sub(' ', line)
        line = re.sub(r'\s+', ' ', line).strip(' :-•|\t')
        if len(line) >= 2:
            lines.append(line)
    return ' '.join(lines).strip(' .,;:')


def keyword_variants(text, limit=5):
    text = clean_text(text)
    if len(text) < 5:
        return []
    main = text[:220]
    words = list(dict.fromkeys(tokens(text)))
    candidates = [main]
    if len(words) >= 3:
        candidates.append(' '.join(words[:8]))
    if 5 <= len(words) < 7:
        candidates.append(' '.join(words[:4]))
    if len(words) >= 7:
        mid = len(words) // 2
        candidates += [' '.join(words[max(0, mid-4):mid+4]), ' '.join(words[-8:])]
    for part in re.split(r'(?<=[.!?;])\s+', text):
        if 16 < len(part) < len(text):
            candidates.append(part[:170])
    if 3 <= len(words) <= 8:
        candidates.append(' '.join(words))
    seen, output = set(), []
    for c in candidates:
        c = c.strip(' ,.;!')
        if len(c) >= 5 and c.casefold() not in seen:
            output.append(c)
            seen.add(c.casefold())
    return output[:limit]


def relevance(query, claim):
    a, b = set(tokens(query)), set(tokens(claim))
    if not a or not b:
        return 0.0
    if bool(NEG.search(query)) != bool(NEG.search(claim)):
        return 0.0
    nums_a = set(re.findall(r'(?<!\w)\d+(?:[.,]\d+)*(?!\w)', query))
    nums_b = set(re.findall(r'(?<!\w)\d+(?:[.,]\d+)*(?!\w)', claim))
    if nums_a and nums_b and not (nums_a & nums_b):
        return 0.0
    shared = a & b
    if len(shared) < (1 if max(len(a),len(b)) < 3 else 2):
        return 0.0
    recall = len(shared) / len(a)
    precision = len(shared) / len(b)
    score = 2 * recall * precision / (recall + precision)
    if nums_a and nums_b and nums_a != nums_b:
        score *= .70
    return round(score, 3) if score >= .44 else 0.0


def rating_type(rating):
    value = normalize(rating)
    if not value:
        return 'unknown'
    if re.search(r'(?:sebagian besar salah|mostly false|mostly incorrect)', value):
        return 'false'
    if re.search(r'(?<!\w)(?:sebagian|separuh|setengah|mixed|partly|partially|half|konteks|context|missing context|unproven|belum terbukti|tidak terbukti)(?!\w)', value):
        return 'partial'
    if re.search(r'(?<!\w)(?:tidak benar|tidak akurat|salah|keliru|hoaks|hoax|palsu|bohong|false|fake|misleading|menyesatkan|fabricated|incorrect|untrue|not true|inaccurate)(?!\w)', value):
        return 'false'
    if re.search(r'(?<!\w)(?:benar|fakta|akurat|valid|terbukti|true|correct|accurate)(?!\w)', value):
        return 'true'
    return 'unknown'


def assess(reviews):
    strong = [item for item in reviews if item.get('relevansi', 0) >= .66]
    explicit = [rating_type(x.get('rating')) for x in strong]
    assessed = [x for x in explicit if x != 'unknown']
    if not assessed:
        return ('Belum ditemukan', 'Belum ada ulasan dengan penilaian jelas dan kecocokan cukup kuat.')
    if 'partial' in assessed or ('true' in assessed and 'false' in assessed):
        return ('Perlu konteks', 'Ulasan yang cocok mengandung penilaian sebagian benar atau saling berbeda.')
    if all(x == 'false' for x in assessed):
        return ('Hoaks', f'{len(assessed)} penilaian sumber cek fakta yang relevan menyatakan klaim salah.')
    if all(x == 'true' for x in assessed):
        return ('Fakta', f'{len(assessed)} penilaian sumber cek fakta yang relevan menyatakan klaim benar.')
    return ('Belum ditemukan', 'Sumber yang ditemukan belum cukup untuk menyimpulkan.')


def wikipedia_reference(text, timeout=6):
    """Ambil referensi ensiklopedis. Auto-verifikasi hanya untuk tanggal kemerdekaan eksplisit."""
    original = clean_text(text)
    if len(original) < 8 or len(original) > 250:
        return [], False
    date_match = DATE.search(original)
    independence = re.search(r'\b(?:merdeka|kemerdekaan|proklamasi)\b', original, re.I)
    strict = re.fullmatch(
        r'(?:benarkah\s+)?(?P<subject>[\w\s.-]{3,45}?)\s+'
        r'(?:merdeka|memproklamasikan\s+kemerdekaan(?:nya)?|proklamasi\s+kemerdekaan)\s+'
        r'(?:pada\s+(?:tanggal\s+)?)?'
        r'(?P<date>\d{1,2}\s+' + MONTH + r'\s+\d{4})[.!?]?',
        original, flags=re.I)
    subject = (strict.group('subject').strip() if strict else '')
    if date_match and independence:
        broad_subject = re.split(r'\b(?:merdeka|kemerdekaan|proklamasi)\b', original, maxsplit=1, flags=re.I)[0]
        search = 'proklamasi kemerdekaan ' + (subject or broad_subject[:40] or 'Indonesia')
    elif date_match:
        search = re.sub(r'\b(?:pada|tanggal)\b.*', '', original, flags=re.I)[:75]
    else:
        search = ' '.join(tokens(original)[:7])
    if len(search) < 4:
        return [], False
    params = {'action':'query', 'format':'json', 'generator':'search', 'gsrsearch':search,
              'gsrlimit':3, 'prop':'extracts|info', 'exintro':1, 'explaintext':1,
              'exchars':1000, 'inprop':'url'}
    try:
        r = requests.get(WIKIPEDIA_API, params=params, timeout=timeout, headers={'User-Agent': UA})
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError, KeyError):
        return [], False
    pages = list(data.get('query', {}).get('pages', {}).values())
    pages.sort(key=lambda x: x.get('index', 99))
    refs = []
    verified_date = False
    for page in pages[:3]:
        extract = str(page.get('extract') or '').strip()
        title = str(page.get('title') or '')
        url = str(page.get('fullurl') or '')
        if not extract or not url.startswith('https://'):
            continue
        refs.append({'judul':title, 'kutipan':extract[:550], 'url':url, 'sumber':'Wikipedia',
                     'catatan':'Referensi ensiklopedia; tidak otomatis memverifikasi seluruh klaim.'})
        if strict and date_match and independence and not NEG.search(original):
            day, month, year = date_match.groups()
            expected = f'{int(day)} {month.lower()} {year}'
            extract_norm = normalize(extract)
            title_norm = normalize(title)
            subject_tokens = set(tokens(subject))
            contains_subject = bool(subject_tokens and (subject_tokens & set(tokens(title + ' ' + extract[:250]))))
            historical_context = bool(re.search('merdeka|kemerdekaan|proklamasi', extract_norm))
            # Persis cocok tanggal pada kalimat yang menerangkan proklamasi/kemerdekaan.
            sentences = re.split(r'(?<=[.!?])\s+', extract_norm)
            linked_date = any(expected in s and re.search(r'merdeka|kemerdekaan|proklamasi', s)
                              for s in sentences)
            if contains_subject and historical_context and linked_date and ('proklamasi' in title_norm or 'kemerdekaan' in title_norm):
                verified_date = True
    return refs[:3], verified_date
