import html
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from app import create_app


ROOT = Path(__file__).resolve().parents[1]


class PortalRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "CONTENT_FILE": ROOT / "data" / "site.json",
        })
        self.client = self.app.test_client()
        self.content = json.loads((ROOT / "data" / "site.json").read_text(encoding="utf-8"))

    def test_main_routes_render(self):
        for path in (
            "/", "/profil", "/akademik", "/program", "/berita", "/galeri",
            "/hafalan", "/kontak", "/psb", "/masuk",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"Pondok Pesantren", response.data)

    def test_home_uses_json_content(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        rendered = html.unescape(response.get_data(as_text=True))
        for program in self.content["programs"]:
            self.assertIn(program["title"], rendered)

    def test_article_detail_and_missing_article(self):
        slug = self.content["news"][0]["slug"]
        response = self.client.get(f"/berita/{slug}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.content["news"][0]["title"].encode(), response.data)

        missing = self.client.get("/berita/tidak-ada")
        self.assertEqual(missing.status_code, 404)
        self.assertIn("Halaman ini".encode(), missing.data)

    def test_unknown_route_renders_not_found_page(self):
        response = self.client.get("/halaman-tidak-ada")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Kembali ke Home".encode(), response.data)

    def test_admin_edits_are_saved_to_preferensi_json(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            preferences_path = Path(temporary_directory) / "preferensi.json"
            shutil.copyfile(ROOT / "data" / "site.json", preferences_path)
            app = create_app({
                "TESTING": True,
                "CONTENT_FILE": preferences_path,
                "ADMIN_PASSWORD": "test-secret",
                "SECRET_KEY": "test-secret-key",
            })
            client = app.test_client()
            login_page = client.get("/admin")
            self.assertEqual(login_page.status_code, 200)
            token = re.search(r'name="csrf_token" value="([^"]+)"', login_page.get_data(as_text=True)).group(1)
            login_response = client.post(
                "/admin/login",
                data={"csrf_token": token, "password": "test-secret"},
                follow_redirects=True,
            )
            self.assertEqual(login_response.status_code, 200)
            self.assertIn(b"Komponen website", login_response.data)

            token = re.search(r'name="csrf_token" value="([^"]+)"', login_response.get_data(as_text=True)).group(1)
            saved_response = client.post(
                "/admin/save",
                data={
                    "csrf_token": token,
                    "component": "stats",
                    "stat_value_0": "1200",
                    "stat_label_0": "Santri Aktif",
                },
                follow_redirects=True,
            )
            self.assertEqual(saved_response.status_code, 200)
            self.assertIn(b"Perubahan berhasil disimpan", saved_response.data)
            saved_preferences = json.loads(preferences_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_preferences["stats"][0]["value"], "1200")
            self.assertIn(b"1200", client.get("/").data)

    def test_shared_image_asset_is_available(self):
        response = self.client.get("/static/images/pondok-campus.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b"\xff\xd8\xff") or response.mimetype == "image/jpeg")
        response.close()


if __name__ == "__main__":
    unittest.main()
