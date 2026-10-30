import copy
import html
import json
import re
import shutil
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from app import _safe_image_url, create_app
from cloudinary_service import upload_image, upload_local_image
from content_store import MongoPortalStore
from migrate_portal_data_to_mongodb import load_portal_content, prepare_portal_content
from pymongo.errors import PyMongoError
from werkzeug.datastructures import FileStorage


ROOT = Path(__file__).resolve().parents[1]


class PortalRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        temporary_root = Path(self.temporary_directory.name)
        self.content_file = temporary_root / "preferensi.json"
        self.news_file = temporary_root / "berita.json"
        self.gallery_file = temporary_root / "gallery.json"
        shutil.copyfile(ROOT / "preferensi.json", self.content_file)
        shutil.copyfile(ROOT / "berita.json", self.news_file)
        shutil.copyfile(ROOT / "gallery.json", self.gallery_file)
        self.app = create_app({
            "TESTING": True,
            "CONTENT_FILE": self.content_file,
            "NEWS_FILE": self.news_file,
            "GALLERY_FILE": self.gallery_file,
        })
        self.client = self.app.test_client()
        self.content = json.loads(self.content_file.read_text(encoding="utf-8"))
        self.content["news"] = json.loads(self.news_file.read_text(encoding="utf-8"))
        self.content["gallery"] = json.loads(self.gallery_file.read_text(encoding="utf-8"))

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_legacy_embedded_news_and_gallery_migrate_to_separate_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            preferences_path = temporary_root / "preferensi.json"
            news_path = temporary_root / "berita.json"
            gallery_path = temporary_root / "gallery.json"
            legacy_content = json.loads((ROOT / "data" / "site.json").read_text(encoding="utf-8"))
            legacy_content["news"] = json.loads((ROOT / "data" / "berita.json").read_text(encoding="utf-8"))
            legacy_content["gallery"] = json.loads((ROOT / "data" / "gallery.json").read_text(encoding="utf-8"))
            preferences_path.write_text(json.dumps(legacy_content, ensure_ascii=False), encoding="utf-8")
            app = create_app({
                "TESTING": True,
                "CONTENT_FILE": preferences_path,
                "NEWS_FILE": news_path,
                "GALLERY_FILE": gallery_path,
            })

            response = app.test_client().get("/")
            self.assertEqual(response.status_code, 200)
            saved_preferences = json.loads(preferences_path.read_text(encoding="utf-8"))
            self.assertNotIn("news", saved_preferences)
            self.assertNotIn("gallery", saved_preferences)
            self.assertEqual(json.loads(news_path.read_text(encoding="utf-8")), legacy_content["news"])
            self.assertEqual(json.loads(gallery_path.read_text(encoding="utf-8")), legacy_content["gallery"])

    def test_manual_cloudinary_urls_receive_delivery_optimizations(self):
        raw_url = "https://res.cloudinary.com/demo/image/upload/v123/ppru/site/legacy-cover.jpg"
        optimized = _safe_image_url(raw_url, "")
        self.assertIn("c_limit,h_1600,q_auto:good,w_1600,f_auto", optimized)
        self.assertIn("/v123/ppru/site/legacy-cover.jpg", optimized)

    def test_cloudinary_service_uploads_with_resize_and_auto_quality(self):
        file_storage = FileStorage(
            stream=BytesIO(b"\x89PNG\r\n\x1a\npng-payload"),
            filename="santri.png",
        )
        expected_url = "https://res.cloudinary.com/demo/image/upload/c_limit,h_1600,q_auto:good,w_1600,f_auto/v123/ppru/site/santri"
        credentials = {"cloud_name": "demo", "api_key": "test-key", "api_secret": "test-secret"}
        with (
            patch("cloudinary_service.cloudinary.config") as config_mock,
            patch("cloudinary_service.uploader.upload", return_value={
                "public_id": "ppru/site/santri",
                "version": 123,
                "secure_url": "https://res.cloudinary.com/demo/image/upload/v123/ppru/site/santri.png",
            }) as upload_mock,
            patch("cloudinary_service.utils.cloudinary_url", return_value=(expected_url, {})) as url_mock,
        ):
            result = upload_image(file_storage, credentials, "site")

        self.assertEqual(result["url"], expected_url)
        config_mock.assert_called_once_with(
            cloud_name="demo",
            api_key="test-key",
            api_secret="test-secret",
            secure=True,
        )
        upload_options = upload_mock.call_args.kwargs
        self.assertEqual(upload_options["folder"], "ppru/site")
        self.assertEqual(upload_options["transformation"]["crop"], "limit")
        self.assertEqual(upload_options["transformation"]["quality"], "auto:good")
        self.assertEqual(url_mock.call_args.kwargs["transformation"]["fetch_format"], "auto")

    def test_migration_upload_uses_content_hash_for_stable_cloudinary_public_id(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            image_path = Path(temporary_directory) / "campus.jpg"
            image_path.write_bytes(b"\xff\xd8\xffsample-jpeg")
            expected_url = "https://res.cloudinary.com/demo/image/upload/c_limit,h_1600,q_auto:good,w_1600,f_auto/v123/ppru/site/portal-hash"
            credentials = {"cloud_name": "demo", "api_key": "test-key", "api_secret": "test-secret"}

            with (
                patch("cloudinary_service.cloudinary.config"),
                patch("cloudinary_service.uploader.upload", return_value={
                    "public_id": "ppru/site/portal-hash",
                    "version": 123,
                    "secure_url": "https://res.cloudinary.com/demo/image/upload/v123/ppru/site/portal-hash.jpg",
                }) as upload_mock,
                patch("cloudinary_service.utils.cloudinary_url", return_value=(expected_url, {})),
            ):
                result = upload_local_image(
                    image_path,
                    credentials,
                    folder="site",
                    public_id="portal-hash",
                )

        self.assertEqual(result["url"], expected_url)
        self.assertEqual(upload_mock.call_args.kwargs["public_id"], "portal-hash")
        self.assertTrue(upload_mock.call_args.kwargs["overwrite"])
        self.assertFalse(upload_mock.call_args.kwargs["unique_filename"])

    def test_portal_migration_prefers_current_json_and_rewrites_images_to_cloudinary(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "data").mkdir()
            (root / "static" / "images").mkdir(parents=True)
            (root / "static" / "images" / "campus.jpg").write_bytes(b"jpeg-campus")
            (root / "static" / "images" / "mark.svg").write_text("<svg/>", encoding="utf-8")
            (root / "preferensi.json").write_text(
                json.dumps({"site": {"title": "Runtime title", "placeholder_image": "/static/images/campus.jpg"}}),
                encoding="utf-8",
            )
            (root / "berita.json").write_text(
                json.dumps([{"slug": "runtime-news", "image": "/static/images/campus.jpg"}]),
                encoding="utf-8",
            )
            (root / "gallery.json").write_text(
                json.dumps([
                    {"id": "runtime-gallery", "image": "/static/images/mark.svg"},
                    {"id": "existing-cloudinary", "image": "https://res.cloudinary.com/demo/image/upload/v12/ppru/gallery/photo.jpg"},
                ]),
                encoding="utf-8",
            )
            (root / "data" / "site.json").write_text(json.dumps({"site": {"title": "Seed title"}}), encoding="utf-8")
            (root / "data" / "berita.json").write_text(json.dumps([{"slug": "seed-news"}]), encoding="utf-8")
            (root / "data" / "gallery.json").write_text(json.dumps([]), encoding="utf-8")

            content = load_portal_content(root)
            self.assertEqual(content["site"]["title"], "Runtime title")
            self.assertEqual(content["news"][0]["slug"], "runtime-news")
            self.assertEqual(len(content["gallery"]), 2)
            source_content = copy.deepcopy(content)
            upload_calls = []

            def fake_upload(path, _credentials, folder, public_id):
                upload_calls.append((path.name, folder, public_id))
                return {
                    "url": (
                        "https://res.cloudinary.com/demo/image/upload/"
                        f"c_limit,h_1600,q_auto:good,w_1600,f_auto/v123/ppru/{folder}/{public_id}"
                    )
                }

            migrated, counts = prepare_portal_content(
                content,
                root=root,
                cloudinary_credentials={"cloud_name": "demo", "api_key": "key", "api_secret": "secret"},
                upload_fn=fake_upload,
            )

        self.assertEqual(content, source_content)
        self.assertEqual(counts, {
            "local_image_urls": 2,
            "cloudinary_assets": 2,
            "news_items": 1,
            "gallery_items": 2,
        })
        self.assertEqual(len(upload_calls), 2)
        self.assertEqual(migrated["site"]["placeholder_image"], migrated["news"][0]["image"])
        self.assertIn("w_1600", migrated["site"]["placeholder_image"])
        self.assertIn("f_auto", migrated["gallery"][0]["image"])
        self.assertIn("w_1600", migrated["gallery"][1]["image"])
        self.assertNotIn("/static/", json.dumps(migrated))

    def test_legacy_quran_challenge_preferences_migrate_to_nadzom(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            preferences_path = Path(temporary_directory) / "preferensi.json"
            news_path = Path(temporary_directory) / "berita.json"
            gallery_path = Path(temporary_directory) / "gallery.json"
            legacy = json.loads((ROOT / "data" / "site.json").read_text(encoding="utf-8"))
            legacy["hafalan"] = {
                "title": "Sambung Ayat Challenge",
                "eyebrow": "Uji hafalanmu di sini",
                "description": "Pilih rentang juz dan jumlah soal untuk memulai latihan hafalan.",
                "frequent_items": [{"surah": "Al-Baqarah", "note": "Murajaah", "count": "2x"}],
            }
            preferences_path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
            shutil.copyfile(ROOT / "berita.json", news_path)
            shutil.copyfile(ROOT / "gallery.json", gallery_path)
            app = create_app({
                "TESTING": True,
                "CONTENT_FILE": preferences_path,
                "NEWS_FILE": news_path,
                "GALLERY_FILE": gallery_path,
            })

            response = app.test_client().get("/hafalan")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Sambung Nadzom Challenge".encode(), response.data)
            self.assertNotIn("Sambung Ayat Challenge".encode(), response.data)
            saved = json.loads(preferences_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["hafalan"]["title"], "Sambung Nadzom Challenge")
            self.assertNotIn("frequent_items", saved["hafalan"])

    def test_hafalan_page_uses_nadzom_books_and_chapter_ranges(self):
        response = self.client.get("/hafalan")
        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        self.assertIn("Sambung Nadzom Challenge", rendered)
        self.assertIn("Alfiyah Ibnu Malik", rendered)
        self.assertIn("Imrity", rendered)
        self.assertIn("Bab awal", rendered)
        self.assertIn("Sampai bab", rendered)
        self.assertIn("jumlah soal", rendered.lower())
        self.assertNotIn("Pilih rentang juz", rendered)

        alfiyah_response = self.client.get("/hafalan/data/alfiyah")
        self.assertEqual(alfiyah_response.status_code, 200)
        alfiyah_rows = alfiyah_response.get_json()
        self.assertEqual(len(alfiyah_rows), 1002)
        self.assertIn("syathr1", alfiyah_rows[0])
        self.assertIn("syathr2", alfiyah_rows[0])

        imrity_response = self.client.get("/hafalan/data/imrity")
        self.assertEqual(imrity_response.status_code, 200)
        self.assertEqual(len(imrity_response.get_json()), 254)
        self.assertEqual(self.client.get("/hafalan/data/unknown").status_code, 404)

    def test_main_routes_render(self):
        for path in (
            "/", "/profil", "/akademik", "/program", "/berita", "/galeri",
            "/hafalan", "/kontak", "/psb", "/masuk",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"Pondok Pesantren", response.data)

    def test_home_hero_promo_is_hidden_only_on_mobile(self):
        styles = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")
        desktop_styles = styles.split("@media (max-width: 960px)", 1)[0]
        mobile_styles = styles.split("@media (max-width: 740px)", 1)[1].split("@media (max-width: 520px)", 1)[0]

        self.assertIn(".hero-promo { position: relative;", desktop_styles)
        self.assertIn(".hero-promo { display: none; }", mobile_styles)

    def test_gallery_photos_open_popup_with_download_and_share_actions(self):
        response = self.client.get("/galeri")
        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        self.assertIn("data-gallery-open", rendered)
        self.assertIn('id="gallery-lightbox"', rendered)
        self.assertIn('id="gallery-lightbox-download"', rendered)
        self.assertIn('id="gallery-lightbox-share"', rendered)
        self.assertIn('aria-live="polite"', rendered)

        styles = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".gallery-card-caption", styles)
        self.assertNotIn("figcaption", styles)

    def test_vercel_admin_deletes_explain_missing_persistent_storage(self):
        app = create_app({
            "TESTING": True,
            "VERCEL": True,
            "MONGODB_URI": "",
            "CONTENT_FILE": self.content_file,
            "NEWS_FILE": self.news_file,
            "GALLERY_FILE": self.gallery_file,
            "ADMIN_PASSWORD": "test-secret",
            "SECRET_KEY": "test-secret-key",
        })
        client = app.test_client()
        login_page = client.get("/admin")
        token = re.search(r'name="csrf_token" value="([^"]+)"', login_page.get_data(as_text=True)).group(1)
        login_response = client.post(
            "/admin/login",
            data={"csrf_token": token, "password": "test-secret"},
            follow_redirects=True,
        )
        self.assertEqual(login_response.status_code, 200)
        token = re.search(r'name="csrf_token" value="([^"]+)"', login_response.get_data(as_text=True)).group(1)

        news_slug = self.content["news"][0]["slug"]
        news_delete = client.post(f"/admin/berita/{news_slug}/hapus", data={"csrf_token": token})
        self.assertEqual(news_delete.status_code, 503)
        self.assertIn("MONGODB_URI", news_delete.get_data(as_text=True))
        self.assertTrue(any(item["slug"] == news_slug for item in json.loads(self.news_file.read_text(encoding="utf-8"))))

        gallery_id = self.content["gallery"][0]["id"]
        gallery_delete = client.post(f"/admin/galeri/{gallery_id}/hapus", data={"csrf_token": token})
        self.assertEqual(gallery_delete.status_code, 503)
        self.assertIn("MONGODB_URI", gallery_delete.get_data(as_text=True))
        self.assertTrue(any(item["id"] == gallery_id for item in json.loads(self.gallery_file.read_text(encoding="utf-8"))))

    def test_mongodb_store_seeds_and_atomically_persists_portal_sections(self):
        class MemoryCollection:
            def __init__(self):
                self.document = None
                self.replace_count = 0

            def find_one(self, _query):
                return self.document

            def replace_one(self, _query, replacement, upsert=False):
                self.document = dict(replacement)
                self.replace_count += 1
                return type("WriteResult", (), {"acknowledged": True})()

        store = MongoPortalStore(
            preferences_file=self.content_file,
            news_file=self.news_file,
            gallery_file=self.gallery_file,
            seed_preferences_file=ROOT / "data" / "site.json",
            seed_news_file=ROOT / "data" / "berita.json",
            seed_gallery_file=ROOT / "data" / "gallery.json",
            mongo_uri="mongodb+srv://test.invalid",
            database_name="test_db",
            collection_name="portal_state",
            document_id="ppru:test",
        )
        collection = MemoryCollection()
        store._collection = collection

        content = store.load()
        self.assertTrue(content["news"])
        self.assertTrue(content["gallery"])
        self.assertEqual(collection.replace_count, 1)
        content["news"] = [{"slug": "persisted-from-mongodb"}]
        store.save(content)

        self.assertEqual(store.load()["news"], [{"slug": "persisted-from-mongodb"}])
        self.assertEqual(collection.replace_count, 2)
        self.assertEqual(collection.document["_id"], "ppru:test")
        self.assertIn("preferensi", collection.document)
        self.assertIn("berita", collection.document)
        self.assertIn("gallery", collection.document)

    def test_vercel_mongodb_write_failure_returns_error_without_claiming_success(self):
        class FailingCollection:
            def __init__(self, document):
                self.document = document
                self.write_attempts = 0

            def find_one(self, _query):
                return copy.deepcopy(self.document)

            def replace_one(self, _query, _replacement, upsert=False):
                self.write_attempts += 1
                raise PyMongoError("simulated Atlas outage")

        initial_document = {
            "_id": "ppru:production",
            "preferensi": json.loads((ROOT / "data" / "site.json").read_text(encoding="utf-8")),
            "berita": json.loads((ROOT / "data" / "berita.json").read_text(encoding="utf-8")),
            "gallery": json.loads((ROOT / "data" / "gallery.json").read_text(encoding="utf-8")),
        }
        collection = FailingCollection(initial_document)
        app = create_app({
            "TESTING": True,
            "VERCEL": True,
            "VERCEL_ENV": "production",
            "MONGODB_URI": "mongodb://atlas.example.invalid",
            "CONTENT_FILE": self.content_file,
            "NEWS_FILE": self.news_file,
            "GALLERY_FILE": self.gallery_file,
            "SECRET_KEY": "test-secret-key",
        })
        client = app.test_client()
        with client.session_transaction() as admin_session:
            admin_session["admin_authenticated"] = True
            admin_session["_csrf_token"] = "test-csrf-token"

        with patch.object(MongoPortalStore, "_get_collection", return_value=collection):
            response = client.post(
                "/admin/save",
                data={
                    "csrf_token": "test-csrf-token",
                    "component": "stats",
                    "stat_value_0": "1200",
                    "stat_label_0": "Santri Aktif",
                },
            )

        response_text = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 503)
        self.assertIn("MongoDB Atlas sedang tidak dapat dihubungi", response_text)
        self.assertIn("Perubahan belum tersimpan", response_text)
        self.assertNotIn("Perubahan berhasil disimpan", response_text)
        self.assertEqual(collection.write_attempts, 1)
        self.assertEqual(collection.document, initial_document)

    def test_home_renders_two_news_posts_without_hard_coded_indexes(self):
        two_news = self.content["news"][:2]
        self.news_file.write_text(json.dumps(two_news, ensure_ascii=False), encoding="utf-8")

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        rendered = html.unescape(response.get_data(as_text=True))
        for post in two_news:
            self.assertIn(post["title"], rendered)

    def test_home_and_news_listing_render_when_news_is_empty(self):
        self.news_file.write_text("[]", encoding="utf-8")

        home_response = self.client.get("/")
        self.assertEqual(home_response.status_code, 200)
        self.assertIn(b"Berita &amp; Kegiatan Terkini", home_response.data)

        news_response = self.client.get("/berita")
        self.assertEqual(news_response.status_code, 200)
        self.assertIn("Belum ada berita yang dipublikasikan".encode(), news_response.data)

    def test_home_uses_json_content(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        rendered = html.unescape(response.get_data(as_text=True))
        for program in self.content["programs"]:
            self.assertIn(program["title"], rendered)

    def test_home_shows_only_three_newest_published_stories(self):
        news = list(reversed(json.loads(self.news_file.read_text(encoding="utf-8"))))
        draft = dict(news[0])
        draft.update({
            "slug": "draft-future",
            "title": "Draft Future Tidak Boleh Tampil",
            "status": "draft",
            "published_at": "2030-01-01T00:00:00+07:00",
        })
        news.append(draft)
        self.news_file.write_text(json.dumps(news, ensure_ascii=False), encoding="utf-8")

        response = self.client.get("/")
        rendered = html.unescape(response.get_data(as_text=True))
        public_posts = [item for item in news if item.get("status") != "draft"]
        latest_three = sorted(public_posts, key=lambda item: item["published_at"], reverse=True)[:3]
        older_posts = sorted(public_posts, key=lambda item: item["published_at"], reverse=True)[3:]
        for post in latest_three:
            self.assertIn(post["title"], rendered)
        for post in older_posts:
            self.assertNotIn(post["title"], rendered)
        self.assertNotIn(draft["title"], rendered)

    def test_article_detail_and_missing_article(self):
        slug = self.content["news"][0]["slug"]
        response = self.client.get(f"/berita/{slug}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.content["news"][0]["title"].encode(), response.data)
        self.assertIn("1 kali dilihat".encode(), response.data)
        saved_news = json.loads(self.news_file.read_text(encoding="utf-8"))
        viewed_post = next(item for item in saved_news if item["slug"] == slug)
        self.assertEqual(viewed_post["views"], 1)

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
            news_path = Path(temporary_directory) / "berita.json"
            gallery_path = Path(temporary_directory) / "gallery.json"
            shutil.copyfile(ROOT / "data" / "site.json", preferences_path)
            app = create_app({
                "TESTING": True,
                "CONTENT_FILE": preferences_path,
                "NEWS_FILE": news_path,
                "GALLERY_FILE": gallery_path,
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

            news_panel = client.get("/admin?tab=news")
            self.assertEqual(news_panel.status_code, 200)
            self.assertIn(b"Buat berita baru", news_panel.data)
            self.assertIn(b"Manajemen berita", news_panel.data)
            self.assertIn(b"Edit", news_panel.data)
            self.assertIn(b"Hapus", news_panel.data)
            self.assertIn(self.content["news"][0]["title"].encode(), news_panel.data)
            self.assertIn(b"kunjungan", news_panel.data)
            self.assertNotIn(b'name="body_html"', news_panel.data)

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
            self.assertNotIn("news", saved_preferences)
            self.assertNotIn("gallery", saved_preferences)
            self.assertTrue(news_path.is_file())
            self.assertTrue(gallery_path.is_file())
            self.assertIn(b"1200", client.get("/").data)

            new_form = client.get("/admin/berita/baru")
            self.assertEqual(new_form.status_code, 200)
            self.assertIn(b"data-editor-command=\"bold\"", new_form.data)
            self.assertIn(b"data-cloudinary-upload-button", new_form.data)
            token = re.search(r'name="csrf_token" value="([^"]+)"', new_form.get_data(as_text=True)).group(1)
            create_response = client.post(
                "/admin/berita/simpan",
                data={
                    "csrf_token": token,
                    "title": "Berita Baru Aman",
                    "slug": "",
                    "category": "Kegiatan",
                    "excerpt": "",
                    "image_alt": "Foto pesantren",
                    "image": "https://res.cloudinary.com/demo/image/upload/q_auto:good,f_auto/v123/ppru/news/test-cover",
                    "status": "published",
                    "published_at": "",
                    "body_html": "<p>Isi <strong>berita</strong>.</p><script>alert(1)</script>",
                },
            )
            self.assertEqual(create_response.status_code, 302)
            saved_news = json.loads(news_path.read_text(encoding="utf-8"))
            created_post = next(item for item in saved_news if item["slug"] == "berita-baru-aman")
            self.assertIn("<strong>berita</strong>", created_post["body_html"])
            self.assertNotIn("<script", created_post["body_html"])
            detail_response = client.get("/berita/berita-baru-aman")
            self.assertEqual(detail_response.status_code, 200)
            self.assertIn(b"Isi <strong>berita</strong>.", detail_response.data)

            news_panel = client.get("/admin?tab=news")
            rendered_panel = html.unescape(news_panel.get_data(as_text=True))
            self.assertIn("Berita Baru Aman", rendered_panel)
            self.assertIn("1 kunjungan", rendered_panel)
            self.assertIn("Buat berita baru", rendered_panel)
            self.assertIn("Thumbnail Berita Baru Aman", rendered_panel)

    def test_admin_gallery_upload_edit_delete_and_dashboard_list(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            preferences_path = Path(temporary_directory) / "preferensi.json"
            news_path = Path(temporary_directory) / "berita.json"
            gallery_path = Path(temporary_directory) / "gallery.json"
            shutil.copyfile(ROOT / "data" / "site.json", preferences_path)
            app = create_app({
                "TESTING": True,
                "CONTENT_FILE": preferences_path,
                "NEWS_FILE": news_path,
                "GALLERY_FILE": gallery_path,
                "ADMIN_PASSWORD": "test-secret",
                "SECRET_KEY": "test-secret-key",
            })
            client = app.test_client()
            login_page = client.get("/admin")
            token = re.search(r'name="csrf_token" value="([^"]+)"', login_page.get_data(as_text=True)).group(1)
            client.post("/admin/login", data={"csrf_token": token, "password": "test-secret"})

            gallery_panel = client.get("/admin?tab=gallery")
            self.assertEqual(gallery_panel.status_code, 200)
            self.assertIn(b"Upload galeri baru", gallery_panel.data)
            self.assertIn(b"Kebersamaan di pesantren", gallery_panel.data)
            self.assertIn(b"Edit", gallery_panel.data)
            self.assertIn(b"Hapus", gallery_panel.data)

            upload_form = client.get("/admin/galeri/baru")
            self.assertEqual(upload_form.status_code, 200)
            self.assertIn(b"data-cloudinary-upload-button", upload_form.data)
            token = re.search(r'name="csrf_token" value="([^"]+)"', upload_form.get_data(as_text=True)).group(1)
            missing_credentials = client.post(
                "/admin/upload-image",
                data={
                    "csrf_token": token,
                    "folder": "gallery",
                    "image_file": (BytesIO(b"\x89PNG\r\n\x1a\npng-payload"), "foto-baru.png"),
                },
                content_type="multipart/form-data",
            )
            self.assertEqual(missing_credentials.status_code, 503)
            cloudinary_url = "https://res.cloudinary.com/demo/image/upload/c_limit,f_auto,h_1600,q_auto:good,w_1600/v123/ppru/gallery/foto-test"
            with patch("app.upload_image", return_value={"url": cloudinary_url, "public_id": "ppru/gallery/foto-test"}) as upload_mock:
                cloudinary_response = client.post(
                    "/admin/upload-image",
                    data={
                        "csrf_token": token,
                        "folder": "gallery",
                        "image_file": (BytesIO(b"fake-image-bytes"), "foto-baru.jpg"),
                    },
                    content_type="multipart/form-data",
                )
            self.assertEqual(cloudinary_response.status_code, 200)
            upload_mock.assert_called_once()
            self.assertEqual(cloudinary_response.get_json()["url"], cloudinary_url)

            upload_response = client.post(
                "/admin/galeri/simpan",
                data={
                    "csrf_token": token,
                    "original_id": "",
                    "title": "Foto Kegiatan Baru",
                    "caption": "Kegiatan santri di kelas.",
                    "category": "Kegiatan",
                    "image_alt": "Santri sedang belajar",
                    "shape": "wide",
                    "position": "center",
                    "image": cloudinary_url,
                },
                follow_redirects=True,
            )
            self.assertEqual(upload_response.status_code, 200)
            saved_gallery = json.loads(gallery_path.read_text(encoding="utf-8"))
            uploaded_item = next(item for item in saved_gallery if item["title"] == "Foto Kegiatan Baru")
            self.assertEqual(uploaded_item["image"], cloudinary_url)

            edit_form = client.get(f"/admin/galeri/{uploaded_item['id']}/edit")
            self.assertEqual(edit_form.status_code, 200)
            token = re.search(r'name="csrf_token" value="([^"]+)"', edit_form.get_data(as_text=True)).group(1)
            edit_response = client.post(
                "/admin/galeri/simpan",
                data={
                    "csrf_token": token,
                    "original_id": uploaded_item["id"],
                    "title": "Foto Kegiatan Diperbarui",
                    "caption": "Caption diperbarui.",
                    "category": "Santri",
                    "image_alt": "Santri belajar bersama",
                    "shape": "small",
                    "position": "top",
                },
                follow_redirects=True,
            )
            self.assertEqual(edit_response.status_code, 200)
            saved_gallery = json.loads(gallery_path.read_text(encoding="utf-8"))
            edited_item = next(item for item in saved_gallery if item["id"] == uploaded_item["id"])
            self.assertEqual(edited_item["title"], "Foto Kegiatan Diperbarui")
            self.assertEqual(edited_item["image"], uploaded_item["image"])
            self.assertIn(b"Foto Kegiatan Diperbarui", edit_response.data)

            token = re.search(r'name="csrf_token" value="([^"]+)"', edit_response.get_data(as_text=True)).group(1)
            delete_response = client.post(
                f"/admin/galeri/{uploaded_item['id']}/hapus",
                data={"csrf_token": token},
                follow_redirects=True,
            )
            self.assertEqual(delete_response.status_code, 200)
            saved_gallery = json.loads(gallery_path.read_text(encoding="utf-8"))
            self.assertFalse(any(item["id"] == uploaded_item["id"] for item in saved_gallery))
            self.assertFalse(any(item["image"] == cloudinary_url for item in saved_gallery))

    def test_cloudinary_failure_logs_useful_error_without_exposing_credentials(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            preferences_path = Path(temporary_directory) / "preferensi.json"
            news_path = Path(temporary_directory) / "berita.json"
            gallery_path = Path(temporary_directory) / "gallery.json"
            shutil.copyfile(ROOT / "data" / "site.json", preferences_path)
            app = create_app({
                "TESTING": True,
                "CONTENT_FILE": preferences_path,
                "NEWS_FILE": news_path,
                "GALLERY_FILE": gallery_path,
                "ADMIN_PASSWORD": "test-admin-password",
                "SECRET_KEY": "test-session-secret",
                "CLOUDINARY_CLOUD_NAME": "test-cloud",
                "CLOUDINARY_API_KEY": "test-api-key",
                "CLOUDINARY_API_SECRET": "test-api-secret",
            })
            client = app.test_client()
            login_page = client.get("/admin")
            token = re.search(r'name="csrf_token" value="([^"]+)"', login_page.get_data(as_text=True)).group(1)
            client.post("/admin/login", data={"csrf_token": token, "password": "test-admin-password"})
            admin_page = client.get("/admin")
            token = re.search(r'name="csrf_token" value="([^"]+)"', admin_page.get_data(as_text=True)).group(1)

            with patch("app.upload_image", side_effect=RuntimeError("Cloudinary rejected test-api-secret and test-api-key")):
                with self.assertLogs("app", level="ERROR") as captured:
                    response = client.post(
                        "/admin/upload-image",
                        data={
                            "csrf_token": token,
                            "folder": "news",
                            "image_file": (BytesIO(b"fake-image-bytes"), "cover.jpg"),
                        },
                        content_type="multipart/form-data",
                    )

            self.assertEqual(response.status_code, 502)
            log_message = "\\n".join(captured.output)
            self.assertIn("RuntimeError", log_message)
            self.assertIn("[redacted]", log_message)
            self.assertNotIn("test-api-secret", log_message)
            self.assertNotIn("test-api-key", log_message)
            self.assertIn("log server", response.get_json()["error"])

    def test_shared_image_asset_is_available(self):
        response = self.client.get("/static/images/pondok-campus.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b"\xff\xd8\xff") or response.mimetype == "image/jpeg")
        response.close()


if __name__ == "__main__":
    unittest.main()
