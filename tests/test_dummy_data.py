"""Tes data dummy: semua bagian terisi, bisa diedit lewat admin, dan seed otomatis."""
import json
import shutil
from pathlib import Path

from app import create_app
from app.defaults import DEFAULT_SETTINGS
from app.situs_schema import SECTIONS
from conftest import CSRF, PASSWORD, ROOT, admin_client

from test_admin import _post


def _kosong(nilai):
    if isinstance(nilai, dict):
        return all(_kosong(v) for v in nilai.values())
    if isinstance(nilai, list):
        return len(nilai) == 0
    return nilai in ("", None)


def test_default_settings_tidak_ada_bagian_kosong():
    for key, spec in SECTIONS.items():
        value = DEFAULT_SETTINGS[key]
        assert not _kosong(value), f"bagian {key} kosong"
        if spec["type"] == "list":
            assert len(value) >= 2, key
            for row in value:
                for name, _, _ in spec["fields"]:
                    assert str(row.get(name, "")).strip(), f"{key}.{name}"


def test_data_json_dummy_terisi():
    settings = json.loads((ROOT / "data" / "settings.json").read_text(encoding="utf-8"))
    assert settings == DEFAULT_SETTINGS
    berita = json.loads((ROOT / "data" / "berita.json").read_text(encoding="utf-8"))
    assert isinstance(berita, list)
    assert sum(b["status"] == "publish" for b in berita) >= 4
    assert {b["kategori"] for b in berita} == {"kegiatan", "karya-santri"}
    assert any(b["status"] == "draft" for b in berita)
    galeri = json.loads((ROOT / "data" / "galeri.json").read_text(encoding="utf-8"))
    assert len(galeri) >= 6 and all(g["path"].startswith("/static/img/dummy/") for g in galeri)
    for g in galeri:
        assert (ROOT / "app" / g["path"].lstrip("/")).exists(), g["path"]


def test_galeri_dummy_tampil_di_publik(tmp_path):
    data_dir = tmp_path / "data"
    app = create_app({"TESTING": True, "DATA_DIR": data_dir, "UPLOAD_DIR": tmp_path / "up",
                      "ADMIN_PASSWORD": PASSWORD, "SECRET_KEY": "k"})
    html = app.test_client().get("/galeri").get_data(as_text=True)
    assert "Lorem ipsum dolor 1" in html and "/static/img/dummy/galeri-1.svg" in html


def test_seed_dibuat_jika_file_belum_ada(tmp_path):
    data_dir = tmp_path / "data"
    app = create_app({"TESTING": True, "DATA_DIR": data_dir, "UPLOAD_DIR": tmp_path / "up",
                      "ADMIN_PASSWORD": PASSWORD, "SECRET_KEY": "k"})
    assert len(app.extensions["ppru"]["berita"].all()) == 6
    assert len(app.extensions["ppru"]["galeri"].all()) == 8
    assert app.extensions["ppru"]["settings"].section("hero")["judul"]


def test_semua_bagian_situs_bisa_dibuka(app):
    c = admin_client(app)
    for key in SECTIONS:
        resp = c.get(f"/admin/situs/{key}")
        assert resp.status_code == 200, key


def test_semua_bagian_situs_bisa_diubah(app):
    c = admin_client(app)
    _post(c, "/admin/situs/hero", {"judul": "Judul Uji", "subjudul": "Sub uji",
                                   "tombol_utama_teks": "Tombol", "tombol_utama_link": "/kontak",
                                   "tombol_kedua_teks": "Dua", "tombol_kedua_link": "/profil",
                                   "gambar": "/static/img/dummy/hero.svg"})
    assert app.extensions["ppru"]["settings"].section("hero")["judul"] == "Judul Uji"
    # Daftar: ubah baris pertama program
    # Daftar: form mengirim kolom sebagai "nama[]" (satu nilai per baris)
    _post(c, "/admin/situs/program", {"judul[]": ["Program Uji"], "deskripsi[]": ["Desk"],
                                       "link[]": ["/program"]})
    assert app.extensions["ppru"]["settings"].section("program") == [
        {"judul": "Program Uji", "deskripsi": "Desk", "link": "/program"}]
    # Agenda: tambah beberapa baris sekaligus
    _post(c, "/admin/situs/agenda", {"tanggal[]": ["2026-12-01", "2026-12-05"], "kategori[]": ["Uji", "Uji"],
                                      "judul[]": ["Agenda Uji", "Agenda Dua"], "deskripsi[]": ["Desk", "Desk 2"]})
    agenda = app.extensions["ppru"]["settings"].section("agenda")
    assert any(a["judul"] == "Agenda Uji" for a in agenda)


def test_beranda_dan_halaman_publik_pakai_data_dummy(app):
    c = app.test_client()
    html = c.get("/").get_data(as_text=True)
    assert "Lorem ipsum" in html and "Pengajian Rutin Malam Jumat" in html
    assert "Lorem Ipsum: Kegiatan Santri" in html
    # Fixture tes memulai galeri kosong; tampilan kosong harus tetap 200.
    assert c.get("/galeri").status_code == 200
    assert "Pengajian Rutin Malam Jumat" in c.get("/kalender").get_data(as_text=True)
    assert "Haflatul Imtihan Semester" in c.get("/kalender").get_data(as_text=True)
