import copy
from datetime import datetime, timedelta
import html
import json
import re
import shutil
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from app import _google_maps_urls, _safe_image_url, _safe_social_url, _split_paragraphs, _youtube_embed_url, create_app, now_jakarta
from cloudinary_service import upload_image, upload_local_image
from content_store import MongoPortalStore
from migrate_portal_data_to_mongodb import load_portal_content, prepare_portal_content
from news_service import news_summary, sanitize_rich_text
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
        expected_url = "https://res.cloudinary.com/demo/image/upload/c_limit,h_1600,q_auto:good,w_1600,f_auto/v123/ppru/programs/santri"
        credentials = {"cloud_name": "demo", "api_key": "test-key", "api_secret": "test-secret"}
        with (
            patch("cloudinary_service.cloudinary.config") as config_mock,
            patch("cloudinary_service.uploader.upload", return_value={
                "public_id": "ppru/programs/santri",
                "version": 123,
                "secure_url": "https://res.cloudinary.com/demo/image/upload/v123/ppru/programs/santri.png",
            }) as upload_mock,
            patch("cloudinary_service.utils.cloudinary_url", return_value=(expected_url, {})) as url_mock,
        ):
            result = upload_image(file_storage, credentials, "programs")

        self.assertEqual(result["url"], expected_url)
        config_mock.assert_called_once_with(
            cloud_name="demo",
            api_key="test-key",
            api_secret="test-secret",
            secure=True,
        )
        upload_options = upload_mock.call_args.kwargs
        self.assertEqual(upload_options["folder"], "ppru/programs")
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
            self.assertIn("Kitab Klasik".encode(), response.data)
            self.assertIn("Sambung Nadzom".encode(), response.data)
            self.assertNotIn("Sambung Ayat Challenge".encode(), response.data)
            saved = json.loads(preferences_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["hafalan"]["title"], "Sambung Nadzom Challenge")
            self.assertNotIn("frequent_items", saved["hafalan"])

    def test_hafalan_page_uses_two_challenges_and_nadzom_books(self):
        response = self.client.get("/hafalan")
        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        self.assertIn('data-hafalan-choice="nadzom"', rendered)
        self.assertIn('data-hafalan-choice="quran"', rendered)
        self.assertIn("Kitab Klasik", rendered)
        self.assertIn("Al-Qur’an", rendered)
        self.assertIn("Surah Challenge", rendered)
        self.assertIn("Rentang Juz", rendered)
        self.assertIn("Bil Ghaib · 30 Juz", rendered)
        self.assertIn('id="quran-surah-juz"', rendered)
        self.assertIn("Sambung Nadzom", rendered)
        self.assertIn("Alfiyah Ibnu Malik", rendered)
        self.assertIn("Imrity", rendered)
        self.assertIn("Bab awal", rendered)
        self.assertIn("Sampai bab", rendered)
        self.assertIn("jumlah soal", rendered.lower())
        self.assertIn("Nama lengkap peserta", rendered)
        self.assertIn("Cetak / Simpan PDF", rendered)
        self.assertIn("Unduh PNG", rendered)
        self.assertIn("Unduh JPG", rendered)
        self.assertIn("Bagikan", rendered)
        self.assertIn("Sertifikat Partisipasi", rendered)
        self.assertIn('alt="Logo Pondok Pesantren Roudlotul Ulum"', rendered)
        self.assertIn('class="nav-link is-active" href="/hafalan"', rendered)

        quran_response = self.client.get("/static/data/quran.json")
        self.assertEqual(quran_response.status_code, 200)
        quran = quran_response.get_json()
        quran_response.close()
        self.assertEqual(len(quran), 114)
        self.assertEqual(sum(len(surah["ayahs"]) for surah in quran), 6236)
        self.assertEqual(
            {ayah["juz"] for surah in quran for ayah in surah["ayahs"]},
            set(range(1, 31)),
        )
        self.assertEqual(quran[0]["name"], "Al-Fatihah")
        self.assertIn("arab", quran[0]["ayahs"][0])

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

    def test_hafalan_navigation_revision_renames_only_the_existing_label(self):
        content = json.loads(self.content_file.read_text(encoding="utf-8"))
        content.pop("_hafalan_navigation_revision", None)
        hafalan_item = next(item for item in content["site"]["navigation"] if item["id"] == "hafalan")
        hafalan_item["label"] = "Sambung Nadzom"
        original_url = hafalan_item["url"]
        original_navigation_ids = [item["id"] for item in content["site"]["navigation"]]
        self.content_file.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")

        response = self.client.get("/hafalan")
        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        self.assertIn('class="nav-link is-active" href="/hafalan"', rendered)
        saved = json.loads(self.content_file.read_text(encoding="utf-8"))
        updated = next(item for item in saved["site"]["navigation"] if item["id"] == "hafalan")
        self.assertEqual(updated["label"], "Hafalan")
        self.assertEqual(updated["url"], original_url)
        self.assertEqual([item["id"] for item in saved["site"]["navigation"]], original_navigation_ids)
        self.assertEqual(saved["_hafalan_navigation_revision"], "hafalan-navigation-2026-v1")

    def test_main_routes_render(self):
        for path in (
            "/", "/profil", "/akademik", "/program", "/berita", "/galeri",
            "/hafalan", "/kontak", "/psb", "/masuk",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"Pondok Pesantren", response.data)

    def test_psb_programs_use_the_academic_program_source(self):
        preferences = json.loads(self.content_file.read_text(encoding="utf-8"))
        preferences["admission"]["programs"] = [{"name": "Program Duplikat", "detail": "Data lama"}]
        preferences["programs"][0]["title"] = "Program Akademik Utama"
        self.content_file.write_text(json.dumps(preferences, ensure_ascii=False), encoding="utf-8")

        psb_html = self.client.get("/psb").get_data(as_text=True)
        self.assertIn("Program Akademik Utama", psb_html)
        self.assertNotIn("Program Duplikat", psb_html)
        self.assertIn('href="/akademik/non-formal"', psb_html)
        self.assertIn('href="https://bit.ly/spmb-ppru"', psb_html)
        program_cards = psb_html.split('class="admission-programs">', 1)[1].split("</div></div></section>", 1)[0]
        self.assertEqual(program_cards.count("<article>"), 3)

        with self.client.session_transaction() as admin_session:
            admin_session["admin_authenticated"] = True
            admin_session["_csrf_token"] = "admission-csrf-token"
        admin_html = self.client.get("/admin?tab=admission").get_data(as_text=True)
        self.assertIn("Program Akademik Utama", admin_html)
        self.assertNotIn("Program PSB 01", admin_html)
        self.assertNotIn('name="admission_program_name_0"', admin_html)
        saved = self.client.post(
            "/admin/save",
            data={
                "csrf_token": "admission-csrf-token",
                "component": "admission",
                "admission_title": "PSB Terbaru",
            },
        )
        self.assertEqual(saved.status_code, 302)
        updated_admission = json.loads(self.content_file.read_text(encoding="utf-8"))["admission"]
        self.assertNotIn("programs", updated_admission)
        updated_psb_html = self.client.get("/psb").get_data(as_text=True)
        self.assertRegex(updated_psb_html, r"PSB Terbaru Tahun Ajaran 14\d{2}/14\d{2}")
        self.assertNotIn("1447/1448", updated_psb_html)

    def test_admin_academic_can_choose_three_distinct_psb_program_slots(self):
        preferences = json.loads(self.content_file.read_text(encoding="utf-8"))
        programs_by_number = {item["number"]: item for item in preferences["programs"]}
        selected_numbers = ["04", "02", "06"]
        self.assertTrue(all(number in programs_by_number for number in selected_numbers))

        with self.client.session_transaction() as admin_session:
            admin_session["admin_authenticated"] = True
            admin_session["admin_role"] = "main"

        slot_page = self.client.get("/admin/akademik?tab=psb")
        self.assertEqual(slot_page.status_code, 200)
        slot_html = slot_page.get_data(as_text=True)
        self.assertIn("Pilih Program PSB", slot_html)
        self.assertIn('name="program_slot_0"', slot_html)
        self.assertIn('name="program_slot_1"', slot_html)
        self.assertIn('name="program_slot_2"', slot_html)
        self.assertIn("Kajian Sorogan &amp; Bandungan", slot_html)
        csrf_token = re.search(r'name="csrf_token" value="([^"]+)"', slot_html).group(1)

        saved = self.client.post(
            "/admin/akademik/psb/simpan",
            data={
                "csrf_token": csrf_token,
                "program_slot_0": selected_numbers[0],
                "program_slot_1": selected_numbers[1],
                "program_slot_2": selected_numbers[2],
            },
        )
        self.assertEqual(saved.status_code, 302)
        self.assertIn("tab=psb", saved.location)
        persisted = json.loads(self.content_file.read_text(encoding="utf-8"))
        self.assertEqual(persisted["admission"]["program_slots"], selected_numbers)

        psb_html = self.client.get("/psb").get_data(as_text=True)
        program_cards = psb_html.split('class="admission-programs">', 1)[1].split("</div></div></section>", 1)[0]
        self.assertEqual(program_cards.count("<article>"), 3)
        expected_titles = [html.escape(programs_by_number[number]["title"]) for number in selected_numbers]
        self.assertEqual(
            [program_cards.index(title) for title in expected_titles],
            sorted(program_cards.index(title) for title in expected_titles),
        )
        self.assertNotIn(programs_by_number["01"]["title"], program_cards)

        duplicate = self.client.post(
            "/admin/akademik/psb/simpan",
            data={
                "csrf_token": csrf_token,
                "program_slot_0": "02",
                "program_slot_1": "02",
                "program_slot_2": "04",
            },
            follow_redirects=True,
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertIn("Pilih program yang tersedia dan berbeda", duplicate.get_data(as_text=True))
        unchanged = json.loads(self.content_file.read_text(encoding="utf-8"))
        self.assertEqual(unchanged["admission"]["program_slots"], selected_numbers)

    def test_psb_hijri_academic_year_updates_automatically(self):
        with patch("app.now_jakarta", return_value=datetime(2026, 10, 31, 12, 0)):
            current_year_page = self.client.get("/psb")
        self.assertEqual(current_year_page.status_code, 200)
        current_year_html = current_year_page.get_data(as_text=True)
        self.assertIn("Penerimaan Santri Baru Tahun Ajaran 1448/1449", current_year_html)
        self.assertNotIn("1447/1448", current_year_html)

        with patch("app.now_jakarta", return_value=datetime(2027, 7, 1, 12, 0)):
            next_year_page = self.client.get("/psb")
        self.assertIn("Penerimaan Santri Baru Tahun Ajaran 1449/1450", next_year_page.get_data(as_text=True))

    def test_footer_uses_local_fontawesome_icons_and_user_supplied_social_urls(self):
        rendered = self.client.get("/").get_data(as_text=True)
        footer = rendered.split('<footer class="site-footer">', 1)[1].split("</footer>", 1)[0]
        self.assertIn("/static/vendor/fontawesome-free/css/brands.min.css?v=6.7.2", rendered)
        self.assertNotIn("bootstrap-icons", rendered)

        icons_css = self.client.get("/static/vendor/fontawesome-free/css/brands.min.css")
        icons_font = self.client.get("/static/vendor/fontawesome-free/webfonts/fa-brands-400.woff2")
        self.assertEqual(icons_css.status_code, 200)
        self.assertEqual(icons_font.status_code, 200)
        icons_css.close()
        icons_font.close()

        expected_links = (
            ('href="https://www.facebook.com/pprukarangtanjungisrugans/?locale=id_ID"', "fa-facebook-f"),
            ('href="https://www.instagram.com/roudlotululum_karangtanjung/"', "fa-instagram"),
            ('href="https://www.youtube.com/@mediaroudlatululum6018"', "fa-youtube"),
            ('href="https://www.tiktok.com/@roudlotululum1983?_r=1&amp;_t=ZS-9AzQydgGWTx"', "fa-tiktok"),
        )
        for href, icon in expected_links:
            with self.subTest(icon=icon):
                self.assertIn(href, footer)
                self.assertIn(icon, footer)
        self.assertNotIn('href="#footer"', footer)
        self.assertIn('class="footer-icon fa-solid fa-location-dot"', footer)

    def test_social_links_revision_adds_official_urls_without_overwriting_admin_links(self):
        content = json.loads(self.content_file.read_text(encoding="utf-8"))
        content.pop("_social_links_revision", None)
        content["site"]["social_links"] = {
            "facebook": "https://www.facebook.com/admin-managed-profile",
        }
        self.content_file.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")

        rendered = self.client.get("/").get_data(as_text=True)
        saved = json.loads(self.content_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["_social_links_revision"], "official-social-links-2026-v1")
        self.assertEqual(saved["site"]["social_links"]["facebook"], "https://www.facebook.com/admin-managed-profile")
        self.assertEqual(saved["site"]["social_links"]["instagram"], "https://www.instagram.com/roudlotululum_karangtanjung/")
        self.assertEqual(saved["site"]["social_links"]["youtube"], "https://www.youtube.com/@mediaroudlatululum6018")
        self.assertEqual(saved["site"]["social_links"]["tiktok"], "https://www.tiktok.com/@roudlotululum1983?_r=1&_t=ZS-9AzQydgGWTx")
        self.assertIn('href="https://www.facebook.com/admin-managed-profile"', rendered)
        self.assertIn("fa-instagram", rendered)
        self.assertIn("fa-youtube", rendered)
        self.assertIn("fa-tiktok", rendered)

    def test_template_icons_use_fontawesome_not_unicode_or_bootstrap_glyphs(self):
        forbidden_icons = "↗←→↓↑⌄×ⓘ◉✓▶✳✦◷⌕⌖✉◎▤⬇‹›¶•"
        for template in Path(ROOT / "templates").rglob("*.html"):
            content = template.read_text(encoding="utf-8")
            with self.subTest(template=template.name):
                self.assertNotIn("bi-", content)
                self.assertFalse(set(forbidden_icons).intersection(content))

    def test_contact_page_embeds_google_map_for_the_confirmed_address(self):
        expected_address = "Dk. Krajan RT 05 / RW 01, Desa Karangtanjung, Kecamatan Alian, Kabupaten Kebumen, Jawa Tengah 54352."
        page = self.client.get("/kontak")
        rendered = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn(expected_address, rendered)
        self.assertIn('<iframe src="https://www.google.com/maps?q=Dk.+Krajan+RT+05+%2F+RW+01%2C+Desa+Karangtanjung%2C+Kecamatan+Alian%2C+Kabupaten+Kebumen%2C+Jawa+Tengah+54352&amp;output=embed"', rendered)
        self.assertIn('title="Peta Pondok Pesantren Roudlotul Ulum, Karangtanjung, Kebumen"', rendered)
        self.assertIn("https://www.google.com/maps/search/?api=1&amp;query=", rendered)
        self.assertIn("fa-location-dot", rendered)
        self.assertNotIn("map_image or", rendered)
        self.assertEqual(
            _google_maps_urls("Dk. Krajan RT 05 / RW 01, Kebumen."),
            (
                "https://www.google.com/maps?q=Dk.+Krajan+RT+05+%2F+RW+01%2C+Kebumen&output=embed",
                "https://www.google.com/maps/search/?api=1&query=Dk.+Krajan+RT+05+%2F+RW+01%2C+Kebumen",
            ),
        )

    def test_contact_address_migration_updates_only_address_and_syncs_site_location(self):
        content = json.loads(self.content_file.read_text(encoding="utf-8"))
        content.pop("_contact_address_revision", None)
        content["site"]["address"] = "Alamat lama"
        content["contact"]["address"] = "Alamat lama"
        original_phone = content["contact"]["phone"]
        self.content_file.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")

        rendered = self.client.get("/kontak").get_data(as_text=True)
        saved = json.loads(self.content_file.read_text(encoding="utf-8"))
        expected_address = "Dk. Krajan RT 05 / RW 01, Desa Karangtanjung, Kecamatan Alian, Kabupaten Kebumen, Jawa Tengah 54352."
        self.assertIn(expected_address, rendered)
        self.assertEqual(saved["site"]["address"], expected_address)
        self.assertEqual(saved["contact"]["address"], expected_address)
        self.assertEqual(saved["contact"]["phone"], original_phone)
        self.assertEqual(saved["_contact_address_revision"], "contact-address-2026-v1")

    def test_home_stats_revision_replaces_old_counters_with_requested_metrics(self):
        content = json.loads(self.content_file.read_text(encoding="utf-8"))
        content.pop("_home_stats_revision", None)
        content["stats"] = [
            {"value": "4", "label": "Program takhassus"},
            {"value": "30", "label": "Prestasi"},
        ]
        self.content_file.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")

        rendered = self.client.get("/").get_data(as_text=True)
        saved = json.loads(self.content_file.read_text(encoding="utf-8"))
        self.assertEqual(
            saved["stats"],
            [
                {"value": "—", "label": "Santri aktif"},
                {"value": "—", "label": "Alumni"},
                {"value": "1983", "label": "Tahun berdiri"},
                {"value": "2", "label": "Unit pendidikan formal"},
            ],
        )
        self.assertEqual(saved["_home_stats_revision"], "home-stats-santri-alumni-2026-v1")
        self.assertIn("Santri aktif", rendered)
        self.assertIn("Alumni", rendered)
        self.assertIn("Tahun berdiri", rendered)
        self.assertIn("Unit pendidikan formal", rendered)

    def test_social_url_admin_fields_accept_https_and_reject_unsafe_links(self):
        self.assertEqual(_safe_social_url("https://www.instagram.com/pondok/"), "https://www.instagram.com/pondok/")
        self.assertEqual(_safe_social_url("javascript:alert(1)"), "")
        self.assertEqual(_safe_social_url("http://instagram.com/pondok"), "")
        self.assertEqual(_safe_social_url("javascript:alert(1)", "https://www.instagram.com/existing"), "https://www.instagram.com/existing")

        with self.client.session_transaction() as admin_session:
            admin_session["admin_authenticated"] = True
            admin_session["_csrf_token"] = "social-csrf-token"
        response = self.client.post(
            "/admin/save",
            data={
                "csrf_token": "social-csrf-token",
                "component": "brand",
                "social_facebook": "https://www.facebook.com/official.test",
                "social_instagram": "javascript:alert(1)",
                "social_youtube": "",
                "social_tiktok": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        saved = json.loads(self.content_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["site"]["social_links"]["facebook"], "https://www.facebook.com/official.test")
        self.assertEqual(
            saved["site"]["social_links"]["instagram"],
            "https://www.instagram.com/roudlotululum_karangtanjung/",
        )
        self.assertNotIn("social_facebook", saved["site"])
        rendered = self.client.get("/kontak").get_data(as_text=True)
        self.assertIn('href="https://www.facebook.com/official.test"', rendered)
        self.assertIn("fa-facebook-f", rendered)
        self.assertNotIn("href=\"javascript:alert(1)\"", rendered)
        admin_html = self.client.get("/admin?tab=brand").get_data(as_text=True)
        self.assertIn('name="social_facebook"', admin_html)
        self.assertIn('name="social_tiktok"', admin_html)

    def test_home_upcoming_events_are_the_next_three_academic_calendar_items(self):
        today = now_jakarta().date()
        upcoming_dates = [today + timedelta(days=days) for days in (20, 4, -1, 10, 40)]
        preferences = json.loads(self.content_file.read_text(encoding="utf-8"))
        preferences["academic_events"] = [
            {"date": event_date.isoformat(), "title": title, "category": "Kalender", "description": title}
            for event_date, title in zip(
                upcoming_dates,
                ("Ketiga", "Paling Dekat", "Sudah Lewat", "Kedua", "Di Luar Tiga Terdekat"),
            )
        ]
        self.content_file.write_text(json.dumps(preferences, ensure_ascii=False), encoding="utf-8")

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        self.assertIn('href="/akademik#kalender-akademik"', rendered)
        self.assertIn("Paling Dekat", rendered)
        self.assertIn("Kedua", rendered)
        self.assertIn("Ketiga", rendered)
        self.assertNotIn("Sudah Lewat", rendered)
        self.assertNotIn("Di Luar Tiga Terdekat", rendered)
        self.assertNotIn("Peringatan Hari Santri Nasional", rendered)
        self.assertEqual(rendered.count('class="event-card"'), 3)
        self.assertLess(rendered.index("Paling Dekat"), rendered.index("Kedua"))
        self.assertLess(rendered.index("Kedua"), rendered.index("Ketiga"))

    def test_profile_navigation_dropdown_and_siapik_portal_link(self):
        legacy_preferences = json.loads(self.content_file.read_text(encoding="utf-8"))
        legacy_preferences["site"]["login_label"] = "Masuk"
        legacy_preferences["site"]["login_url"] = "/masuk"
        self.content_file.write_text(json.dumps(legacy_preferences, ensure_ascii=False), encoding="utf-8")

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        self.assertIn('data-nav-dropdown', rendered)
        self.assertIn('href="/profil#sejarah">Sejarah</a>', rendered)
        self.assertIn('href="/profil#visi-misi">Visi misi</a>', rendered)
        self.assertIn('href="/profil#masyayikh">Pendiri &amp; Pengasuh</a>', rendered)
        self.assertIn('href="https://siapik.com">Masuk Portal Santri</a>', rendered)
        migrated_preferences = json.loads(self.content_file.read_text(encoding="utf-8"))
        self.assertEqual(migrated_preferences["site"]["login_url"], "https://siapik.com")
        self.assertEqual(migrated_preferences["site"]["login_label"], "Masuk Portal Santri")

    def test_musyawarah_profile_copy_migrates_once_and_preserves_admin_media(self):
        seed = json.loads((ROOT / "data" / "site.json").read_text(encoding="utf-8"))
        legacy = copy.deepcopy(seed)
        legacy.pop("_profile_content_revision", None)
        legacy["site"]["description"] = "Deskripsi lama"
        legacy["hero"]["title"] = "Judul lama"
        legacy["hero"]["image_alt"] = "Label hero lama"
        legacy["stats"] = [{"value": "1095", "label": "Santri Aktif"}]
        legacy["history"]["intro"] = "Ringkasan sejarah lama"
        legacy["history"]["image_alt"] = "Elyasir Independent School ( EYIS )"
        legacy["profile"]["vision"] = "Visi lama"
        legacy["profile"]["history_paragraphs"] = ["Sejarah lama"]
        legacy["profile"]["image"] = "https://res.cloudinary.com/demo/image/upload/v123/ppru/site/profile"
        legacy["history"]["image"] = "https://res.cloudinary.com/demo/image/upload/v123/ppru/site/history"
        legacy["faq"][1]["answer"] = "Jawaban program lama"
        preserved_logo = "https://res.cloudinary.com/demo/image/upload/c_limit,h_1600,q_auto:good,w_1600,f_auto/v123/ppru/programs/smp-logo"
        legacy["programs"] = [
            {"id": "legacy-formal", "number": "02", "title": "SPM (Muadalah)", "category": "Formal", "description": "Lama", "education_type": "formal", "icon": "school", "color": "orange", "logo": preserved_logo, "kitabs": ["Kurikulum"]},
            {"id": "legacy-diniyah", "number": "03", "title": "Diniyah Takmiliyah", "category": "Nonformal", "description": "Lama", "education_type": "non_formal", "icon": "book", "color": "blue", "logo": "", "kitabs": ["Kitab"]},
            {"id": "legacy-tahfidz", "number": "01", "title": "Tahfidzul Qur’an", "category": "Tahfidz", "description": "Lama", "education_type": "non_formal", "icon": "quran", "color": "green", "logo": "", "kitabs": ["Al-Qur’an"]},
            {"id": "custom-program", "title": "Program Tambahan Admin", "category": "Nonformal", "description": "Konten khusus pengelola", "education_type": "non_formal", "kitabs": ["Materi khusus"]},
        ]
        self.content_file.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

        response = self.client.get("/profil")
        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        self.assertIn("Pada 27 Sya‘ban 1404 H (1983 M)", rendered)
        self.assertIn("Menjadi lembaga pendidikan dan pengajaran agama Islam", rendered)
        self.assertIn("K.H. Bahaudin Al Yasir", rendered)
        self.assertIn("Musabaqah Qira’atil Kutub", rendered)

        migrated = json.loads(self.content_file.read_text(encoding="utf-8"))
        self.assertEqual(migrated["_profile_content_revision"], "musyawarah-profil-2026-v2")
        self.assertEqual(migrated["site"]["description"], seed["site"]["description"])
        self.assertEqual(migrated["hero"]["title"], seed["hero"]["title"])
        self.assertEqual(migrated["hero"]["image_alt"], seed["hero"]["image_alt"])
        self.assertEqual(migrated["history"]["image_alt"], seed["history"]["image_alt"])
        self.assertEqual(migrated["stats"], seed["stats"])
        self.assertEqual(migrated["faq"][1]["answer"], seed["faq"][1]["answer"])
        self.assertEqual(migrated["profile"]["image"], legacy["profile"]["image"])
        self.assertEqual(migrated["history"]["image"], legacy["history"]["image"])
        formal_program = next(item for item in migrated["programs"] if item["title"] == "Pendidikan Formal SMP & SMK")
        self.assertEqual(formal_program["id"], "legacy-formal")
        self.assertEqual(formal_program["logo"], preserved_logo)
        self.assertEqual(len({item["id"] for item in migrated["programs"]}), len(migrated["programs"]))
        self.assertIn("Program Tambahan Admin", [item["title"] for item in migrated["programs"]])

        migrated["profile"]["vision"] = "Perubahan admin setelah pembaruan."
        self.content_file.write_text(json.dumps(migrated, ensure_ascii=False), encoding="utf-8")
        later_response = self.client.get("/profil")
        self.assertEqual(later_response.status_code, 200)
        self.assertIn("Perubahan admin setelah pembaruan.", later_response.get_data(as_text=True))

    def test_madrasah_diniyah_details_link_and_academic_admin_editing(self):
        legacy_content = json.loads(self.content_file.read_text(encoding="utf-8"))
        legacy_content.pop("_academic_program_details_revision", None)
        madrasah = next(item for item in legacy_content["programs"] if item["title"] == "Madrasah Diniyah")
        madrasah.pop("class_details", None)
        madrasah["description"] = "Keterangan Madrasah Diniyah lama."
        self.content_file.write_text(json.dumps(legacy_content, ensure_ascii=False), encoding="utf-8")

        overview = self.client.get("/akademik")
        self.assertEqual(overview.status_code, 200)
        self.assertIn('href="/akademik/program/madrasah-diniyah"', overview.get_data(as_text=True))
        detail = self.client.get("/akademik/program/madrasah-diniyah")
        self.assertEqual(detail.status_code, 200)
        detail_html = detail.get_data(as_text=True)
        self.assertIn("Kelas dan kitab", detail_html)
        self.assertIn("Fathul Qorib", detail_html)
        self.assertIn("Ta’limul Muta’allim", detail_html)
        self.assertIn("06.30–08.30", detail_html)
        self.assertIn("Tafsir Al-Qur’an", detail_html)
        self.assertIn("Syawir dilaksanakan selepas salat Isya hingga pukul 23.00.", detail_html)
        self.assertIn('href="/akademik/program/madrasah-diniyah"', self.client.get("/psb").get_data(as_text=True))

        migrated = json.loads(self.content_file.read_text(encoding="utf-8"))
        self.assertEqual(migrated["_academic_program_details_revision"], "madrasah-diniyah-details-2026-v2")
        migrated_madrasah = next(item for item in migrated["programs"] if item["title"] == "Madrasah Diniyah")
        self.assertEqual(len(migrated_madrasah["class_details"]), 4)
        self.assertIn("06.30–08.30", migrated_madrasah["description"])

        with self.client.session_transaction() as admin_session:
            admin_session["admin_authenticated"] = True
            admin_session["admin_role"] = "main"
        madrasah_panel = self.client.get("/admin/akademik?tab=non_formal")
        self.assertEqual(madrasah_panel.status_code, 200)
        self.assertIn("Edit kelas Madrasah", madrasah_panel.get_data(as_text=True))
        programs = migrated["programs"]
        madrasah_index = next(index for index, item in enumerate(programs) if item["title"] == "Madrasah Diniyah")
        item_id = str(migrated_madrasah.get("id") or migrated_madrasah.get("number") or madrasah_index)
        edit_response = self.client.get(f"/admin/akademik/program/{item_id}/edit")
        self.assertEqual(edit_response.status_code, 200)
        edit_html = edit_response.get_data(as_text=True)
        self.assertIn('name="class_details"', edit_html)
        self.assertIn("Kelas Madrasah Diniyah dan kitabnya", edit_html)
        self.assertIn("Satu kelas per baris", edit_html)
        csrf_token = re.search(r'name="csrf_token" value="([^"]+)"', edit_html).group(1)
        updated = self.client.post(
            "/admin/akademik/program/simpan",
            data={
                "csrf_token": csrf_token,
                "item_id": item_id,
                "title": migrated_madrasah["title"],
                "category": migrated_madrasah["category"],
                "education_type": "non_formal",
                "description": migrated_madrasah["description"],
                "kitabs_label": migrated_madrasah["kitabs_label"],
                "kitabs": "I’dadiyah\nIbtida\nTsanawi\nAliyah",
                "class_details": "Ibtida | Contoh yang diedit di Admin Akademik | Safinatun Najah; Jurumiyah",
                "info_url": "/kontak",
                "icon": migrated_madrasah["icon"],
                "program_logo": migrated_madrasah.get("logo", ""),
            },
        )
        self.assertEqual(updated.status_code, 302)
        saved_detail = self.client.get("/akademik/program/madrasah-diniyah")
        self.assertIn("Contoh yang diedit di Admin Akademik", saved_detail.get_data(as_text=True))
        self.assertIn("Safinatun Najah", saved_detail.get_data(as_text=True))

    def test_madrasah_schedule_revision_preserves_prior_admin_class_edits(self):
        content = json.loads(self.content_file.read_text(encoding="utf-8"))
        content["_academic_program_details_revision"] = "madrasah-diniyah-details-2026-v1"
        madrasah = next(item for item in content["programs"] if item["title"] == "Madrasah Diniyah")
        tsanawi = next(item for item in madrasah["class_details"] if item["name"] == "Tsanawi")
        aliyah = next(item for item in madrasah["class_details"] if item["name"] == "Aliyah")
        tsanawi["description"] = "Catatan jadwal khusus dari Admin Akademik."
        tsanawi["kitabs"] = ["Kitab pilihan admin"]
        aliyah["description"] = "Syawir selepas Isya sampai 23.00."
        madrasah["class_details"].append({
            "name": "Kelas tambahan admin",
            "description": "Rincian tambahan yang harus tetap ada.",
            "kitabs_label": "Kitab pilihan",
            "kitabs": ["Kitab Admin"],
        })
        self.content_file.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")

        page = self.client.get("/akademik/program/madrasah-diniyah")
        self.assertEqual(page.status_code, 200)
        migrated = json.loads(self.content_file.read_text(encoding="utf-8"))
        migrated_madrasah = next(item for item in migrated["programs"] if item["title"] == "Madrasah Diniyah")
        migrated_tsanawi = next(item for item in migrated_madrasah["class_details"] if item["name"] == "Tsanawi")
        migrated_aliyah = next(item for item in migrated_madrasah["class_details"] if item["name"] == "Aliyah")
        self.assertEqual(
            migrated_tsanawi["description"],
            "Catatan jadwal khusus dari Admin Akademik; Syawir dilaksanakan selepas salat Isya hingga pukul 23.00.",
        )
        self.assertEqual(migrated_tsanawi["kitabs"], ["Kitab pilihan admin"])
        self.assertEqual(migrated_aliyah["description"], "Syawir selepas Isya sampai 23.00.")
        self.assertIn("Kelas tambahan admin", [item["name"] for item in migrated_madrasah["class_details"]])
        self.assertEqual(migrated["_academic_program_details_revision"], "madrasah-diniyah-details-2026-v2")

    def test_profile_admin_saves_single_history_textarea_and_real_youtube_embed(self):
        with self.client.session_transaction() as admin_session:
            admin_session["admin_authenticated"] = True
            admin_session["_csrf_token"] = "profile-csrf-token"

        admin_page = self.client.get("/admin?tab=profile")
        admin_html = admin_page.get_data(as_text=True)
        self.assertEqual(admin_page.status_code, 200)
        self.assertIn('data-live-preview-frame', admin_html)
        self.assertIn('name="history_paragraphs"', admin_html)
        history_textarea = re.search(r'<textarea name="history_paragraphs" rows="10">(.*?)</textarea>', admin_html, re.S)
        self.assertIsNotNone(history_textarea)
        self.assertIn("\n\n", html.unescape(history_textarea.group(1)))
        self.assertNotIn('name="history_paragraph_0"', admin_html)
        self.assertIn('name="video_embed_url"', admin_html)
        self.assertIn('name="profile_leadership_title"', admin_html)
        self.assertIn('name="profile_leadership_note"', admin_html)
        default_profile = self.client.get("/profil").get_data(as_text=True)
        self.assertIn("Video profil belum tersedia.", default_profile)
        self.assertNotIn("play-button", default_profile)

        response = self.client.post(
            "/admin/save",
            data={
                "csrf_token": "profile-csrf-token",
                "component": "profile",
                "profile_title": "Profil Pesantren",
                "profile_leadership_title": "Penerus Kepemimpinan",
                "profile_leadership_note": "Keterangan kepemimpinan yang diperbarui.",
                "history_paragraphs": "Sejarah pertama dengan\nbaris lanjutan.\n\nSejarah kedua.",
                "video_embed_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            },
        )
        self.assertEqual(response.status_code, 302)
        saved_preferences = json.loads(self.content_file.read_text(encoding="utf-8"))
        self.assertEqual(
            saved_preferences["profile"]["history_paragraphs"],
            ["Sejarah pertama dengan baris lanjutan.", "Sejarah kedua."],
        )
        self.assertEqual(
            saved_preferences["profile"]["video_embed_url"],
            "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
        )
        self.assertEqual(saved_preferences["profile"]["leadership_note"], "Keterangan kepemimpinan yang diperbarui.")

        profile_page = self.client.get("/profil")
        profile_html = profile_page.get_data(as_text=True)
        self.assertIn('src="https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"', profile_html)
        self.assertIn('id="sejarah"', profile_html)
        self.assertIn('id="visi-misi"', profile_html)
        self.assertIn('id="masyayikh"', profile_html)
        self.assertIn("Penerus Kepemimpinan", profile_html)
        self.assertIn("Keterangan kepemimpinan yang diperbarui.", profile_html)
        self.assertNotIn("play-button", profile_html)

        self.client.post(
            "/admin/save",
            data={
                "csrf_token": "profile-csrf-token",
                "component": "profile",
                "video_embed_url": "https://evil.example/video/unsafe-id",
            },
        )
        saved_after_invalid_url = json.loads(self.content_file.read_text(encoding="utf-8"))
        self.assertEqual(
            saved_after_invalid_url["profile"]["video_embed_url"],
            "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
        )

    def test_profile_vision_and_mission_use_textareas_and_render_numbered_missions(self):
        with self.client.session_transaction() as admin_session:
            admin_session["admin_authenticated"] = True
            admin_session["_csrf_token"] = "vision-mission-csrf-token"

        admin_html = self.client.get("/admin?tab=profile").get_data(as_text=True)
        self.assertRegex(admin_html, r'<textarea name="profile_vision" rows="3">')
        self.assertRegex(admin_html, r'<textarea name="profile_mission_items" rows="6">')
        self.assertNotIn('name="mission_0"', admin_html)

        response = self.client.post(
            "/admin/save",
            data={
                "csrf_token": "vision-mission-csrf-token",
                "component": "profile",
                "profile_vision": "Menjadi pesantren yang unggul.",
                "profile_mission_items": "1. Membangun akhlak.\n2) Menguatkan ilmu.\n• Mengabdi kepada masyarakat.",
            },
        )
        self.assertEqual(response.status_code, 302)
        saved_profile = json.loads(self.content_file.read_text(encoding="utf-8"))["profile"]
        self.assertEqual(saved_profile["vision"], "Menjadi pesantren yang unggul.")
        self.assertEqual(
            saved_profile["mission"],
            ["Membangun akhlak.", "Menguatkan ilmu.", "Mengabdi kepada masyarakat."],
        )

        profile_html = self.client.get("/profil").get_data(as_text=True)
        mission_list = re.search(r'<article class="mission-card".*?<ol>(.*?)</ol>', profile_html, re.S)
        self.assertIsNotNone(mission_list)
        self.assertIn("<li>Membangun akhlak.</li>", mission_list.group(1))
        self.assertIn("<li>Menguatkan ilmu.</li>", mission_list.group(1))
        self.assertIn("<li>Mengabdi kepada masyarakat.</li>", mission_list.group(1))

    def test_profile_admin_live_preview_does_not_save_unsaved_changes(self):
        with self.client.session_transaction() as admin_session:
            admin_session["admin_authenticated"] = True
            admin_session["_csrf_token"] = "preview-csrf-token"

        saved_before = self.content_file.read_text(encoding="utf-8")
        response = self.client.post(
            "/admin/live-preview",
            data={
                "csrf_token": "preview-csrf-token",
                "component": "profile",
                "profile_title": "Judul Pratinjau Saja",
                "history_paragraphs": "Cerita pratinjau satu.\n\nCerita pratinjau dua.",
                "video_embed_url": "https://www.youtube.com/embed/dQw4w9WgXcQ",
            },
        )
        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        self.assertIn("Judul Pratinjau Saja", rendered)
        self.assertIn("Cerita pratinjau satu.", rendered)
        self.assertIn('src="https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"', rendered)
        self.assertEqual(self.content_file.read_text(encoding="utf-8"), saved_before)

    def test_youtube_embed_url_only_accepts_youtube_links(self):
        self.assertEqual(
            _youtube_embed_url("https://youtu.be/dQw4w9WgXcQ", ""),
            "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
        )
        self.assertEqual(_youtube_embed_url("https://evil.example/watch?v=dQw4w9WgXcQ", ""), "")
        self.assertEqual(_split_paragraphs("  first\nline\n\n\nsecond  "), ["first line", "second"])

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

        expected_runtime_preferences = json.loads(self.content_file.read_text(encoding="utf-8"))
        expected_runtime_news = json.loads(self.news_file.read_text(encoding="utf-8"))
        expected_runtime_gallery = json.loads(self.gallery_file.read_text(encoding="utf-8"))
        content = store.load()
        self.assertEqual(content["site"]["name"], expected_runtime_preferences["site"]["name"])
        self.assertEqual(content["news"], expected_runtime_news)
        self.assertEqual(content["gallery"], expected_runtime_gallery)
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
        self.assertEqual(json.loads(self.news_file.read_text(encoding="utf-8")), [{"slug": "persisted-from-mongodb"}])
        self.assertNotIn("news", json.loads(self.content_file.read_text(encoding="utf-8")))
        self.assertNotIn("gallery", json.loads(self.content_file.read_text(encoding="utf-8")))

    def test_local_mongodb_outage_falls_back_to_json_and_surfaces_fallback_state(self):
        class FailingCollection:
            def find_one(self, _query):
                raise PyMongoError("simulated Atlas outage")

            def replace_one(self, _query, _replacement, upsert=False):
                raise PyMongoError("simulated Atlas outage")

        store = MongoPortalStore(
            preferences_file=self.content_file,
            news_file=self.news_file,
            gallery_file=self.gallery_file,
            seed_preferences_file=ROOT / "data" / "site.json",
            seed_news_file=ROOT / "data" / "berita.json",
            seed_gallery_file=ROOT / "data" / "gallery.json",
            mongo_uri="mongodb://atlas.example.invalid",
            document_id="ppru:local",
            mirror_json=True,
            allow_json_fallback=True,
        )
        store._collection = FailingCollection()
        content = store.load()
        self.assertTrue(store.json_fallback_active)
        content["stats"][0]["value"] = "321"
        store.save(content)
        self.assertTrue(store.json_fallback_active)
        self.assertEqual(json.loads(self.content_file.read_text(encoding="utf-8"))["stats"][0]["value"], "321")

    def test_local_admin_shows_json_fallback_popup_when_atlas_is_down(self):
        class FailingCollection:
            def find_one(self, _query):
                raise PyMongoError("simulated Atlas outage")

        app = create_app({
            "TESTING": True,
            "VERCEL": False,
            "MONGODB_URI": "mongodb://atlas.example.invalid",
            "CONTENT_FILE": self.content_file,
            "NEWS_FILE": self.news_file,
            "GALLERY_FILE": self.gallery_file,
            "SECRET_KEY": "test-secret-key",
        })
        client = app.test_client()
        with client.session_transaction() as admin_session:
            admin_session["admin_authenticated"] = True
            admin_session["_csrf_token"] = "fallback-csrf-token"

        with patch.object(MongoPortalStore, "_get_collection", return_value=FailingCollection()):
            response = client.get("/admin?tab=profile")

        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        self.assertIn('role="alertdialog"', rendered)
        self.assertIn("mongo eror sementara pakai preferensi.json", rendered)
        self.assertIn("belum tersinkron ke MongoDB Atlas", rendered)

    def test_mongodb_store_can_skip_ephemeral_vercel_json_mirror(self):
        class MemoryCollection:
            def replace_one(self, _query, replacement, upsert=False):
                self.document = dict(replacement)
                return type("WriteResult", (), {"acknowledged": True})()

        original_preferences = self.content_file.read_bytes()
        original_news = self.news_file.read_bytes()
        original_gallery = self.gallery_file.read_bytes()
        store = MongoPortalStore(
            preferences_file=self.content_file,
            news_file=self.news_file,
            gallery_file=self.gallery_file,
            seed_preferences_file=ROOT / "data" / "site.json",
            seed_news_file=ROOT / "data" / "berita.json",
            seed_gallery_file=ROOT / "data" / "gallery.json",
            mongo_uri="mongodb://atlas.example.invalid",
            document_id="ppru:production",
            mirror_json=False,
            allow_json_fallback=False,
        )
        store._collection = MemoryCollection()
        store.save(self.content)
        self.assertEqual(self.content_file.read_bytes(), original_preferences)
        self.assertEqual(self.news_file.read_bytes(), original_news)
        self.assertEqual(self.gallery_file.read_bytes(), original_gallery)

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
        self.assertIn('class="theme-toggle"', response_text)
        self.assertIn("css/theme.css?v=1", response_text)
        self.assertIn("MongoDB Atlas sedang tidak dapat dihubungi", response_text)
        self.assertIn("mongo eror sementara pakai preferensi.json", response_text)
        self.assertIn("Perubahan belum tersimpan", response_text)
        self.assertIn("file JSON deployment tidak persisten", response_text)
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
        for program in self.content["programs"][:3]:
            self.assertIn(program["title"], rendered)
        academic_rendered = html.unescape(self.client.get("/akademik").get_data(as_text=True))
        for program in self.content["programs"]:
            self.assertIn(program["title"], academic_rendered)

    def test_home_program_cards_match_the_three_admin_selected_psb_slots(self):
        preferences = json.loads(self.content_file.read_text(encoding="utf-8"))
        selected_numbers = ["04", "02", "06"]
        preferences.setdefault("admission", {})["program_slots"] = selected_numbers
        self.content_file.write_text(json.dumps(preferences, ensure_ascii=False), encoding="utf-8")
        programs_by_number = {item["number"]: item for item in preferences["programs"]}

        home_response = self.client.get("/")
        psb_response = self.client.get("/psb")
        self.assertEqual(home_response.status_code, 200)
        self.assertEqual(psb_response.status_code, 200)
        home_html = html.unescape(home_response.get_data(as_text=True))
        home_program_section = home_html.split('<section class="section programs-section" id="akademik">', 1)[1].split("</section>", 1)[0]
        psb_html = html.unescape(psb_response.get_data(as_text=True))
        psb_program_section = psb_html.split('class="admission-programs">', 1)[1].split("</div></div></section>", 1)[0]

        self.assertEqual(psb_program_section.count("<article>"), 3)
        expected_titles = [programs_by_number[number]["title"] for number in selected_numbers]
        for title in expected_titles:
            with self.subTest(title=title):
                self.assertIn(title, home_program_section)
                self.assertIn(title, psb_program_section)
        self.assertEqual(
            [home_program_section.index(title) for title in expected_titles],
            sorted(home_program_section.index(title) for title in expected_titles),
        )
        self.assertNotIn(programs_by_number["01"]["title"], home_program_section)

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

    def test_news_summary_uses_article_text_and_appends_ellipsis_at_the_160_character_limit(self):
        short_summary = news_summary({
            "body_html": "<p>Kegiatan belajar santri berlangsung dengan tertib.</p>",
            "excerpt": "Ringkasan lama yang seharusnya tidak dipakai.",
        })
        self.assertEqual(short_summary, "Kegiatan belajar santri berlangsung dengan tertib.")

        long_body = "<p>" + ("Madrasah mengadakan kegiatan keilmuan bagi seluruh santri di lingkungan pesantren. " * 8) + "</p>"
        long_summary = news_summary({"body_html": long_body, "excerpt": "Ringkasan manual lama."})
        self.assertLessEqual(len(long_summary), 160)
        self.assertTrue(long_summary.endswith("..."))
        self.assertNotIn("Ringkasan manual lama", long_summary)

    def test_news_rich_text_keeps_responsive_cloudinary_images_and_removes_unsafe_markup(self):
        cloudinary_image = "https://res.cloudinary.com/demo/image/upload/v123/ppru/news/inline-photo.jpg"
        sanitized = sanitize_rich_text(
            '<p class="article-image" style="float:left"><img '
            f'src="{cloudinary_image}" alt="Foto kegiatan" onerror="alert(1)"></p>'
            '<script>alert(1)</script><img src="https://example.invalid/unsafe.jpg">'
        )
        self.assertIn('class="article-image"', sanitized)
        self.assertIn(cloudinary_image, sanitized)
        self.assertIn('alt="Foto kegiatan"', sanitized)
        self.assertNotIn("style=", sanitized)
        self.assertNotIn("onerror", sanitized)
        self.assertNotIn("<script", sanitized)
        self.assertNotIn("https://example.invalid/unsafe.jpg", sanitized)

    def test_article_detail_and_missing_article(self):
        slug = self.content["news"][0]["slug"]
        response = self.client.get(f"/berita/{slug}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.content["news"][0]["title"].encode(), response.data)
        self.assertIn("1 kali dilihat".encode(), response.data)
        rendered = response.get_data(as_text=True)
        self.assertIn('class="article-breadcrumbs"', rendered)
        self.assertIn('class="article-main"', rendered)
        self.assertIn('class="article-sidebar"', rendered)
        self.assertLess(rendered.index('class="article-main"'), rendered.index('class="article-sidebar"'))
        self.assertNotIn('class="page-banner', rendered)
        self.assertIn('data-share-whatsapp', rendered)
        self.assertIn('data-share-instagram', rendered)
        self.assertIn('data-copy-article-link', rendered)
        self.assertIn("Berita Terkini", rendered)
        saved_news = json.loads(self.news_file.read_text(encoding="utf-8"))
        viewed_post = next(item for item in saved_news if item["slug"] == slug)
        self.assertEqual(viewed_post["views"], 1)

        missing = self.client.get("/berita/tidak-ada")
        self.assertEqual(missing.status_code, 404)
        self.assertIn("Halaman ini".encode(), missing.data)

    def test_global_dark_mode_is_fixed_persistent_and_light_by_default(self):
        response = self.client.get("/")
        rendered = response.get_data(as_text=True)
        self.assertIn('class="theme-toggle"', rendered)
        self.assertIn('aria-label="Aktifkan mode gelap"', rendered)
        self.assertIn("css/theme.css?v=1", rendered)
        self.assertIn("js/theme.js?v=1", rendered)
        self.assertIn('localStorage.getItem("ppru-theme") === "dark"', rendered)

        theme_js = self.client.get("/static/js/theme.js")
        theme_css = self.client.get("/static/css/theme.css")
        self.assertEqual(theme_js.status_code, 200)
        self.assertEqual(theme_css.status_code, 200)
        theme_js_source = theme_js.get_data(as_text=True)
        theme_css_source = theme_css.get_data(as_text=True)
        self.assertIn('localStorage.setItem(storageKey, dark ? "dark" : "light")', theme_js_source)
        self.assertIn('window.addEventListener("storage"', theme_js_source)
        self.assertIn("position: fixed", theme_css_source)
        self.assertIn("right: calc(18px + env(safe-area-inset-right))", theme_css_source)
        self.assertIn("bottom: calc(18px + env(safe-area-inset-bottom))", theme_css_source)
        self.assertIn(':root[data-theme="dark"]', theme_css_source)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 295px", theme_css_source)
        self.assertIn("@media (max-width: 720px)", theme_css_source)
        self.assertIn("max-width: 100%", theme_css_source)
        theme_js.close()
        theme_css.close()

    def test_unknown_route_renders_not_found_page(self):
        response = self.client.get("/halaman-tidak-ada")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Kembali ke Home".encode(), response.data)

    def test_main_admin_manages_academic_user_and_academic_login_is_isolated(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            preferences_path = root / "preferensi.json"
            shutil.copyfile(ROOT / "data" / "site.json", preferences_path)
            app = create_app({
                "TESTING": True,
                "CONTENT_FILE": preferences_path,
                "NEWS_FILE": root / "berita.json",
                "GALLERY_FILE": root / "gallery.json",
                "ADMIN_PASSWORD": "main-admin-secret",
                "SECRET_KEY": "test-secret-key",
            })
            main_client = app.test_client()
            login_page = main_client.get("/admin")
            login_page_html = login_page.get_data(as_text=True)
            token = re.search(r'name="csrf_token" value="([^"]+)"', login_page_html).group(1)
            self.assertIn("Admin Pendidikan/Akademik", login_page_html)
            main_client.post("/admin/login", data={"csrf_token": token, "password": "main-admin-secret"})

            users_page = main_client.get("/admin?tab=users")
            users_html = users_page.get_data(as_text=True)
            self.assertIn("Kelola User Admin", users_html)
            self.assertIn("Akun Admin Akademik belum dibuat", users_html)
            self.assertNotIn('data-admin-tab="programs"', users_html)
            token = re.search(r'name="csrf_token" value="([^"]+)"', users_html).group(1)
            password = "education-admin-password"
            saved_users = main_client.post(
                "/admin/users/save",
                data={
                    "csrf_token": token,
                    "username": "admin-pendidikan",
                    "password": password,
                    "password_confirm": password,
                    "active": "1",
                },
                follow_redirects=True,
            )
            self.assertEqual(saved_users.status_code, 200)
            self.assertIn(b"Akun Admin Akademik aktif", saved_users.data)
            saved_preferences = json.loads(preferences_path.read_text(encoding="utf-8"))
            account = saved_preferences["admin_users"]["academic"]
            self.assertNotIn(account["password_hash"].encode(), saved_users.data)
            self.assertNotEqual(account["password_hash"], password)
            self.assertTrue(account["password_hash"].startswith("scrypt:"))
            self.assertNotIn(password, preferences_path.read_text(encoding="utf-8"))
            self.assertNotIn(account["password_hash"].encode(), main_client.get("/").data)

            logout_page = main_client.get("/admin?tab=users")
            token = re.search(r'name="csrf_token" value="([^"]+)"', logout_page.get_data(as_text=True)).group(1)
            main_client.post("/admin/logout", data={"csrf_token": token})
            academic_client = app.test_client()
            login_page = academic_client.get("/admin")
            token = re.search(r'name="csrf_token" value="([^"]+)"', login_page.get_data(as_text=True)).group(1)
            missing_username = academic_client.post(
                "/admin/login",
                data={"csrf_token": token, "password": password},
            )
            self.assertEqual(missing_username.status_code, 401)
            login_response = academic_client.post(
                "/admin/login",
                data={"csrf_token": token, "username": "admin-pendidikan", "password": password},
            )
            self.assertEqual(login_response.status_code, 302)
            self.assertEqual(login_response.location, "/admin/akademik")
            dashboard = academic_client.get("/admin/akademik")
            self.assertEqual(dashboard.status_code, 200)
            self.assertIn(b"Program Pendidikan", dashboard.data)
            self.assertIn(b"Kalender Akademik", dashboard.data)
            self.assertIn(b"Pengumuman / Berita", dashboard.data)
            self.assertEqual(academic_client.get("/admin?tab=brand").location, "/admin/akademik")
            self.assertEqual(academic_client.get("/admin/berita/baru").status_code, 403)

            announcement_form = academic_client.get("/admin/akademik/pengumuman/baru")
            self.assertEqual(announcement_form.status_code, 200)
            token = re.search(r'name="csrf_token" value="([^"]+)"', announcement_form.get_data(as_text=True)).group(1)
            announcement_image = "https://res.cloudinary.com/demo/image/upload/c_limit,h_1600,q_auto:good,w_1600,f_auto/v123/ppru/news/announcement"
            announcement_response = academic_client.post(
                "/admin/akademik/pengumuman/simpan",
                data={
                    "csrf_token": token,
                    "title": "Pengumuman Ujian",
                    "slug": "",
                    "category": "Pendidikan",
                    "excerpt": "Jadwal ujian semester.",
                    "image_alt": "Informasi ujian",
                    "image": announcement_image,
                    "status": "published",
                    "published_at": "",
                    "body_html": "<p>Ujian dimulai <strong>Senin</strong>.</p>",
                },
                follow_redirects=True,
            )
            self.assertEqual(announcement_response.status_code, 200)
            self.assertIn(b"Pengumuman Ujian", announcement_response.data)
            self.assertIn(b"Pengumuman Ujian", academic_client.get("/berita").data)

            root_client = app.test_client()
            login_page = root_client.get("/admin")
            token = re.search(r'name="csrf_token" value="([^"]+)"', login_page.get_data(as_text=True)).group(1)
            root_client.post("/admin/login", data={"csrf_token": token, "password": "main-admin-secret"})
            users_page = root_client.get("/admin?tab=users")
            token = re.search(r'name="csrf_token" value="([^"]+)"', users_page.get_data(as_text=True)).group(1)
            root_client.post(
                "/admin/users/save",
                data={"csrf_token": token, "username": "admin-pendidikan", "active": "0"},
            )
            revoked = academic_client.get("/admin/akademik")
            self.assertEqual(revoked.status_code, 302)
            self.assertEqual(revoked.location, "/admin")

    def test_legacy_academic_program_categories_are_normalized_into_types(self):
        legacy_content = json.loads(self.content_file.read_text(encoding="utf-8"))
        for program in legacy_content["programs"]:
            program.pop("education_type", None)
        self.content_file.write_text(json.dumps(legacy_content, ensure_ascii=False), encoding="utf-8")

        response = self.client.get("/akademik")
        self.assertEqual(response.status_code, 200)
        saved_programs = json.loads(self.content_file.read_text(encoding="utf-8"))["programs"]
        types_by_title = {program["title"]: program["education_type"] for program in saved_programs}
        self.assertEqual(types_by_title["Pendidikan Formal SMP & SMK"], "formal")
        self.assertEqual(types_by_title["Takhassus Tahfidzul Qur’an"], "non_formal")
        self.assertEqual(types_by_title["Madrasah Diniyah"], "non_formal")

    def test_academic_program_menus_separate_formal_and_nonformal_programs(self):
        overview = self.client.get("/akademik")
        self.assertEqual(overview.status_code, 200)
        overview_html = overview.get_data(as_text=True)
        self.assertIn("Pendidikan Formal", overview_html)
        self.assertIn("Pendidikan Non Formal", overview_html)
        self.assertIn('href="/akademik/formal"', overview_html)
        self.assertIn('href="/akademik/non-formal"', overview_html)

        formal_page = self.client.get("/akademik/formal")
        self.assertEqual(formal_page.status_code, 200)
        formal_html = formal_page.get_data(as_text=True)
        self.assertIn("Pendidikan Formal SMP &amp; SMK", formal_html)
        self.assertNotIn("Takhassus Tahfidzul Qur’an", formal_html)
        self.assertNotIn("Madrasah Diniyah", formal_html)

        nonformal_page = self.client.get("/akademik/non-formal")
        self.assertEqual(nonformal_page.status_code, 200)
        nonformal_html = nonformal_page.get_data(as_text=True)
        self.assertIn("Takhassus Tahfidzul Qur’an", nonformal_html)
        self.assertIn("Madrasah Diniyah", nonformal_html)
        self.assertNotIn("Pendidikan Formal SMP &amp; SMK", nonformal_html)
        self.assertEqual(self.client.get("/akademik/unknown").status_code, 404)

        with self.client.session_transaction() as admin_session:
            admin_session["admin_authenticated"] = True
            admin_session["admin_role"] = "main"
        formal_admin = self.client.get("/admin/akademik?tab=formal")
        self.assertEqual(formal_admin.status_code, 200)
        self.assertIn(b"Pendidikan Formal SMP &amp; SMK", formal_admin.data)
        self.assertNotIn("Takhassus Tahfidzul Qur’an".encode(), formal_admin.data)
        nonformal_admin = self.client.get("/admin/akademik?tab=non_formal")
        self.assertEqual(nonformal_admin.status_code, 200)
        self.assertIn("Takhassus Tahfidzul Qur’an".encode(), nonformal_admin.data)
        self.assertNotIn(b"Pendidikan Formal SMP &amp; SMK", nonformal_admin.data)

        new_nonformal = self.client.get("/admin/akademik/program/baru?education_type=non_formal")
        self.assertEqual(new_nonformal.status_code, 200)
        self.assertIn(b'<option value="non_formal" selected>', new_nonformal.data)
        self.assertIn(b'name="kitabs_label"', new_nonformal.data)
        self.assertIn("Kitab, materi, atau jenjang program".encode(), new_nonformal.data)
        token = re.search(r'name="csrf_token" value="([^"]+)"', new_nonformal.get_data(as_text=True)).group(1)
        saved_nonformal = self.client.post(
            "/admin/akademik/program/simpan",
            data={
                "csrf_token": token,
                "title": "Kajian Kitab Dasar",
                "category": "Program diniyah",
                "education_type": "non_formal",
                "description": "Pembelajaran diniyah untuk santri.",
                "kitabs": "Safinatun Najah",
                "info_url": "/kontak",
            },
        )
        self.assertEqual(saved_nonformal.status_code, 302)
        self.assertEqual(saved_nonformal.location, "/admin/akademik?tab=non_formal&saved=1")
        saved_programs = json.loads(self.content_file.read_text(encoding="utf-8"))["programs"]
        saved_item = next(item for item in saved_programs if item["title"] == "Kajian Kitab Dasar")
        self.assertEqual(saved_item["education_type"], "non_formal")
        self.assertIn(b"Kajian Kitab Dasar", self.client.get("/akademik/non-formal").data)

    def test_academic_program_logo_upload_and_fontawesome_fallback(self):
        with self.client.session_transaction() as admin_session:
            admin_session["admin_authenticated"] = True
            admin_session["admin_role"] = "main"
            admin_session["_csrf_token"] = "program-logo-csrf-token"

        form_response = self.client.get("/admin/akademik/program/baru?education_type=formal")
        form_html = form_response.get_data(as_text=True)
        self.assertEqual(form_response.status_code, 200)
        self.assertIn('name="program_logo"', form_html)
        self.assertIn('data-cloudinary-folder="programs"', form_html)
        self.assertIn(">Upload logo</button>", form_html)
        self.assertIn('name="icon"', form_html)
        self.assertIn("Font Awesome", form_html)
        token = re.search(r'name="csrf_token" value="([^"]+)"', form_html).group(1)

        uploaded_logo = "https://res.cloudinary.com/demo/image/upload/c_limit,h_1600,q_auto:good,w_1600,f_auto/v123/ppru/programs/kajian-kitab"
        with patch("app.upload_image", return_value={"url": uploaded_logo, "public_id": "ppru/programs/kajian-kitab"}) as upload_mock:
            upload_response = self.client.post(
                "/admin/upload-image",
                data={
                    "csrf_token": token,
                    "folder": "programs",
                    "image_file": (BytesIO(b"fake-image-bytes"), "logo.png"),
                },
                content_type="multipart/form-data",
            )
        self.assertEqual(upload_response.status_code, 200)
        self.assertEqual(upload_response.get_json()["url"], uploaded_logo)
        self.assertEqual(upload_mock.call_args.args[2], "programs")

        created = self.client.post(
            "/admin/akademik/program/simpan",
            data={
                "csrf_token": token,
                "title": "Kajian Kitab Logo",
                "category": "Pendidikan formal",
                "education_type": "formal",
                "description": "Program dengan identitas visual khusus.",
                "kitabs": "Safinatun Najah",
                "info_url": "/kontak",
                "icon": "graduation-cap",
                "program_logo": uploaded_logo,
            },
            follow_redirects=True,
        )
        self.assertEqual(created.status_code, 200)
        saved_programs = json.loads(self.content_file.read_text(encoding="utf-8"))["programs"]
        program = next(item for item in saved_programs if item["title"] == "Kajian Kitab Logo")
        self.assertEqual(program["logo"], uploaded_logo)
        self.assertEqual(program["icon"], "graduation-cap")

        psb_slots_form = self.client.get("/admin/akademik?tab=psb").get_data(as_text=True)
        psb_slots_token = re.search(r'name="csrf_token" value="([^"]+)"', psb_slots_form).group(1)
        psb_slots_saved = self.client.post(
            "/admin/akademik/psb/simpan",
            data={
                "csrf_token": psb_slots_token,
                "program_slot_0": program["number"],
                "program_slot_1": "",
                "program_slot_2": "",
            },
        )
        self.assertEqual(psb_slots_saved.status_code, 302)

        academic_html = self.client.get("/akademik").get_data(as_text=True)
        self.assertIn(f'<img class="program-logo-image" src="{uploaded_logo}"', academic_html)
        self.assertIn('class="fa-solid fa-quran"', academic_html)
        self.assertIn("vendor/fontawesome-free/css/fontawesome.min.css?v=6.7.2", academic_html)
        admin_html = self.client.get("/admin/akademik?tab=formal").get_data(as_text=True)
        self.assertIn(f'<img src="{uploaded_logo}" alt="">', admin_html)
        psb_html = self.client.get("/psb").get_data(as_text=True)
        self.assertIn(f'<img class="admission-program-logo" src="{uploaded_logo}"', psb_html)

        edit_form = self.client.get(f"/admin/akademik/program/{program['id']}/edit")
        token = re.search(r'name="csrf_token" value="([^"]+)"', edit_form.get_data(as_text=True)).group(1)
        cleared = self.client.post(
            "/admin/akademik/program/simpan",
            data={
                "csrf_token": token,
                "item_id": program["id"],
                "title": program["title"],
                "category": program["category"],
                "education_type": "formal",
                "description": program["description"],
                "kitabs": "Safinatun Najah",
                "info_url": "/kontak",
                "icon": "scroll",
                "program_logo": "",
            },
            follow_redirects=True,
        )
        self.assertEqual(cleared.status_code, 200)
        cleared_program = next(
            item for item in json.loads(self.content_file.read_text(encoding="utf-8"))["programs"]
            if item.get("id") == program["id"]
        )
        self.assertEqual(cleared_program["logo"], "")
        self.assertEqual(cleared_program["icon"], "scroll")
        fallback_html = self.client.get("/akademik").get_data(as_text=True)
        self.assertIn('class="fa-solid fa-scroll"', fallback_html)
        self.assertNotIn(f'<img class="program-logo-image" src="{uploaded_logo}"', fallback_html)

        for asset in (
            "/static/vendor/fontawesome-free/css/fontawesome.min.css",
            "/static/vendor/fontawesome-free/css/solid.min.css",
            "/static/vendor/fontawesome-free/webfonts/fa-solid-900.woff2",
        ):
            with self.subTest(asset=asset):
                response = self.client.get(asset)
                self.assertEqual(response.status_code, 200)
                response.close()

    def test_academic_admin_manages_programs_and_calendar_at_bottom_of_page(self):
        with self.client.session_transaction() as admin_session:
            admin_session["admin_authenticated"] = True
            admin_session["admin_role"] = "main"

        program_form = self.client.get("/admin/akademik/program/baru")
        self.assertEqual(program_form.status_code, 200)
        token = re.search(r'name="csrf_token" value="([^"]+)"', program_form.get_data(as_text=True)).group(1)
        program_response = self.client.post(
            "/admin/akademik/program/simpan",
            data={
                "csrf_token": token,
                "title": "Kelas Tsanawiyah",
                "category": "Pendidikan formal",
                "description": "Pembelajaran bertahap di lingkungan pesantren.",
                "kitabs_label": "Materi pembelajaran",
                "kitabs": "Safinatun Najah\nJurumiyah, Amtsilati",
                "info_url": "/psb",
            },
            follow_redirects=True,
        )
        self.assertEqual(program_response.status_code, 200)
        self.assertIn(b"Kelas Tsanawiyah", program_response.data)
        saved_preferences = json.loads(self.content_file.read_text(encoding="utf-8"))
        added_program = next(item for item in saved_preferences["programs"] if item["title"] == "Kelas Tsanawiyah")
        self.assertEqual(added_program["kitabs"], ["Safinatun Najah", "Jurumiyah", "Amtsilati"])
        self.assertEqual(added_program["kitabs_label"], "Materi pembelajaran")
        academic_page = self.client.get("/akademik")
        self.assertEqual(academic_page.status_code, 200)
        academic_html = academic_page.get_data(as_text=True)
        self.assertIn("Safinatun Najah", academic_html)
        self.assertIn("Informasi lebih lanjut", academic_html)
        self.assertIn('href="/psb"', academic_html)

        edit_form = self.client.get(f"/admin/akademik/program/{added_program['id']}/edit")
        self.assertEqual(edit_form.status_code, 200)
        token = re.search(r'name="csrf_token" value="([^"]+)"', edit_form.get_data(as_text=True)).group(1)
        invalid_link_response = self.client.post(
            "/admin/akademik/program/simpan",
            data={
                "csrf_token": token,
                "item_id": added_program["id"],
                "title": "Kelas Tsanawiyah Terpadu",
                "description": "Kelas dengan jadwal pembelajaran terpadu.",
                "kitabs": "Safinatun Najah",
                "info_url": "javascript:alert(1)",
            },
        )
        self.assertEqual(invalid_link_response.status_code, 400)
        self.assertIn(b"Tautan informasi harus berupa", invalid_link_response.data)
        updated_program = self.client.post(
            "/admin/akademik/program/simpan",
            data={
                "csrf_token": token,
                "item_id": added_program["id"],
                "title": "Kelas Tsanawiyah Terpadu",
                "description": "Kelas dengan jadwal pembelajaran terpadu.",
                "kitabs": "Safinatun Najah",
                "info_url": "/kontak",
            },
            follow_redirects=True,
        )
        self.assertEqual(updated_program.status_code, 200)
        saved_preferences = json.loads(self.content_file.read_text(encoding="utf-8"))
        updated_item = next(item for item in saved_preferences["programs"] if item.get("id") == added_program["id"])
        self.assertEqual(updated_item["info_url"], "/kontak")
        self.assertEqual(updated_item["title"], "Kelas Tsanawiyah Terpadu")
        self.assertEqual(updated_item["education_type"], "formal")
        self.assertEqual(updated_item["kitabs_label"], "Materi pembelajaran")

        calendar_form = self.client.get("/admin/akademik/kalender/baru")
        self.assertEqual(calendar_form.status_code, 200)
        token = re.search(r'name="csrf_token" value="([^"]+)"', calendar_form.get_data(as_text=True)).group(1)
        calendar_response = self.client.post(
            "/admin/akademik/kalender/simpan",
            data={
                "csrf_token": token,
                "date": "2027-01-23",
                "title": "Ujian Semester",
                "category": "Ujian",
                "description": "Ujian semester ganjil untuk seluruh kelas.",
            },
            follow_redirects=True,
        )
        self.assertEqual(calendar_response.status_code, 200)
        academic_page = self.client.get("/akademik")
        rendered = academic_page.get_data(as_text=True)
        self.assertIn("23 Januari 2027", rendered)
        self.assertIn("Ujian Semester", rendered)
        self.assertGreater(rendered.index('id="kalender-akademik"'), rendered.index("class=\"academic-note\""))

        self.assertEqual(
            self.client.post(
                f"/admin/akademik/program/{added_program['id']}/hapus",
                data={"csrf_token": token},
                follow_redirects=True,
            ).status_code,
            200,
        )
        saved_preferences = json.loads(self.content_file.read_text(encoding="utf-8"))
        self.assertFalse(any(item.get("id") == added_program["id"] for item in saved_preferences["programs"]))

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
            self.assertIn(b"data-editor-toggle", new_form.data)
            self.assertIn(b"data-editor-value=\"blockquote\"", new_form.data)
            self.assertIn(b"data-editor-insert-image", new_form.data)
            self.assertIn(b"data-news-summary-preview", new_form.data)
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
            self.assertEqual(created_post["excerpt"], "Isi berita.")
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
