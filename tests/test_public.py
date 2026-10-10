from conftest import admin_client


def test_halaman_publik_tampil(client):
    for url in ["/", "/profil", "/program", "/artikel", "/galeri", "/kalender", "/kontak"]:
        resp = client.get(url)
        assert resp.status_code == 200, url
        assert "Roudlotululum".encode() in resp.data, url


def test_beranda_memuat_bagian_seperti_referensi(client):
    html = client.get("/").get_data(as_text=True)
    for teks in ["Program Unggulan", "Pendidikan Holistik Berbasis Adab", "خادم المعهد",
                 "Berita &amp; Kegiatan Terkini", "Karya Santri", "Galeri Kehidupan Santri",
                 "Kegiatan Mendatang", "Pertanyaan Umum (FAQ)", "Daftar PSB", "Nderes Dulu Yuk",
                 "Scroll Down"]:
        assert teks in html, teks


def test_navbar_dan_menu_mobile(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="navbar"' in html and 'id="menuToggle"' in html and 'id="mobileMenu"' in html
    assert 'name="viewport"' in html and 'lg:hidden' in html
    assert 'href="/profil#visimisi"' in html


def test_head_selaras_referensi(client):
    html = client.get("/").get_data(as_text=True)
    for frag in ['og:type', 'twitter:card', 'summary_large_image', 'aos@2.3.1', 'swiper@11',
                 'lang="id"', 'scroll-smooth', 'css/app.css']:
        assert frag in html, frag


def test_psb_badge_hanya_saat_dibuka(app, client):
    assert "Penerimaan Santri Baru" not in client.get("/").get_data(as_text=True)
    settings = app.extensions["ppru"]["settings"]
    value = settings.section("psb")
    value["status"] = "open"
    settings.save_section("psb", value)
    html = app.test_client().get("/").get_data(as_text=True)
    assert "Penerimaan Santri Baru" in html and "Dibuka" in html


def test_profil_menampilkan_visi_misi(client):
    html = client.get("/profil").get_data(as_text=True)
    assert 'id="visimisi"' in html and "Visi" in html and "Misi" in html


def test_artikel_hanya_menampilkan_terbit(app, client):
    berita = app.extensions["ppru"]["berita"]
    berita.create({"judul": "Rahasia Draf", "slug": "rahasia-draf", "kategori": "kegiatan",
                   "tanggal": "2026-10-02", "isi": "isi", "status": "draft", "gambar": "",
                   "tempat": "", "penulis": "", "ringkasan": ""})
    html = client.get("/artikel").get_data(as_text=True)
    assert "Rahasia Draf" not in html
    assert "CONTOH" in html
    assert client.get("/artikel/detail/rahasia-draf").status_code == 404


def test_detail_artikel_dan_escape_html(app, client):
    berita = app.extensions["ppru"]["berita"]
    berita.create({"judul": "<script>alert(1)</script>", "slug": "xss-uji", "kategori": "kegiatan",
                   "tanggal": "2026-10-03", "isi": "Baris satu\n\nBaris dua <b>x</b>", "status": "publish",
                   "gambar": "", "tempat": "KEBUMEN", "penulis": "Tim", "ringkasan": ""})
    html = client.get("/artikel/detail/xss-uji").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html
    assert "3 Oktober 2026" in html


def test_kategori_filter(client):
    html = client.get("/artikel?kategori=karya-santri").get_data(as_text=True)
    assert "Contoh Karya Santri" in html or "CONTOH] Karya Santri" in html
    assert "Kegiatan Santri Pekan Ini" not in html


def test_perubahan_admin_tampil_di_situs(app):
    c = admin_client(app)
    resp = c.post("/admin/situs/identitas", data={
        "csrf_token": "token-uji-123", "nama": "PP Uji", "nama_lengkap": "PP Uji Lengkap",
        "tagline": "Tagline uji", "alamat": "Alamat uji", "telepon": "0812-0000-0000",
        "telepon_2": "", "email": "", "instagram": "https://www.instagram.com/x/", "youtube": "",
        "website": "", "maps": "", "ketua_yayasan": "", "logo": "/static/img/logo.png",
    })
    assert resp.status_code == 302
    html = app.test_client().get("/").get_data(as_text=True)
    assert "0812-0000-0000" in html and "PP Uji" in html


def test_halaman_404_ramah(client):
    resp = client.get("/tidak-ada")
    assert resp.status_code == 404
    assert "tidak ditemukan" in resp.get_data(as_text=True)
