# Portal Pondok Pesantren Roudlotul Ulum

Website publik responsif berbasis **Python, Flask, dan Jinja2**. Pola halaman mengikuti referensi: beranda, profil/sejarah, akademik, berita, galeri, tantangan hafalan, kontak, dan penerimaan santri baru.

## Admin website

- Buka `/admin`, lalu masuk dengan kata sandi pengembangan **`admin123`**.
- Sidebar admin dibagi per komponen: Identitas/Logo, Hero, Statistik, Akademik, Profil/Sejarah, Berita, Karya, Galeri, Agenda, FAQ, Kontak, PSB, dan Hafalan.
- Setiap komponen punya tombol simpan sendiri. Path logo, hero, foto profil, foto sejarah, gambar berita, karya, galeri, PSB, dan gambar fallback bisa diubah di panel terkait.
- Path media lokal menggunakan format `/static/images/nama-file.jpg`. Letakkan file gambar di dalam folder `static/`; preview gambar di panel admin akan ikut berubah saat path diedit.
- Nilai seperti **Santri Aktif**, pengajar, alumni, dan tahun mengabdi dapat diedit dari panel **Statistik**.
- Semua data website dibaca dan disimpan pada **`preferensi.json`**. `data/site.json` disediakan sebagai seed/default jika file preferensi belum ada. Penulisan file dilakukan secara atomik agar JSON tidak korup jika proses penyimpanan terhenti.

Kata sandi admin default hanya untuk development. Sebelum deploy, atur environment variable `ADMIN_PASSWORD` dan `SECRET_KEY` dengan nilai rahasia yang kuat. Panel sudah menggunakan sesi login dan token CSRF; jangan mengekspos konfigurasi development ke internet.

> Angka statistik dan naskah saat ini masih data awal yang perlu diverifikasi sebelum publikasi. Formulir kontak, login santri, buletin, dan ujian hafalan belum terhubung ke backend.

## Menjalankan secara lokal

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

Buka `http://127.0.0.1:5000` untuk website atau `http://127.0.0.1:5000/admin` untuk panel admin. Untuk Flask CLI: `flask --app app run --debug`.

## Route publik

- `/` — Beranda
- `/profil` — Sejarah, profil, visi dan misi
- `/akademik` atau `/program` — Program pendidikan
- `/berita` dan `/berita/<slug>` — Daftar dan detail berita
- `/galeri` — Galeri kegiatan dengan filter
- `/hafalan` — Tampilan Sambung Ayat Challenge
- `/kontak` — Informasi kontak dan formulir contoh
- `/psb` — Informasi Penerimaan Santri Baru
- `/masuk` — Tampilan masuk santri
- `/admin` — Panel pengelolaan tampilan dan konten

## Tes route dan penyimpanan admin

```bash
python -m unittest discover -s tests -v
```
