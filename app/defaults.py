"""Konten awal situs. Semua bisa diubah lewat Dashboard Admin (/admin/situs).

Sumber: profil resmi roudlatululum.ponpes.id, blog sejarah pesantren, dan
akun Instagram @roudlotululum_karangtanjung. Bagian bertanda VERIFIKASI
perlu dicek ulang oleh pengurus.
"""

DEFAULT_SETTINGS = {
    "identitas": {
        "nama": "Pondok Pesantren Roudlotululum",
        "nama_lengkap": "Pondok Pesantren Roudlotululum Karangtanjung Alian Kebumen",
        "tagline": "Membentuk santri yang berilmu, berakhlak, dan berdaya guna bagi masyarakat",
        "alamat": "Dukuh Krajan RT 05 RW 01, Desa Karangtanjung, Kecamatan Alian, Kabupaten Kebumen, Jawa Tengah 54352",
        "telepon": "0878-3222-6229",
        "telepon_2": "0813-9142-9557",
        "email": "",
        "instagram": "https://www.instagram.com/roudlotululum_karangtanjung/",
        "youtube": "",
        "website": "https://roudlatululum.ponpes.id",
        "maps": "",
        "ketua_yayasan": "Romo Kyai Zaenal Mustofa",
        "logo": "/static/img/logo.png",
    },
    "hero": {
        "judul": "Selamat Datang di Pondok Pesantren Roudlotululum",
        "subjudul": "Pesantren salaf yang memadukan kajian kitab kuning, tahfidz Al-Qur'an, dan pendidikan formal dalam satu lingkungan berakhlak.",
        "tombol_utama_teks": "Daftar PSB",
        "tombol_utama_link": "/kontak#psb",
        "tombol_kedua_teks": "Profil Pesantren",
        "tombol_kedua_link": "/profil",
        "gambar": "",
    },
    "statistik": [
        {"angka": "0", "label": "Santri Aktif"},
        {"angka": "0", "label": "Pendaftar Tahun Ajaran Ini"},
        {"angka": "0", "label": "Alumni"},
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
            "deskripsi": "Pengkajian kitab kuning, ilmu alat (nahwu dan shorof), serta fiqih keseharian dengan metode sorogan dan bandongan sebagaimana tradisi pesantren salaf.",
            "link": "/program#kitab",
        },
        {
            "judul": "Tahfidz Al-Qur'an",
            "deskripsi": "Program menghafal Al-Qur'an dengan bimbingan hafizh dan hafizhah yang berkompeten, dilengkapi murajaah rutin.",
            "link": "/program#tahfidz",
        },
        {
            "judul": "SMP AR RAUDLOH",
            "deskripsi": "Satuan pendidikan formal yang berdiri tahun 2021 di bawah naungan Yayasan Roudlatul 'Ulum Karangtanjung dan Dinas Pendidikan Kabupaten Kebumen.",
            "link": "/program#smp",
        },
    ],
    "sejarah": {
        "judul": "Sejarah Pesantren",
        "sub": "Profil Pondok Pesantren Roudlotululum Karangtanjung",
        "paragraf": "Pondok pesantren ini berakar dari perjuangan Romo Kyai Ilyas Alyasir, putra kelahiran Desa Karangtanjung, Kecamatan Alian, Kabupaten Kebumen, yang lahir pada 11 Oktober 1942.\nSetelah menimba ilmu di beberapa pesantren, di antaranya Riyadul 'Ulum Kalirejo Kebumen, beliau mulai mengabdi di Karangtanjung sejak tahun 1975 dengan mengajarkan nahwu dan shorof secara sorogan kepada masyarakat.\nPada 27 Sya'ban 1404 H (1983 M), beliau mendirikan pondok pesantren bernama Riyadul 'Ulum Al-Hidayah. Pada tahun 1992 namanya berganti menjadi Raudlatul 'Ulum. Pada 24 Maret 2016 pesantren berdiri sebagai yayasan dengan nama Roudlatul 'Ulum Karangtanjung.",
        "gambar": "",
    },
    "kyai": {
        "judul": "Pengasuh Pesantren",
        "nama": "Romo Kyai Ilyas Alyasir",
        "gelar": "Pendiri Pondok Pesantren Roudlotululum",
        "foto": "",
        "paragraf": "Beliau dikenal sebagai sosok yang memiliki keilmuan besar dan kegigihan dalam berjuang di tengah masyarakat.\nBeliau wafat pada 7 Mei 2010. Perjuangan beliau dilanjutkan oleh istri tercinta, Ibu Nyai Suratmi, bersama para putra dan menantu.",
    },
    "faq": [
        {
            "pertanyaan": "Bagaimana cara mendaftar santri baru?",
            "jawaban": "Pendaftaran dapat dilakukan dengan menghubungi nomor pesantren di atas, atau datang langsung ke alamat pesantren pada jam kerja.",
        },
        {
            "pertanyaan": "Apa saja persyaratan masuk pesantren?",
            "jawaban": "Persyaratan umum meliputi ijazah atau surat keterangan pendidikan terakhir, Kartu Keluarga, akta kelahiran, pas foto, serta lulus tes membaca Al-Qur'an dan wawancara. Konfirmasi persyaratan terbaru kepada pengurus.",
        },
    ],
    "agenda": [],
    "visi_misi": {
        "visi": "Membentuk santri yang berilmu, berakhlak, dan berdaya guna bagi masyarakat.",
        "misi": "Menyelenggarakan pengkajian kitab kuning dan ilmu alat secara sorogan dan bandongan.\nMembina hafalan Al-Qur'an dengan sanad dan murajaah rutin.\nMenyelenggarakan pendidikan formal yang bersinergi dengan pendidikan pesantren.\nMenanamkan akhlakul karimah dalam kehidupan sehari-hari santri.",
    },
    "psb": {
        "status": "closed",
        "tahun_ajaran": "2027/2028",
    },
}
