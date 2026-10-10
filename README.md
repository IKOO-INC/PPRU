# PPRU — OFFICIAL PORTAL ROUDLOTULUL ULUM

Website **Pondok Pesantren Roudlotululum Karangtanjung Alian Kebumen** dibangun dengan Flask (Python).
Tampilan dan urutan bagian mengikuti situs referensi, dengan dashboard admin yang dilindungi login.

## Fitur

- **Publik**: Beranda (hero, statistik, program unggulan, nderes, sejarah, pengasuh, berita, karya santri,
  galeri, agenda, FAQ), Profil, Program, Berita & Karya (filter kategori, detail artikel), Galeri, Kalender, Kontak & PSB.
- **Responsif mobile**: menu hamburger, grid menyesuaikan lebar layar, tabel admin berubah menjadi kartu di layar kecil.
- **Admin (dilindungi)**:
  - Login dengan password ter-hash, proteksi CSRF, pembatasan 5 percobaan gagal per 15 menit, cookie sesi `HttpOnly`.
  - Dashboard ringkasan.
  - **Berita**: tulis, edit, terbitkan/draf, hapus. Ada kolom *Tempat (dateline)* dan *Pembuat/Penulis*.
    Gambar bisa diisi lewat **path** atau dipilih dari file yang sudah ada, atau diunggah sementara ke folder lokal.
  - **Galeri**: unggah banyak foto sekaligus, atau tambahkan lewat path. Judul bisa diubah dan foto bisa dihapus.
  - **Konten Situs**: semua teks, kontak, banner, ayat, statistik, program, sejarah, pengasuh, FAQ, dan agenda bisa diubah tanpa menyentuh kode.
  - **Akun**: ganti password.

## Menjalankan (development)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="isi-string-acak-panjang"
export ADMIN_PASSWORD="password-yang-kuat"   # dipakai saat akun admin dibuat pertama kali
python run.py                                # http://localhost:5000  | admin: /admin/login
```

Jika `ADMIN_PASSWORD` tidak diset, password sementara acak ditampilkan sekali di konsol.
Ganti lewat menu **Akun**.

## Tes

```bash
pip install pytest && python -m pytest -q
```

## Struktur

```
app/
  __init__.py        factory create_app(), registrasi blueprint & repository
  config.py          konfigurasi (env: SECRET_KEY, ADMIN_PASSWORD, PPRU_DATA_DIR, ...)
  public.py          route publik
  admin.py           route admin (login, berita, galeri, situs, akun)
  auth.py            CSRF, pembatasan login, pembuatan akun admin pertama
  media.py           simpan gambar (lokal sekarang; ganti ke Cloudinary nanti)
  situs_schema.py    definisi field editor situs
  defaults.py        konten awal situs
  storage/           repository JSON (berita = JSON array) -> nanti MongoDB (pymongo)
  templates/         base.html, public/, admin/
  static/css|js|img/ aset; static/uploads/ = upload sementara (tidak masuk Git)
data/
  berita.json        JSON array berita
  galeri.json        JSON array galeri
  settings.json      konten situs
  admin.json         akun admin (dibuat otomatis, TIDAK masuk Git)
tests/               tes fungsional (publik, admin, keamanan, upload)
```

## Route

| Publik | Keterangan |
|---|---|
| `/` | Beranda |
| `/profil` | Sejarah & pengasuh |
| `/program` | Program unggulan |
| `/artikel` | Daftar berita (`?kategori=kegiatan` atau `karya-santri`) |
| `/artikel/detail/<slug>` | Detail berita terbit |
| `/galeri` | Galeri foto |
| `/kalender` | Agenda |
| `/kontak` | Kontak & info PSB |

| Admin (`/admin`) | Keterangan |
|---|---|
| `GET/POST /login`, `POST /logout` | Login/logout |
| `/` | Dashboard |
| `/berita`, `/berita/baru` | Daftar & tulis berita |
| `/berita/<id>/edit` | Edit berita |
| `/berita/<id>/status` (POST) | Terbitkan / jadikan draf |
| `/berita/<id>/hapus` (POST) | Hapus berita |
| `/galeri` | Kelola galeri |
| `/galeri/tambah` (POST) | Unggah / tambah foto via path |
| `/galeri/<id>/edit`, `/galeri/<id>/hapus` (POST) | Ubah judul / hapus foto |
| `/situs`, `/situs/<bagian>` | Edit konten situs (`identitas`, `hero`, `ayat`, `statistik`, `program`, `sejarah`, `kyai`, `faq`, `agenda`) |
| `/akun` | Ganti password |

## Menjalankan di production (sementara, tahap JSON)

Penyimpanan JSON hanya aman untuk **satu proses** (lock ada di dalam proses). Jalankan dengan satu worker:

```bash
gunicorn -w 1 --threads 8 -b 0.0.0.0:8000 run:app
```

Set juga `SESSION_COOKIE_SECURE=1` saat sudah pakai HTTPS.

## Rencana migrasi

1. **MongoDB (pymongo)**: buat kelas repository baru di `app/storage/` dengan method yang sama
   (`all`, `get`, `create`, `update`, `delete`, `published`), lalu ganti di `app/__init__.py`. Tampilan tidak perlu diubah.
2. **Cloudinary**: ganti isi `save_image()` di `app/media.py` agar mengunggah ke Cloudinary dan mengembalikan `secure_url`.
   Field gambar menyimpan URL, jadi data lama tetap bisa dipakai.
3. Tambahkan jadwal backup `data/` (atau dump MongoDB).

## Catatan konten

- Sumber data: profil resmi Roudlatul 'Ulum (roudlatululum.ponpes.id), blog sejarah pesantren, dan Instagram @roudlotululum_karangtanjung.
- Jumlah santri, pendaftar, dan alumni masih **0** sebagai placeholder. Isi lewat *Konten Situs → Statistik*.
- Nomor telepon di sumber berbeda-beda (0878-3222-6229 dan 0813-9142-9557). Keduanya dipasang dan perlu dikonfirmasi pengurus.
- Email, YouTube, dan link Google Maps belum tersedia, jadi dikosongkan.
- Berita contoh bertanda `[CONTOH]` di `data/berita.json` sebaiknya dihapus dari dashboard.
