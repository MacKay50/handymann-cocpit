from __future__ import annotations

import io

from fastapi.testclient import TestClient


def _small_png_bytes() -> bytes:
    import struct
    import zlib

    def make_png(width: int = 1, height: int = 1) -> bytes:
        def chunk(name: bytes, data: bytes) -> bytes:
            c = struct.pack(">I", len(data)) + name + data
            return c + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        raw_row = b"\x00" + b"\xFF\x00\x00" * width
        compressed = zlib.compress(raw_row * height)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", compressed)
            + chunk(b"IEND", b"")
        )

    return make_png()


def test_upload_valid_png_returns_201(client: TestClient, company_id: str, tmp_path, monkeypatch):
    logo_dir = tmp_path / "logos"
    logo_dir.mkdir(parents=True, exist_ok=True)

    import haandvaerker.api.company_logo as logo_mod
    monkeypatch.setattr(logo_mod, "LOGOS_DIR", logo_dir)

    png_bytes = _small_png_bytes()
    r = client.post(
        "/companies/logo",
        files={"file": ("photo.png", io.BytesIO(png_bytes), "image/png")},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert "logo_url" in data
    expected_file = logo_dir / f"{company_id}.png"
    assert expected_file.exists()
    assert expected_file.read_bytes() == png_bytes


def test_upload_txt_returns_422(client: TestClient, company_id: str, tmp_path, monkeypatch):
    logo_dir = tmp_path / "logos"
    logo_dir.mkdir(parents=True, exist_ok=True)

    import haandvaerker.api.company_logo as logo_mod
    monkeypatch.setattr(logo_mod, "LOGOS_DIR", logo_dir)

    r = client.post(
        "/companies/logo",
        files={"file": ("readme.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert r.status_code == 422, r.text


def test_upload_oversized_returns_422(client: TestClient, company_id: str, tmp_path, monkeypatch):
    logo_dir = tmp_path / "logos"
    logo_dir.mkdir(parents=True, exist_ok=True)

    import haandvaerker.api.company_logo as logo_mod
    monkeypatch.setattr(logo_mod, "LOGOS_DIR", logo_dir)
    monkeypatch.setattr(logo_mod, "MAX_SIZE_BYTES", 1024)

    big_bytes = b"\xFF" * (1024 + 1)
    r = client.post(
        "/companies/logo",
        files={"file": ("big.png", io.BytesIO(big_bytes), "image/png")},
    )
    assert r.status_code == 422, r.text


def test_delete_logo_removes_file_and_clears_ref(
    client: TestClient, company_id: str, tmp_path, monkeypatch
):
    logo_dir = tmp_path / "logos"
    logo_dir.mkdir(parents=True, exist_ok=True)

    import haandvaerker.api.company_logo as logo_mod
    monkeypatch.setattr(logo_mod, "LOGOS_DIR", logo_dir)

    png_bytes = _small_png_bytes()
    up = client.post(
        "/companies/logo",
        files={"file": ("photo.png", io.BytesIO(png_bytes), "image/png")},
    )
    assert up.status_code == 201, up.text

    logo_file = logo_dir / f"{company_id}.png"
    assert logo_file.exists()

    del_r = client.delete("/companies/logo")
    assert del_r.status_code == 204, del_r.text
    assert not logo_file.exists()

    get_r = client.get(f"/companies/{company_id}")
    assert get_r.status_code == 200
    assert get_r.json()["logo_url"] is None


def test_get_company_returns_logo_url_when_set(
    client: TestClient, company_id: str, tmp_path, monkeypatch
):
    logo_dir = tmp_path / "logos"
    logo_dir.mkdir(parents=True, exist_ok=True)

    import haandvaerker.api.company_logo as logo_mod
    monkeypatch.setattr(logo_mod, "LOGOS_DIR", logo_dir)

    png_bytes = _small_png_bytes()
    up = client.post(
        "/companies/logo",
        files={"file": ("photo.png", io.BytesIO(png_bytes), "image/png")},
    )
    assert up.status_code == 201
    logo_url = up.json()["logo_url"]
    assert logo_url.startswith("/static/")

    get_r = client.get(f"/companies/{company_id}")
    assert get_r.status_code == 200
    assert get_r.json()["logo_url"] == logo_url


def test_delete_nonexistent_logo_is_idempotent(
    client: TestClient, company_id: str, tmp_path, monkeypatch
):
    logo_dir = tmp_path / "logos"
    logo_dir.mkdir(parents=True, exist_ok=True)

    import haandvaerker.api.company_logo as logo_mod
    monkeypatch.setattr(logo_mod, "LOGOS_DIR", logo_dir)

    del_r = client.delete("/companies/logo")
    assert del_r.status_code == 204, del_r.text
