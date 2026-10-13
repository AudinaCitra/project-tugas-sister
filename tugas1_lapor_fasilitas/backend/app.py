"""
TUGAS 1 - APLIKASI A: BACK END (REST API) LAPOR FASILITAS RUSAK
Jalankan : python app.py            -> http://127.0.0.1:5000
Opsional : PETUGAS_PIN=rahasia HOST=0.0.0.0 python app.py   (HOST=0.0.0.0 agar bisa diakses laptop lain)
"""
import os
import sqlite3

from flask import Flask, jsonify, request
from flask_cors import CORS

DB = "laporan.db"
PETUGAS_PIN = os.getenv("PETUGAS_PIN", "petugas123")
KATEGORI = ["Listrik", "Air", "AC / Kipas", "Kebersihan", "Furnitur", "Lainnya"]
PRIORITAS = ["Rendah", "Sedang", "Tinggi"]
STATUS = ["Baru", "Diproses", "Selesai"]

app = Flask(__name__)
CORS(app)  # izinkan Aplikasi B (front end) memanggil API ini


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS laporan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pelapor TEXT NOT NULL,
            lokasi TEXT NOT NULL,
            kategori TEXT NOT NULL,
            prioritas TEXT NOT NULL,
            deskripsi TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Baru',
            dibuat TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            selesai_pada TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS riwayat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            laporan_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            catatan TEXT,
            waktu TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (laporan_id) REFERENCES laporan(id) ON DELETE CASCADE)""")


def butuh_petugas():
    """Kembalikan response error jika PIN petugas salah, atau None jika benar."""
    if request.headers.get("X-Petugas-Pin", "") != PETUGAS_PIN:
        return jsonify(error="PIN petugas salah atau belum diisi"), 401
    return None


# ---------- PENGHUNI ----------
@app.post("/laporan")
def buat_laporan():
    d = request.get_json(silent=True) or {}
    pelapor = str(d.get("pelapor", "")).strip()
    lokasi = str(d.get("lokasi", "")).strip()
    deskripsi = str(d.get("deskripsi", "")).strip()
    kategori = d.get("kategori", "")
    prioritas = d.get("prioritas", "Sedang")

    if not pelapor or not lokasi or len(deskripsi) < 5:
        return jsonify(error="Nama, lokasi, dan deskripsi (minimal 5 karakter) wajib diisi"), 400
    if kategori not in KATEGORI:
        return jsonify(error=f"Kategori harus salah satu dari: {', '.join(KATEGORI)}"), 400
    if prioritas not in PRIORITAS:
        return jsonify(error=f"Prioritas harus salah satu dari: {', '.join(PRIORITAS)}"), 400

    with db() as c:
        cur = c.execute(
            "INSERT INTO laporan (pelapor, lokasi, kategori, prioritas, deskripsi) VALUES (?,?,?,?,?)",
            (pelapor[:60], lokasi[:80], kategori, prioritas, deskripsi[:500]))
        c.execute("INSERT INTO riwayat (laporan_id, status, catatan) VALUES (?,?,?)",
                  (cur.lastrowid, "Baru", "Laporan dibuat"))
    return jsonify(id=cur.lastrowid, pesan="Laporan terkirim"), 201


@app.get("/laporan")
def daftar_laporan():
    status = request.args.get("status", "")
    kategori = request.args.get("kategori", "")
    sql, params = "SELECT * FROM laporan WHERE 1=1", []
    if status:
        sql += " AND status = ?"; params.append(status)
    if kategori:
        sql += " AND kategori = ?"; params.append(kategori)
    # Urut: prioritas tinggi dulu, lalu yang terbaru
    sql += """ ORDER BY CASE prioritas WHEN 'Tinggi' THEN 0 WHEN 'Sedang' THEN 1 ELSE 2 END, id DESC"""
    rows = db().execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/laporan/<int:laporan_id>")
def detail_laporan(laporan_id):
    conn = db()
    lap = conn.execute("SELECT * FROM laporan WHERE id = ?", (laporan_id,)).fetchone()
    if not lap:
        return jsonify(error="Laporan tidak ditemukan"), 404
    riwayat = conn.execute(
        "SELECT status, catatan, waktu FROM riwayat WHERE laporan_id = ? ORDER BY id", (laporan_id,)).fetchall()
    return jsonify(**dict(lap), riwayat=[dict(r) for r in riwayat])


@app.get("/statistik")
def statistik():
    conn = db()
    total = conn.execute("SELECT COUNT(*) FROM laporan").fetchone()[0]
    per_status = {s: 0 for s in STATUS}
    for r in conn.execute("SELECT status, COUNT(*) n FROM laporan GROUP BY status"):
        per_status[r["status"]] = r["n"]
    per_kategori = {r["kategori"]: r["n"] for r in
                    conn.execute("SELECT kategori, COUNT(*) n FROM laporan GROUP BY kategori ORDER BY n DESC")}
    rata = conn.execute("""SELECT AVG((julianday(selesai_pada) - julianday(dibuat)) * 24)
                           FROM laporan WHERE selesai_pada IS NOT NULL""").fetchone()[0]
    return jsonify(total=total, per_status=per_status, per_kategori=per_kategori,
                   rata_jam_selesai=round(rata, 1) if rata is not None else None)


@app.get("/opsi")
def opsi():
    return jsonify(kategori=KATEGORI, prioritas=PRIORITAS, status=STATUS)


# ---------- PETUGAS (butuh header X-Petugas-Pin) ----------
@app.get("/petugas/cek")
def cek_petugas():
    return butuh_petugas() or jsonify(pesan="PIN benar")


@app.patch("/laporan/<int:laporan_id>/status")
def ubah_status(laporan_id):
    err = butuh_petugas()
    if err:
        return err
    d = request.get_json(silent=True) or {}
    status = d.get("status", "")
    catatan = str(d.get("catatan", "")).strip()[:200]
    if status not in STATUS:
        return jsonify(error=f"Status harus salah satu dari: {', '.join(STATUS)}"), 400

    conn = db()
    if not conn.execute("SELECT 1 FROM laporan WHERE id = ?", (laporan_id,)).fetchone():
        return jsonify(error="Laporan tidak ditemukan"), 404
    selesai = "CURRENT_TIMESTAMP" if status == "Selesai" else "NULL"
    conn.execute(f"UPDATE laporan SET status = ?, selesai_pada = {selesai} WHERE id = ?", (status, laporan_id))
    conn.execute("INSERT INTO riwayat (laporan_id, status, catatan) VALUES (?,?,?)",
                 (laporan_id, status, catatan or f"Status diubah menjadi {status}"))
    conn.commit()
    return jsonify(pesan="Status diperbarui")


@app.delete("/laporan/<int:laporan_id>")
def hapus_laporan(laporan_id):
    err = butuh_petugas()
    if err:
        return err
    with db() as c:
        cur = c.execute("DELETE FROM laporan WHERE id = ?", (laporan_id,))
    if cur.rowcount == 0:
        return jsonify(error="Laporan tidak ditemukan"), 404
    return jsonify(pesan="Laporan dihapus")


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host=os.getenv("HOST", "127.0.0.1"), port=5000)
