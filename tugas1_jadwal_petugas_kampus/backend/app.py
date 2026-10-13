import hmac
import os
import sqlite3
from datetime import date, timedelta

from flask import Flask, abort, g, jsonify, request
from flask_cors import CORS
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
CORS(app)
DB = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "jadwal.db"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
PETUGAS_PASSWORD = os.getenv("PETUGAS_PASSWORD", "petugas123")
PIN = os.getenv("ADMIN_PIN", ADMIN_PASSWORD)
signer = URLSafeTimedSerializer(os.getenv("APP_SECRET") or os.urandom(32).hex())

GEDUNG = ["Gedung A & Perpustakaan", "Gedung E", "Gedung F", "Gedung G", "Gedung H", "Gedung L"]
KONDISI = ["Rusak Ringan", "Rusak Berat", "Tidak Berfungsi", "Perlu Pemeriksaan"]
STATUS = ["Dilaporkan", "Diproses", "Selesai"]
SHIFT = {"Pagi": "07:00-15:00", "Siang": "15:00-23:00", "Malam": "23:00-07:00"}
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BAGIAN = {
    "Keamanan": {"shift": ["Pagi", "Siang", "Malam"], "hari": list(range(7))},
    "Kebersihan": {"shift": ["Pagi", "Siang"], "hari": list(range(6))},
    "Perpustakaan": {"shift": ["Pagi", "Siang"], "hari": list(range(6))},
    "Laboratorium": {"shift": ["Pagi", "Siang"], "hari": list(range(5))},
    "Administrasi": {"shift": ["Pagi"], "hari": list(range(5))},
}


@app.errorhandler(HTTPException)
def tangani_error(e):
    return jsonify(error=e.description), e.code


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def tutup_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    with sqlite3.connect(DB) as c:
        c.execute("PRAGMA foreign_keys=ON")
        c.executescript("""
            CREATE TABLE IF NOT EXISTS anggota (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nama TEXT NOT NULL, bagian TEXT NOT NULL,
                maks_shift_minggu INTEGER DEFAULT 5, aktif INTEGER DEFAULT 1,
                UNIQUE(nama, bagian));
            CREATE TABLE IF NOT EXISTS cuti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anggota_id INTEGER REFERENCES anggota(id) ON DELETE CASCADE,
                tanggal TEXT NOT NULL, alasan TEXT,
                UNIQUE(anggota_id, tanggal));
            CREATE TABLE IF NOT EXISTS jadwal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT NOT NULL, shift TEXT NOT NULL,
                anggota_id INTEGER REFERENCES anggota(id) ON DELETE CASCADE,
                UNIQUE(tanggal, shift, anggota_id));
            CREATE TABLE IF NOT EXISTS laporan_kerusakan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gedung TEXT, ruang TEXT, barang TEXT, kondisi TEXT, keterangan TEXT,
                petugas_id INTEGER REFERENCES anggota(id) ON DELETE SET NULL,
                status TEXT DEFAULT 'Dilaporkan', tindakan TEXT DEFAULT '',
                dibuat_pada TEXT DEFAULT (datetime('now','localtime')),
                diperbarui_pada TEXT DEFAULT (datetime('now','localtime')));
        """)
        if not c.execute("SELECT 1 FROM anggota LIMIT 1").fetchone():
            contoh = {
                "Keamanan": ["Budi Santoso", "Agus Pratama", "Dedi Kurniawan", "Eko Wahyudi", "Rizal Fauzi", "Hendra Gunawan"],
                "Kebersihan": ["Siti Aminah", "Ratna Dewi", "Joko Susilo", "Wati Lestari"],
                "Perpustakaan": ["Lina Marlina", "Dewi Anggraini", "Fajar Nugroho"],
                "Laboratorium": ["Rudi Hartono", "Nanda Putri", "Yoga Permana"],
                "Administrasi": ["Maya Sari", "Andi Wijaya"],
            }
            c.executemany("INSERT INTO anggota(nama,bagian) VALUES (?,?)",
                          [(nama, bagian) for bagian, nama_list in contoh.items() for nama in nama_list])


def data():
    return request.get_json(silent=True) or {}


def tanggal(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        abort(400, "Format tanggal harus YYYY-MM-DD")


def angka(value, default, minimum, maksimum):
    try:
        n = int(default if value is None else value)
        if minimum <= n <= maksimum:
            return n
    except (TypeError, ValueError):
        pass
    abort(400, f"Angka harus antara {minimum} dan {maksimum}")


def periode():
    mulai = tanggal(request.args.get("mulai", (date.today() - timedelta(days=date.today().weekday())).isoformat()))
    selesai = tanggal(request.args.get("selesai", (mulai + timedelta(days=6)).isoformat()))
    if selesai < mulai or (selesai - mulai).days > 92:
        abort(400, "Rentang tanggal tidak valid")
    return mulai.isoformat(), selesai.isoformat()


def anggota_by_id(id):
    a = db().execute("SELECT * FROM anggota WHERE id=?", (id,)).fetchone()
    if not a:
        abort(404, "Petugas tidak ditemukan")
    return a


def pengguna():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        abort(401, "Silakan login terlebih dahulu")
    try:
        u = signer.loads(auth[7:], max_age=43200)
    except BadSignature:
        abort(401, "Sesi login tidak valid")
    if u.get("role") == "admin":
        return {"role": "admin", "anggota_id": None, "nama": "Administrator Kampus", "bagian": "Pengelola"}
    if u.get("role") != "petugas":
        abort(401, "Akun tidak valid")
    a = anggota_by_id(u.get("anggota_id"))
    if not a["aktif"]:
        abort(401, "Akun tidak aktif")
    return {"role": "petugas", "anggota_id": a["id"], "nama": a["nama"], "bagian": a["bagian"]}


def admin():
    if request.headers.get("Authorization", "").startswith("Bearer "):
        if pengguna()["role"] != "admin":
            abort(403, "Akses khusus admin")
    elif not hmac.compare_digest(request.headers.get("X-Admin-Pin", ""), PIN):
        abort(401, "PIN admin salah")


def boleh_jaga(a, t, shift):
    c = db()
    if not a["aktif"] or shift not in BAGIAN[a["bagian"]]["shift"] or t.weekday() not in BAGIAN[a["bagian"]]["hari"]:
        return False
    if c.execute("SELECT 1 FROM cuti WHERE anggota_id=? AND tanggal=?", (a["id"], str(t))).fetchone():
        return False
    if c.execute("SELECT 1 FROM jadwal WHERE anggota_id=? AND tanggal=?", (a["id"], str(t))).fetchone():
        return False
    senin = t - timedelta(days=t.weekday())
    total = c.execute("SELECT COUNT(*) FROM jadwal WHERE anggota_id=? AND tanggal BETWEEN ? AND ?",
                      (a["id"], str(senin), str(senin + timedelta(days=6)))).fetchone()[0]
    if total >= a["maks_shift_minggu"]:
        return False
    hari_tetangga = (t - timedelta(days=1)) if shift == "Pagi" else (t + timedelta(days=1))
    shift_tetangga = "Malam" if shift == "Pagi" else "Pagi"
    if shift in ("Pagi", "Malam") and c.execute(
        "SELECT 1 FROM jadwal WHERE anggota_id=? AND tanggal=? AND shift=?",
        (a["id"], str(hari_tetangga), shift_tetangga)).fetchone():
        return False
    return True


@app.get("/opsi")
def opsi():
    return jsonify(bagian=BAGIAN, shift=SHIFT, hari=HARI)


@app.get("/gedung")
def gedung():
    return jsonify(gedung=GEDUNG, kondisi=KONDISI, status=STATUS)


@app.post("/auth/login")
def login():
    d = data()
    role = d.get("role")
    password = str(d.get("password", ""))
    if role == "admin" and hmac.compare_digest(password, ADMIN_PASSWORD):
        u = {"role": "admin"}
    elif role == "petugas" and hmac.compare_digest(password, PETUGAS_PASSWORD):
        id = angka(d.get("anggota_id"), 0, 1, 1000000)
        if not anggota_by_id(id)["aktif"]:
            abort(403, "Petugas tidak aktif")
        u = {"role": "petugas", "anggota_id": id}
    else:
        abort(401, "Login gagal")
    token = signer.dumps(u)
    return jsonify(token=token, pengguna=info_akun(u))


def info_akun(u):
    if u["role"] == "admin":
        return {"role": "admin", "anggota_id": None, "nama": "Administrator Kampus", "bagian": "Pengelola"}
    a = anggota_by_id(u["anggota_id"])
    return {"role": "petugas", "anggota_id": a["id"], "nama": a["nama"], "bagian": a["bagian"]}


@app.get("/auth/me")
def auth_me():
    return jsonify(pengguna())


@app.get("/admin/cek")
def cek_admin():
    admin()
    return jsonify(pesan="PIN benar")


@app.get("/anggota")
def daftar_anggota():
    sql, args = "SELECT * FROM anggota WHERE 1=1", []
    if request.args.get("bagian"):
        sql += " AND bagian=?"
        args.append(request.args["bagian"])
    if request.args.get("aktif") == "1":
        sql += " AND aktif=1"
    return jsonify([dict(r) for r in db().execute(sql + " ORDER BY bagian,nama", args)])


@app.post("/anggota")
def tambah_anggota():
    admin()
    d = data()
    nama, bagian = str(d.get("nama", "")).strip(), d.get("bagian")
    if not nama or bagian not in BAGIAN:
        abort(400, "Nama dan bagian wajib diisi")
    try:
        cur = db().execute("INSERT INTO anggota(nama,bagian,maks_shift_minggu) VALUES (?,?,?)",
                           (nama, bagian, angka(d.get("maks_shift_minggu"), 5, 1, 7)))
        db().commit()
    except sqlite3.IntegrityError:
        abort(409, "Petugas sudah terdaftar")
    return jsonify(id=cur.lastrowid, pesan="Anggota ditambahkan"), 201


@app.put("/anggota/<int:id>")
def ubah_anggota(id):
    admin()
    a, d = anggota_by_id(id), data()
    nama = str(d.get("nama", a["nama"])).strip()
    bagian = d.get("bagian", a["bagian"])
    if not nama or bagian not in BAGIAN:
        abort(400, "Nama atau bagian tidak valid")
    try:
        db().execute("UPDATE anggota SET nama=?,bagian=?,aktif=?,maks_shift_minggu=? WHERE id=?",
                     (nama, bagian, int(bool(d.get("aktif", a["aktif"]))),
                      angka(d.get("maks_shift_minggu"), a["maks_shift_minggu"], 1, 7), id))
        db().commit()
    except sqlite3.IntegrityError:
        abort(409, "Petugas sudah terdaftar")
    return jsonify(pesan="Anggota diperbarui")


@app.delete("/anggota/<int:id>")
def hapus_anggota(id):
    admin()
    anggota_by_id(id)
    db().execute("DELETE FROM anggota WHERE id=?", (id,))
    db().commit()
    return jsonify(pesan="Anggota dihapus")


@app.get("/cuti")
def daftar_cuti():
    admin()
    mulai = tanggal(request.args.get("mulai", date.today().isoformat()))
    sql = """SELECT c.*, a.nama, a.bagian FROM cuti c JOIN anggota a ON a.id=c.anggota_id
             WHERE c.tanggal>=? ORDER BY c.tanggal,a.nama"""
    return jsonify([dict(r) for r in db().execute(sql, (str(mulai),))])


@app.post("/cuti")
def tambah_cuti():
    admin()
    d = data()
    anggota_by_id(d.get("anggota_id"))
    try:
        db().execute("INSERT INTO cuti(anggota_id,tanggal,alasan) VALUES (?,?,?)",
                     (d["anggota_id"], str(tanggal(d.get("tanggal"))), d.get("alasan", "")))
        db().commit()
    except sqlite3.IntegrityError:
        abort(409, "Cuti sudah tercatat")
    return jsonify(pesan="Cuti dicatat"), 201


@app.delete("/cuti/<int:id>")
def hapus_cuti(id):
    admin()
    result = db().execute("DELETE FROM cuti WHERE id=?", (id,))
    db().commit()
    if not result.rowcount:
        abort(404, "Cuti tidak ditemukan")
    return jsonify(pesan="Cuti dihapus")


@app.get("/jadwal")
def lihat_jadwal():
    mulai, selesai = periode()
    sql = """SELECT j.*, a.nama, a.bagian FROM jadwal j JOIN anggota a ON j.anggota_id=a.id
             WHERE j.tanggal BETWEEN ? AND ?"""
    args = [mulai, selesai]
    if request.args.get("bagian"):
        sql += " AND a.bagian=?"
        args.append(request.args["bagian"])
    if request.args.get("anggota_id"):
        sql += " AND j.anggota_id=?"
        args.append(request.args["anggota_id"])
    rows = db().execute(sql + " ORDER BY j.tanggal,j.shift,a.nama", args)
    return jsonify(mulai=mulai, selesai=selesai, jadwal=[dict(r) for r in rows])


@app.post("/jadwal")
def tambah_jadwal():
    admin()
    d = data()
    a, t, shift = anggota_by_id(d.get("anggota_id")), tanggal(d.get("tanggal")), d.get("shift")
    if shift not in SHIFT or not boleh_jaga(a, t, shift):
        abort(409, "Petugas tidak tersedia pada jadwal tersebut")
    cur = db().execute("INSERT INTO jadwal(tanggal,shift,anggota_id) VALUES (?,?,?)", (str(t), shift, a["id"]))
    db().commit()
    return jsonify(id=cur.lastrowid, pesan="Penugasan ditambahkan"), 201


@app.delete("/jadwal/<int:id>")
def hapus_jadwal(id):
    admin()
    cur = db().execute("DELETE FROM jadwal WHERE id=?", (id,))
    db().commit()
    if not cur.rowcount:
        abort(404, "Jadwal tidak ditemukan")
    return jsonify(pesan="Penugasan dihapus")


@app.delete("/jadwal")
def hapus_jadwal_bagian():
    admin()
    mulai, selesai = periode()
    bagian = request.args.get("bagian")
    if bagian not in BAGIAN:
        abort(400, "Bagian tidak valid")
    result = db().execute("""DELETE FROM jadwal WHERE tanggal BETWEEN ? AND ?
                             AND anggota_id IN (SELECT id FROM anggota WHERE bagian=?)""", (mulai, selesai, bagian))
    db().commit()
    return jsonify(pesan=f"{result.rowcount} penugasan dihapus")


@app.post("/jadwal/generate")
def generate_jadwal():
    admin()
    d = data()
    bagian, mulai = d.get("bagian"), tanggal(d.get("mulai"))
    if bagian not in BAGIAN:
        abort(400, "Bagian tidak valid")
    hari = angka(d.get("hari"), 7, 1, 31)
    per_shift = angka(d.get("per_shift"), 1, 1, 5)
    selesai = mulai + timedelta(days=hari - 1)
    c = db()
    daftar = c.execute("SELECT * FROM anggota WHERE bagian=? AND aktif=1", (bagian,)).fetchall()
    if not daftar:
        abort(400, "Belum ada petugas aktif")
    c.execute("""DELETE FROM jadwal WHERE tanggal BETWEEN ? AND ?
                 AND anggota_id IN (SELECT id FROM anggota WHERE bagian=?)""", (str(mulai), str(selesai), bagian))
    dibuat, kurang = 0, []
    for i in range(hari):
        t = mulai + timedelta(days=i)
        if t.weekday() not in BAGIAN[bagian]["hari"]:
            continue
        for shift in [s for s in ("Malam", "Siang", "Pagi") if s in BAGIAN[bagian]["shift"]]:
            kandidat = [a for a in daftar if boleh_jaga(a, t, shift)]
            def nilai(a):
                r = c.execute("""SELECT COUNT(*) AS total, SUM(shift=?) AS sejenis,
                                MAX(tanggal) AS terakhir FROM jadwal WHERE anggota_id=?""",
                              (shift, a["id"])).fetchone()
                return (r["total"], r["sejenis"] or 0, r["terakhir"] or "", a["id"])
            kandidat.sort(key=nilai)
            for a in kandidat[:per_shift]:
                c.execute("INSERT INTO jadwal(tanggal,shift,anggota_id) VALUES (?,?,?)", (str(t), shift, a["id"]))
                dibuat += 1
            if len(kandidat) < per_shift:
                kurang.append({"tanggal": str(t), "hari": HARI[t.weekday()], "shift": shift,
                               "kurang": per_shift - len(kandidat)})
    c.commit()
    return jsonify(pesan=f"Jadwal {bagian} dibuat: {dibuat} penugasan", dibuat=dibuat,
                   mulai=str(mulai), selesai=str(selesai), belum_terisi=kurang), 201


@app.get("/statistik")
def statistik():
    mulai, selesai = periode()
    sql = """SELECT a.id,a.nama,a.bagian,a.maks_shift_minggu,COUNT(j.id) total,
             COALESCE(SUM(j.shift='Pagi'),0) pagi,COALESCE(SUM(j.shift='Siang'),0) siang,
             COALESCE(SUM(j.shift='Malam'),0) malam FROM anggota a
             LEFT JOIN jadwal j ON a.id=j.anggota_id AND j.tanggal BETWEEN ? AND ?
             WHERE a.aktif=1"""
    args = [mulai, selesai]
    if request.args.get("bagian"):
        sql += " AND a.bagian=?"
        args.append(request.args["bagian"])
    rows = [dict(r) for r in db().execute(sql + " GROUP BY a.id ORDER BY a.bagian,a.nama", args)]
    return jsonify(mulai=mulai, selesai=selesai, anggota=rows,
                   total_anggota=len(rows), total_penugasan=sum(r["total"] for r in rows))


def laporan_by_id(id):
    row = db().execute("SELECT * FROM laporan_kerusakan WHERE id=?", (id,)).fetchone()
    if not row:
        abort(404, "Laporan tidak ditemukan")
    return row


def isi_laporan(d, lama=None):
    v = {k: str(d.get(k, lama[k] if lama else "")).strip() for k in
         ("gedung", "ruang", "barang", "kondisi", "keterangan")}
    if v["gedung"] not in GEDUNG or v["kondisi"] not in KONDISI or not v["ruang"] or not v["barang"]:
        abort(400, "Data laporan belum lengkap")
    petugas_id = d.get("petugas_id", lama["petugas_id"] if lama else None)
    if petugas_id in ("", 0):
        petugas_id = None
    if petugas_id is not None and not anggota_by_id(petugas_id)["aktif"]:
        abort(400, "Petugas tidak aktif")
    return (v["gedung"], v["ruang"], v["barang"], v["kondisi"], v["keterangan"], petugas_id)


@app.get("/laporan")
def daftar_laporan():
    u = pengguna()
    sql = """SELECT l.*,a.nama nama_petugas,a.bagian bagian_petugas FROM laporan_kerusakan l
             LEFT JOIN anggota a ON a.id=l.petugas_id WHERE 1=1"""
    args = []
    if u["role"] == "petugas":
        sql += " AND l.petugas_id=?"
        args.append(u["anggota_id"])
    if request.args.get("gedung") in GEDUNG:
        sql += " AND l.gedung=?"
        args.append(request.args["gedung"])
    if request.args.get("status") in STATUS:
        sql += " AND l.status=?"
        args.append(request.args["status"])
    return jsonify([dict(r) for r in db().execute(sql + " ORDER BY l.id DESC", args)])


@app.post("/laporan")
def tambah_laporan():
    admin()
    vals = isi_laporan(data())
    cur = db().execute("""INSERT INTO laporan_kerusakan
        (gedung,ruang,barang,kondisi,keterangan,petugas_id) VALUES (?,?,?,?,?,?)""", vals)
    db().commit()
    return jsonify(id=cur.lastrowid, pesan="Laporan dibuat"), 201


@app.put("/laporan/<int:id>")
def ubah_laporan(id):
    admin()
    vals = isi_laporan(data(), laporan_by_id(id))
    db().execute("""UPDATE laporan_kerusakan SET gedung=?,ruang=?,barang=?,kondisi=?,keterangan=?,
                    petugas_id=?,diperbarui_pada=datetime('now','localtime') WHERE id=?""", (*vals, id))
    db().commit()
    return jsonify(pesan="Laporan diperbarui")


@app.patch("/laporan/<int:id>/status")
def ubah_status(id):
    u, lama, d = pengguna(), laporan_by_id(id), data()
    if u["role"] == "petugas" and lama["petugas_id"] != u["anggota_id"]:
        abort(403, "Bukan tugas kamu")
    status = d.get("status")
    if status not in STATUS:
        abort(400, "Status tidak valid")
    if u["role"] == "petugas" and STATUS.index(status) not in (STATUS.index(lama["status"]), STATUS.index(lama["status"]) + 1):
        abort(409, "Urutan status tidak valid")
    db().execute("""UPDATE laporan_kerusakan SET status=?,tindakan=?,
                    diperbarui_pada=datetime('now','localtime') WHERE id=?""",
                 (status, d.get("tindakan") or lama["tindakan"], id))
    db().commit()
    return jsonify(pesan="Status diperbarui")


@app.delete("/laporan/<int:id>")
def hapus_laporan(id):
    admin()
    laporan_by_id(id)
    db().execute("DELETE FROM laporan_kerusakan WHERE id=?", (id,))
    db().commit()
    return jsonify(pesan="Laporan dihapus")


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
