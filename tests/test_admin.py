import io
import json

from conftest import CSRF, PASSWORD, PNG_BYTES, admin_client


def _post(c, url, data=None, **kw):
    data = dict(data or {})
    data.setdefault("csrf_token", CSRF)
    return c.post(url, data=data, **kw)


BERITA_OK = {"judul": "Pengajian Akbar", "kategori": "kegiatan", "status": "publish",
             "tempat": "KARANGTANJUNG", "penulis": "Tim Humas", "tanggal": "2026-10-05",
             "gambar": "/static/uploads/berita/foto.jpg", "ringkasan": "Ringkas",
             "isi": "Paragraf satu.\n\nParagraf dua."}


# ---------- Proteksi ----------

def test_halaman_admin_wajib_login(client):
    for url in ["/admin/", "/admin/berita", "/admin/berita/baru", "/admin/galeri",
                "/admin/situs", "/admin/situs/identitas", "/admin/akun"]:
        resp = client.get(url)
        assert resp.status_code == 302, url
        assert "/admin/login" in resp.headers["Location"], url


def test_post_tanpa_csrf_ditolak(client):
    resp = client.post("/admin/login", data={"username": "admin", "password": PASSWORD})
    assert resp.status_code == 400


def test_post_admin_tanpa_csrf_ditolak(app):
    c = admin_client(app)
    resp = c.post("/admin/berita/baru", data=BERITA_OK)  # tanpa csrf_token
    assert resp.status_code == 400


def test_login_salah_dan_dikunci(client):
    client.get("/admin/login")
    with client.session_transaction() as s:
        s["_csrf"] = "x"
    for _ in range(5):
        resp = client.post("/admin/login", data={"username": "admin", "password": "salah",
                                                  "csrf_token": "x"})
    assert "Username atau password salah" in resp.get_data(as_text=True)
    # Setelah 5 kali gagal, percobaan dengan password benar pun ditolak sementara.
    resp = client.post("/admin/login", data={"username": "admin", "password": PASSWORD, "csrf_token": "x"})
    assert "Terlalu banyak" in resp.get_data(as_text=True)


def test_login_berhasil_dan_logout(app):
    c = admin_client(app)
    assert c.get("/admin/").status_code == 200
    _post(c, "/admin/logout")
    assert c.get("/admin/").status_code == 302


def test_redirect_next_tidak_boleh_keluar_situs(app):
    c = app.test_client()
    c.get("/admin/login")
    with c.session_transaction() as s:
        s["_csrf"] = CSRF
    resp = c.post("/admin/login?next=https://evil.example", data={
        "username": "admin", "password": PASSWORD, "csrf_token": CSRF})
    assert resp.headers["Location"].endswith("/admin/")
    assert "evil" not in resp.headers["Location"]


def test_password_disimpan_sebagai_hash(app):
    data = json.loads((app.config["DATA_DIR"] / "admin.json").read_text())
    assert PASSWORD not in json.dumps(data)
    assert data["password_hash"].startswith(("scrypt:", "pbkdf2:"))


# ---------- Berita ----------

def test_buat_berita_masuk_json_array(app):
    c = admin_client(app)
    resp = _post(c, "/admin/berita/baru", BERITA_OK)
    assert resp.status_code == 302
    data = json.loads((app.config["DATA_DIR"] / "berita.json").read_text())
    assert isinstance(data, list)
    item = next(b for b in data if b["judul"] == "Pengajian Akbar")
    assert item["slug"] == "pengajian-akbar"
    assert item["tempat"] == "KARANGTANJUNG" and item["penulis"] == "Tim Humas"
    assert item["gambar"] == "/static/uploads/berita/foto.jpg"
    public = app.test_client().get("/artikel/detail/pengajian-akbar")
    assert public.status_code == 200
    assert b"KARANGTANJUNG" in public.data and b"Tim Humas" in public.data


def test_slug_unik_untuk_judul_sama(app):
    c = admin_client(app)
    _post(c, "/admin/berita/baru", BERITA_OK)
    _post(c, "/admin/berita/baru", BERITA_OK)
    slugs = [b["slug"] for b in app.extensions["ppru"]["berita"].all() if b["judul"] == "Pengajian Akbar"]
    assert slugs == ["pengajian-akbar", "pengajian-akbar-2"]


def test_validasi_berita(app):
    c = admin_client(app)
    before = len(app.extensions["ppru"]["berita"].all())
    resp = _post(c, "/admin/berita/baru", {"judul": "", "isi": "", "kategori": "xxx",
                                           "status": "publish", "tanggal": "bukan-tanggal"})
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Judul wajib diisi" in html and "Isi berita wajib diisi" in html
    assert "Kategori tidak valid" in html and "Format tanggal" in html
    assert len(app.extensions["ppru"]["berita"].all()) == before


def test_path_gambar_berbahaya_ditolak(app):
    c = admin_client(app)
    for bad in ["javascript:alert(1)", "/static/../../etc/passwd", "file:///etc/passwd",
                "https//salah"]:
        resp = _post(c, "/admin/berita/baru", {**BERITA_OK, "gambar": bad})
        assert "Path gambar harus" in resp.get_data(as_text=True), bad
    assert all(b["judul"] != "Pengajian Akbar" for b in app.extensions["ppru"]["berita"].all())


def test_edit_pertahankan_slug_dan_hapus(app):
    c = admin_client(app)
    _post(c, "/admin/berita/baru", BERITA_OK)
    item = next(b for b in app.extensions["ppru"]["berita"].all() if b["judul"] == "Pengajian Akbar")
    _post(c, f"/admin/berita/{item['id']}/edit", {**BERITA_OK, "judul": "Pengajian Akbar Revisi",
                                                  "isi": "Isi baru"})
    updated = app.extensions["ppru"]["berita"].get(item["id"])
    assert updated["judul"] == "Pengajian Akbar Revisi"
    assert updated["slug"] == "pengajian-akbar"
    _post(c, f"/admin/berita/{item['id']}/hapus")
    assert app.extensions["ppru"]["berita"].get(item["id"]) is None


def test_toggle_terbit_draf(app):
    c = admin_client(app)
    _post(c, "/admin/berita/baru", BERITA_OK)
    item = next(b for b in app.extensions["ppru"]["berita"].all() if b["judul"] == "Pengajian Akbar")
    _post(c, f"/admin/berita/{item['id']}/status")
    assert app.test_client().get("/artikel/detail/pengajian-akbar").status_code == 404
    _post(c, f"/admin/berita/{item['id']}/status")
    assert app.test_client().get("/artikel/detail/pengajian-akbar").status_code == 200


def test_upload_gambar_berita_lokal(app):
    c = admin_client(app)
    data = {**BERITA_OK, "gambar": "", "gambar_file": (io.BytesIO(PNG_BYTES), "foto.png"), "csrf_token": CSRF}
    resp = c.post("/admin/berita/baru", data=data, content_type="multipart/form-data")
    assert resp.status_code == 302
    item = next(b for b in app.extensions["ppru"]["berita"].all() if b["judul"] == "Pengajian Akbar")
    assert item["gambar"].startswith("/static/uploads/berita/") and item["gambar"].endswith(".png")
    saved = app.config["UPLOAD_DIR"] / "berita" / item["gambar"].rsplit("/", 1)[-1]
    assert saved.exists() and saved.read_bytes() == PNG_BYTES


def test_upload_palsu_ditolak(app):
    c = admin_client(app)
    data = {**BERITA_OK, "gambar": "", "gambar_file": (io.BytesIO(b"<html>bukan gambar</html>"), "x.png"),
            "csrf_token": CSRF}
    resp = c.post("/admin/berita/baru", data=data, content_type="multipart/form-data")
    assert "bukan gambar yang valid" in resp.get_data(as_text=True)
    assert not any(p.is_file() for p in (app.config["UPLOAD_DIR"] / "berita").iterdir())


def test_form_berita_menampilkan_pilihan_gambar(app):
    c = admin_client(app)
    (app.config["UPLOAD_DIR"] / "berita" / "ada.jpg").write_bytes(b"\xff\xd8\xff")
    html = c.get("/admin/berita/baru").get_data(as_text=True)
    assert 'name="gambar"' in html and "/static/uploads/berita/ada.jpg" in html


# ---------- Galeri ----------

def test_galeri_upload_dan_tampil_publik(app):
    c = admin_client(app)
    data = {"judul": "Pemberangkatan Santri", "tanggal": "2026-10-04", "csrf_token": CSRF,
            "foto": [(io.BytesIO(PNG_BYTES), "a.png"), (io.BytesIO(PNG_BYTES), "b.png")]}
    resp = c.post("/admin/galeri/tambah", data=data, content_type="multipart/form-data")
    assert resp.status_code == 302
    items = app.extensions["ppru"]["galeri"].all()
    assert len(items) == 2 and all(i["path"].startswith("/static/uploads/galeri/") for i in items)
    assert b"Pemberangkatan Santri" in app.test_client().get("/galeri").data
    assert isinstance(json.loads((app.config["DATA_DIR"] / "galeri.json").read_text()), list)


def test_galeri_tambah_via_path(app):
    c = admin_client(app)
    _post(c, "/admin/galeri/tambah", {"judul": "Path manual", "tanggal": "2026-10-04",
                                       "path": "/static/uploads/galeri/manual.jpg"})
    assert app.extensions["ppru"]["galeri"].all()[-1]["path"] == "/static/uploads/galeri/manual.jpg"


def test_galeri_tolak_file_bukan_gambar_dan_kosong(app):
    c = admin_client(app)
    resp = c.post("/admin/galeri/tambah", data={
        "judul": "X", "foto": [(io.BytesIO(b"hello"), "tulisan.png")], "csrf_token": CSRF,
    }, content_type="multipart/form-data", follow_redirects=True)
    assert "bukan gambar" in resp.get_data(as_text=True)
    resp = _post(c, "/admin/galeri/tambah", {"judul": "X"}, follow_redirects=True)
    assert "Pilih minimal satu foto" in resp.get_data(as_text=True)
    assert app.extensions["ppru"]["galeri"].all() == []


def test_galeri_edit_dan_hapus(app):
    c = admin_client(app)
    _post(c, "/admin/galeri/tambah", {"judul": "Lama", "path": "/static/uploads/galeri/a.jpg"})
    item = app.extensions["ppru"]["galeri"].all()[0]
    _post(c, f"/admin/galeri/{item['id']}/edit", {"judul": "Baru", "tanggal": "2026-10-05",
                                                    "path": "/static/uploads/galeri/b.jpg"})
    diubah = app.extensions["ppru"]["galeri"].get(item["id"])
    assert (diubah["judul"], diubah["tanggal"], diubah["path"]) == ("Baru", "2026-10-05", "/static/uploads/galeri/b.jpg")
    # Validasi: tanggal rusak dan path di luar /static/ ditolak
    _post(c, f"/admin/galeri/{item['id']}/edit", {"judul": "X", "tanggal": "bukan-tanggal", "path": "/static/a.jpg"})
    _post(c, f"/admin/galeri/{item['id']}/edit", {"judul": "X", "tanggal": "2026-10-05", "path": "/etc/passwd"})
    assert app.extensions["ppru"]["galeri"].get(item["id"])["judul"] == "Baru"
    _post(c, f"/admin/galeri/{item['id']}/hapus")
    assert app.extensions["ppru"]["galeri"].all() == []


def test_upload_ukuran_besar_ditolak(app):
    app.config["MAX_CONTENT_LENGTH"] = 1024
    c = admin_client(app)
    big = io.BytesIO(PNG_BYTES + b"0" * 4096)
    resp = c.post("/admin/galeri/tambah", data={"judul": "B", "foto": (big, "b.png"),
                                                 "csrf_token": CSRF},
                  content_type="multipart/form-data")
    assert resp.status_code == 413


# ---------- Situs ----------

def test_edit_program_tambah_dan_hapus_baris(app):
    c = admin_client(app)
    html = c.get("/admin/situs/program").get_data(as_text=True)
    assert "Kajian Kitab Kuning" in html
    base = app.extensions["ppru"]["settings"].section("program")
    data = {"csrf_token": CSRF,
            "judul[]": [p["judul"] for p in base] + ["Program Baru", ""],
            "deskripsi[]": [p["deskripsi"] for p in base] + ["Deskripsi baru", ""],
            "link[]": [p["link"] for p in base] + ["/program", ""]}
    resp = c.post("/admin/situs/program", data=data)
    assert resp.status_code == 302
    programs = app.extensions["ppru"]["settings"].section("program")
    assert len(programs) == len(base) + 1
    assert programs[-1]["judul"] == "Program Baru"
    # hapus semua baris kecuali satu
    c.post("/admin/situs/program", data={"csrf_token": CSRF, "judul[]": ["Satu"],
                                         "deskripsi[]": [""], "link[]": [""]})
    assert [p["judul"] for p in app.extensions["ppru"]["settings"].section("program")] == ["Satu"]


def test_situs_validasi_url_dan_tanggal(app):
    c = admin_client(app)
    resp = c.post("/admin/situs/identitas", data={
        "csrf_token": CSRF, "nama": "x", "instagram": "javascript:alert(1)", "logo": "/static/img/logo.png"})
    assert "harus diawali https://" in resp.get_data(as_text=True)
    resp = c.post("/admin/situs/agenda", data={"csrf_token": CSRF, "tanggal[]": ["2026-13-40"],
                                               "kategori[]": ["x"], "judul[]": ["Y"], "deskripsi[]": [""]})
    assert "tidak valid" in resp.get_data(as_text=True)


def test_situs_bagian_tidak_dikenal_404(app):
    c = admin_client(app)
    assert c.get("/admin/situs/tidak-ada").status_code == 404


def test_agenda_tampil_di_kalender_dan_beranda(app):
    c = admin_client(app)
    c.post("/admin/situs/agenda", data={"csrf_token": CSRF, "tanggal[]": ["2026-11-21"],
                                        "kategori[]": ["kegiatan"], "judul[]": ["Hari Santri Uji"],
                                        "deskripsi[]": ["Deskripsi uji"]})
    assert b"Hari Santri Uji" in app.test_client().get("/kalender").data
    assert b"Hari Santri Uji" in app.test_client().get("/").data


# ---------- Akun ----------

def test_ganti_password(app):
    c = admin_client(app)
    resp = _post(c, "/admin/akun", {"password_lama": "salah", "password_baru": "password-baru-1",
                                    "konfirmasi": "password-baru-1"})
    assert "Password lama tidak sesuai" in resp.get_data(as_text=True)
    resp = _post(c, "/admin/akun", {"password_lama": PASSWORD, "password_baru": "password-baru-1",
                                    "konfirmasi": "password-baru-1"})
    assert resp.status_code == 302
    fresh = app.test_client()
    fresh.get("/admin/login")
    with fresh.session_transaction() as s:
        s["_csrf"] = CSRF
    assert fresh.post("/admin/login", data={"username": "admin", "password": PASSWORD,
                                            "csrf_token": CSRF}).status_code == 200
    assert fresh.post("/admin/login", data={"username": "admin", "password": "password-baru-1",
                                            "csrf_token": CSRF}).status_code == 302


def test_dashboard_menampilkan_ringkasan(app):
    c = admin_client(app)
    html = c.get("/admin/").get_data(as_text=True)
    assert "Total Berita" in html and "Foto Galeri" in html


def test_header_keamanan_dan_galeri_edit_404(app):
    c = app.test_client()
    resp = c.get("/")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
    admin = admin_client(app)
    assert admin.post("/admin/galeri/9999/edit", data={"judul": "x", "tanggal": "2026-10-05",
                                                 "path": "/static/uploads/galeri/x.jpg", "csrf_token": CSRF}).status_code == 404
