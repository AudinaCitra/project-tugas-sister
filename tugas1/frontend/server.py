"""
TUGAS 1 - APLIKASI B (FRONT END): JADWAL PIKET PETUGAS KAMPUS

Tampilan dibuat dengan HTML + CSS + JavaScript (folder static/).
Python (Flask) HANYA dipakai di file ini untuk menjalankan halaman tersebut
sebagai aplikasi sendiri di http://127.0.0.1:8000. Semua data diambil
oleh JavaScript dengan memanggil API Aplikasi A.

Jika back end ada di laptop lain:  API_URL=http://192.168.1.10:5000 python server.py
"""
import json
import os

from flask import Flask, Response, send_from_directory

API_URL = os.getenv("API_URL", "http://127.0.0.1:5000")
BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(BASE, "static"))


@app.get("/")
def beranda():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/config.js")
def config():
    # json.dumps memastikan nilai aman dimasukkan ke JavaScript
    return Response(f"window.API_URL = {json.dumps(API_URL)};", mimetype="text/javascript")


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1", host=os.getenv("HOST", "127.0.0.1"), port=8000)
