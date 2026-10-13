"""Penelusuran DINAMIS sumber tepercaya: RSS pencarian publik + halaman sumber.
Tidak ada URL ARTIKEL/fakta yang dipasang khusus untuk suatu klaim.

RSS bukan API Google Fact Check; pencarian RSS tidak memakai GOOGLE_FACTCHECK_API_KEY.
Sumber yang tidak bisa dibaca diberi status referensi, bukan bukti benar/salah.
"""
import re
import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from verifikasi import claim_relation, clean_text, normalize, tokens, numbers

# Nama DOMAIN saja untuk preferensi; tidak ada berita yang ditentukan di sini.
TRUSTED_NEWS = ('kompas.com', 'tempo.co', 'antaranews.com', 'turnbackhoax.id', 'cekfakta.com',
                'tirto.id', 'detik.com', 'liputan6.com', 'cnnindonesia.com',
                'bbc.com', 'reuters.com', 'apnews.com', 'theconversation.com')
TRUSTED_OFFICIAL = ('go.id', 'ac.id', 'gov', 'edu', 'who.int', 'un.org', 'worldbank.org',
                    'bnpb.go.id', 'bmkg.go.id', 'bps.go.id')
UA = 'Mozilla/5.0 (compatible; FaktaLensEducational/3.0; +https://developers.google.com/fact-check/tools/api/)'
TIMEOUT = (3.5, 6.5)


def host_name(url):
    try: return (urlparse(url).hostname or '').lower().rstrip('.')
    except ValueError: return ''


def trusted(host):
    if not host or host.endswith('.wikipedia.org'):
        return ''
    if any(host == x or host.endswith('.' + x) for x in TRUSTED_OFFICIAL):
        return 'Instansi resmi / lembaga pendidikan'
    if any(host == x or host.endswith('.' + x) for x in TRUSTED_NEWS):
        return 'Media / pemeriksa fakta'
    return ''


def public_url(url):
    try:
        p = urlparse(url)
        if p.scheme != 'https' or p.username or p.password or not p.hostname or p.port not in (None, 443):
            return False
        host = p.hostname.lower()
        if host == 'localhost' or host.endswith('.local') or host.endswith('.internal'):
            return False
        info = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        return bool(info) and all(ipaddress.ip_address(x[4][0]).is_global for x in info)
    except (OSError, ValueError):
        return False


def fetch_page(url):
    """Ambil HTML langsung dari publisher terpercaya saja; tiap redirect diperiksa ulang."""
    current = url
    for _ in range(3):
        if not trusted(host_name(current)) or not public_url(current):
            return None
        try:
            with requests.get(current, timeout=TIMEOUT, allow_redirects=False, stream=True,
                              headers={'User-Agent': UA, 'Accept': 'text/html'}) as res:
                if res.status_code in (301, 302, 303, 307, 308):
                    current = urljoin(current, res.headers.get('Location', ''))
                    continue
                if res.status_code != 200 or 'html' not in res.headers.get('Content-Type', '').lower():
                    return None
                chunks, size = [], 0
                for chunk in res.iter_content(16384):
                    size += len(chunk)
                    if size > 260000: break
                    chunks.append(chunk)
                raw = b''.join(chunks)
            soup = BeautifulSoup(raw, 'html.parser')
            for tag in soup(['script','style','noscript','nav','footer','header','form','aside']):
                tag.decompose()
            doc = soup.select_one('article') or soup.select_one('main') or soup.body or soup
            paragraphs = [p.get_text(' ', strip=True) for p in doc.select('p, h1, h2, h3')]
            paragraphs = [p for p in paragraphs if 35 <= len(p) <= 2500]
            body = ' '.join(paragraphs)[:13000]
            if not body:
                body = doc.get_text(' ', strip=True)[:13000]
            return {'teks': body, 'url': current}
        except requests.RequestException:
            return None
    return None


def parse_rss(xml, max_items=12):
    try: root = ET.fromstring(xml)
    except ET.ParseError: return []
    items = []
    for node in root.findall('.//channel/item')[:max_items]:
        url = (node.findtext('link') or '').strip()
        title = re.sub(r'\s+', ' ', BeautifulSoup(node.findtext('title') or '', 'html.parser').get_text(' ', strip=True))
        desc = BeautifulSoup(node.findtext('description') or '', 'html.parser').get_text(' ', strip=True)
        source = node.find('source')
        publisher = (source.text or '').strip() if source is not None else ''
        publisher_url = source.get('url','') if source is not None else ''
        if not url.startswith('https://'): continue
        items.append({'judul': title[:230], 'url': url, 'kutipan': desc[:350],
                      'sumber': publisher or host_name(url), 'asal_situs': publisher_url, 'tanggal': (node.findtext('pubDate') or '')[:50]})
    return items


def search_feed(engine, query):
    if engine == 'bing':
        endpoint = 'https://www.bing.com/search'
        params = {'format':'rss', 'q':query}
    else:
        endpoint = 'https://news.google.com/rss/search'
        params = {'q':query, 'hl':'id', 'gl':'ID', 'ceid':'ID:id'}
    try:
        response = requests.get(endpoint, params=params, timeout=TIMEOUT, headers={'User-Agent': UA})
        response.raise_for_status()
        return parse_rss(response.content)
    except requests.RequestException:
        return []


def candidate_queries(claim):
    # 3 sumber pencarian otomatis berdasarkan INPUT, bukan topik tetap.
    words = tokens(claim)
    core = ' '.join(w.replace('_', ' ') for w in words[:9])[:115] or claim[:110]
    original = clean_text(claim)[:110]
    return [('bing', core + ' (site:go.id OR site:ac.id OR site:who.int)'),
            ('bing', core + ' (site:kompas.com OR site:tempo.co OR site:antaranews.com)'),
            ('google_news', original),
            ('google_news', core + ' cek fakta')]


def sentences(text):
    text = re.sub(r'\s+', ' ', text)
    # Sebagian situs memakai satu paragraf panjang: potong dengan tanda baca.
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', text)
    return [x.strip()[:550] for x in raw if 28 < len(x) < 1800][:85]


def source_evidence(claim, article_text):
    """Hasil: (tingkat, cuplikan, skor) — tidak disamakan dengan hasil cek fakta.
    Hanya kalimat ringkas yang bisa dibandingkan, bukan seluruh artikel.
    """
    best = ('Topik terkait', '', 0.0)
    q_words = set(tokens(claim))
    if not q_words: return best
    for sentence in sentences(article_text):
        score, relation = claim_relation(claim, sentence)
        score = float(score)
        if score <= best[2]: continue
        verdict = 'Topik terkait'
        n1, n2 = numbers(claim), numbers(sentence)
        claim_short = len(q_words) <= 16
        # Penerbit dapat mengutip klaim salah. Hindari menjadikan kutipan viral sebagai fakta.
        context = bool(re.search(r'\b(?:hoaks|hoax|kabar|isu|klaim|viral|rumor|dibantah|tidak benar|disinformasi|cek fakta|disanggah)\b', sentence, re.I))
        if claim_short and score >= .83 and not context and relation == 'sama':
            verdict = 'Mendukung'
        if claim_short and score >= .79 and not context and relation == 'lawan':
            verdict = 'Membantah'
        # Angka berbeda tidak serta merta membuat berita salah: pertanyaan lain/datum berbeda.
        best = verdict, sentence[:460], round(score, 3)
    return best


def _enrich(candidate, claim):
    link = candidate['url']
    host = host_name(link)
    category = trusted(host)
    item = dict(candidate)
    item.update({'kategori':category or trusted(host_name(item.get('asal_situs',''))) or 'Hasil pencarian berita',
                 'penilaian':'Topik terkait', 'kecocokan':0, 'bisa_diverifikasi':False})
    if not category:
        # news.google.com adalah aggregator; tidak ada kesimpulan dari judul.
        return item
    page = fetch_page(link)
    if page and page.get('teks'):
        assessment, excerpt, score = source_evidence(claim, page['teks'])
        item.update({'url':page['url'], 'kutipan':excerpt or item['kutipan'],
                     'penilaian':assessment, 'kecocokan':score, 'bisa_diverifikasi':True})
    return item


def search_trusted(claim, max_results=9):
    """Search engine RSS gratis bisa gagal/rate-limit; hasil kosong bukan berarti tidak ada fakta."""
    claim = clean_text(claim)
    if len(claim) < 5: return [], []
    outputs = []
    searches = candidate_queries(claim)
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {executor.submit(search_feed, engine, query): (engine, query)
                      for engine, query in searches}
        for future in as_completed(future_map):
            try: outputs.extend(future.result())
            except Exception: pass
    unique, seen = [], set()
    for entry in outputs:
        key = entry['url'].split('?')[0]
        if key in seen: continue
        seen.add(key)
        host = host_name(key)
        if not trusted(host) and not (host == 'news.google.com' and trusted(host_name(entry.get('asal_situs','')))):
            continue
        entry['skor_judul'] = claim_relation(claim, entry['judul'])[0]
        unique.append(entry)
    unique.sort(key=lambda item: (bool(trusted(host_name(item['url']))), item['skor_judul']), reverse=True)
    shortlist = unique[:max_results]
    # Maks 6 artikel (tidak semua situs memungkinkan ekstraksi).
    direct = shortlist[:6]
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_enrich, ref, claim): i for i, ref in enumerate(direct)}
        indexed = {}
        for f in as_completed(futures):
            try: indexed[futures[f]] = f.result()
            except Exception: pass
    result = [indexed.get(i, dict(entry, kategori='Terkait',penilaian='Topik terkait',kecocokan=0,bisa_diverifikasi=False))
              for i, entry in enumerate(direct)]
    for entry in shortlist[6:]:
        result.append(dict(entry, kategori=trusted(host_name(entry['url'])) or 'Terkait',
                           penilaian='Topik terkait',kecocokan=0,bisa_diverifikasi=False))
    return result, [q for _, q in searches]


def verdict_from_sources(references):
    """Sumber artikel tidak punya rating Fact Check. Syarat lebih berat:
    sedikitnya 2 situs berbeda; atau 1 bukti publikasi instansi resmi yang eksplisit.
    Tetap bukan pengganti validasi manusia.
    """
    strong = [x for x in references if x.get('penilaian') in ('Mendukung','Membantah') and x.get('bisa_diverifikasi')]
    groups = {'Mendukung':set(), 'Membantah':set()}
    for item in strong:
        host = host_name(item['url'])
        # domain independen: subdomain lembaga berbeda boleh cukup spesifik; .go.id tetap domain masing-masing
        parts = host.split('.')
        base = '.'.join(parts[-3:] if host.endswith(('.go.id','.ac.id')) else parts[-2:])
        groups[item['penilaian']].add(base)
    yes, no = groups['Mendukung'], groups['Membantah']
    if yes and no:
        return 'Perlu konteks', 'Terdapat referensi tepercaya dengan isi yang tampak bertentangan. Periksa artikel lengkapnya.'
    if len(yes) >= 2 or (len(yes) >= 1 and any('Instansi resmi' in x['kategori'] and x['penilaian']=='Mendukung' and x.get('kecocokan', 0) >= .82 for x in strong)):
        return 'Fakta', 'Kalimat dalam sumber tepercaya mendukung pernyataan ini. Verifikasi dengan membaca artikel lengkapnya.'
    if len(no) >= 2 or (len(no) >= 1 and any('Instansi resmi' in x['kategori'] and x['penilaian']=='Membantah' and x.get('kecocokan', 0) >= .82 for x in strong)):
        return 'Hoaks', 'Kalimat dalam sumber tepercaya tampak membantah pernyataan ini. Verifikasi dengan membaca artikel lengkapnya.'
    if strong:
        return 'Perlu konteks', 'Ada referensi dengan kecocokan isi, tetapi bukti belum cukup kuat untuk label Fakta/Hoaks.'
    return 'Belum ditemukan', 'Pencarian menemukan referensi terkait, tetapi belum ada kalimat bukti yang cukup jelas untuk menyimpulkan.'
