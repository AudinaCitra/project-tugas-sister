import unittest
from unittest.mock import patch

import verifikasi as check


class VerifikasiTest(unittest.TestCase):
    def test_rating(self):
        expected = {
            'Keliru': 'false', 'Sebagian besar salah': 'false', 'Menyesatkan': 'false',
            'Benar': 'true', 'Sebagian benar': 'partial', 'Tidak terbukti': 'partial',
            'False': 'false', 'Mostly false': 'false', 'True': 'true',
            'Informasi belum diperiksa': 'unknown'
        }
        for rating, result in expected.items():
            with self.subTest(rating=rating):
                self.assertEqual(check.rating_type(rating), result)

    def test_no_false_match_on_negation_or_date(self):
        self.assertEqual(check.relevance('Indonesia tidak merdeka pada 17 Agustus 1945',
                                         'Indonesia merdeka pada 17 Agustus 1945'), 0)
        self.assertEqual(check.relevance('Indonesia merdeka pada 17 Agustus 1945',
                                         'Indonesia merdeka pada 20 Agustus 1947'), 0)
        self.assertEqual(check.relevance('Starlink dipungut biaya di pengungsian',
                                         'Bantuan pangan gratis di sekolah'), 0)
        self.assertGreater(check.relevance('Vaksin COVID-19 mengandung microchip',
                                           'Vaksin covid 19 mengandung chip'), .66)

    def test_only_strong_evidence_decides(self):
        self.assertEqual(check.assess([])[0], 'Belum ditemukan')
        self.assertEqual(check.assess([{'relevansi': .50, 'rating': 'Keliru'}])[0], 'Belum ditemukan')
        self.assertEqual(check.assess([{'relevansi': .92, 'rating': 'Keliru'}])[0], 'Hoaks')
        self.assertEqual(check.assess([{'relevansi': .92, 'rating': 'Benar'}])[0], 'Fakta')
        self.assertEqual(check.assess([{'relevansi': .92, 'rating': 'Sebagian benar'}])[0], 'Perlu konteks')
        self.assertEqual(check.assess([{'relevansi': .92, 'rating': 'Benar'},
                                       {'relevansi': .80, 'rating': 'Keliru'}])[0], 'Perlu konteks')

    def test_keywords_not_hardcoded(self):
        subjects = ['Starlink ditarik biaya saat banjir',
                    'Pembelian LPG 3 kg dibatasi satu tabung per NIK per bulan',
                    'Bansos akan cair tanggal 10 November 2026']
        for s in subjects:
            self.assertGreaterEqual(len(check.keyword_variants(s)), 2)

    @patch.object(check.requests, 'get')
    def test_wikipedia_exact_date_support_only(self, get):
        get.return_value.status_code = 200
        get.return_value.raise_for_status.return_value = None
        get.return_value.json.return_value = {'query': {'pages': {'123': {
            'index': 1, 'title': 'Proklamasi Kemerdekaan Indonesia',
            'fullurl': 'https://id.wikipedia.org/wiki/Proklamasi_Kemerdekaan_Indonesia',
            'extract': 'Proklamasi Kemerdekaan Indonesia dilaksanakan pada 17 Agustus 1945 di Jakarta.'
        }}}}
        reference, verified = check.wikipedia_reference('Indonesia merdeka pada 17 Agustus 1945')
        self.assertTrue(verified)
        self.assertEqual(len(reference), 1)
        _, negative = check.wikipedia_reference('Indonesia tidak merdeka pada 17 Agustus 1945')
        self.assertFalse(negative)
        _, different_date = check.wikipedia_reference('Indonesia merdeka pada 16 Agustus 1945')
        self.assertFalse(different_date)
        _, multi_claim = check.wikipedia_reference('Indonesia merdeka pada 17 Agustus 1945 dan vaksin mengandung microchip')
        self.assertFalse(multi_claim)


if __name__ == '__main__':
    unittest.main()
