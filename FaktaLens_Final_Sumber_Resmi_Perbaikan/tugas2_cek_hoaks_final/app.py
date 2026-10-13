import hashlib
import ipaddress
import json
import os
import re
import socket
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from verifikasi import clean_text, keyword_variants, relevance, assess
from sumber_resmi import verifikasi_resmi

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))
DB = os.getenv("DB_PATH", os.path.join(BASE, "riwayat.db"))
GOOGLE_KEY = os.getenv("GOOGLE_FACTCHECK_API_KEY", "").strip()
GOOGLE_API = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
GOOGLE_IMAGE_API = "https://factchecktools.googleapis.com/v1alpha1/claims:imageSearch"
NEWS_RSS = "https://news.google.com/rss/search"
TIMEOUT = 12
app = Flask(__name__, static_folder="static")


class ApiError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


@app.errorhandler(ApiError)
def api_error(err):
    return jsonify(error=err.message), err.status


def connection():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS riwayat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teks TEXT NOT NULL,
            kesimpulan TEXT,
            jumlah_hasil INTEGER DEFAULT 0,
            waktu TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(riwayat)")}
        for name, definition in {
            "jenis": "TEXT DEFAULT 'teks'",
            "tautan": "TEXT DEFAULT ''",
            "detail": "TEXT DEFAULT '{}'",
        }.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE riwayat ADD COLUMN {name} {definition}")
        conn.execute("""CREATE TABLE IF NOT EXISTS cache (
            kunci TEXT PRIMARY KEY,
            hasil TEXT NOT NULL,
            waktu TEXT DEFAULT CURRENT_TIMESTAMP
        )""")


def is_public_url(value):
    try:
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username:
            return False
        host = parsed.hostname.lower().rstrip(".")
        if host in ("localhost", "localhost.localdomain") or host.endswith(".local"):
            return False
        addresses = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        return bool(addresses) and all(
            ipaddress.ip_address(info[4][0]).is_global for info in addresses
        )
    except (ValueError, OSError, TypeError):
        return False


def fetch_public(url, *, max_bytes=280000):
    current = url
    for _ in range(4):
        if not is_public_url(current):
            raise ApiError("Tautan tidak valid atau alamat tidak diizinkan.")
        try:
            with requests.get(current, timeout=8, stream=True, allow_redirects=False,
                              headers={"User-Agent": "Mozilla/5.0 (compatible; HoaxChecker/1.0)"}) as res:
                if res.status_code in (301, 302, 303, 307, 308):
                    from urllib.parse import urljoin
                    current = urljoin(current, res.headers.get("Location", ""))
                    continue
                res.raise_for_status()
                chunks, total = [], 0
                for chunk in res.iter_content(16384):
                    total += len(chunk)
                    if total > max_bytes:
                        break
                    chunks.append(chunk)
                return b"".join(chunks), res.url
        except requests.RequestException as exc:
            raise ApiError("Tidak dapat mengambil judul tautan. Coba isi judul/klaim secara manual.", 502) from exc
    raise ApiError("Terlalu banyak pengalihan tautan.")


def link_context(url):
    if not is_public_url(url):
        raise ApiError("Masukkan URL publik dengan awalan https://")
    host = urlparse(url).hostname.lower()
    video = host in ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be")
    if video:
        try:
            response = requests.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"}, timeout=8)
            response.raise_for_status()
            data = response.json()
            return {"judul": data.get("title", ""), "situs": "YouTube",
                    "gambar": data.get("thumbnail_url", ""), "url": url, "jenis": "video"}
        except (requests.RequestException, ValueError):
            return {"judul": "", "situs": "YouTube", "gambar": "", "url": url, "jenis": "video"}
    page, final_url = fetch_public(url)
    soup = BeautifulSoup(page, "html.parser")
    title_tag = soup.find("meta", attrs={"property": "og:title"})
    description_tag = soup.find("meta", attrs={"property": "og:description"})
    image_tag = soup.find("meta", attrs={"property": "og:image"})
    title = (title_tag.get("content") if title_tag else None) or (soup.title.get_text(" ", strip=True) if soup.title else "")
    description = description_tag.get("content", "") if description_tag else ""
    image = image_tag.get("content", "") if image_tag else ""
    if image and not urlparse(image).scheme:
        from urllib.parse import urljoin
        image = urljoin(final_url, image)
    if image and not image.startswith("https://"):
        image = ""
    return {"judul": str(title)[:240], "deskripsi": str(description)[:300],
            "situs": host.replace("www.", ""), "gambar": image, "url": url, "jenis": "artikel"}


def google_request(endpoint, params):
    try:
        response = requests.get(endpoint, params={**params, "key": GOOGLE_KEY}, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else 0
        if code in (400, 401, 403):
            raise ApiError("API Key ditolak. Pastikan Fact Check Tools API aktif dan key benar.", 502) from exc
        if code == 429:
            raise ApiError("Kuota Google Fact Check sedang habis. Coba lagi nanti.", 502) from exc
        raise ApiError("Google Fact Check sedang mengalami gangguan.", 502) from exc
    except (requests.RequestException, ValueError) as exc:
        raise ApiError("Gagal menghubungi Google Fact Check. Periksa koneksi internet.", 502) from exc


def clean_reviews(claims):
    results, seen = [], set()
    for claim in claims:
        for review in claim.get("claimReview", []):
            link = review.get("url", "")
            publisher = review.get("publisher") or {}
            item = {"klaim": claim.get("text", ""), "rating": review.get("textualRating", ""),
                    "judul": review.get("title") or claim.get("text", ""),
                    "penerbit": publisher.get("name", "Pemeriksa fakta"),
                    "url": link, "tanggal": review.get("reviewDate", "")[:10]}
            key = (str(item["klaim"]).lower(), str(item["penerbit"]).lower(), link)
            if key not in seen and link.startswith(("https://", "http://")):
                seen.add(key)
                results.append(item)
    return results[:12]


def factcheck_text(query):
    base = {"query": " ".join(query.split())[:220], "pageSize": 10}
    initial = google_request(GOOGLE_API, {**base, "languageCode": "id"})
    claims = initial.get("claims", [])
    if not claims:
        claims = google_request(GOOGLE_API, base).get("claims", [])
    return clean_reviews(claims)


def bersihkan_ocr(teks):
    return clean_text(teks)


def variasi_kata_kunci(teks, maks=5):
    return keyword_variants(teks, maks)


def kemiripan(teks_asli, ulasan):
    return relevance(teks_asli, ulasan.get("klaim") or ulasan.get("judul") or "")


def kumpulkan_ulasan(queries, teks_asli, maksimum=10):
    ditemukan, sudah, dicoba = [], set(), []
    for query in queries[:5]:
        dicoba.append(query)
        for ulasan in factcheck_text(query):
            url = ulasan.get("url", "")
            if url in sudah:
                continue
            skor = kemiripan(teks_asli, ulasan)
            if skor < .44:
                continue
            ditemukan.append({**ulasan, "relevansi": skor, "kata_kunci": query})
            sudah.add(url)
        kuat = [item for item in ditemukan if item["relevansi"] >= .66]
        if len(kuat) >= 3:
            break
    ditemukan.sort(key=lambda x: x["relevansi"], reverse=True)
    return ditemukan[:maksimum], dicoba


def factcheck_image(image_url):
    data = google_request(GOOGLE_IMAGE_API, {"imageUri": image_url, "pageSize": 10})
    return clean_reviews([result.get("claim", {}) for result in data.get("results", [])])


def verdict(results):
    return assess(results)[0]


def related_news(query):
    try:
        resp = requests.get(NEWS_RSS, params={"q": " ".join(query.split()[:10]), "hl": "id", "gl": "ID", "ceid": "ID:id"}, timeout=6)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall("./channel/item")[:5]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            source = item.find("source")
            items.append({"judul": title, "url": link, "situs": source.text if source is not None else "Google News"})
        return items
    except (requests.RequestException, ET.ParseError):
        return []


def summary(status, count, reason="", official=False):
    if official:
        return f"{reason} Bukti ini dikurasi dari dua situs pemerintah untuk klaim sejarah yang spesifik, bukan verifikasi otomatis untuk seluruh berita."
    if not count:
        return "Belum ditemukan ulasan cek fakta yang cukup sesuai. Ini tidak berarti klaim benar atau salah. Periksa referensi tambahan dan konteksnya."
    return f"Ditemukan {count} ulasan terkait. {reason} Buka artikel aslinya untuk meninjau konteks dan tanggal.".strip()


@app.get("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/status")
def status():
    return jsonify(google_aktif=bool(GOOGLE_KEY) and "isi_api_key" not in GOOGLE_KEY,
                   layanan="Google Fact Check Tools API", mode="lokal")


@app.post("/api/cek")
def check():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Data harus berupa JSON.")
    kind = str(data.get("jenis", "teks")).lower()
    if kind not in ("teks", "gambar", "tautan"):
        raise ApiError("Jenis pemeriksaan tidak dikenal.")
    text = str(data.get("teks") or "").strip()
    url = str(data.get("url") or "").strip()
    image_url = str(data.get("image_url") or "").strip()
    if len(text) > 3500:
        raise ApiError("Teks maksimal 3500 karakter.")
    if kind == "tautan" and not url:
        raise ApiError("Masukkan tautan berita atau YouTube.")
    if kind == "gambar" and image_url and not is_public_url(image_url):
        raise ApiError("URL gambar harus publik dan menggunakan HTTPS atau HTTP.")
    if len(text) < 5 and kind != "tautan" and not image_url:
        raise ApiError("Masukkan setidaknya 5 karakter teks.")
    if not GOOGLE_KEY or "isi_api_key" in GOOGLE_KEY:
        raise ApiError("Masukkan GOOGLE_FACTCHECK_API_KEY ke file .env terlebih dahulu.", 503)

    key = hashlib.sha256(json.dumps(["faktalens-v7-sumber-resmi", kind, text.lower(), url, image_url], ensure_ascii=False).encode()).hexdigest()
    with connection() as conn:
        cached = conn.execute("SELECT hasil FROM cache WHERE kunci=? AND waktu > datetime('now','-1 day')", (key,)).fetchone()
        if cached:
            previous = json.loads(cached["hasil"])
            if not isinstance(previous, dict):
                cached = None
        if cached:
            result = previous
            result["dari_cache"] = True
        else:
            preview = None
            query = text
            if kind == "tautan":
                try:
                    preview = link_context(url)
                except ApiError:
                    if not text:
                        raise
                    preview = {"judul": "", "situs": urlparse(url).hostname or "Tautan", "url": url, "gambar": ""}
                query = " ".join([preview.get("judul", ""), text]).strip()
                if len(query) < 5:
                    raise ApiError("Judul tautan tidak dapat dibaca. Tambahkan isi klaim pada kolom keterangan.")
            query = bersihkan_ocr(query)
            pencarian = variasi_kata_kunci(query)
            if kind == 'gambar' and image_url and not query:
                pencarian = []
            results, hasil_pencarian = kumpulkan_ulasan(pencarian, query) if pencarian else ([], [])
            kata_kunci_terpakai = hasil_pencarian[0] if hasil_pencarian else query
            if results:
                kata_kunci_terpakai = results[0]['kata_kunci']
            if kind == 'gambar' and image_url:
                image_results = factcheck_image(image_url)
                urls = {r['url'] for r in results}
                for item in image_results:
                    if item['url'] not in urls:
                        # Google mencocokkan URL gambar publik secara langsung.
                        results.append({**item, 'relevansi': 1, 'kata_kunci': 'Pencarian gambar publik'})
                        urls.add(item['url'])
                results = results[:12]
            conclusion, reason = assess(results)
            references, verified_official = ([], False)
            if conclusion == 'Belum ditemukan' and query and kind == 'teks':
                proof = verifikasi_resmi(query)
                if proof:
                    conclusion, reason, references = proof
                    verified_official = True
            articles = related_news(kata_kunci_terpakai) if len(kata_kunci_terpakai) >= 5 else []
            result = {
                "jenis": kind, "kueri": query, "kesimpulan": conclusion, "hasil": results,
                "label_penjelasan": "Kesimpulan didasarkan pada kecocokan klaim dan penilaian sumber; bukan kepastian 100%.",
                "alasan": reason, "referensi": references, "sumber_verifikasi": "Referensi resmi terkurasi Kemdikbud" if verified_official else "Google Fact Check",
                "kata_kunci_dicoba": hasil_pencarian,
                "kata_kunci_terpakai": kata_kunci_terpakai,
                "jumlah_hasil": len(results), "ringkasan": summary(conclusion, len(results), reason, verified_official),
                "berita_terkait": articles, "tautan_asli": preview,
                "tautan_youtube": "https://www.youtube.com/results?search_query=" + quote(kata_kunci_terpakai[:150]),
                "tautan_berita": "https://news.google.com/search?q=" + quote(kata_kunci_terpakai[:150]),
                "tautan_google": "https://www.google.com/search?q=" + quote(kata_kunci_terpakai[:150]),
                "tanggal": datetime.now().isoformat(timespec="seconds"), "dari_cache": False,
            }
            conn.execute("INSERT OR REPLACE INTO cache(kunci, hasil, waktu) VALUES (?, ?, CURRENT_TIMESTAMP)",
                         (key, json.dumps(result, ensure_ascii=False)))
        conn.execute("INSERT INTO riwayat(teks, kesimpulan, jumlah_hasil, jenis, tautan, detail) VALUES (?, ?, ?, ?, ?, ?)",
                     ((result.get("kueri") or text or url)[:400], result["kesimpulan"], result["jumlah_hasil"],
                      kind, url or image_url, json.dumps(result, ensure_ascii=False)))
        result["id"] = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return jsonify(result)


@app.get("/api/riwayat")
def history():
    with connection() as conn:
        records = conn.execute("""SELECT id, teks, jenis, kesimpulan, jumlah_hasil, waktu, tautan
                                  FROM riwayat ORDER BY id DESC LIMIT 30""").fetchall()
    return jsonify([dict(row) for row in records])


@app.get("/api/riwayat/<int:item_id>")
def history_detail(item_id):
    with connection() as conn:
        row = conn.execute("SELECT * FROM riwayat WHERE id=?", (item_id,)).fetchone()
    if not row:
        raise ApiError("Riwayat tidak ditemukan.", 404)
    detail = json.loads(row["detail"] or "{}")
    if not detail:
        detail = {"jenis": row["jenis"], "kueri": row["teks"], "kesimpulan": row["kesimpulan"],
                  "jumlah_hasil": row["jumlah_hasil"], "hasil": [], "berita_terkait": [],
                  "ringkasan": "Data lama: hanya ringkasan pemeriksaan yang tersimpan."}
    return jsonify({**detail, "id": row["id"]})


@app.delete("/api/riwayat")
def delete_history():
    with connection() as conn:
        conn.execute("DELETE FROM riwayat")
    return jsonify(pesan="Riwayat berhasil dihapus")


@app.get("/api/statistik")
def stats():
    with connection() as conn:
        rows = conn.execute("""SELECT jenis, COUNT(*) AS jumlah FROM riwayat GROUP BY jenis""").fetchall()
        total = conn.execute("SELECT COUNT(*) FROM riwayat").fetchone()[0]
        disputed = conn.execute("SELECT COUNT(*) FROM riwayat WHERE kesimpulan='Hoaks'").fetchone()[0]
        reviewed = conn.execute("SELECT COUNT(*) FROM riwayat WHERE jumlah_hasil > 0").fetchone()[0]
    return jsonify(total=total, kemungkinan_hoaks=disputed, ada_sumber=reviewed,
                   per_jenis={row["jenis"]: row["jumlah"] for row in rows})


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=os.getenv("FLASK_DEBUG") == "1")
