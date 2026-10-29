# Portal Pondok Pesantren Roudlotul Ulum

Website publik responsif berbasis **Python, Flask, dan Jinja2**. Pola halaman mengikuti referensi: beranda, profil/sejarah, akademik, berita, galeri, tantangan hafalan, kontak, dan penerimaan santri baru.

## Admin website

- Buka `/admin`, lalu masuk dengan kata sandi pengembangan **`admin123`**.
- Sidebar admin dibagi per komponen: Identitas/Logo, Hero, Statistik, Akademik, Profil/Sejarah, Berita, Karya, Galeri, Agenda, FAQ, Kontak, PSB, dan Hafalan.
- Setiap komponen punya tombol simpan sendiri. Semua field gambar memakai **URL foto** dengan tombol **Upload** di sampingnya; unggahan dikirim ke Cloudinary dan URL hasilnya mengisi field secara otomatis.
- Gambar situs disajikan melalui URL Cloudinary yang mengaktifkan format otomatis dan kompresi kualitas otomatis. Upload raster menerima JPG, PNG, GIF, dan WebP sampai 10 MB, lalu membatasi dimensi sumber hingga 2400 × 2400 piksel. Delivery gambar dibatasi hingga 1600 × 1600 piksel.
- Data dipisah berdasarkan jenis: pengaturan dan konten lain disimpan di **`preferensi.json`**, artikel di **`berita.json`**, dan item galeri di **`gallery.json`**. Data awal masing-masing berada di `data/site.json`, `data/berita.json`, dan `data/gallery.json`. Setiap file ditulis secara atomik.

### Konfigurasi Cloudinary

SDK Cloudinary tercantum di `requirements.txt`. Isi tiga variabel berikut melalui environment deployment atau secret manager (bukan source code, file JSON, maupun chat):

- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`

`.env.example` hanya berisi nama variabel dan placeholder; aplikasi tidak memuat file `.env` secara otomatis. Untuk shell lokal, ekspor nilai konfigurasi di proses/shell sebelum menjalankan aplikasi. Endpoint `POST /admin/upload-image` mewajibkan sesi admin dan token CSRF, memvalidasi file, lalu mengembalikan URL Cloudinary. Tanpa konfigurasi lengkap, unggahan ditolak dengan pesan konfigurasi yang jelas.

Setelah konfigurasi tersedia, jalankan migrasi satu kali untuk mengganti referensi lama `/static/...` yang dipakai sebagai gambar pada JSON runtime dan seed:

```bash
python migrate_images_to_cloudinary.py
```

Skrip mengunggah aset raster dan SVG lokal yang dirujuk data (SVG hanya untuk migrasi aset lama), lalu mengganti referensinya dengan URL Cloudinary. Pastikan semua aset lokal yang direferensikan masih tersedia di `static/` dan cadangkan file JSON sebelum migrasi. Skrip tidak menghapus file lokal. Tinjau diff JSON setelah migrasi dan jangan masukkan kredensial ke Git.

Kata sandi admin default hanya untuk development. Sebelum deploy, atur `ADMIN_PASSWORD` dan `SECRET_KEY` dengan nilai rahasia yang kuat. Panel memakai sesi login dan token CSRF; jangan mengekspos konfigurasi development ke internet.

### Penyimpanan data di Vercel

Vercel menjalankan aplikasi Flask sebagai serverless function dengan filesystem deployment yang tidak dapat dipakai untuk menyimpan perubahan JSON secara permanen. Untuk mengaktifkan penyimpanan berita, galeri, dan preferensi admin, hubungkan database **Upstash Redis** ke project Vercel dan sediakan variabel environment `KV_REST_API_URL` serta `KV_REST_API_TOKEN` (alternatif: `UPSTASH_REDIS_REST_URL` dan `UPSTASH_REDIS_REST_TOKEN`). Aplikasi menyimpan tiga bagian JSON sebagai key terpisah dengan prefix environment, misalnya `ppru:production`, dan menulisnya dalam satu perintah `MSET`.

Tanpa konfigurasi KV di Vercel, halaman publik tetap dapat membaca file seed, tetapi perubahan admin ditolak dengan pesan konfigurasi (HTTP 503), bukan gagal sebagai Internal Server Error atau tampak berhasil tanpa tersimpan. Untuk lokal, penyimpanan JSON/file tetap digunakan seperti biasa.

### Berita

- Tab **Berita** di admin menampilkan semua artikel dengan thumbnail, judul, dan jumlah kunjungan; setiap baris menyediakan tombol edit/hapus. Tombol **Buat berita baru** membuka form artikel.
- Form berita mendukung draft/terbit, kategori, ringkasan, waktu publikasi, URL foto dengan tombol unggah Cloudinary, serta toolbar sederhana untuk bold, italic, underline, heading, daftar, kutipan, dan tautan. HTML difilter di server sebelum disimpan.
- Beranda hanya menampilkan **3 berita terbit terbaru**, diurutkan berdasarkan `published_at`; draft tidak muncul di area publik.
- Setiap pembukaan route `/berita/<slug>` menambah `views` dan menyimpannya ke `berita.json`; jumlahnya tampil di baris berita pada admin.

### Galeri

- Tab **Galeri** menampilkan thumbnail foto yang sudah ada beserta judul dan tombol **Edit/Hapus**. Tombol **Upload galeri baru** membuka form terpisah.
- Form galeri menerima URL Cloudinary atau unggahan JPG, PNG, GIF, dan WebP sampai 10 MB. Metadata dan URL foto disimpan di `gallery.json`; penghapusan item galeri tidak menghapus aset di Cloudinary.
- Foto galeri dapat dibuka dalam popup; pengunjung bisa mengunduh foto atau membagikan tautannya.

### Tantangan Sambung Nadzom

- `/hafalan` kini berisi kuis sambung bait untuk kitab nahwu **Alfiyah Ibnu Malik** dan **Imrity**, bukan latihan berdasarkan juz atau ayat Al-Qur’an.
- Peserta mengisi nama, memilih kitab, bab awal hingga bab akhir, lalu menentukan jumlah soal. Daftar bab dan bait dimuat dari `data/alfiyah.json` serta `data/imrity.json`.
- Setiap soal menampilkan syathr pertama dengan pilihan sambungannya. Jawaban tidak ditandai benar/salah sampai seluruh soal selesai; setelah itu peserta melihat nilai dan dapat membuka kesalahan beserta motivasi atau mencetak sertifikat.
- Nilai dan sertifikat dibuat di browser, tanpa menyimpan nama atau jawaban peserta ke server.

> Angka statistik dan naskah awal perlu diverifikasi sebelum publikasi. Formulir kontak, login santri, dan buletin belum terhubung ke backend.

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
- `/hafalan` — Kuis Sambung Nadzom Alfiyah dan Imrity
- `/kontak` — Informasi kontak dan formulir contoh
- `/psb` — Informasi Penerimaan Santri Baru
- `/masuk` — Tampilan masuk santri
- `/admin` — Panel pengelolaan tampilan dan konten

## Tes route dan penyimpanan admin

```bash
python -m unittest discover -s tests -v
```
