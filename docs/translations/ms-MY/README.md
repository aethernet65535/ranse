# Ranse

**Isi templat hamparan secara langsung (*in place*) daripada data mingguan anda — dengan satu arahan sahaja.**

## Apa itu Ranse?

Ranse ialah alatan baris arahan yang mengisi buku kerja Excel (xlsx) **di tempat asal** daripada fail data sumber, tanpa mengganggu sebarang sel yang tidak ditulisnya. Ia dipacu sepenuhnya oleh satu **profil** YAML: di mana fail berada, apa yang dikongsi, dan **handler** mana yang dijalankan, secara berurutan.

Ia dihantar bersedia untuk perniagaan pertamanya: mengisi buku kerja **e-RPH** (*Rancangan Pengajaran Harian*) Malaysia daripada jadual waktu mingguan. Perniagaan itu — dan mana-mana perniagaan lain yang boleh anda konfigurasi — hidup sepenuhnya dalam handler dan fail data, langsung bukan dalam rangka kerja teras yang diterangkan di bawah.

## Ciri-ciri

- **Mengekalkan format asal** — mengedit XML dalaman fail xlsx terus, jadi semua gaya sel, sel digabungkan dan sempadan kekal utuh. Helaian yang tiada siapa menulis disalin terus bait demi bait.
- **Teras tulis-sahaja** — enjin tidak boleh membaca semula sel; ia tiada pengetahuan tentang hari, subjek atau susun atur, dan tiada apa daripada itu boleh bocor ke dalamnya.
- **Dipacu profil** — satu YAML bagi setiap guru/templat menyatakan `inputs` (di mana fail berada), `context` (nilai dikongsi) dan `handlers` (pipeline eksplisit, berurutan). Buku kerja boleh menjadi pola `{week}` (`…/M{week}.xlsx`), jadi satu profil berkhidmat untuk setahun.
- **Pipeline dua fasa** — handler `resolve` mengira input dahulu, handler `fill` menulis sel kemudian; nama dan params handler disahkan sebelum apa-apa disentuh, dan penulis terakhir menang pada sel berkongsi.
- **Dua format input** — baca jadual waktu daripada `.xlsx` atau `.csv`.
- **Penulisan satu sel** — `ranse write MENU!B3 "ALI BIN ABU"` untuk pembetulan sekali sahaja.
- **Sedar tarikh** — tarikh lalai ialah hari Ahad minggu semasa; gantikan dengan `--date`.
- **Jalanan semula tentatif** — handler tanpa keadaan; menjalankan minggu yang sama dua kali menghasilkan buku kerja yang sama.
- **Ralat bertipus** — kegagalan mencetak `Error: …` pada stderr dan keluar dengan kod 1; kesilapan penggunaan keluar dengan kod 2.

## Dokumentasi

Rangka kerja dan setiap kawasan perniagaan didokumenkan secara berasingan:

| Dokumen | Kandungan |
|---|---|
| [`docs/DESIGN.md`](../../DESIGN.md) | reka bentuk rangka kerja teras: enjin, CLI, sistem handler, skema profil, pipeline |
| [`src/ranse/handlers/README.md`](../../../src/ranse/handlers/README.md) | peraturan perniagaan handler yang dihantar — indeks; setiap handler mempunyai DESIGN.md sendiri dalam foldernya |
| [`src/ranse/inputs/README.md`](../../../src/ranse/inputs/README.md) | indeks pembaca fail sumber; setiap pembaca mempunyai DESIGN.md sendiri |
| [`config/README.md`](../../../config/README.md) | indeks fail data; setiap folder mempunyai DESIGN.md sendiri |
| [`README.md`](../../../README.md) | versi English README ini |

## Struktur Projek

```
profiles/                    # Satu profil bagi setiap guru/templat (mula di sini)
  ali-bin-abu/               # satu folder bagi setiap profil: profile.yaml + dokumen
    profile.yaml
config/school-weeks/          # Fail data kalendar sekolah (lihat config/README.md)
docs/
  DESIGN.md                  # Reka bentuk rangka kerja teras
src/ranse/
  cli.py                     # ranse fill / write
  model.py                   # Lesson / Schedule / Week / Profile
  core/                      # enjin xlsx tulis-sahaja (tiada pengetahuan perniagaan)
  inputs/                    # pembaca fail sumber — satu folder + DESIGN.md setiap satu
  handlers/                  # week/ menu/ fixed_cells/ dskp/ — satu folder + DESIGN.md setiap satu
tests/                       # ujian unit + baseline regresi golden
```

## Keperluan

- Python 3.9 atau lebih baru
- [PyYAML](https://pypi.org/project/PyYAML/) (dipasang secara automatik)

## Pemasangan

```bash
pip install -e .
```

Ini memasang arahan `ranse`. `pip install -e ".[dev]"` juga memasang pytest untuk pembangunan.

> **Nota:** Fail boleh laku Windows yang berdiri sendiri (tanpa Python) dirancang untuk keluaran akan datang.

## Penggunaan

### `ranse fill` — isi buku kerja minggu ini

```bash
ranse fill --profile profiles/ali-bin-abu/profile.yaml --date 2026-09-20
```

Satu arahan menyelesaikan input, membuka buku kerja profil, menjalankan handler secara berurutan dan menulis semula buku kerja **di tempat asal**. Tiada apa-apa perlu diedit antara minggu.

| Pilihan | Diperlukan | Penerangan |
|---|---|---|
| `--profile` | Ya | Laluan ke fail profil YAML (`inputs` + `handlers`) |

`--profile` sahaja pilihan yang ditambah oleh `ranse fill` sendiri. Semua
pilihan lain datang daripada handler yang diaktifkan profil, dan setiap
handler mendokumenkan pilihannya sendiri dalam `DESIGN.md` (indeks:
[`src/ranse/handlers/README.md`](../../../src/ranse/handlers/README.md)).
Dengan profil yang dihantar, itu bermakna:

| Pilihan | Diisytiharkan oleh | Penerangan |
|---|---|---|
| `--date YYYY-MM-DD` | [`week`](../../../src/ranse/handlers/week/DESIGN.md) | Permulaan minggu (lalai: hari Ahad minggu semasa; hari lain dikembalikan ke Ahadnya) |
| `--week N` | [`week`](../../../src/ranse/handlers/week/DESIGN.md) | Gantikan nombor minggu (lalai: diselesaikan daripada `--date`) |
| `--no-dskp-auto` | [`dskp`](../../../src/ranse/handlers/dskp/DESIGN.md) | Langkau pengisian automatik handler itu untuk jalan ini |

Tiada `--xlsx` dengan sengaja: buku kerja ialah input profil, jadi kesilapan pada baris arahan tidak boleh menulis ganti fail yang salah.

### `ranse write` — satu sel

```bash
ranse write --profile profiles/ali-bin-abu/profile.yaml MENU!B3 "ALI BIN ABU"
```

Menulis satu sel (`SHEET!CELL`, atau `SHEET!FROM:TO` — sudu kiri atas julat atau julat digabungkan digunakan) dan menyimpan buku kerja. Ia tiada pilihan selain `--profile`: ia menjalankan fasa resolve profil, jadi buku kerja minggu mana yang ditulis ditentukan sama seperti `ranse fill`. Nilai ditulis sebagai teks; gunakan `ranse fill` dengan handler `fixed_cells` untuk nilai yang perlu menjadi nombor.

### `python -m ranse.inputs.dskp` — hurai kandungan DSKP

```bash
python -m ranse.inputs.dskp --txt assets/bc-dskp/t1.txt --select 1 1 1 -o t1.json
python -m ranse.inputs.dskp --pdf dskp.pdf --pages 35-45 -o t1.json
python -m ranse.inputs.dskp --list
```

Menghasilkan JSON berstruktur daripada sumber DSKP txt/pdf. Pembaca ini berjalan sebagai modulnya sendiri supaya `ranse --help` hanya menyenaraikan `fill` / `write` rangka kerja. Format: [`src/ranse/inputs/dskp/DESIGN.md`](../../../src/ranse/inputs/dskp/DESIGN.md).

## Konfigurasi (profil)

Profil ialah satu-satunya perkara yang diperlukan oleh `ranse fill` / `ranse write`. Ia mempunyai tiga bahagian:

```yaml
profile: ali-bin-abu-2026

inputs:
  template: "assets/ALI BIN ABU/12. ERPH/2026/*/M{week}.xlsx"  # wajib
  calendar: "config/school-weeks/school-weeks.yaml"            # kalendar minggu
  period_times: "config/period-times/period-times.yaml"          #jadual tempoh
  # templates: {18: "…/06. JUNE/M18.xlsx"}    # tetapkan satu minggu secara eksplisit
  # timetable: "assets/timetable/jadual-waktu-2026-siri-7.xlsx"  # gantian pilihan
  # csv: "timetable.csv"

context:
  days: [Sunday, Monday, Tuesday, Wednesday, Thursday]  # blok hari yang dimiliki templat
  subjects:
    BC: "BAHASA CINA 华 文"

handlers:
  - name: week
  - name: menu
  - name: fixed_cells
    params:
      cells:
        - [MENU, "B3:C3", "ALI BIN ABU"]
  - name: dskp
    params:
      mode: auto
      # … params khusus handler, lihat src/ranse/handlers/README.md
```

### `inputs`

| Kunci | Penerangan |
|---|---|
| `template` | **Wajib.** Buku kerja yang akan diisi di tempat asal. Boleh mengandungi `{week}` dan wildcard glob |
| `templates` | Peta `minggu → laluan` (pilihan); menang atas `template` bagi minggu tersebut |
| `calendar` | Fail data kalendar minggu (didokumenkan dalam [`config/school-weeks/DESIGN.md`](../../../config/school-weeks/DESIGN.md)) |
| `timetable` | Fail jadual waktu xlsx eksplisit (pilihan); mengalahkan carian siri |
| `csv` | Fail jadual waktu csv eksplisit (pilihan); mengalahkan carian siri |
| `period_times` | Jadual tempoh pilihan (tempoh → `[mula, tamat]`); menggantikan jadual terbina dalam (didokumenkan dalam [`config/period-times/DESIGN.md`](../../../config/period-times/DESIGN.md)) |

Laluan relatif diselesaikan terhadap direktori profil itu sendiri, kemudian direktori semasa, kemudian akar repositori (langkah terakhir hanya dalam checkout sumber — pemasangan pakej tiada akar repositori) — jadi profil yang disertakan berfungsi di mana-mana sahaja anda menjalankannya.

**Satu profil untuk setahun.** `template` ialah satu pola: `{week}` digantikan dengan nombor minggu yang diselesaikan, dan wildcard `*`/`?` mencari fail tersebut. Pola mesti sepadan dengan **tepat satu** buku kerja; jika ia sepadan dua (contohnya minggu lama disalin ke folder lain), `ranse fill` menyenaraikan calonnya dan anda tetapkan minggu itu:

```yaml
inputs:
  templates:
    25: "assets/ALI BIN ABU/12. ERPH/2026/07. TMP-NEW/M25.xlsx"
```

Minggu yang buku kerjanya belum wujud dilaporkan dengan cara yang sama, dengan `no workbook matched`.

### `context`

Nilai yang dikongsi oleh beberapa handler — ditulis sekali dan bukannya diduplikasi ke dalam params kedua-duanya: satu peta `subjects` yang digunakan oleh dua handler, dan senarai `days` (blok hari yang dimiliki templat) yang dilalui oleh `menu` dan `dskp` keduanya.

### `handlers`

Senarai eksplisit dan tersusun. Hanya handler terbina dalam boleh dinamakan — nama yang tidak dikenali ialah ralat, dan setiap handler mengesahkan `params`nya sendiri sebelum apa-apa ditulis. Pada sel berkongsi, **handler terakhir dalam senarai menang**.

| Handler | Fasa | Apa yang dilakukannya |
|---|---|---|
| `week` | resolve | tarikh → nombor minggu/siri → laluan jadual waktu (minggu cuti ialah ralat) |
| `menu` | fill | menulis data waktu minggu ke helaian MENU |
| `fixed_cells` | fill | menulis `params.cells` — senarai `[sheet, range, value]` |
| `dskp` | fill | menulis baris standard DSKP ke helaian hari |

Peraturan setiap handler dan rujukan `params` penuh hidup dalam DESIGN.md
handler itu sendiri (indeks: [`src/ranse/handlers/README.md`](../../../src/ranse/handlers/README.md)).

## Seni Bina

```
cli.py ──▶ handlers/ ──▶ core/        (API Workbook / Sheet tulis-sahaja)
              │
              └──────▶ inputs/        (baca fail sumber, bukan buku kerja)
```

- **`core/`** — xlsx ialah arkib ZIP bahagian XML; Ranse memintas `openpyxl` dan mengedit XML helaian terus, mengekalkan setiap atribut yang tidak diubah secara sengaja. Ia tulis-sahaja dan tiada pengetahuan tentang minggu sekolah, subjek atau susun atur.
- **`inputs/`** — pembaca yang mengubah fail kalendar, jadual waktu dan DSKP menjadi objek model; mereka tidak menyentuh buku kerja sasaran.
- **`handlers/`** — semua peraturan perniagaan, melaksanakan dua protokol (`resolve` / `fill`) dan ditemui daripada registri terbina dalam.
- **`cli.py`** — argparse serta susunan pipeline; `RanseError` menjadi `Error: …` + keluar 1.

Reka bentuk penuh (antara muka, keputusan, kitaran hayat, risiko):
[`docs/DESIGN.md`](../../DESIGN.md).

## Pembangunan

```bash
pip install -e ".[dev]"
pytest
```

`tests/golden/` menyimpan baseline XML setiap helaian; ujian regresi mengisi salinan sementara templat dan membandingkan XML helaian bait demi bait. Ia dilangkau apabila `assets/` (diabaikan oleh git) tiada, jadi klon baharu masih menjalankan ujian unit.

## Lesen

Projek ini dilesenkan di bawah [Lesen Awam Umum GNU v2.0](../../../LICENSE).
