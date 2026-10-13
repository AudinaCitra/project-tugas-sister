
"""Pencarian sumber tepercaya FaktaLens dari internet.

Google Fact Check API tetap diproses oleh app.py.
Modul ini mencari artikel melalui RSS, membaca isi situs,
dan membandingkan bukti dengan klaim pengguna.

Tidak menggunakan Wikipedia atau jawaban fakta hardcoded.
"""

import ipaddress
import json
import re
import socket
import xml.etree.ElementTree as ET

from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from verifikasi import claim_relation, clean_text, tokens

try:
    from googlenewsdecoder import gnewsdecoder
except ImportError:
    gnewsdecoder = None


# Daftar domain sumber, bukan daftar jawaban berita.
TRUSTED_NEWS = (
    "kompas.com",
    "tempo.co",
    "antaranews.com",
    "turnbackhoax.id",
    "cekfakta.com",
    "tirto.id",
    "detik.com",
    "liputan6.com",
    "cnnindonesia.com",
    "bbc.com",
    "reuters.com",
    "apnews.com",
    "theconversation.com",
)

TRUSTED_OFFICIAL = (
    "go.id",
    "ac.id",
    "gov",
    "edu",
    "who.int",
    "un.org",
    "worldbank.org",
)

USER_AGENT = "Mozilla/5.0 (compatible; FaktaLensEducational/4.0)"
TIMEOUT = (4, 8)


def host_name(url):
    try:
        return (urlparse(str(url or "")).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def _matches_domain(host, domain):
    return host == domain or host.endswith("." + domain)


def trusted(host):
    host = str(host or "").lower().rstrip(".")

    if not host:
        return ""

    if _matches_domain(host, "wikipedia.org"):
        return ""

    if _matches_domain(host, "wikidata.org"):
        return ""

    if any(_matches_domain(host, d) for d in TRUSTED_OFFICIAL):
        return "Instansi resmi / lembaga pendidikan"

    if any(_matches_domain(host, d) for d in TRUSTED_NEWS):
        return "Media / pemeriksa fakta"

    return ""


def public_url(url):
    """Mencegah pengambilan alamat lokal atau privat."""
    try:
        parsed = urlparse(str(url or ""))

        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            return False

        host = parsed.hostname.lower().rstrip(".")

        if host == "localhost" or host.endswith((".local", ".internal")):
            return False

        addresses = socket.getaddrinfo(
            host, 443, type=socket.SOCK_STREAM
        )

        return bool(addresses) and all(
            ipaddress.ip_address(entry[4][0]).is_global
            for entry in addresses
        )

    except (OSError, ValueError):
        return False


def _extract_article(raw):
    """Ekstraksi isi artikel HTML dan JSON-LD."""
    soup = BeautifulSoup(raw, "html.parser")
    jsonld = []

    for script in soup.select(
        'script[type="application/ld+json"]'
    )[:12]:
        try:
            value = json.loads(
                script.string or script.get_text() or "{}"
            )
        except (json.JSONDecodeError, TypeError):
            continue

        todo = value if isinstance(value, list) else [value]

        while todo:
            node = todo.pop()

            if isinstance(node, dict):
                if isinstance(node.get("articleBody"), str):
                    jsonld.append(node["articleBody"])

                nested = node.get("@graph")

                if isinstance(nested, list):
                    todo.extend(nested[:30])

    for tag in soup([
        "script", "style", "noscript", "nav",
        "footer", "header", "form", "aside"
    ]):
        tag.decompose()

    root = (
        soup.select_one("article")
        or soup.select_one("main")
        or soup.body
        or soup
    )

    paragraphs = [
        p.get_text(" ", strip=True)
        for p in root.select("h1, h2, h3, p, li")
    ]

    paragraphs = [
        p for p in paragraphs
        if 35 <= len(p) <= 2300
    ]

    visible = " ".join(paragraphs) or root.get_text(
        " ", strip=True
    )

    text = max([visible] + jsonld, key=len, default="")

    return re.sub(r"\s+", " ", text).strip()[:25000]


def fetch_page(url):
    """Membaca isi artikel dari situs penerbit."""
    current = url

    for _ in range(4):
        if (
            not trusted(host_name(current))
            or not public_url(current)
        ):
            return None

        try:
            with requests.get(
                current,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html",
                },
                timeout=TIMEOUT,
                allow_redirects=False,
                stream=True,
            ) as response:

                if response.status_code in (
                    301, 302, 303, 307, 308
                ):
                    location = response.headers.get(
                        "Location"
                    )

                    if not location:
                        return None

                    current = urljoin(current, location)
                    continue

                if (
                    response.status_code != 200
                    or "html" not in response.headers.get(
                        "Content-Type", ""
                    ).lower()
                ):
                    return None

                content = bytearray()

                for chunk in response.iter_content(
                    chunk_size=16384
                ):
                    content.extend(chunk)

                    if len(content) >= 950000:
                        break

            text = _extract_article(bytes(content))

            if len(text) < 150:
                return None

            return {
                "url": current,
                "teks": text,
            }

        except (requests.RequestException, ValueError):
            return None

    return None


def parse_rss(xml, max_items=12):
    """Mengubah hasil RSS menjadi daftar artikel."""
    try:
        root = ET.fromstring(xml)
    except (ET.ParseError, TypeError):
        return []

    items = []

    for node in root.findall(
        ".//channel/item"
    )[:max_items]:
        url = (node.findtext("link") or "").strip()

        if not url.startswith("https://"):
            continue

        title = BeautifulSoup(
            node.findtext("title") or "",
            "html.parser"
        ).get_text(" ", strip=True)

        desc = BeautifulSoup(
            node.findtext("description") or "",
            "html.parser"
        ).get_text(" ", strip=True)

        source = node.find("source")

        publisher = (
            (source.text or "").strip()
            if source is not None
            else ""
        )

        publisher_url = (
            source.get("url", "")
            if source is not None
            else ""
        )

        items.append({
            "judul": re.sub(r"\s+", " ", title)[:230],
            "url": url,
            "kutipan": desc[:350],
            "sumber": publisher or host_name(url),
            "asal_situs": publisher_url,
            "tanggal": (
                node.findtext("pubDate") or ""
            )[:50],
        })

    return items


def search_feed(engine, query):
    """Mencari artikel secara dinamis di internet."""
    if engine == "bing":
        endpoint = "https://www.bing.com/search"
        params = {
            "q": query,
            "format": "rss",
        }

    elif engine == "gdelt":
        endpoint = (
            "https://api.gdeltproject.org/api/v2/doc/doc"
        )
        params = {
            "query": query,
            "mode": "artlist",
            "format": "rss",
            "maxrecords": 12,
            "timespan": "3months",
        }

    else:
        endpoint = (
            "https://news.google.com/rss/search"
        )
        params = {
            "q": query,
            "hl": "id",
            "gl": "ID",
            "ceid": "ID:id",
        }

    try:
        response = requests.get(
            endpoint,
            params=params,
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )

        response.raise_for_status()
        return parse_rss(response.content)

    except requests.RequestException:
        return []


def candidate_queries(claim):
    """Membuat kata kunci dari input pengguna."""
    raw = clean_text(claim)

    words = [
        word.replace("_", " ")
        for word in tokens(raw)
    ]

    short = " ".join(words[:10])[:115] or raw[:115]
    precise = raw[:150]

    queries = [
        ("bing", short + " site:go.id"),
        ("bing", short + " site:ac.id"),
        ("bing", short + " site:kompas.com"),
        ("bing", short + " site:antaranews.com"),
        ("bing", short + " site:tempo.co"),
        ("bing", precise),
        ("gdelt", short),
        ("google_news", precise),
        ("google_news", short + " cek fakta"),
    ]

    seen = set()
    unique = []

    for engine, query in queries:
        if (engine, query) not in seen:
            seen.add((engine, query))
            unique.append((engine, query))

    return unique


def sentences(text):
    text = re.sub(r"\s+", " ", text)

    raw = re.split(
        r"(?<=[.!?])\s+(?=[A-Z0-9])",
        text
    )

    return [
        part.strip()[:600]
        for part in raw
        if 25 < len(part) < 1800
    ][:130]


def source_evidence(claim, article_text):
    """Mencari kalimat bukti di isi artikel."""
    best = ("Topik terkait", "", 0.0)
    best_rank = -1

    if not tokens(claim):
        return best

    for sentence in sentences(article_text):
        score, relation = claim_relation(
            claim, sentence
        )

        if score < 0.28:
            continue

        # Jangan menganggap kutipan rumor sebagai fakta.
        caution = bool(re.search(
            r"\b(?:hoaks|hoax|klaim|viral|rumor|"
            r"dibantah|bantahan|tidak benar|"
            r"disinformasi|cek fakta|menyesatkan|"
            r"disebut-sebut|beredar kabar)\b",
            sentence,
            re.I,
        ))

        label = "Topik terkait"

        if (
            not caution
            and relation == "sama"
            and score >= 0.79
        ):
            label = "Mendukung"

        elif (
            not caution
            and relation == "lawan"
            and score >= 0.83
        ):
            label = "Membantah"

        rank = score + (
            1 if label != "Topik terkait" else 0
        )

        if rank > best_rank:
            best_rank = rank
            best = (
                label,
                sentence[:480],
                round(float(score), 3),
            )

    return best


def resolve_google_news(candidate):
    """Mengurai link Google News menjadi URL penerbit."""
    result = dict(candidate)
    url = result.get("url", "")

    if host_name(url) != "news.google.com":
        result["status_akses"] = "URL artikel langsung"
        return result

    result["status_akses"] = (
        "Tautan Google News belum berhasil diurai"
    )

    publisher = host_name(
        result.get("asal_situs", "")
    )

    if not trusted(publisher) or gnewsdecoder is None:
        return result

    try:
        decoded = gnewsdecoder(url)

        link = (
            decoded.get("decoded_url", "")
            if (
                isinstance(decoded, dict)
                and (
                    decoded.get("status")
                    or decoded.get("success")
                )
            )
            else ""
        )

        if (
            link.startswith("https://")
            and trusted(host_name(link))
            and public_url(link)
        ):
            result["url_google_news"] = url
            result["url"] = link
            result["status_akses"] = (
                "URL penerbit berhasil ditemukan"
            )

    except Exception:
        pass

    return result


def _enrich(candidate, claim):
    """Melengkapi referensi dengan bukti artikel."""
    item = resolve_google_news(candidate)

    url = item.get("url", "")
    category = trusted(host_name(url))

    item.update({
        "kategori": (
            category
            or trusted(
                host_name(item.get("asal_situs", ""))
            )
            or "Terkait"
        ),
        "penilaian": "Topik terkait",
        "kecocokan": 0,
        "bisa_diverifikasi": False,
    })

    if not category:
        return item

    page = fetch_page(url)

    if not page:
        item["status_akses"] = (
            "Isi artikel penerbit belum berhasil dibaca"
        )
        return item

    assessment, excerpt, score = source_evidence(
        claim,
        page["teks"],
    )

    item.update({
        "url": page["url"],
        "kutipan": excerpt or item.get("kutipan", ""),
        "penilaian": assessment,
        "kecocokan": score,
        "bisa_diverifikasi": True,
        "status_akses": "Isi artikel berhasil dibaca",
    })

    return item


def search_trusted(claim, max_results=11):
    """Mencari referensi dari berbagai sumber internet."""
    claim = clean_text(claim)

    if len(claim) < 5:
        return [], []

    searches = candidate_queries(claim)
    outputs = []

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [
            pool.submit(search_feed, engine, query)
            for engine, query in searches
        ]

        for future in as_completed(futures):
            try:
                outputs.extend(future.result())
            except Exception:
                continue

    seen = set()
    unique = []

    for entry in outputs:
        url = entry.get("url", "")
        host = host_name(url)

        allowed = trusted(host)

        google_news_allowed = (
            host == "news.google.com"
            and trusted(
                host_name(
                    entry.get("asal_situs", "")
                )
            )
        )

        if not allowed and not google_news_allowed:
            continue

        key = url.split("?", 1)[0]

        if key in seen:
            continue

        seen.add(key)

        entry["skor_judul"] = claim_relation(
            claim,
            entry.get("judul", ""),
        )[0]

        unique.append(entry)

    unique.sort(
        key=lambda ref: (
            bool(trusted(host_name(ref["url"]))),
            ref["skor_judul"],
        ),
        reverse=True,
    )

    shortlist = unique[:max_results]
    indexed = {}

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_enrich, ref, claim): idx
            for idx, ref in enumerate(shortlist)
        }

        for future in as_completed(futures):
            try:
                indexed[futures[future]] = future.result()
            except Exception:
                pass

    fallback = {
        "kategori": "Terkait",
        "penilaian": "Topik terkait",
        "kecocokan": 0,
        "bisa_diverifikasi": False,
        "status_akses": "Gagal membuka referensi",
    }

    result = [
        indexed.get(i, dict(ref, **fallback))
        for i, ref in enumerate(shortlist)
    ]

    unique_result = []
    seen_url = set()

    for ref in result:
        canonical = ref["url"].split("?", 1)[0]

        if canonical not in seen_url:
            unique_result.append(ref)
            seen_url.add(canonical)

    return unique_result, [
        query for _, query in searches
    ]


def _publisher_domain(host):
    parts = host.split(".")

    if host.endswith((".go.id", ".ac.id")):
        if len(parts) >= 3:
            return ".".join(parts[-3:])

    if len(parts) >= 2:
        return ".".join(parts[-2:])

    return host


def verdict_from_sources(references):
    """Menentukan kesimpulan terbatas dari bukti artikel."""
    strong = [
        item for item in references
        if item.get("bisa_diverifikasi")
        and item.get("penilaian") in (
            "Mendukung", "Membantah"
        )
    ]

    groups = {
        "Mendukung": set(),
        "Membantah": set(),
    }

    for item in strong:
        host = host_name(item.get("url", ""))

        domain = _publisher_domain(host)

        groups[item["penilaian"]].add(domain)

    yes = groups["Mendukung"]
    no = groups["Membantah"]

    if yes and no:
        return (
            "Perlu konteks",
            "Artikel yang berhasil dibaca memberikan "
            "indikasi berbeda. Periksa isi sumber aslinya.",
        )

    official_yes = any(
        "Instansi resmi" in item.get("kategori", "")
        and item["penilaian"] == "Mendukung"
        and item.get("kecocokan", 0) >= 0.86
        for item in strong
    )

    official_no = any(
        "Instansi resmi" in item.get("kategori", "")
        and item["penilaian"] == "Membantah"
        and item.get("kecocokan", 0) >= 0.86
        for item in strong
    )

    if len(yes) >= 2 or official_yes:
        return (
            "Fakta",
            "Ada bukti yang selaras dalam artikel tepercaya "
            "yang berhasil dibaca. Tetap periksa sumber aslinya.",
        )

    if len(no) >= 2 or official_no:
        return (
            "Hoaks",
            "Ada bukti yang bertentangan dalam artikel "
            "tepercaya yang berhasil dibaca. "
            "Tetap periksa sumber aslinya.",
        )

    if strong:
        return (
            "Perlu konteks",
            "Ada satu bukti yang berkaitan, tetapi belum "
            "cukup kuat untuk kesimpulan tegas.",
        )

    return (
        "Belum ditemukan",
        "Referensi terkait ditemukan, tetapi belum ada "
        "isi artikel yang cukup jelas sebagai bukti.",
    )
