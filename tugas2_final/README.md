# FaktaLens — Tugas 2 Sistem Terdistribusi

Aplikasi web pemeriksa klaim berita berbasis **Python Flask** yang menggunakan **Google Fact Check Tools API** melalui internet dan melakukan pencarian **dinamis** ke situs berita/lembaga terpercaya. Dibuat untuk Tugas 2 Sistem Terdistribusi.

> Tidak ada aturan yang mengunci kalimat tertentu (misalnya proklamasi) atau daftar tautan artikel yang menentukan benar/salah. Setiap pemeriksaan memerlukan penelusuran sumber saat dijalankan. Hasil tidak dapat dijamin akurat 90–100% atau selalu mengeluarkan Fakta/Hoaks.

## 1. Fitur

- Cek klaim **teks**, **gambar/screenshot** (OCR Tesseract.js), **link berita atau YouTube** (judul artikel/video).
- **Google Fact Check Tools API**: mengambil klaim, nama penerbit, rating asli, tanggal, dan URL ulasan.
- Otomatis mencoba beberapa **variasi kata kunci** untuk meningkatkan cakupan pencarian.
- Menghindari salah memaknai klaim yang memakai kata **tidak**, **palsu vs asli**, angka atau tanggal berbeda; skor teks bukan tingkat kebenaran.
- Pencarian referensi **dinamis** dari sumber berita dan lembaga melalui **Bing RSS** dan **Google News RSS**. Saat situs memungkinkan dibaca, program menampilkan cuplikan isi yang paling sesuai. Situs resmi (*.go.id, *.ac.id) serta media/pemeriksa fakta (contohnya Kompas, Tempo, Antara) diprioritaskan pada hasil pencarian.
- Kesimpulan: **Hoaks**, **Fakta**, **Perlu konteks**, atau **Belum ditemukan**.
- Riwayat pemeriksaan SQLite, hasil terkait, dan simpan PDF via fungsi cetak browser.

## 2. Persyaratan

- Python 3.10 atau lebih baru
- Internet untuk akses Google Fact Check, RSS, situs berita, dan OCR Tesseract.js.
- API key Google Cloud dengan **Fact Check Tools API** diaktifkan.
- Browser Chrome / Edge terbaru.

## 3. Instalasi Windows melalui VS Code

Ekstrak ZIP. Buka **folder `tugas2_cek_hoaks_final`**, yakni folder yang berisi `app.py`, melalui **File → Open Folder**. Pilih **Terminal → New Terminal**.

Install library:

```powershell
python -m pip install -r requirements.txt
```

Buat file `.env` jika belum ada:

```powershell
Copy-Item .env.example .env
```

Buka file `.env` di VS Code, isi API key milik kamu:

```dotenv
GOOGLE_FACTCHECK_API_KEY=ISI_API_KEY_GOOGLE_MILIKMU
```

Jalankan:

```powershell
python app.py
```

Buka di Chrome: **http://127.0.0.1:5001**

Untuk **menguji API secara nyata**, buka **http://127.0.0.1:5001/api/koneksi**. Jika berhasil, tampil `"google_terhubung": true` (ini melakukan permintaan sungguhan ke layanan Google, bukan sekadar mengecek file `.env`).

> Kalau proyek sebelumnya sudah ada file `.env` dan `riwayat.db`, jangan diganti atau dihapus. Ketika update kode saja, **tetap gunakan `.env` lama**.

## 4. Cara kerja (untuk laporan dosen)

1. Pengguna menulis klaim atau mengunggah gambar / memasukkan URL.
2. Front End mengirim permintaan ke Flask `POST /api/cek` via HTTP/JSON.
3. Flask memanggil **Google Fact Check Tools API** memakai API key dari `.env` (server-side, tidak dikirim ke browser).
4. Flask mencari referensi berita dan instansi tepercaya secara **dinamis melalui RSS internet**. Pencarian RSS adalah layanan tambahan yang **tidak** memakai Fact Check API key.
5. Sistem membandingkan ulasan yang relevan, rating pemeriksa fakta, serta kalimat dari artikel yang bisa dibaca; sumber artikel umum ditampilkan terpisah dari ulasan Fact Check.
6. Keputusan ditampilkan dengan sumber, alasan, dan keterbatasan; hasil disimpan di SQLite.

**Penting:** `google_aktif: true` pada `/api/status` hanya menyatakan API key telah dikonfigurasi; **bukan bukti** koneksi internet berhasil. Untuk pembuktian, buka `/api/koneksi` (permintaan Google sungguhan), lalu periksa klaim dan lihat URL ulasan sumber pada hasil.

## 5. Struktur utama

```text
tugas2_cek_hoaks_final/
├─ app.py                 # Flask, API, Google Fact Check, database
├─ verifikasi.py          # Pencocokan klaim dan pembacaan rating
├─ sumber_terpercaya.py   # Pencarian RSS dinamis dan referensi sumber
├─ static/
│  ├─ index.html
│  ├─ style.css
│  └─ app.js
├─ requirements.txt
├─ .env.example           # contoh variabel, tanpa key asli
├─ .gitignore
├─ MULAI_WINDOWS.bat
└─ README.md
```

`riwayat.db` dibuat otomatis ketika aplikasi digunakan dan **tidak** disertakan ke ZIP.

## 6. Keterangan empat status

- **Hoaks:** bukti relevan menunjukkan pernyataan salah.
- **Fakta:** bukti relevan mendukung pernyataan.
- **Perlu konteks:** penilaian bercampur, sebagian benar, atau referensi cukup relevan tapi belum tegas.
- **Belum ditemukan:** belum ada bukti yang cukup; **bukan** berarti klaim otomatis benar/salah.

Tidak semua topik tercakup Google Fact Check. Contoh fakta pengetahuan umum mungkin hanya ditemukan di situs resmi/media; sebaliknya berita viral bisa baru dan belum diperiksa. Situs tertentu bisa memblokir RSS/ekstraksi, sehingga beberapa referensi hanya berisi judul/tautan. Tidak ada mesin yang dapat memeriksa *setiap* pernyataan sembarang dengan kepastian 100%.

## 7. Jika sebelumnya sudah memakai versi lama

Cara mudah: hentikan server (`Ctrl+C`), ekstrak ZIP ini dan gunakan folder baru. Pindahkan hanya file `.env` dan `riwayat.db` lama (jika riwayat ingin disimpan), lalu jalankan `python app.py`.

Cara update folder lama: ganti `app.py`, `verifikasi.py`, `static/app.js`, `static/index.html`, `static/style.css`, `requirements.txt`; **tambahkan `sumber_terpercaya.py`**. `sumber_resmi.py` lama boleh dihapus karena **tidak digunakan** lagi.

Kemudian refresh browser dengan **Ctrl+F5**.

Jika hasil lama masih tampak di menu **Riwayat**, itu data tersimpan dari pemeriksaan sebelumnya. Lakukan pencarian **baru** untuk menggunakan logika baru. Cache versi lama sengaja diabaikan oleh kode baru.

## 8. Masalah umum

- `ModuleNotFoundError`: ulangi `python -m pip install -r requirements.txt`.
- `API Key ditolak`: cek `.env`, aktifkan Fact Check Tools API di Google Cloud, pastikan kuota/pembatasan key sesuai.
- `0 ulasan Google`: mungkin klaim belum ditinjau atau tidak tercakup. Lihat referensi dinamis lain.
- `0 referensi`: layanan RSS mungkin menolak akses atau pencarian tidak menghasilkan situs terpercaya.
- `Belum ditemukan`: sistem tidak memiliki dasar yang cukup kuat, **tidak boleh memaksa hasil Hoaks/Fakta**.
- OCR butuh internet untuk mengunduh model bahasa Tesseract pertama kali; baca dan koreksi teks sebelum klik periksa.

## 9. Keamanan dan etika

- **Jangan upload `.env` atau API key asli ke GitHub atau Word.** `.gitignore` sudah mengabaikannya.
- Jangan gunakan aplikasi sebagai satu-satunya dasar keputusan penting. Periksa tanggal, konteks, dan link artikel aslinya.
- Google Fact Check menyediakan ulasan yang *sudah pernah* diperiksa; pencarian RSS adalah referensi tambahan, bukan API verifikasi kebenaran universal.
- Jika `.env` pernah terunggah ke GitHub atau dibagikan publik, **rotasi API key** di Google Cloud.
