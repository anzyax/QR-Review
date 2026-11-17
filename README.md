# QR Review

Generator kartu QR untuk ulasan Google Maps. Sekali scan, pelanggan langsung
masuk ke kotak ulasan usaha. Dibuat untuk membantu UMKM mendapat ulasan lebih
mudah.

Input berupa file CSV berisi daftar usaha. Output berupa kartu 50 x 85 mm
(PNG 300 dpi) dan lembar A4 (PDF) yang siap dicetak.

## Fitur

- Satu CSV menghasilkan banyak kartu sekaligus
- Ukuran 50 x 85 mm, resolusi cetak 300 dpi
- Lembar A4 otomatis dengan garis potong dan margin aman printer
- Validasi link: hanya domain Google yang diterima
- Peringatan kalau link belum langsung ke kotak ulasan
- Nama usaha panjang otomatis dikecilkan agar muat
- Cek scan otomatis (opsional, butuh OpenCV)

## Instalasi

Butuh Python 3.9 ke atas.

```
py -m pip install -r requirements.txt
```

Opsional, untuk cek scan otomatis:

```
py -m pip install opencv-python-headless
```

## Cara pakai

1. Salin `usaha_contoh.csv` menjadi `usaha.csv`, lalu isi datanya.
2. Jalankan:

```
py main.py usaha.csv
```

3. Hasil ada di folder `output/`:
   - `output/png/<nama-usaha>.png`: kartu satuan
   - `output/lembar_A4_1.pdf`: lembar cetak (9 kartu per lembar)

Cetak PDF dengan skala 100% (Actual size), bukan Fit to page.

## Format CSV

```
nama_usaha,link,jumlah
Warung Bu Tini,https://search.google.com/local/writereview?placeid=ChIJxxxx,2
```

| Kolom | Wajib | Keterangan |
|---|---|---|
| nama_usaha | ya | Teks di bagian bawah kartu |
| link | ya | Link ulasan Google Maps |
| jumlah | tidak | Jumlah salinan di lembar A4 (default 1) |

## Cara mendapat link ulasan

Format link: `https://search.google.com/local/writereview?placeid=PLACE_ID`

Cari Place ID usaha lewat
[Place ID Finder Google](https://developers.google.com/maps/documentation/places/web-service/place-id),
lalu tempel ke format di atas. Selalu tes link dari HP sebelum dicetak.

## Font

Secara default memakai Arial (Windows/Mac) atau DejaVu/Liberation (Linux).
Untuk tampilan sesuai desain, taruh `Roboto-Regular.ttf` dan `Roboto-Bold.ttf`
di folder `fonts/`.

## Catatan

- Selalu tes scan hasil cetak asli dari jarak 20-30 cm di beberapa HP.
- Gunakan laminating doff supaya tidak silau.
- Proyek ini tidak berafiliasi dengan Google.
