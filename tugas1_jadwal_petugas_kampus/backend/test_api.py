"""Tes otomatis back end. Jalankan: python -m unittest test_api -v"""
import os
import tempfile
import unittest
from datetime import date, timedelta

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DB_PATH"] = _tmp.name
os.environ["ADMIN_PIN"] = "uji123"

import app as backend  # noqa: E402

PIN = {"X-Admin-Pin": "uji123"}
SENIN = date(2026, 10, 12)  # hari Senin


class TesApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = backend.app.test_client()

    def buat(self, bagian="Keamanan", mulai=SENIN, hari=7, per_shift=1):
        return self.c.post("/jadwal/generate", headers=PIN,
                           json={"bagian": bagian, "mulai": mulai.isoformat(), "hari": hari, "per_shift": per_shift})

    def jadwal(self, mulai=SENIN, hari=7, bagian=None):
        q = f"/jadwal?mulai={mulai}&selesai={mulai + timedelta(days=hari - 1)}"
        if bagian:
            q += f"&bagian={bagian}"
        return self.c.get(q).get_json()["jadwal"]

    def test_pin_wajib(self):
        self.assertEqual(self.c.post("/anggota", json={"nama": "Xx", "bagian": "Keamanan"}).status_code, 401)
        self.assertEqual(self.c.get("/admin/cek", headers=PIN).status_code, 200)

    def test_generate_keamanan_terisi_penuh(self):
        r = self.buat()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["dibuat"], 21)          # 7 hari x 3 shift
        self.assertEqual(r.get_json()["belum_terisi"], [])

    def test_aturan_dasar_terpenuhi(self):
        self.buat(per_shift=2, hari=14)
        data = self.jadwal(hari=14, bagian="Keamanan")
        per_hari, per_minggu, malam = {}, {}, set()
        for j in data:
            k = (j["anggota_id"], j["tanggal"])
            self.assertNotIn(k, per_hari, "satu orang dua shift di hari yang sama")
            per_hari[k] = j["shift"]
            minggu = date.fromisoformat(j["tanggal"]).isocalendar()[1]
            per_minggu[(j["anggota_id"], minggu)] = per_minggu.get((j["anggota_id"], minggu), 0) + 1
            if j["shift"] == "Malam":
                malam.add(k)
        for (aid, minggu), n in per_minggu.items():
            self.assertLessEqual(n, 5)
        for (aid, t) in malam:                                # Malam -> besoknya bukan Pagi
            besok = (date.fromisoformat(t) + timedelta(days=1)).isoformat()
            self.assertNotEqual(per_hari.get((aid, besok)), "Pagi")

    def test_beban_merata(self):
        self.buat(hari=28)
        s = self.c.get(f"/statistik?mulai={SENIN}&selesai={SENIN + timedelta(days=27)}&bagian=Keamanan").get_json()
        total = [a["total"] for a in s["anggota"]]
        self.assertLessEqual(max(total) - min(total), 2)

    def test_hari_dan_shift_sesuai_bagian(self):
        self.buat("Administrasi")
        data = self.jadwal(bagian="Administrasi")
        self.assertEqual(len(data), 5)                        # Senin-Jumat, hanya Pagi
        self.assertTrue(all(j["shift"] == "Pagi" for j in data))
        self.assertTrue(all(date.fromisoformat(j["tanggal"]).weekday() < 5 for j in data))

    def test_cuti_dihormati(self):
        anggota = self.c.get("/anggota?bagian=Administrasi").get_json()
        maya = next(a for a in anggota if a["nama"] == "Maya Sari")
        cuti = self.c.post("/cuti", headers=PIN, json={"anggota_id": maya["id"], "tanggal": "2026-10-14", "alasan": "Sakit"})
        self.assertEqual(cuti.status_code, 201)
        self.assertEqual(self.c.post("/cuti", headers=PIN, json={"anggota_id": maya["id"], "tanggal": "2026-10-14"}).status_code, 409)
        self.buat("Administrasi")
        rabu = [j for j in self.jadwal(bagian="Administrasi") if j["tanggal"] == "2026-10-14"]
        self.assertTrue(rabu and all(j["anggota_id"] != maya["id"] for j in rabu))

    def test_anggota_kurang_dilaporkan(self):
        r = self.buat("Administrasi", per_shift=3).get_json()  # hanya 2 anggota
        self.assertEqual(len(r["belum_terisi"]), 5)
        self.assertTrue(all(b["kurang"] == 1 for b in r["belum_terisi"]))

    def test_tambah_manual_ditolak_bila_melanggar(self):
        self.buat("Administrasi")
        data = self.jadwal(bagian="Administrasi")
        senin = next(j for j in data if j["tanggal"] == SENIN.isoformat())
        r = self.c.post("/jadwal", headers=PIN, json={"anggota_id": senin["anggota_id"], "tanggal": SENIN.isoformat(), "shift": "Pagi"})
        self.assertEqual(r.status_code, 409)                  # sudah bertugas hari itu
        r = self.c.post("/jadwal", headers=PIN, json={"anggota_id": senin["anggota_id"], "tanggal": "2026-10-17", "shift": "Pagi"})
        self.assertEqual(r.status_code, 409)                  # Sabtu bukan hari kerja Administrasi

    def test_hapus_penugasan_dan_validasi(self):
        self.buat("Administrasi")
        j = self.jadwal(bagian="Administrasi")[0]
        self.assertEqual(self.c.delete(f"/jadwal/{j['id']}", headers=PIN).status_code, 200)
        self.assertEqual(self.c.delete(f"/jadwal/{j['id']}", headers=PIN).status_code, 404)
        self.assertEqual(self.c.get("/jadwal?mulai=bukan-tanggal").status_code, 400)
        self.assertEqual(self.buat(hari=99).status_code, 400)

    def test_anggota_crud_dan_cascade(self):
        r = self.c.post("/anggota", headers=PIN, json={"nama": "Tes Satu", "bagian": "Laboratorium", "maks_shift_minggu": 3})
        self.assertEqual(r.status_code, 201)
        aid = r.get_json()["id"]
        self.assertEqual(self.c.post("/anggota", headers=PIN, json={"nama": "Tes Satu", "bagian": "Laboratorium"}).status_code, 409)
        self.assertEqual(self.c.post("/anggota", headers=PIN, json={"nama": "Tes", "bagian": "Dapur"}).status_code, 400)
        self.assertEqual(self.c.put(f"/anggota/{aid}", headers=PIN, json={"aktif": False}).status_code, 200)
        self.assertEqual(self.c.delete(f"/anggota/{aid}", headers=PIN).status_code, 200)
        self.assertEqual(self.c.delete(f"/anggota/{aid}", headers=PIN).status_code, 404)

    def test_buat_ulang_menimpa_bukan_menggandakan(self):
        self.buat("Administrasi")
        self.buat("Administrasi")
        self.assertEqual(len(self.jadwal(bagian="Administrasi")), 5)


if __name__ == "__main__":
    unittest.main()
