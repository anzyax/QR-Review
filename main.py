#!/usr/bin/env python3
"""
Generator kartu QR Review (ukuran 50 x 85 mm).

Cara pakai:
    pip install qrcode pillow
    python main.py usaha.csv

Format CSV (baris pertama wajib berisi nama kolom):
    nama_usaha,link,jumlah
    Warung Bu Tini,https://search.google.com/local/writereview?placeid=XXXX,2
    Kopi Senja,https://g.page/r/XXXX/review,1

Kolom `jumlah` boleh dikosongkan (default 1 kartu).

Hasil (folder `output/`):
    output/png/<nama-usaha>.png   kartu satuan, 300 dpi, 591 x 1004 px
    output/lembar_A4_1.pdf, ...   lembar A4 berisi banyak kartu, siap cetak

Opsional: font Roboto. Taruh Roboto-Regular.ttf dan Roboto-Bold.ttf di folder
`fonts/` di samping script ini. Kalau tidak ada, script memakai Arial
(Windows/Mac) atau DejaVu/Liberation (Linux).
"""

import argparse
import csv
import math
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.constants import ERROR_CORRECT_M

# ----------------------------------------------------------------------------
# Pengaturan (ubah di sini kalau perlu)
# ----------------------------------------------------------------------------
DPI = 300
CARD_W_MM = 50
CARD_H_MM = 85
SHEET_SAFE_MARGIN_MM = 5   # margin aman printer biasa, supaya kartu tidak terpotong
SHEET_GAP_MM = 2           # jarak antar kartu di lembar A4

COLOR_WHITE = (255, 255, 255)
COLOR_INK = (17, 17, 17)
COLOR_TEAL = (15, 107, 99)
COLOR_GOLD = (245, 163, 0)

TEXT_HEADLINE = "BAGIKAN PENGALAMANMU"
TEXT_MAPS = "di Google Maps"
TEXT_SCAN = "SCAN QR CODE"
TEXT_SCAN_SUB = "UNTUK MEMBERI ULASAN"

ALLOWED_HOSTS = {
    "maps.app.goo.gl", "goo.gl", "g.page", "g.co",
    "google.com", "www.google.com", "maps.google.com", "search.google.com",
    "google.co.id", "www.google.co.id",
}

# ----------------------------------------------------------------------------
# Ukuran. Desain dibuat di kanvas 400 x 680 satuan (8 satuan = 1 mm).
# ----------------------------------------------------------------------------
MM = DPI / 25.4
CARD_W = round(CARD_W_MM * MM)
CARD_H = round(CARD_H_MM * MM)
SCALE = MM / 8


def u(x):
    """Ubah satuan desain ke piksel."""
    return round(x * SCALE)


# ----------------------------------------------------------------------------
# Font
# ----------------------------------------------------------------------------
_FONT_DIR = Path(__file__).resolve().parent / "fonts"
_REGULAR = [
    _FONT_DIR / "Roboto-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_BOLD = [
    _FONT_DIR / "Roboto-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _first_existing(paths):
    for p in paths:
        if Path(p).exists():
            return str(p)
    return None


_REGULAR_PATH = _first_existing(_REGULAR)
_BOLD_PATH = _first_existing(_BOLD)


def get_font(size_px, bold=False):
    path = _BOLD_PATH if bold else _REGULAR_PATH
    size_px = max(1, int(size_px))
    if path:
        return ImageFont.truetype(path, size_px)
    try:
        return ImageFont.load_default(size_px)
    except TypeError:
        return ImageFont.load_default()


def fit_font(text, size_px, max_w_px, bold=False, min_size_px=10):
    """Kecilkan font sampai teks muat di lebar maksimal."""
    size = size_px
    font = get_font(size, bold)
    while font.getlength(text) > max_w_px and size > min_size_px:
        size -= 1
        font = get_font(size, bold)
    return font


# ----------------------------------------------------------------------------
# Bentuk (bintang dan pin) digambar 4x lebih besar lalu dikecilkan, biar halus
# ----------------------------------------------------------------------------
_SS = 4


def _aa_layer(size_px, painter):
    big = Image.new("RGBA", (size_px * _SS, size_px * _SS), (0, 0, 0, 0))
    painter(ImageDraw.Draw(big), size_px * _SS)
    return big.resize((size_px, size_px), Image.LANCZOS)


def _paint_star(d, n):
    cx = cy = n / 2
    outer = n * 0.48
    inner = outer * 0.48
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        r = outer if i % 2 == 0 else inner
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a) + n * 0.03))
    d.polygon(pts, fill=COLOR_GOLD)


def _paint_pin(d, n):
    k = n / 24

    def p(x, y):
        return ((12 + (x - 12) * 0.62) * k, (12 + (y - 12) * 0.62) * k)

    def r(v):
        return v * 0.62 * k

    d.ellipse((0, 0, n - 1, n - 1), fill=COLOR_TEAL)
    cx, cy = p(12, 9)
    head = r(7)
    d.ellipse((cx - head, cy - head, cx + head, cy + head), fill=COLOR_WHITE)
    d.polygon([p(5.4, 11.5), p(12, 22), p(18.6, 11.5)], fill=COLOR_WHITE)
    hole = r(2.5)
    d.ellipse((cx - hole, cy - hole, cx + hole, cy + hole), fill=COLOR_TEAL)


def _paste(card, layer, x, y):
    card.paste(layer, (int(x), int(y)), layer)


# ----------------------------------------------------------------------------
# QR
# ----------------------------------------------------------------------------
def make_matrix(url):
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, border=0)
    qr.add_data(url)
    qr.make(fit=True)
    return qr.get_matrix()


def draw_qr(card, matrix, cx, cy, target_px):
    """Gambar QR dengan modul berukuran bilangan bulat piksel (tajam, tanpa blur)."""
    n = len(matrix)
    mod = max(1, target_px // n)
    size = mod * n
    x0 = cx - size // 2
    y0 = cy - size // 2
    d = ImageDraw.Draw(card)
    for r, row in enumerate(matrix):
        for c, filled in enumerate(row):
            if filled:
                d.rectangle(
                    (x0 + c * mod, y0 + r * mod,
                     x0 + (c + 1) * mod - 1, y0 + (r + 1) * mod - 1),
                    fill=COLOR_INK,
                )
    return mod


# ----------------------------------------------------------------------------
# Render satu kartu
# ----------------------------------------------------------------------------
def render_card(name, url):
    card = Image.new("RGB", (CARD_W, CARD_H), COLOR_WHITE)
    d = ImageDraw.Draw(card)
    cx = CARD_W // 2
    content_w = u(352)

    # Judul
    f = fit_font(TEXT_HEADLINE, u(22), content_w)
    d.text((cx, u(37)), TEXT_HEADLINE, font=f, fill=COLOR_INK, anchor="mm")

    # Baris pin + "di Google Maps"
    f = fit_font(TEXT_MAPS, u(26), content_w - u(40), bold=True)
    pin_px = u(30)
    gap = u(8)
    row_w = pin_px + gap + f.getlength(TEXT_MAPS)
    x_start = cx - row_w / 2
    cy = u(67)
    _paste(card, _aa_layer(pin_px, _paint_pin), x_start, cy - pin_px / 2)
    d.text((x_start + pin_px + gap, cy), TEXT_MAPS, font=f, fill=COLOR_INK, anchor="lm")

    # Lima bintang
    star_px = u(40)
    star_gap = u(6)
    star = _aa_layer(star_px, _paint_star)
    total = 5 * star_px + 4 * star_gap
    sx = cx - total // 2
    for i in range(5):
        _paste(card, star, sx + i * (star_px + star_gap), u(113))

    # Ajakan scan
    f = fit_font(TEXT_SCAN, u(21), content_w, bold=True)
    d.text((cx, u(196.5)), TEXT_SCAN, font=f, fill=COLOR_INK, anchor="mm")
    f = fit_font(TEXT_SCAN_SUB, u(18), content_w)
    d.text((cx, u(222)), TEXT_SCAN_SUB, font=f, fill=COLOR_INK, anchor="mm")

    # Bingkai sudut (emas dan teal)
    frame = u(340)
    fx = cx - frame // 2
    fy = u(261)
    arm = u(40)
    th = u(6)
    fr = fx + frame
    fb = fy + frame
    # kiri atas (emas)
    d.rectangle((fx, fy, fx + arm, fy + th), fill=COLOR_GOLD)
    d.rectangle((fx, fy, fx + th, fy + arm), fill=COLOR_GOLD)
    # kanan atas (teal)
    d.rectangle((fr - arm, fy, fr, fy + th), fill=COLOR_TEAL)
    d.rectangle((fr - th, fy, fr, fy + arm), fill=COLOR_TEAL)
    # kiri bawah (teal)
    d.rectangle((fx, fb - th, fx + arm, fb), fill=COLOR_TEAL)
    d.rectangle((fx, fb - arm, fx + th, fb), fill=COLOR_TEAL)
    # kanan bawah (emas)
    d.rectangle((fr - arm, fb - th, fr, fb), fill=COLOR_GOLD)
    d.rectangle((fr - th, fb - arm, fr, fb), fill=COLOR_GOLD)

    # QR di tengah bingkai
    module_px = draw_qr(card, make_matrix(url), cx, fy + frame // 2, u(280))

    # Nama usaha
    f = fit_font(name, u(20), content_w, bold=True)
    d.text((cx, u(644)), name, font=f, fill=COLOR_INK, anchor="mm")

    return card, module_px


# ----------------------------------------------------------------------------
# Validasi link
# ----------------------------------------------------------------------------
def check_link(url):
    """Kembalikan (error, peringatan). Error = baris dilewati."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return "link harus diawali https://", None
    host = parsed.netloc.lower()
    if host not in ALLOWED_HOSTS:
        return f"domain '{host}' bukan domain Google/Google Maps", None
    if "writereview" not in url and "/review" not in url:
        return None, (
            "link ini mungkin hanya membuka halaman tempat, bukan langsung kotak "
            "ulasan. Pakai link ulasan dari Google Business Profile (Minta ulasan) "
            "atau link writereview?placeid=..."
        )
    return None, None


# ----------------------------------------------------------------------------
# Lembar A4
# ----------------------------------------------------------------------------
def build_sheets(cards, out_dir):
    a4_w, a4_h = round(210 * MM), round(297 * MM)
    safe = round(SHEET_SAFE_MARGIN_MM * MM)
    gap = round(SHEET_GAP_MM * MM)
    cols = max(1, (a4_w - 2 * safe + gap) // (CARD_W + gap))
    rows = max(1, (a4_h - 2 * safe + gap) // (CARD_H + gap))
    per_page = cols * rows
    grid_w = cols * CARD_W + (cols - 1) * gap
    grid_h = rows * CARD_H + (rows - 1) * gap
    x0 = (a4_w - grid_w) // 2
    y0 = (a4_h - grid_h) // 2

    paths = []
    for page_no, start in enumerate(range(0, len(cards), per_page), start=1):
        page = Image.new("RGB", (a4_w, a4_h), COLOR_WHITE)
        d = ImageDraw.Draw(page)
        for j, card in enumerate(cards[start:start + per_page]):
            r, c = divmod(j, cols)
            x = x0 + c * (CARD_W + gap)
            y = y0 + r * (CARD_H + gap)
            page.paste(card, (x, y))
            d.rectangle((x, y, x + CARD_W - 1, y + CARD_H - 1),
                        outline=(190, 190, 190), width=1)  # garis potong tipis
        path = out_dir / f"lembar_A4_{page_no}.pdf"
        page.save(path, "PDF", resolution=float(DPI))
        paths.append(path)
    return paths, per_page


# ----------------------------------------------------------------------------
# Cek scan otomatis (butuh opencv, opsional)
# ----------------------------------------------------------------------------
def verify_scan(path, url):
    try:
        import cv2
    except ImportError:
        return None
    img = cv2.imread(str(path))
    if img is None:
        return False
    value, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
    return value == url


# ----------------------------------------------------------------------------
# Utilitas
# ----------------------------------------------------------------------------
def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "usaha"


def read_rows(csv_path):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            sys.exit("CSV kosong.")
        reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]
        missing = {"nama_usaha", "link"} - set(reader.fieldnames)
        if missing:
            sys.exit(f"Kolom wajib tidak ada di CSV: {', '.join(sorted(missing))}")
        return list(reader)


def main():
    ap = argparse.ArgumentParser(description="Generator kartu QR Review 50x85 mm")
    ap.add_argument("csv", help="file CSV: nama_usaha, link, jumlah (opsional)")
    ap.add_argument("--out", default="output", help="folder hasil (default: output)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    png_dir = out_dir / "png"
    png_dir.mkdir(parents=True, exist_ok=True)

    if _REGULAR_PATH is None or _BOLD_PATH is None:
        print("[peringatan] Font Roboto/Arial/DejaVu tidak ditemukan, "
              "memakai font bawaan Pillow. Tampilan teks bisa berbeda.")

    cards = []
    used_slugs = set()
    ok_count = 0
    for line_no, row in enumerate(read_rows(args.csv), start=2):
        name = (row.get("nama_usaha") or "").strip()
        url = (row.get("link") or "").strip()
        if not name or not url:
            print(f"[baris {line_no}] dilewati: nama_usaha atau link kosong")
            continue
        error, warning = check_link(url)
        if error:
            print(f"[baris {line_no}] {name}: dilewati, {error}")
            continue
        if warning:
            print(f"[baris {line_no}] {name}: PERINGATAN, {warning}")
        try:
            copies = int((row.get("jumlah") or "1").strip() or 1)
        except ValueError:
            print(f"[baris {line_no}] {name}: kolom jumlah bukan angka, dipakai 1")
            copies = 1
        copies = max(1, copies)

        card, module_px = render_card(name, url)
        if module_px < 6:
            print(f"[baris {line_no}] {name}: PERINGATAN, QR terlalu padat "
                  f"(modul {module_px}px). Pakai link yang lebih pendek.")

        slug = slugify(name)
        base, i = slug, 2
        while slug in used_slugs:
            slug = f"{base}-{i}"
            i += 1
        used_slugs.add(slug)

        png_path = png_dir / f"{slug}.png"
        card.save(png_path, dpi=(DPI, DPI))
        cards.extend([card] * copies)
        ok_count += 1

        scan = verify_scan(png_path, url)
        if scan is None:
            status = "tidak dicek (opencv belum terpasang)"
        else:
            status = "scan OK" if scan else "SCAN GAGAL, jangan dicetak"
        print(f"[ok] {name} -> {png_path.name} x{copies}, {status}")

    if not cards:
        sys.exit("Tidak ada kartu yang berhasil dibuat.")

    pdfs, per_page = build_sheets(cards, out_dir)
    print(f"\n{ok_count} usaha, {len(cards)} kartu, {per_page} kartu per lembar A4.")
    for p in pdfs:
        print(f"  {p}")
    print("Cetak PDF dengan skala 100% (Actual size), bukan Fit to page.")


if __name__ == "__main__":
    main()