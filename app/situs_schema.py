"""Definisi field untuk editor situs di dashboard admin.

type "object": satu set field untuk satu bagian (mis. identitas).
type "list": daftar baris (mis. program, FAQ). Admin bisa menambah/menghapus baris.
Setiap field: (nama, label, tipe_input). tipe: text | textarea | url | date | image
"""

SECTIONS = {
    "identitas": {
        "label": "Identitas & Kontak",
        "type": "object",
        "fields": [
            ("nama", "Nama Pesantren (singkat)", "text"),
            ("nama_lengkap", "Nama Lengkap", "text"),
            ("tagline", "Tagline", "text"),
            ("alamat", "Alamat", "textarea"),
            ("telepon", "Telepon", "text"),
            ("telepon_2", "Telepon Alternatif", "text"),
            ("email", "Email", "text"),
            ("instagram", "Instagram (URL)", "url"),
            ("youtube", "YouTube (URL)", "url"),
            ("website", "Website (URL)", "url"),
            ("maps", "Link Google Maps (URL)", "url"),
            ("ketua_yayasan", "Ketua Yayasan", "text"),
            ("logo", "Path Logo", "image"),
        ],
    },
    "hero": {
        "label": "Banner Beranda (Hero)",
        "type": "object",
        "fields": [
            ("judul", "Judul", "text"),
            ("subjudul", "Sub judul", "textarea"),
            ("tombol_utama_teks", "Teks Tombol Utama", "text"),
            ("tombol_utama_link", "Link Tombol Utama", "text"),
            ("tombol_kedua_teks", "Teks Tombol Kedua", "text"),
            ("tombol_kedua_link", "Link Tombol Kedua", "text"),
            ("gambar", "Path Gambar Banner", "image"),
        ],
    },
    "ayat": {
        "label": "Ayat Harian (Nderes)",
        "type": "object",
        "fields": [
            ("arab", "Teks Arab", "textarea"),
            ("terjemah", "Terjemahan", "textarea"),
            ("surat", "Sumber (surat:ayat)", "text"),
        ],
    },
    "statistik": {
        "label": "Statistik",
        "type": "list",
        "fields": [("angka", "Angka", "text"), ("label", "Label", "text")],
    },
    "program": {
        "label": "Program Unggulan",
        "type": "list",
        "fields": [
            ("judul", "Judul Program", "text"),
            ("deskripsi", "Deskripsi", "textarea"),
            ("link", "Link Selengkapnya", "text"),
        ],
    },
    "sejarah": {
        "label": "Sejarah Pesantren",
        "type": "object",
        "fields": [
            ("judul", "Judul", "text"),
            ("sub", "Sub judul", "text"),
            ("paragraf", "Paragraf (satu baris = satu paragraf)", "textarea"),
            ("gambar", "Path Gambar", "image"),
        ],
    },
    "kyai": {
        "label": "Pengasuh (Kyai)",
        "type": "object",
        "fields": [
            ("judul", "Judul Bagian", "text"),
            ("nama", "Nama", "text"),
            ("gelar", "Gelar / Keterangan", "text"),
            ("foto", "Path Foto", "image"),
            ("paragraf", "Paragraf (satu baris = satu paragraf)", "textarea"),
        ],
    },
    "faq": {
        "label": "Pertanyaan Umum (FAQ)",
        "type": "list",
        "fields": [("pertanyaan", "Pertanyaan", "text"), ("jawaban", "Jawaban", "textarea")],
    },
    "agenda": {
        "label": "Kegiatan Mendatang (Agenda)",
        "type": "list",
        "fields": [
            ("tanggal", "Tanggal", "date"),
            ("kategori", "Kategori", "text"),
            ("judul", "Judul Kegiatan", "text"),
            ("deskripsi", "Deskripsi", "textarea"),
        ],
    },
}
