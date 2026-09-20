# Ranse (染色)

**Isi borang e-RPH xlsx secara automatik dengan data jadual waktu mingguan anda — dengan satu arahan sahaja.**

## Apa itu Ranse?

Ranse ialah alatan baris arahan yang direka untuk guru-guru sekolah di Malaysia. Ia mengambil jadual waktu kelas mingguan anda (dalam format xlsx atau csv) dan mengisi templat Excel **e-RPH** (Rancangan Pengajaran Harian elektronik) secara automatik, supaya anda tidak perlu melakukannya setiap minggu secara manual.

Jika anda pernah menghabiskan masa menyalin nama kelas, waktu, dan subjek ke dalam borang e-RPH dengan tangan, Ranse boleh menjimatkan usaha anda.

## Ciri-ciri

- **Mengekalkan format asal** — Mengedit terus XML dalaman fail xlsx, supaya semua gaya sel, sel digabungkan, dan sempadan kekal utuh.
- **Dua format input** — Baca jadual waktu anda dari fail `.xlsx` atau `.csv`.
- **Penggabungan waktu secara automatik** — Waktu berturut-turut dengan kelas dan subjek yang sama digabungkan menjadi satu baris.
- **Pemetaan subjek yang boleh dikonfigurasi** — Petakan kod pendek seperti `BC` kepada nama penuh seperti "BAHASA CINA 华文".
- **Nilai sel tetap** — Tulis nilai tetap (contohnya nama guru) ke sel tertentu merentasi beberapa helaian.
- **Pelesenan tarikh** — Tetapkan tarikh mula minggu untuk mengisi lajur tarikh dengan betul.

## Struktur Projek

```
fill-erph.py       # Skrip utama
constants.py       # Masa waktu, nama hari, dan pemalar lain
erph-config.yaml   # Fail konfigurasi (kod subjek, sel tetap)
```

## Keperluan

- Python 3.6 atau kemudian
- [PyYAML](https://pypi.org/project/PyYAML/)

## Pemasangan

```bash
pip install pyyaml
```

> **Nota:** Fail boleh laku Windows yang berdiri sendiri (tanpa Python) dirancang untuk keluaran akan datang.

## Penggunaan

### Arahan asas

```bash
python fill-erph.py --xlsx <templat_eRPH.xlsx> --timetable-xlsx <jadual_waktu.xlsx>
```

Atau dengan jadual waktu CSV:

```bash
python fill-erph.py --xlsx <templat_eRPH.xlsx> --csv <jadual_waktu.csv>
```

### Semua pilihan

| Pilihan | Diperlukan | Penerangan |
|---|---|---|
| `--xlsx` | Ya | Laluan ke fail templat e-RPH xlsx |
| `--timetable-xlsx` | Salah satu dari `--timetable-xlsx` atau `--csv` diperlukan | Laluan ke fail jadual waktu xlsx |
| `--csv` | Salah satu dari `--timetable-xlsx` atau `--csv` diperlukan | Laluan ke fail jadual waktu csv |
| `--config` | Tidak | Laluan ke fail YAML konfigurasi (lalai: `./erph-config.yaml`) |
| `--date` | Tidak | Tarikh mula minggu dalam format `YYYY-MM-DD` (lalai: hari ini) |

### Contoh

```bash
python fill-erph.py \
  --xlsx eRPH-saya.xlsx \
  --timetable-xlsx jadual-mingguan.xlsx \
  --config erph-config.yaml \
  --date 2026-09-21
```

Ini akan:
1. Membaca jadual waktu dari `jadual-mingguan.xlsx`
2. Mengisi templat e-RPH `eRPH-saya.xlsx` dengan jadual untuk minggu bermula 21 September 2026
3. Menulis semula `eRPH-saya.xlsx` dengan hasil yang telah diisi

## Konfigurasi

Fail `erph-config.yaml` mempunyai dua bahagian:

### `subjects`

Petakan kod subjek pendek kepada nama penuh seperti yang sepatutnya muncul dalam e-RPH:

```yaml
subjects:
  BC: "BAHASA CINA 华文"
  BI: "ENGLISH"
  BM: "BAHASA MELAYU"
  MT: "MATEMATIK"
  SC: "SAINS"
```

Sebarang kod yang tidak tersenarai di sini akan ditulis ke dalam templat seperti sedia ada.

### `fixed_cells`

Tulis nilai tetap ke sel tertentu. Setiap baris dipisahkan dengan **tab** dan mempunyai tiga medan:

```
<SHEET>    <CELL_RANGE>    <VALUE>
```

Contoh:

```yaml
fixed_cells: |
  MENU	B3:C3	ALI BIN ABU
```

Ini menulis "ALI BIN ABU" ke sel `B3` (atau sudu kiri atas julat digabungkan `B3:C3`) pada helaian `MENU`.

## Bagaimana Ia Berfungsi

Ranse memintas pustaka seperti `openpyxl` dan bekerja terus dengan XML dalaman fail xlsx. Fail xlsx sebenarnya ialah arkib ZIP yang mengandungi fail XML. Ranse:

1. **Membuka zip** fail xlsx
2. **Menghurai** XML helaian menggunakan `xml.etree.ElementTree` terbina dalam Python
3. **Mengubah suai** hanya nilai sel (`<v>`) sambil mengekalkan setiap atribut asal (gaya, format nombor, dsb.) dengan sempurna
4. **Semula zip** semuanya kembali menjadi fail xlsx yang sah

Pendekatan ini memastikan bahawa format, sel digabungkan, dan butiran reka bentuk lain tidak pernah hilang.

## Format Input Jadual Waktu

### Format xlsx

Jadual waktu xlsx harus mempunyai susun atur berikut:

| | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| 1 | Waktu | Ahad | Isnin | Selasa | Rabu | Khamis |
| 2 | 1 | BC-1A | BI-2B | ... | ... | ... |
| 3 | 2 | ... | ... | ... | ... | ... |

- **Baris 1** ialah baris pengepala dengan nama hari
- **Lajur A** mengandungi nombor waktu
- **Lajur lain** mengandungi kod kelas dalam format `<SUBJEK>-<TINGKATAN><KELAS>` (contohnya, `BC-1A` bermaksud Bahasa Cina, Tingkatan 1, Kelas A)

### Format csv

CSV harus mempunyai lajur ini:

```
Date,Class,Start Time,End Time,Subject,Tingkatan
```

## Lesen

Projek ini dilesenkan di bawah [Lesen Awam Umum GNU v2.0](LICENSE).
