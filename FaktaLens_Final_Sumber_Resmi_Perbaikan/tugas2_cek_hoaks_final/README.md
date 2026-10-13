# FaktaLens — Cek Fakta Multi-Input

Aplikasi web berbasis Python Flask, SQLite, HTML, CSS, JavaScript, OCR di browser, dan **Google Fact Check Tools API**. Versi ini menambahkan logika penilaian sumber terpisah di `verifikasi.py` dan referensi Wikipedia untuk fakta sejarah sederhana.

## Menjalankan

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Isi `GOOGLE_FACTCHECK_API_KEY` di `.env` terlebih dahulu. Buka <http://127.0.0.1:5001>.

## Kegunaan file

- `app.py`: REST API, integrasi Google, penyimpanan riwayat SQLite, analisis tautan
- `verifikasi.py`: normalisasi OCR, variasi kata kunci, penilaian kesesuaian, klasifikasi rating, dan referensi Wikipedia
- `static/index.html`: struktur halaman dashboard
- `static/app.js`: komunikasi browser dengan API, OCR, hasil, riwayat
- `static/style.css`: tampilan dashboard
- `test_app.py` dan `test_verifikasi.py`: pengujian
- `ukur_akurasi.py`: evaluasi dengan contoh berlabel, bukan persentase yang direkayasa

## Status

**Hoaks**, **Fakta**, **Perlu konteks**, **Belum ditemukan**. Putusan bukan jaminan kebenaran. Penilaian sumber, kemiripan teks, dan referensi tambahan perlu diperiksa oleh pengguna. Tidak adanya hasil bukan bukti berita benar.

Lihat `PANDUAN_VERSI_FINAL.txt` untuk langkah pembaruan dari folder lama.
