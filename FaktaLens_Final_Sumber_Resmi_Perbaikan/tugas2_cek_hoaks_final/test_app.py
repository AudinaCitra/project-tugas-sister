import os
import tempfile
import unittest
from unittest.mock import patch

_temp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_temp.close()
os.environ["DB_PATH"] = _temp.name
os.environ["GOOGLE_FACTCHECK_API_KEY"] = "key-test"

import app as cek

SAMPLE = [{"klaim": "Vaksin mengandung microchip", "rating": "Keliru", "judul": "Periksa fakta vaksin",
           "penerbit": "Media cek fakta", "url": "https://example.com/periksa", "tanggal": "2026-10-13", "relevansi": .95}]


class TestHoaxChecker(unittest.TestCase):
    def setUp(self):
        self.client = cek.app.test_client()
        with cek.connection() as db:
            db.execute("DELETE FROM cache")
            db.execute("DELETE FROM riwayat")

    def test_home(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/api/status").status_code, 200)

    def test_input_validation(self):
        self.assertEqual(self.client.post("/api/cek", json={"jenis": "teks", "teks": "a"}).status_code, 400)
        self.assertEqual(self.client.post("/api/cek", json={"jenis": "teks", "teks": "x" * 3501}).status_code, 400)
        self.assertEqual(self.client.post("/api/cek", json={"jenis": "tautan", "url": ""}).status_code, 400)
        self.assertEqual(self.client.post("/api/cek", json={"jenis": "gambar", "teks": ""}).status_code, 400)

    def test_verdict(self):
        self.assertEqual(cek.verdict(SAMPLE), "Hoaks")
        self.assertEqual(cek.verdict([{**SAMPLE[0], "rating": "Sebagian benar"}]), "Perlu konteks")
        self.assertEqual(cek.verdict([]), "Belum ditemukan")

    @patch.object(cek, "related_news", return_value=[])
    @patch.object(cek, "factcheck_text", return_value=SAMPLE)
    def test_text_and_history(self, search, news):
        result = self.client.post("/api/cek", json={"jenis": "teks", "teks": "Vaksin mengandung microchip"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["kesimpulan"], "Hoaks")
        second = self.client.post("/api/cek", json={"jenis": "teks", "teks": "Vaksin mengandung microchip"})
        self.assertTrue(second.json["dari_cache"])
        self.assertGreaterEqual(search.call_count, 1)
        items = self.client.get("/api/riwayat").json
        self.assertEqual(len(items), 2)
        self.assertEqual(self.client.get(f"/api/riwayat/{items[0]['id']}").status_code, 200)
        self.assertEqual(self.client.get("/api/statistik").json["total"], 2)
        self.client.delete("/api/riwayat")
        self.assertEqual(self.client.get("/api/statistik").json["total"], 0)

    @patch.object(cek, "related_news", return_value=[])
    @patch.object(cek, "factcheck_image", return_value=SAMPLE)
    @patch.object(cek, "factcheck_text", return_value=[])
    @patch.object(cek, "is_public_url", return_value=True)
    def test_image_url(self, public, text_search, image_search, news):
        result = self.client.post("/api/cek", json={"jenis": "gambar", "teks": "", "image_url": "https://example.org/photo.jpg"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["jumlah_hasil"], 1)
        image_search.assert_called_once()

    @patch.object(cek, "related_news", return_value=[])
    @patch.object(cek, "factcheck_text", return_value=SAMPLE)
    @patch.object(cek, "link_context", return_value={"judul": "Vaksin mengandung microchip", "situs": "YouTube", "url": "https://youtu.be/abcdef", "gambar": ""})
    def test_youtube_link(self, context, search, news):
        result = self.client.post("/api/cek", json={"jenis": "tautan", "url": "https://youtu.be/abcdef"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["jenis"], "tautan")
        self.assertIn("Vaksin mengandung microchip", result.json["kueri"])

    def test_variasi_bukan_cuma_vaksin(self):
        cases = [
            'VIRAL! Internet gratis dari Musk, Starlink diduga jadi bahan pungli. Korban diminta bayar 20 ribu per jam, pengungsi rugi.',
            'Mulai 1 November 2024 pemerintah mewajibkan pembelian LPG 3 kg memakai KTP dan membatasi satu tabung per NIK.',
            'Pemerintah memastikan harga minyak goreng turun menjadi 10 ribu rupiah per liter.',
        ]
        for teks in cases:
            variasi = cek.variasi_kata_kunci(teks)
            self.assertGreaterEqual(len(variasi), 2)
            self.assertNotEqual(variasi[0], variasi[-1])

    @patch.object(cek, 'wikipedia_reference', return_value=([], False))
    @patch.object(cek, 'related_news', return_value=[])
    @patch.object(cek, 'factcheck_text', return_value=[])
    def test_tidak_ada_sumber_tidak_dianggap_fakta(self, search, news, wiki):
        result = self.client.post('/api/cek', json={'jenis':'gambar', 'teks': 'Starlink dipungut biaya di pengungsian padahal gratis'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['kesimpulan'], 'Belum ditemukan')
        self.assertGreaterEqual(len(result.json['kata_kunci_dicoba']), 2)

    def test_penilaian_harus_sesuai_sumber(self):
        self.assertEqual(cek.verdict([{**SAMPLE[0], 'rating':'Benar'}]), 'Fakta')
        self.assertEqual(cek.verdict([{**SAMPLE[0], 'rating':'Salah'}, {**SAMPLE[0], 'rating':'Benar'}]), 'Perlu konteks')
        self.assertEqual(cek.verdict([]), 'Belum ditemukan')
        self.assertEqual(cek.kemiripan('Starlink dipungli di lokasi pengungsian',
                                     {'klaim':'Bantuan pangan gratis di sekolah', 'judul':'Bantuan sosial'}), 0)


if __name__ == "__main__":
    unittest.main()
