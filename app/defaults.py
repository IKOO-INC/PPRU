"""Konten awal situs (data DUMMY untuk tahap pengembangan).

Semua teks di sini bisa diganti lewat Dashboard Admin (/admin/situs/<bagian>).
Identitas dasar (nama, alamat, telepon) berasal dari profil resmi pesantren.
Teks lainnya (statistik, program, agenda, FAQ, dan sebagainya) adalah isian
dummy yang harus diganti dengan data sebenarnya sebelum production.
"""

_LOREM = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor "
    "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud "
    "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."
)

DEFAULT_SETTINGS = {
    "identitas": {
        "nama": "Pondok Pesantren Roudlotululum",
        "nama_lengkap": "Pondok Pesantren Roudlotululum Karangtanjung Alian Kebumen",
        "tagline": "Membentuk santri yang berilmu, berakhlak, dan berdaya guna bagi masyarakat",
        "alamat": "Dukuh Krajan RT 05 RW 01, Desa Karangtanjung, Kecamatan Alian, Kabupaten Kebumen, Jawa Tengah 54352",
        "telepon": "0878-3222-6229",
        "telepon_2": "0813-9142-9557",
        "email": "info@contoh.ac.id",
        "instagram": "https://www.instagram.com/roudlotululum_karangtanjung/",
        "youtube": "https://www.youtube.com/",
        "website": "https://roudlatululum.ponpes.id",
        "maps": "https://www.google.com/maps/search/Karangtanjung+Alian+Kebumen",
        "ketua_yayasan": "Romo Kyai Zaenal Mustofa (dummy)",
        "logo": "/static/img/dummy/logo.svg",
    },
    "hero": {
        "judul": "Selamat Datang di Pondok Pesantren Roudlotululum",
        "subjudul": "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore.",
        "tombol_utama_teks": "Daftar PSB",
        "tombol_utama_link": "/kontak#psb",
        "tombol_kedua_teks": "Profil Pesantren",
        "tombol_kedua_link": "/profil",
        "gambar": "/static/img/dummy/hero.svg",
    },
    "statistik": [
        {"angka": "300", "label": "Santri Aktif"},
        {"angka": "120", "label": "Pendaftar Tahun Ajaran Ini"},
        {"angka": "1500", "label": "Alumni"},
        {"angka": "43", "label": "Tahun Mengabdi"},
    ],
    "ayat": {
        "arab": "كَذٰلِكَ وَأَوْرَثْنٰهَا بَنِىٓ إِسْرٰٓءِيلَ",
        "terjemah": "Demikianlah. Dan Kami wariskan (negeri itu) kepada Bani Israil.",
        "surat": "Asy-Syu'ara: 59",
    },
    "program": [
        {
            "judul": "Kajian Kitab Kuning",
            "deskripsi": "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore.",
            "link": "/program#kitab",
        },
        {
            "judul": "Tahfidz Al-Qur'an",
            "deskripsi": "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo.",
            "link": "/program#tahfidz",
        },
        {
            "judul": "Pendidikan Formal",
            "deskripsi": "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.",
            "link": "/program#formal",
        },
    ],
    "sejarah": {
        "judul": "Sejarah Pesantren",
        "sub": "Profil Pondok Pesantren Roudlotululum Karangtanjung",
        "paragraf": (
            "Pondok pesantren ini berakar dari perjuangan Romo Kyai Ilyas Alyasir, putra kelahiran Desa Karangtanjung, "
            "Kecamatan Alian, Kabupaten Kebumen, yang lahir pada 11 Oktober 1942.\n"
            "Setelah menimba ilmu di beberapa pesantren, beliau mulai mengabdi di Karangtanjung sejak tahun 1975 "
            "dengan mengajarkan nahwu dan shorof secara sorogan kepada masyarakat.\n"
            "Pada tahun 1983 beliau mendirikan pondok pesantren bernama Riyadul 'Ulum Al-Hidayah. Pada tahun 1992 "
            "namanya berganti menjadi Raudlatul 'Ulum."
        ),
        "gambar": "/static/img/dummy/sejarah.svg",
    },
    "kyai": {
        "judul": "Pengasuh Pesantren",
        "nama": "Romo Kyai Ilyas Alyasir",
        "gelar": "Pendiri Pondok Pesantren Roudlotululum",
        "foto": "/static/img/dummy/kyai.svg",
        "paragraf": (
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore.\n"
            "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."
        ),
    },
    "faq": [
        {
            "pertanyaan": "Bagaimana cara mendaftar santri baru?",
            "jawaban": "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Hubungi nomor pesantren pada halaman kontak.",
        },
        {
            "pertanyaan": "Apa saja persyaratan masuk pesantren?",
            "jawaban": "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam.",
        },
        {
            "pertanyaan": "Apakah tersedia asrama putra dan putri?",
            "jawaban": "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla.",
        },
        {
            "pertanyaan": "Kapan jadwal kegiatan harian santri?",
            "jawaban": "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim.",
        },
    ],
    "agenda": [
        {
            "tanggal": "2026-10-18",
            "kategori": "Kajian",
            "judul": "Pengajian Rutin Malam Jumat",
            "deskripsi": "Lorem ipsum dolor sit amet, consectetur adipiscing elit sed do eiusmod.",
        },
        {
            "tanggal": "2026-10-25",
            "kategori": "Haflah",
            "judul": "Haflatul Imtihan Semester",
            "deskripsi": "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.",
        },
        {
            "tanggal": "2026-11-08",
            "kategori": "Sosial",
            "judul": "Bakti Sosial Warga Karangtanjung",
            "deskripsi": "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum.",
        },
        {
            "tanggal": "2026-11-20",
            "kategori": "Pendidikan",
            "judul": "Workshop Tahfidz untuk Wali Santri",
            "deskripsi": "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia.",
        },
    ],
    "visi_misi": {
        "visi": "Lorem ipsum dolor sit amet, consectetur adipiscing elit sed do eiusmod tempor.",
        "misi": (
            "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi.\n"
            "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum.\n"
            "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia.\n"
            "Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium."
        ),
    },
    "psb": {
        "status": "open",
        "tahun_ajaran": "2027/2028",
    },
}

# Teks panjang untuk isi berita dummy (dipakai di app/seed.py)
LOREM_PANJANG = _LOREM
