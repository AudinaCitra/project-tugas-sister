import csv
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = 'http://127.0.0.1:5001/api/cek'
VALID = {'Hoaks', 'Fakta', 'Perlu konteks', 'Belum ditemukan'}


def main(filename):
    with open(filename, encoding='utf-8-sig', newline='') as source:
        rows = list(csv.DictReader(source))
    if not rows or not {'teks', 'label'} <= set(rows[0]):
        print('CSV harus memiliki kolom: teks,label')
        return 1
    correct = evaluated = answered = 0
    for row in rows:
        claim = (row.get('teks') or '').strip()
        label = (row.get('label') or '').strip()
        if not claim or label not in VALID:
            continue
        req = Request(URL, data=json.dumps({'jenis':'teks', 'teks':claim}).encode(),
                      headers={'Content-Type':'application/json'}, method='POST')
        try:
            with urlopen(req, timeout=120) as response:
                output = json.load(response)['kesimpulan']
        except (HTTPError, URLError, TimeoutError) as e:
            print('Gagal menguji:', claim[:35], '|', e)
            continue
        evaluated += 1
        correct += output == label
        answered += output in ('Hoaks', 'Fakta')
        print(f'{"BENAR" if output == label else "BEDA ":5} | diharapkan={label:16} hasil={output:16} | {claim[:60]}')
    print('\nJumlah diuji:', evaluated)
    if evaluated:
        print('Kesesuaian label:', f'{correct/evaluated:.1%}')
        print('Proporsi putusan tegas Hoaks/Fakta:', f'{answered/evaluated:.1%}')
    print('Persentase ini hanya berlaku untuk contoh dalam CSV yang sudah diberi label manusia.')
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Penggunaan: python ukur_akurasi.py data_uji.csv')
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1]))
