from flask import Blueprint, abort, current_app, render_template, request

from .utils import slugify

bp = Blueprint("public", __name__)


def _store():
    return current_app.extensions["ppru"]


@bp.route("/")
def index():
    s = _store()
    settings = s["settings"].all()
    return render_template(
        "public/index.html",
        settings=settings,
        berita_terbaru=s["berita"].published(kategori="kegiatan", limit=3),
        karya_terbaru=s["berita"].published(kategori="karya-santri", limit=3),
        galeri_terbaru=s["galeri"].latest(limit=6),
        agenda=sorted(settings["agenda"], key=lambda a: a.get("tanggal", ""))[:3],
    )


@bp.route("/profil")
def profil():
    s = _store()["settings"].all()
    return render_template("public/profil.html", settings=s)


@bp.route("/program")
def program():
    s = _store()["settings"].all()
    return render_template("public/program.html", settings=s)


@bp.route("/artikel")
def artikel():
    kategori = request.args.get("kategori")
    if kategori not in (None, "", "kegiatan", "karya-santri"):
        kategori = None
    items = _store()["berita"].published(kategori=kategori or None)
    return render_template("public/artikel.html", items=items, kategori=kategori or "")


@bp.route("/artikel/detail/<slug>")
def artikel_detail(slug):
    item = _store()["berita"].get_published_by_slug(slug)
    if item is None:
        abort(404)
    terkait = [b for b in _store()["berita"].published(kategori=item.get("kategori")) if b["id"] != item["id"]][:3]
    return render_template("public/artikel_detail.html", item=item, terkait=terkait)


@bp.route("/galeri")
def galeri():
    return render_template("public/galeri.html", items=_store()["galeri"].latest())


@bp.route("/kalender")
def kalender():
    s = _store()["settings"].all()
    agenda = sorted(s["agenda"], key=lambda a: a.get("tanggal", ""))
    return render_template("public/kalender.html", agenda=agenda)


@bp.route("/kontak")
def kontak():
    s = _store()["settings"].all()
    return render_template("public/kontak.html", settings=s)
