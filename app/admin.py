from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from . import media
from .auth import (
    clear_failed_logins,
    login_locked,
    record_failed_login,
    verify_csrf,
)
from .situs_schema import SECTIONS
from .utils import slugify, unique_slug

bp = Blueprint("admin", __name__)

KATEGORI_BERITA = {"kegiatan": "Kegiatan", "karya-santri": "Karya Santri"}
STATUS_BERITA = {"publish": "Terbit", "draft": "Draf"}


def _store():
    return current_app.extensions["ppru"]


def _safe_next(target):
    """Hanya izinkan redirect ke path internal di /admin (cegah open redirect)."""
    if target and target.startswith("/admin") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("admin.dashboard")


# ---------- Proteksi: semua halaman admin kecuali login wajib sesi admin ----------

@bp.before_request
def _guard():
    if request.method == "POST":
        verify_csrf()
    if request.endpoint != "admin.login" and not session.get("admin"):
        return redirect(url_for("admin.login", next=request.path))


@bp.after_request
def _no_cache(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------- Login / logout ----------

@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin"):
        return redirect(url_for("admin.dashboard"))
    error = None
    if request.method == "POST":
        if login_locked():
            error = "Terlalu banyak percobaan gagal. Coba lagi beberapa menit lagi."
        else:
            account = _store()["admin"].get() or {}
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            ok = (
                username == account.get("username")
                and account.get("password_hash")
                and check_password_hash(account["password_hash"], password)
            )
            if ok:
                clear_failed_logins()
                session.clear()
                session.permanent = True
                session["admin"] = username
                return redirect(_safe_next(request.args.get("next")))
            record_failed_login()
            error = "Username atau password salah."
    return render_template("admin/login.html", error=error)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


# ---------- Dashboard ----------

@bp.route("/")
def dashboard():
    s = _store()
    berita = s["berita"].all()
    return render_template(
        "admin/dashboard.html",
        total_berita=len(berita),
        berita_terbit=sum(1 for b in berita if b.get("status") == "publish"),
        berita_draf=sum(1 for b in berita if b.get("status") == "draft"),
        total_galeri=len(s["galeri"].all()),
        terbaru=sorted(berita, key=lambda b: b["id"], reverse=True)[:5],
    )


# ---------- Berita ----------

def _parse_berita(form, existing=None):
    errors = []
    data = {
        "judul": form.get("judul", "").strip(),
        "kategori": form.get("kategori", "kegiatan"),
        "tempat": form.get("tempat", "").strip(),
        "penulis": form.get("penulis", "").strip(),
        "tanggal": form.get("tanggal", "").strip() or date.today().isoformat(),
        "ringkasan": form.get("ringkasan", "").strip(),
        "isi": form.get("isi", "").strip(),
        "status": form.get("status", "draft"),
        "gambar": form.get("gambar", "").strip(),
    }
    if not data["judul"] or len(data["judul"]) > 200:
        errors.append("Judul wajib diisi (maksimal 200 karakter).")
    if data["kategori"] not in KATEGORI_BERITA:
        errors.append("Kategori tidak valid.")
    if data["status"] not in STATUS_BERITA:
        errors.append("Status tidak valid.")
    if not data["isi"]:
        errors.append("Isi berita wajib diisi.")
    if len(data["tempat"]) > 100 or len(data["penulis"]) > 100:
        errors.append("Tempat dan penulis maksimal 100 karakter.")
    if len(data["ringkasan"]) > 300:
        errors.append("Ringkasan maksimal 300 karakter.")
    try:
        date.fromisoformat(data["tanggal"])
    except ValueError:
        errors.append("Format tanggal tidak valid.")
    try:
        data["gambar"] = media.validate_image_path(data["gambar"])
    except media.MediaError as exc:
        errors.append(str(exc))
    return data, errors


def _apply_upload(data, errors, file):
    """Jika admin mengunggah file, simpan lalu pakai path-nya (menggantikan path manual)."""
    if file and file.filename:
        try:
            data["gambar"] = media.save_image(file, "berita")
        except media.MediaError as exc:
            errors.append(str(exc))


@bp.route("/berita")
def berita_list():
    items = sorted(_store()["berita"].all(), key=lambda b: b["id"], reverse=True)
    return render_template("admin/berita_list.html", items=items,
                           kategori_label=KATEGORI_BERITA, status_label=STATUS_BERITA)


@bp.route("/berita/baru", methods=["GET", "POST"])
def berita_baru():
    repo = _store()["berita"]
    errors = []
    data = {"kategori": "kegiatan", "status": "publish", "tanggal": date.today().isoformat()}
    if request.method == "POST":
        data, errors = _parse_berita(request.form)
        _apply_upload(data, errors, request.files.get("gambar_file"))
        if not errors:
            base = slugify(data["judul"])
            data["slug"] = unique_slug(base, repo.slug_taken)
            repo.create(data)
            flash("Berita berhasil disimpan.", "ok")
            return redirect(url_for("admin.berita_list"))
    return render_template("admin/berita_form.html", item=data, errors=errors,
                           mode="baru", kategori=KATEGORI_BERITA, status=STATUS_BERITA,
                           uploads=media.list_uploads())


@bp.route("/berita/<int:item_id>/edit", methods=["GET", "POST"])
def berita_edit(item_id):
    repo = _store()["berita"]
    item = repo.get(item_id)
    if item is None:
        abort(404)
    errors = []
    if request.method == "POST":
        data, errors = _parse_berita(request.form, existing=item)
        _apply_upload(data, errors, request.files.get("gambar_file"))
        if not errors:
            repo.update(item_id, data)  # slug dipertahankan agar link tidak rusak
            flash("Perubahan berita disimpan.", "ok")
            return redirect(url_for("admin.berita_list"))
        item = {**item, **data}
    return render_template("admin/berita_form.html", item=item, errors=errors,
                           mode="edit", kategori=KATEGORI_BERITA, status=STATUS_BERITA,
                           uploads=media.list_uploads())


@bp.route("/berita/<int:item_id>/hapus", methods=["POST"])
def berita_hapus(item_id):
    if not _store()["berita"].delete(item_id):
        abort(404)
    flash("Berita dihapus.", "ok")
    return redirect(url_for("admin.berita_list"))


@bp.route("/berita/<int:item_id>/status", methods=["POST"])
def berita_status(item_id):
    repo = _store()["berita"]
    item = repo.get(item_id)
    if item is None:
        abort(404)
    new_status = "draft" if item.get("status") == "publish" else "publish"
    repo.update(item_id, {"status": new_status})
    flash("Status berita diubah menjadi " + STATUS_BERITA[new_status] + ".", "ok")
    return redirect(url_for("admin.berita_list"))


# ---------- Galeri ----------

@bp.route("/galeri")
def galeri_list():
    return render_template("admin/galeri.html",
                           items=_store()["galeri"].latest(), uploads=media.list_uploads())


@bp.route("/galeri/tambah", methods=["POST"])
def galeri_tambah():
    judul = request.form.get("judul", "").strip()[:150]
    tanggal = request.form.get("tanggal", "").strip() or date.today().isoformat()
    try:
        date.fromisoformat(tanggal)
    except ValueError:
        flash("Format tanggal tidak valid.", "error")
        return redirect(url_for("admin.galeri_list"))

    files = [f for f in request.files.getlist("foto") if f and f.filename]
    path_manual = request.form.get("path", "").strip()
    saved = []
    try:
        for f in files:
            saved.append(media.save_image(f, "galeri"))
        if path_manual:
            saved.append(media.validate_image_path(path_manual))
    except media.MediaError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.galeri_list"))

    if not saved:
        flash("Pilih minimal satu foto atau isi path gambar.", "error")
        return redirect(url_for("admin.galeri_list"))
    repo = _store()["galeri"]
    for path in saved:
        repo.create({"judul": judul or "Foto Kegiatan", "path": path, "tanggal": tanggal})
    flash(f"{len(saved)} foto ditambahkan ke galeri.", "ok")
    return redirect(url_for("admin.galeri_list"))


@bp.route("/galeri/<int:item_id>/edit", methods=["POST"])
def galeri_edit(item_id):
    judul = request.form.get("judul", "").strip()[:150]
    tanggal = request.form.get("tanggal", "").strip()
    path = request.form.get("path", "").strip()
    if not judul:
        flash("Judul wajib diisi.", "error")
        return redirect(url_for("admin.galeri_list"))
    try:
        date.fromisoformat(tanggal)
    except ValueError:
        flash("Format tanggal tidak valid.", "error")
        return redirect(url_for("admin.galeri_list"))
    try:
        path = media.validate_image_path(path)
    except media.MediaError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.galeri_list"))
    if not path:
        flash("Path gambar wajib diisi.", "error")
        return redirect(url_for("admin.galeri_list"))
    if _store()["galeri"].update(item_id, {"judul": judul, "tanggal": tanggal, "path": path}) is None:
        abort(404)
    flash("Foto diperbarui.", "ok")
    return redirect(url_for("admin.galeri_list"))


@bp.route("/galeri/<int:item_id>/hapus", methods=["POST"])
def galeri_hapus(item_id):
    if not _store()["galeri"].delete(item_id):
        abort(404)
    flash("Foto dihapus dari galeri.", "ok")
    return redirect(url_for("admin.galeri_list"))


# ---------- Editor situs (identitas, hero, program, sejarah, dst.) ----------

def _parse_object(form, fields):
    values, errors = {}, []
    for name, label, kind in fields:
        raw = form.get(name, "").strip()
        values[name], err = _validate_value(raw, label, kind)
        if err:
            errors.append(err)
    return values, errors


def _parse_list(form, fields):
    columns = {name: form.getlist(f"{name}[]") for name, _, _ in fields}
    rows, errors = [], []
    count = max((len(v) for v in columns.values()), default=0)
    for i in range(count):
        row = {}
        for name, label, kind in fields:
            raw = columns[name][i].strip() if i < len(columns[name]) else ""
            row[name], err = _validate_value(raw, f"{label} (baris {len(rows) + 1})", kind)
            if err:
                errors.append(err)
        if any(row.values()):
            rows.append(row)
    return rows, errors


def _validate_value(raw, label, kind):
    if kind == "url" and raw and not raw.startswith(("https://", "http://")):
        return raw, f"{label} harus diawali https:// atau http://"
    if kind == "image":
        try:
            return media.validate_image_path(raw), None
        except media.MediaError as exc:
            return raw, f"{label}: {exc}"
    if kind == "date" and raw:
        try:
            date.fromisoformat(raw)
        except ValueError:
            return raw, f"{label} tidak valid."
    if len(raw) > 2000:
        return raw, f"{label} terlalu panjang."
    return raw, None


@bp.route("/situs")
def situs_index():
    return render_template("admin/situs_index.html", sections=SECTIONS)


@bp.route("/situs/<section>", methods=["GET", "POST"])
def situs_edit(section):
    if section not in SECTIONS:
        abort(404)
    spec = SECTIONS[section]
    repo = _store()["settings"]
    errors = []
    if request.method == "POST":
        if spec["type"] == "list":
            value, errors = _parse_list(request.form, spec["fields"])
        else:
            value, errors = _parse_object(request.form, spec["fields"])
        if not errors:
            repo.save_section(section, value)
            flash(f"Bagian \"{spec['label']}\" berhasil disimpan.", "ok")
            return redirect(url_for("admin.situs_edit", section=section))
        current = value
    else:
        current = repo.section(section)

    rows = current
    if spec["type"] == "list":
        # Tambahkan 2 baris kosong untuk isian baru.
        rows = list(current) + [{name: "" for name, _, _ in spec["fields"]} for _ in range(2)]
    return render_template("admin/situs_edit.html", section=section, spec=spec,
                           data=rows, errors=errors, uploads=media.list_uploads())


# ---------- Akun ----------

@bp.route("/akun", methods=["GET", "POST"])
def akun():
    repo = _store()["admin"]
    account = repo.get()
    errors = []
    if request.method == "POST":
        old = request.form.get("password_lama", "")
        new = request.form.get("password_baru", "")
        confirm = request.form.get("konfirmasi", "")
        if not check_password_hash(account["password_hash"], old):
            errors.append("Password lama tidak sesuai.")
        if len(new) < 8:
            errors.append("Password baru minimal 8 karakter.")
        if new != confirm:
            errors.append("Konfirmasi password tidak sama.")
        if not errors:
            repo.save(account["username"], generate_password_hash(new))
            flash("Password berhasil diganti.", "ok")
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/akun.html", username=account["username"], errors=errors)
