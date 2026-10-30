# Portal Pondok Pesantren Roudlotul Ulum

Website publik responsif berbasis **Python, Flask, dan Jinja2**. Pola halaman mengikuti referensi: beranda, profil/sejarah, akademik, berita, galeri, tantangan hafalan, kontak, dan penerimaan santri baru.

## Admin website

- Buka `/admin`, lalu masuk dengan kata sandi pengembangan **`admin123`**.
- Sidebar **Admin Utama** berisi pengelolaan situs umum dan menu **Kelola User Admin**. Program pendidikan dikelola melalui panel Pendidikan/Akademik yang terpisah.
- Pada desktop, editor preferensi memiliki **live preview** di sisi kiri form. Pratinjau merender perubahan yang belum disimpan; tombol simpan tetap terpisah.
- Setiap komponen punya tombol simpan sendiri. Semua field gambar memakai **URL foto** dengan tombol **Upload** di sampingnya; unggahan dikirim ke Cloudinary dan URL hasilnya mengisi field secara otomatis.
- Gambar situs disajikan melalui URL Cloudinary yang mengaktifkan format otomatis dan kompresi kualitas otomatis. Upload raster menerima JPG, PNG, GIF, dan WebP sampai 10 MB, lalu membatasi dimensi sumber hingga 2400 × 2400 piksel. Delivery gambar dibatasi hingga 1600 × 1600 piksel.
- Dengan `MONGODB_URI`, MongoDB Atlas adalah sumber data utama untuk preferensi, berita, dan galeri. Pada lingkungan lokal yang bisa ditulis, perubahan Atlas juga memperbarui mirror `preferensi.json`, `berita.json`, dan `gallery.json`; tanpa Atlas, lokal tetap memakai file JSON. Filesystem deployment Vercel bukan penyimpanan persisten, sehingga JSON di Vercel tidak dianggap mirror durable.

### Konfigurasi Cloudinary

SDK Cloudinary tercantum di `requirements.txt`. Isi tiga variabel berikut melalui environment deployment atau secret manager (bukan source code, file JSON, maupun chat):

- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`

`.env.example` hanya berisi placeholder dan nilai default, bukan kredensial; aplikasi tidak memuat file `.env` secara otomatis. Untuk shell lokal, ekspor nilai konfigurasi di proses/shell sebelum menjalankan aplikasi. Endpoint `POST /admin/upload-image` mewajibkan sesi admin dan token CSRF, memvalidasi file, lalu mengembalikan URL Cloudinary. Tanpa konfigurasi lengkap, unggahan ditolak dengan pesan konfigurasi yang jelas.

Setelah konfigurasi tersedia, jalankan migrasi satu kali untuk mengganti referensi lama `/static/...` yang dipakai sebagai gambar pada JSON runtime dan seed:

```bash
python migrate_images_to_cloudinary.py
```

Skrip mengunggah aset raster dan SVG lokal yang dirujuk data (SVG hanya untuk migrasi aset lama), lalu mengganti referensinya dengan URL Cloudinary. Pastikan semua aset lokal yang direferensikan masih tersedia di `static/` dan cadangkan file JSON sebelum migrasi. Skrip tidak menghapus file lokal. Tinjau diff JSON setelah migrasi dan jangan masukkan kredensial ke Git. Untuk memasukkan URL Cloudinary ke MongoDB tanpa mengubah file JSON lokal, gunakan migrator Atlas pada bagian berikutnya sebagai gantinya.

Kata sandi admin default hanya untuk development. Sebelum deploy, atur `ADMIN_PASSWORD` dan `SECRET_KEY` dengan nilai rahasia yang kuat. Panel memakai sesi login dan token CSRF; jangan mengekspos konfigurasi development ke internet.

### Penyimpanan data di Vercel dengan MongoDB Atlas

Filesystem deployment Vercel tidak dapat dipakai untuk menyimpan perubahan JSON secara permanen. Untuk CRUD admin, buat cluster dan database user di **MongoDB Atlas**, lalu atur connection string sebagai environment variable rahasia `MONGODB_URI` pada project Vercel. Opsional: atur `MONGODB_DATABASE` (default `ppru`), `MONGODB_COLLECTION` (default `portal_data`), dan `MONGODB_NAMESPACE` (default `ppru`). Aplikasi menyimpan preferensi, berita, dan galeri dalam satu dokumen per environment (`preview` atau `production`) agar perubahan dokumen tersimpan secara atomik.

Atur `MONGODB_URI` pada environment **Preview** dan **Production**, pastikan aturan Network Access Atlas mengizinkan koneksi dari Vercel, lalu deploy ulang. Jangan commit atau mengirim connection string melalui chat. Tanpa URI di Vercel, halaman publik tetap membaca file JSON deployment secara read-only dan perubahan admin ditolak dengan HTTP 503. Di lokal, jika Atlas sementara gagal, aplikasi dapat memakai file JSON dan menampilkan pemberitahuan **“mongo eror sementara pakai preferensi.json”**; perubahan itu hanya fallback lokal dan belum tersinkron ke Atlas. Di Vercel tidak ada fallback tulis ke JSON karena filesystem deployment tidak durable: aplikasi menolak perubahan, memberi pesan yang sama bersama penjelasan bahwa perubahan belum tersimpan, dan tidak menampilkan status sukses.

#### Migrasi data JSON aktif ke MongoDB

Sebelum mengaktifkan `MONGODB_URI` di Vercel, atur `MONGODB_URI` dan tiga kredensial Cloudinary di environment shell yang aman, lalu jalankan:

```bash
python migrate_portal_data_to_mongodb.py --environment production
```

Skrip membaca `preferensi.json`, `berita.json`, dan `gallery.json` aktif (bukan hanya file seed), mengunggah aset foto lokal `/static/...` ke Cloudinary, lalu menyimpan preferensi, berita, metadata galeri, dan **URL preview Cloudinary yang dioptimalkan** dalam satu dokumen MongoDB. File gambar/binary tidak disimpan di MongoDB, dan file JSON lokal tidak diubah. Upload memakai ID Cloudinary stabil berdasarkan isi file agar percobaan ulang tidak membuat salinan media baru.

Skrip tidak menimpa dokumen Atlas yang sudah ada secara default. Jika target dokumen sudah berisi data, tinjau dulu lalu gunakan `--replace-existing` hanya bila memang ingin menggantinya. Jalankan sekali lagi dengan `--environment preview` jika ingin menyalin data yang sama ke dokumen Preview yang terpisah. Setelah migrasi berhasil, tambahkan URI yang sama sebagai secret Vercel Preview/Production dan deploy ulang.

### Berita

- Tab **Berita** di admin menampilkan semua artikel dengan thumbnail, judul, dan jumlah kunjungan; setiap baris menyediakan tombol edit/hapus. Tombol **Buat berita baru** membuka form artikel.
- Form berita mendukung draft/terbit, kategori, ringkasan, waktu publikasi, URL foto dengan tombol unggah Cloudinary, serta toolbar sederhana untuk bold, italic, underline, heading, daftar, kutipan, dan tautan. HTML difilter di server sebelum disimpan.
- Beranda hanya menampilkan **3 berita terbit terbaru**, diurutkan berdasarkan `published_at`; draft tidak muncul di area publik.
- Setiap pembukaan route `/berita/<slug>` menambah `views` dan menyimpannya ke MongoDB Atlas (serta mirror `berita.json` lokal bila file system dapat ditulis); jumlahnya tampil di baris berita pada admin.

### Admin Pendidikan/Akademik

- Login tetap melalui `/admin`. Admin Utama masuk dengan kata sandi `ADMIN_PASSWORD`; di sidebar **Kelola User Admin**, Admin Utama membuat atau menonaktifkan akun Pendidikan/Akademik, menentukan nama pengguna, dan menetapkan kata sandi minimal 12 karakter. Admin pendidikan mengisi nama pengguna serta kata sandi pada halaman login yang sama.
- Kata sandi pendidikan disimpan dalam bentuk hash di penyimpanan aplikasi; sesi admin pendidikan dapat dicabut dari **Kelola User Admin** dengan menonaktifkan akun atau memperbarui kredensial.
- Panel khusus `/admin/akademik` memisahkan menu **Pendidikan Formal** dan **Pendidikan Non Formal**, selain **Kalender Akademik** dan **Pengumuman / Berita**. Setiap program disimpan pada salah satu jenis pendidikan dan dapat dipindahkan melalui formulir edit.
- Navigasi publik **Akademik** memiliki menu **Pendidikan Formal** (`/akademik/formal`) dan **Pendidikan Non Formal** (`/akademik/non-formal`); `/akademik` tetap menjadi halaman ringkasan dengan program dikelompokkan berdasarkan jenisnya.
- Program berisi judul kelas, keterangan, daftar kitab (satu judul per baris), dan tautan **Informasi lebih lanjut**. Isi daftar kitab resmi melalui formulir program sebelum publikasi; daftar yang belum diisi ditandai jelas di situs.
- Halaman PSB dan pratinjau admin mengambil daftar program dari sumber Akademik yang sama; tidak ada daftar program PSB terpisah.
- Kegiatan kalender memiliki tanggal, judul, kategori, dan keterangan. Kalender tampil di bagian paling bawah halaman akademik; bagian **Kegiatan Mendatang** di beranda mengambil hingga tiga event terdekat yang belum lewat dari kalender ini.

### Galeri

- Tab **Galeri** menampilkan thumbnail foto yang sudah ada beserta judul dan tombol **Edit/Hapus**. Tombol **Upload galeri baru** membuka form terpisah.
- Form galeri menerima URL Cloudinary atau unggahan JPG, PNG, GIF, dan WebP sampai 10 MB. Metadata dan URL foto disimpan di MongoDB Atlas (dengan mirror `gallery.json` lokal bila tersedia); penghapusan item galeri tidak menghapus aset di Cloudinary.
- Foto galeri dapat dibuka dalam popup; pengunjung bisa mengunduh foto atau membagikan tautannya.

### Profil

- Menu **Profil** berupa dropdown dengan tautan Sejarah, Visi misi, dan Masyayikh.
- Sejarah berdiri diedit dalam satu textarea; baris kosong memisahkan paragraf. Visi juga memakai textarea, sementara daftar misi diisi satu butir per baris dan ditampilkan bernomor. Field link embed menerima URL YouTube `/embed/`, `watch?v=`, atau `youtu.be/` yang dinormalisasi ke domain `youtube-nocookie.com`.
- Ikon sosial dan kontak di footer memakai Bootstrap Icons yang disajikan lokal; lisensinya disertakan di `static/vendor/bootstrap-icons/LICENSE`.
- Tombol **Masuk Portal Santri** pada header membuka `https://siapik.com`. Tidak ada URL video profil bawaan yang diasumsikan; masukkan tautan resmi melalui panel Profil agar player YouTube ditampilkan.

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
- `/akademik` atau `/program` — Ringkasan program formal dan non formal
- `/akademik/formal` dan `/akademik/non-formal` — Program menurut jenis pendidikan
- `/berita` dan `/berita/<slug>` — Daftar dan detail berita
- `/galeri` — Galeri kegiatan dengan filter
- `/hafalan` — Kuis Sambung Nadzom Alfiyah dan Imrity
- `/kontak` — Informasi kontak dan formulir contoh
- `/psb` — Informasi Penerimaan Santri Baru
- `/masuk` — Halaman demo masuk lama; tombol header **Masuk Portal Santri** diarahkan langsung ke SIAPik
- `/admin` — Login bersama Admin Utama dan Admin Pendidikan/Akademik
- `/admin/akademik` — Panel terpisah pengelolaan program, kalender, dan pengumuman akademik

## Tes route dan penyimpanan admin

```bash
python -m unittest discover -s tests -v
```
