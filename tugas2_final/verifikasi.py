"""Pemadanan klaim umum. Tidak memuat kebenaran/URL berita yang ditanam di kode.

Penting: skor kesamaan TEKS bukan akurasi; label diambil dari ulasan
Fact Check dengan pernyataan yang sepadan atau berlawanan secara eksplisit.
"""
import re
import unicodedata
from difflib import SequenceMatcher

STOP = set('yang dan atau dari untuk dengan pada dalam bahwa telah akan karena agar dapat adalah sebagai menjadi kepada kami anda mereka sebuah tersebut seperti ini itu di ke oleh para jika ketika serta soal terkait mengatakan berita kabar disebut diduga viral heboh terbaru resmi informasi menurut terjadi sudah apa siapa bagaimana mengapa bisa ada sebuah si sang pun oleh pada lewat melalui jadi ya aja tahun tanggal hari'.split())
FILLER = re.compile(r'(?:diteruskan berkali-kali|forwarded many times|ketik pesan|mohon dibagikan|bagikan ke keluarga|share ke grup|baca selengkapnya|pesan diteruskan)', re.I)
NEGATION = re.compile(r'\b(?:tidak|bukan|tak|nggak|belum|never|not|no|tanpa)\b', re.I)
ALIASES = {'hoax':'hoaks', 'covid19':'covid', 'covid-19':'covid', 'korona':'corona', 'microchips':'microchip', 'mikrocip':'microchip', 'cip':'chip', 'nggak':'tidak', 'enggak':'tidak', 'gak':'tidak', 'ngga':'tidak', 'jokowi':'joko_widodo', 'ugm':'gadjah_mada', 'universitas':'', 'gadjah':'gadjah_mada', 'mata':'', 'khabar':'kabar', 'memproklamasikan':'proklamasi', 'memproklamirkan':'proklamasi', 'memproklamasikannya':'proklamasi', 'kemerdekaan':'merdeka', 'kemerdekaannya':'merdeka', 'proklamir':'proklamasi'}
# Hanya perbedaan makna kata, BUKAN daftar berita yang diasumsikan benar.
OPPOSITES = [({'asli', 'otentik', 'sah'}, {'palsu', 'tiruan', 'bodong'}),
             ({'hidup'}, {'meninggal', 'wafat', 'mati'}),
             ({'naik', 'meningkat', 'bertambah'}, {'turun', 'menurun', 'berkurang'}),
             ({'setuju', 'menyetujui', 'disetujui'}, {'menolak', 'ditolak'}),
             ({'lulus'}, {'tidak_lulus'}),
             ({'dibatalkan', 'batal'}, {'disahkan', 'sah'})]


def normalize(value):
    text = unicodedata.normalize('NFKC', str(value or '')).lower()
    text = re.sub(r'\bcovid[ -]?19\b', 'covid', text)
    text = re.sub(r'\bjoko\s+widodo\b', 'joko_widodo', text)
    text = re.sub(r'\buniversitas\s+gadjah\s+mada\b', 'gadjah_mada', text)
    text = re.sub(r'\bgadjah\s+mada\b', 'gadjah_mada', text)
    return re.sub(r'\s+', ' ', text).strip()


def tokens(value, stop=True):
    out = []
    for item in re.findall(r'(?u)\b[\w]+\b', normalize(value)):
        w = ALIASES.get(item, item)
        if w and (len(w) > 2 or w.isdigit()) and (not stop or w not in STOP):
            out.append(w)
    return out


def clean_text(value):
    lines = []
    for line in str(value or '').splitlines():
        line = FILLER.sub(' ', line)
        line = re.sub(r'\s+', ' ', line).strip(' :-•|\t')
        if len(line) >= 2:
            lines.append(line)
    return ' '.join(lines).strip(' .,;:')[:3500]


def keyword_variants(text, limit=6):
    text = clean_text(text)
    if len(text) < 5:
        return []
    words = list(dict.fromkeys(tokens(text)))
    variants = [text[:190]]
    # Bentuk pendek cocok untuk klaim OCR panjang dan pencarian API sempit.
    if words:
        variants.extend([' '.join(w.replace('_', ' ') for w in words[:7]), ' '.join(w.replace('_', ' ') for w in words[:5])])
        if len(words) > 7:
            variants.extend([' '.join(w.replace('_', ' ') for w in words[2:9]), ' '.join(w.replace('_', ' ') for w in words[-7:])])
    sentences = re.split(r'(?<=[.!?;])\s+', text)
    variants.extend(x[:155] for x in sentences[:4] if 14 < len(x) < 240)
    # Kalimat sumber kadang memakai padanan entitas berbeda.
    variants.extend([text[:130].replace('Jokowi', 'Joko Widodo').replace('jokowi', 'joko widodo')])
    seen, output = set(), []
    for q in variants:
        q = q.strip(' .,;!?')
        if len(q) >= 5 and q.casefold() not in seen:
            seen.add(q.casefold()); output.append(q)
    return output[:limit]


def numbers(text):
    # Nomor utama seperti hari/tahun, persen, uang. Hindari angka versi 19 dari COVID.
    clean = re.sub(r'\bcovid[ -]?19\b', 'covid', normalize(text))
    return set(re.findall(r'(?<!\w)\d+(?:[.,]\d+)*(?!\w)', clean))


def _opp(a, b):
    for yes, no in OPPOSITES:
        if (a & yes and b & no) or (a & no and b & yes):
            return True
    return False


def claim_relation(query, reviewed):
    """Return (similarity, relation). relation: sama, lawan, tidak_pasti.

    Bertentangan hanya ketika ada perbedaan eksplisit kata antonim/negasi.
    Tidak berspekulasi perbedaan makna tersirat.
    """
    a, b = set(tokens(query)), set(tokens(reviewed))
    if not a or not b:
        return 0.0, 'tidak_pasti'
    neg_a = bool(NEGATION.search(normalize(query)))
    neg_b = bool(NEGATION.search(normalize(reviewed)))
    core_a, core_b = a - {'tidak', 'bukan', 'tak', 'belum', 'tanpa'}, b - {'tidak', 'bukan', 'tak', 'belum', 'tanpa'}
    opposite = _opp(core_a, core_b)
    # Jangan menghukum antonim saat menghitung kecocokan TOPIK.
    a_key = set(core_a); b_key = set(core_b)
    if opposite:
        for left, right in OPPOSITES:
            if a_key & (left | right) and b_key & (left | right):
                a_key.difference_update(left | right)
                b_key.difference_update(left | right)
    shared = a_key & b_key
    if len(shared) < (1 if min(len(a_key), len(b_key)) <= 2 else 2):
        return 0.0, 'tidak_pasti'
    ratio = (2 * len(shared) / (len(a_key) + len(b_key))) if (a_key or b_key) else 0
    coverage = len(shared) / len(a_key) if a_key else 0
    score = .55 * ratio + .45 * coverage
    # Angka/tanggal yang berbeda membuat klaim tidak ekuivalen; jangan otomatis balik label.
    n1, n2 = numbers(query), numbers(reviewed)
    if n1 and n2 and n1 != n2:
        score *= .52
        return round(score, 3), 'tidak_pasti'
    if opposite and neg_a != neg_b:
        return round(score * .65, 3), 'tidak_pasti'  # negasi + antonim: belum tentu terbalik
    if opposite or neg_a != neg_b:
        return round(min(score, .98), 3), 'lawan' if score >= .67 else 'tidak_pasti'
    # Perbedaan panjang besar: topik sama tetapi klaim ekstra mungkin belum dikaji.
    if coverage < .64 or score < .61:
        return round(score, 3), 'tidak_pasti'
    return round(min(score, .99), 3), 'sama'


def relevance(query, reviewed):
    return claim_relation(query, reviewed)[0]


def rating_type(rating):
    value = normalize(rating)
    if not value:
        return 'unknown'
    partial = r'\b(?:sebagian|separuh|setengah|mostly true|mostly false|mostly accurate|mixed|partly|partially|half true|konteks|context|unproven|belum terbukti|tidak terbukti|misleading|menyesatkan|kurang tepat)\b'
    if re.search(partial, value):
        return 'partial'
    if re.search(r'\b(?:tidak benar|tidak akurat|salah|keliru|hoaks|hoax|palsu|bohong|false|fake|fabricated|incorrect|untrue|not true|inaccurate|disinformasi)\b', value):
        return 'false'
    if re.search(r'\b(?:benar|fakta|akurat|valid|terbukti|true|correct|accurate|sesuai fakta)\b', value):
        return 'true'
    return 'unknown'


def assess(reviews):
    votes = []
    for item in reviews:
        if item.get('relevansi', 0) < .70 or item.get('hubungan') not in ('sama', 'lawan'):
            continue
        label = rating_type(item.get('rating'))
        if label == 'unknown':
            continue
        if item.get('hubungan') == 'lawan' and label in ('true', 'false'):
            label = 'false' if label == 'true' else 'true'
        votes.append((label, item))
    if not votes:
        return 'Belum ditemukan', 'Ulasan yang ditemukan belum memiliki penilaian tegas untuk klaim yang sama. Artikel terkait tetap ditampilkan agar bisa ditinjau.'
    kinds = {v[0] for v in votes}
    if 'partial' in kinds or len(kinds) > 1:
        return 'Perlu konteks', 'Ada ulasan sebagian benar/menyesatkan, atau sumber yang sepadan memberikan penilaian berbeda.'
    if kinds == {'false'}:
        return 'Hoaks', f'{len(votes)} ulasan cek fakta yang sepadan atau secara eksplisit berlawanan mendukung bahwa klaim ini salah.'
    if kinds == {'true'}:
        return 'Fakta', f'{len(votes)} ulasan cek fakta yang sepadan atau secara eksplisit berlawanan mendukung bahwa klaim ini benar.'
    return 'Belum ditemukan', 'Bukti belum cukup.'
