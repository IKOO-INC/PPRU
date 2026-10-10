"""Data berita dan galeri awal (DUMMY). Dipakai saat file JSON belum ada.

Ganti lewat Dashboard Admin. Saat pindah ke MongoDB, data ini cukup dipakai
sebagai bahan impor awal.
"""
from .defaults import LOREM_PANJANG as L

_GAMBAR_BERITA = [
    "/static/img/dummy/berita-1.svg",
    "/static/img/dummy/berita-2.svg",
    "/static/img/dummy/berita-3.svg",
]

DUMMY_BERITA = [
    {
        "id": 1, "judul": "Lorem Ipsum: Kegiatan Santri Pekan Ini", "slug": "lorem-ipsum-kegiatan-santri-pekan-ini",
        "kategori": "kegiatan", "tempat": "KARANGTANJUNG", "penulis": "Tim Humas", "tanggal": "2026-10-06",
        "gambar": _GAMBAR_BERITA[0], "status": "publish",
        "ringkasan": "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
        "isi": f"{L}\n\nUt enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.\n\nDuis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.",
    },
    {
        "id": 2, "judul": "Dolor Sit Amet: Pengajian Akbar Bulanan", "slug": "dolor-sit-amet-pengajian-akbar-bulanan",
        "kategori": "kegiatan", "tempat": "ALIAN", "penulis": "Pengurus Pesantren", "tanggal": "2026-09-28",
        "gambar": _GAMBAR_BERITA[1], "status": "publish",
        "ringkasan": "Consectetur adipiscing elit, sed do eiusmod tempor incididunt.",
        "isi": f"{L}\n\nExcepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.",
    },
    {
        "id": 3, "judul": "Sit Amet Consectetur: Kunjungan Wali Santri", "slug": "sit-amet-consectetur-kunjungan-wali-santri",
        "kategori": "kegiatan", "tempat": "KEBUMEN", "penulis": "Tim Humas", "tanggal": "2026-09-15",
        "gambar": "", "status": "publish",
        "ringkasan": "Ut labore et dolore magna aliqua, ut enim ad minim veniam.",
        "isi": f"{L}\n\nNemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit.",
    },
    {
        "id": 4, "judul": "Karya Santri: Lorem Ipsum Dolor", "slug": "karya-santri-lorem-ipsum-dolor",
        "kategori": "karya-santri", "tempat": "KARANGTANJUNG", "penulis": "Santri Kelas XI", "tanggal": "2026-10-02",
        "gambar": _GAMBAR_BERITA[2], "status": "publish",
        "ringkasan": "Duis aute irure dolor in reprehenderit in voluptate velit esse.",
        "isi": f"{L}\n\nQuis autem vel eum iure reprehenderit qui in ea voluptate velit esse quam nihil molestiae.",
    },
    {
        "id": 5, "judul": "Karya Santri: Tulisan Amet Elit", "slug": "karya-santri-tulisan-amet-elit",
        "kategori": "karya-santri", "tempat": "KARANGTANJUNG", "penulis": "Santri Kelas X", "tanggal": "2026-09-20",
        "gambar": "", "status": "publish",
        "ringkasan": "Excepteur sint occaecat cupidatat non proident, sunt in culpa.",
        "isi": f"{L}\n\nAt vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis praesentium voluptatum.",
    },
    {
        "id": 6, "judul": "Draf: Berita Belum Terbit", "slug": "draf-berita-belum-terbit",
        "kategori": "kegiatan", "tempat": "", "penulis": "Admin", "tanggal": "2026-10-09",
        "gambar": "", "status": "draft",
        "ringkasan": "Contoh berita berstatus draf, tidak tampil di situs.",
        "isi": f"{L}",
    },
]

_GAMBAR_GALERI = [f"/static/img/dummy/galeri-{i}.svg" for i in range(1, 5)]

DUMMY_GALERI = [
    {"id": i + 1, "judul": f"Lorem ipsum dolor {i + 1}", "path": _GAMBAR_GALERI[i % 4],
     "tanggal": f"2026-09-{10 + i:02d}"}
    for i in range(8)
]
