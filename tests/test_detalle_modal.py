from pathlib import Path


def test_detalle_modal_incluye_campo_ruta_documento():
    html = Path("static/notaria_app.html").read_text(encoding="utf-8")

    assert 'id="detail-ruta_documento"' in html
