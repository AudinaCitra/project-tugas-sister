
# SiPiket — Tugas 1 Sistem Terdistribusi

## Deskripsi Aplikasi
SiPiket adalah aplikasi web untuk mengatur jadwal piket petugas kampus serta mencatat laporan kerusakan fasilitas.

Aplikasi ini menerapkan konsep sistem terdistribusi dengan dua aplikasi terpisah, yaitu Front End dan Back End, yang saling berkomunikasi melalui REST API.

## Teknologi yang Digunakan
- Python Flask
- HTML, CSS, JavaScript
- SQLite
- REST API
- JSON

## Struktur Folder

tugas1/
- backend/
  - app.py
  - requirements.txt
  - jadwal.db
- frontend/
  - server.py
  - requirements.txt
  - static/
    - index.html
    - style.css
    - app.js

## Cara Instalasi

Pastikan Python dan Visual Studio Code sudah terinstal.

Buka folder tugas1 di VS Code, kemudian buka dua terminal.

### 1. Terminal Back End

Masuk ke folder backend:

```powershell
cd backend
```

Install library:

```powershell
python -m pip install -r requirements.txt
```

Jalankan server:

```powershell
python app.py
```

Back End berjalan di:
http://127.0.0.1:5000

### 2. Terminal Front End

Buka terminal baru dari folder tugas1.

Masuk ke folder frontend:

```powershell
cd frontend
```

Install library:

```powershell
python -m pip install -r requirements.txt
```

Jalankan server:

```powershell
python server.py
```

Front End berjalan di:
http://127.0.0.1:8000

Kedua server harus berjalan secara bersamaan.

## Akun Login

### Admin
- Role: Admin
- Password: admin123

Cara login:
1. Pilih Admin.
2. Masukkan password.
3. Klik Masuk.

### Petugas
- Role: Petugas
- Password: petugas123

Cara login:
1. Pilih Petugas.
2. Pilih nama petugas.
3. Masukkan password.
4. Klik Masuk.

Catatan: Semua petugas menggunakan password yang sama untuk keperluan demonstrasi aplikasi.

## Fitur Aplikasi
1. Login Admin dan Petugas.
2. Dashboard informasi piket.
3. Pengelolaan data petugas.
4. Pembuatan jadwal piket otomatis.
5. Pembagian shift Pagi, Siang, dan Malam.
6. Pengelolaan cuti dan izin.
7. Statistik pembagian tugas.
8. Laporan kerusakan fasilitas kampus.
9. Pembaruan status perbaikan.
10. Logout pengguna.

## Alur Kerja Sistem

1. Pengguna membuka aplikasi melalui Front End pada port 8000.
2. Front End mengirim permintaan data ke Back End melalui REST API.
3. Back End menerima permintaan dan memproses data.
4. Data disimpan dan diambil dari database SQLite.
5. Back End mengirim respons JSON ke Front End.
6. Hasil ditampilkan pada dashboard pengguna.

## Kesimpulan

SiPiket menggabungkan sistem penjadwalan piket dan pengelolaan laporan kerusakan fasilitas kampus dalam satu aplikasi web.

Aplikasi ini memenuhi konsep Tugas 1 Sistem Terdistribusi karena menggunakan dua aplikasi yang berjalan pada port berbeda dan saling terhubung melalui REST API.

## Catatan

Aplikasi dibuat untuk kebutuhan pembelajaran dan demonstrasi Tugas 1 Sistem Terdistribusi.

Password bawaan hanya untuk pengujian lokal dan sebaiknya diganti jika aplikasi dipublikasikan.
