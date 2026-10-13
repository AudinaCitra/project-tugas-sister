"""
TUGAS 1 - APLIKASI B: FRONT END LAPOR FASILITAS RUSAK
Berjalan sendiri di http://127.0.0.1:8000 dan memanggil API Aplikasi A.
Jika back end ada di laptop lain:  API_URL=http://192.168.1.10:5000 python server.py
"""
import os

from flask import Flask, Response, send_from_directory

API_URL = os.getenv("API_URL", "http://127.0.0.1:5000")
app = Flask(__name__)


@app.get("/")
def beranda():
    return send_from_directory(".", "index.html")


@app.get("/config.js")
def config():
    return Response(f'window.API_URL = "{API_URL}";', mimetype="text/javascript")


if __name__ == "__main__":
    app.run(debug=True, host=os.getenv("HOST", "127.0.0.1"), port=8000)
