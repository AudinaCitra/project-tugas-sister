"""Bukti resmi TERKURASI (bukan hasil pencarian API real-time).
Hanya aturan klaim sederhana yang benar-benar dipadankan; jangan diperluas
menjadi klaim semua berita benar. Tambahkan data baru sesudah diverifikasi manual.
"""
import re
from verifikasi import clean_text, NEG, MONTH

BUKTI_PROKLAMASI = [
    {
        'judul': 'Proklamasi di Pegangsaan Timur',
        'sumber': 'Direktorat Pelindungan Kebudayaan — Kemdikbud',
        'url': 'https://kebudayaan.kemdikbud.go.id/dpk/agustus-1945/',
        'kutipan': 'Proklamasi Kemerdekaan Indonesia dilaksanakan di Jalan Pegangsaan Timur 56 Jakarta pada 17 Agustus 1945 oleh Sukarno dan Hatta.',
        'catatan': 'Sumber pemerintah, dikurasi untuk klaim tanggal proklamasi; bukan hasil penelusuran langsung saat ini.',
    },
    {
        'judul': 'Masa Kemerdekaan',
        'sumber': 'Balai Pelestarian Kebudayaan Wilayah V — Kemdikbud',
        'url': 'https://kebudayaan.kemdikbud.go.id/bpkw5/masa-kemerdekaan/',
        'kutipan': 'Indonesia memproklamasikan kemerdekaan pada tanggal 17 Agustus 1945.',
        'catatan': 'Sumber pemerintah, dikurasi untuk klaim tanggal proklamasi; bukan hasil penelusuran langsung saat ini.',
    },
]

# HANYA satu klaim singkat, subjek Indonesia, tanpa tambahan berita/pernyataan lain.
_PROKLAMASI = re.compile(
    r'^(?:benarkah\s+)?(?:negara\s+|republik\s+)?indonesia\s+'
    r'(?:merdeka|memproklamasikan\s+kemerdekaan(?:nya)?|'
    r'memproklamirkan\s+kemerdekaan(?:nya)?|'
    r'menyatakan\s+kemerdekaan(?:nya)?|'
    r'(?:melakukan\s+)?proklamasi\s+kemerdekaan(?:nya)?)'
    r'\s+(?:pada\s+)?(?:tanggal\s+)?'
    r'(?P<day>\d{1,2})\s+(?P<month>' + MONTH + r')\s+(?P<year>\d{4})[.!?]?$',
    flags=re.I
)

def verifikasi_resmi(klaim):
    """Return (status, reason, references) or None when not in curated coverage."""
    text = clean_text(klaim)
    if len(text) > 170 or NEG.search(text):
        return None
    match = _PROKLAMASI.fullmatch(text)
    if not match:
        return None
    d, m, y = int(match['day']), match['month'].lower(), int(match['year'])
    benar = (d, m, y) == (17, 'agustus', 1945)
    label = 'Fakta' if benar else 'Hoaks'
    alasan = ('Tanggal proklamasi sesuai dua publikasi resmi Kemdikbud.' if benar else
              'Tanggal pada klaim bertentangan dengan sumber resmi Kemdikbud yang mencatat 17 Agustus 1945.')
    return label, alasan, [dict(x) for x in BUKTI_PROKLAMASI]
