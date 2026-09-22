# Ranse (染色)

**Isi borang e-RPH xlsx secara automatik dengan data jadual waktu mingguan anda — dengan satu arahan sahaja.**

## Apa itu Ranse?

Ranse ialah alatan baris arahan yang direka untuk guru-guru sekolah di Malaysia. Ia mengambil jadual waktu kelas mingguan anda (dalam format xlsx atau csv) dan mengisi templat Excel **e-RPH** (Rancangan Pengajaran Harian elektronik) secara automatik, supaya anda tidak perlu melakukannya setiap minggu secara manual.

Jika anda pernah menghabiskan masa menyalin nama kelas, waktu, dan subjek ke dalam borang e-RPH dengan tangan, Ranse boleh menjimatkan usaha anda.

## Ciri-ciri

- **Mengekalkan format asal** — Mengedit terus XML dalaman fail xlsx, supaya semua gaya sel, sel digabungkan, dan sempadan kekal utuh.
- **Profil** — Satu fail YAML bagi setiap guru yang menyatakan di mana fail berada (`inputs`), apa yang dikongsi antara handler (`context`) dan handler mana yang dijalankan (`handlers`). Buku kerja boleh menjadi pola `{minggu}` (`…/M{minggu}.xlsx`), jadi satu profil berkhidmat untuk setahun.
- **Dua format input** — Baca jadual waktu anda dari fail `.xlsx` atau `.csv`.
- **Penggabungan waktu secara automatik** — Waktu berturut-turut dengan kelas dan subjek yang sama digabungkan menjadi satu baris (contohnya dua waktu Bahasa Cina berturut-turut menjadi satu entri).
- **Pemetaan subjek yang boleh dikonfigurasi** — Petakan kod pendek seperti `BC` kepada nama penuh seperti "BAHASA CINA 华文".
- **Nilai sel tetap** — Tulis nilai tetap (contohnya nama guru) ke sel tertentu.
- **Penulisan satu sel** — `ranse write MENU!B3 "ALI BIN ABU"` untuk pembetulan sekali sahaja.
- **Sedar tarikh** — Tarikh lalai ialah hari Ahad minggu semasa; gantikan dengan `--date`.
- **Sedar minggu (minggu → siri)** — Nombor minggu diselesaikan daripada tarikh, jadual waktu yang sepadan (siri 1, 7, …) dipilih secara automatik, dan minggu cuti dilaporkan dan bukannya mengisi minggu yang salah secara senyap.
- **Standard kandungan automatik** — Setiap pelajaran yang dipadankan diisi dengan dua standard kandungan peringkat induk bersebelahan (lajur kiri/kanan), bergerak ke hadapan satu seksyen setiap minggu: `1+2 → 2+3 → … → pusing balik ke 1+2`.
- **Kit DSKP** — `ranse dskp` menghurai DSKP txt/pdf menjadi JSON berstruktur untuk entri manual.

## Struktur Projek

```
profiles/                    # Satu profil bagi setiap guru/templat (mula di sini)
  ali-bin-abu.yaml
config/jadual-minggu.yaml    # Kalendar sekolah: tarikh → minggu → siri → jadual waktu
src/ranse/
  cli.py                     # ranse fill / write / dskp
  model.py                   # Lesson / Schedule / Week / Profile
  core/                      # enjin xlsx tulis-sahaja (tiada pengetahuan sekolah)
  inputs/                    # pembaca jadual waktu, DSKP dan YAML
  handlers/                  # week / menu / fixed_cells / dskp
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
ranse fill --profile profiles/ali-bin-abu.yaml --date 2026-09-20
```

Satu arahan itu menyelesaikan minggu daripada kalendar, memilih buku kerja minggu tersebut, membaca jadual waktu yang sepadan, mengisi helaian MENU, sel tetap dan blok DSKP, kemudian menulis semula buku kerja **di tempat asal**. Tiada apa-apa perlu diedit antara minggu.

| Pilihan | Diperlukan | Penerangan |
|---|---|---|
| `--profile` | Ya | Laluan ke fail profil YAML (`inputs` + `handlers`) |
| `--date` | Tidak | Tarikh mula minggu dalam format `YYYY-MM-DD` (lalai: **hari Ahad minggu semasa**; hari lain dikembalikan ke Ahadnya) |
| `--minggu` | Tidak | Gantikan nombor minggu (lalai: diselesaikan daripada `--date`) |
| `--no-dskp-auto` | Tidak | Matikan pengisian standard kandungan automatik untuk jalan ini |

Tiada `--xlsx` dengan sengaja: buku kerja ialah input profil, jadi kesilapan pada baris arahan tidak boleh menulis ganti fail yang salah.

```bash
ranse fill --profile profiles/ali-bin-abu.yaml --date 2026-09-20
```

Ini akan:
1. Menyelesaikan minggu: `2026-09-20` → **minggu 33**, siri `7` daripada `config/jadual-minggu.yaml`
2. Memilih buku kerja bagi minggu 33 (`…/2026/07. TMP-NEW/M33.xlsx`)
3. Membaca jadual waktu minggu tersebut (`assets/timetable/jadual-waktu-2026-siri-7.xlsx`)
4. Mengisi helaian MENU (lajur tarikh mendapat hari Ahad minggu itu)
5. Mengisi setiap pelajaran yang dipadankan dengan dua standard kandungan peringkat induk (kiri/kanan), bergerak satu seksyen setiap minggu
6. Menulis semula buku kerja di tempat asal

### `ranse write` — satu sel

```bash
ranse write --profile profiles/ali-bin-abu.yaml --minggu 33 MENU!B3 "ALI BIN ABU"
```

Menulis satu sel (`SHEET!CELL`, atau `SHEET!FROM:TO` — sudu kiri atas julat atau julat digabungkan digunakan) dan menyimpan buku kerja. `--minggu` hanya diperlukan apabila `template` profil mengandungi `{minggu}`. Nilai ditulis sebagai teks; gunakan `ranse fill` dengan handler `fixed_cells` untuk nilai yang perlu menjadi nombor.

### `ranse dskp` — hurai kandungan DSKP

```bash
ranse dskp --txt assets/bc-dskp/t1.txt --select 1 1 1 -o t1.json
ranse dskp --pdf dskp.pdf --pages 35-45 -o t1.json
ranse dskp --list
```

Menghasilkan JSON berstruktur yang dirujuk oleh entri `dskp` manual.

## Konfigurasi (profil)

Profil ialah satu-satunya perkara yang diperlukan oleh `ranse fill` / `ranse write`. Ia mempunyai tiga bahagian:

```yaml
profile: ali-bin-abu-2026

inputs:
  template: "assets/ALI BIN ABU/12. ERPH/2026/*/M{minggu}.xlsx"  # wajib
  jadual: "config/jadual-minggu.yaml"                            # kalendar minggu
  # templates: {18: "…/06. JUNE/M18.xlsx"}    # tetapkan satu minggu secara eksplisit
  # timetable: "assets/timetable/jadual-waktu-2026-siri-7.xlsx"  # gantian pilihan
  # csv: "timetable.csv"

context:
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
      file: "assets/bc-dskp/t{tingkatan}.txt"
      match_codes: [BC]
      match_names: ["BAHASA CINA", "华文"]
      cs: 1
      ls: 1
      left_col: 2
      right_col: 5
```

### `inputs`

| Kunci | Penerangan |
|---|---|
| `template` | **Wajib.** Buku kerja e-RPH yang akan diisi di tempat asal. Boleh mengandungi `{minggu}` dan wildcard glob |
| `templates` | Peta `minggu → laluan` (pilihan); menang atas `template` bagi minggu tersebut |
| `jadual` | Kalendar minggu (`config/jadual-minggu.yaml`) |
| `timetable` | Fail jadual waktu xlsx eksplisit (pilihan); mengalahkan carian siri |
| `csv` | Fail jadual waktu csv eksplisit (pilihan); mengalahkan carian siri |

Laluan relatif diselesaikan terhadap direktori profil itu sendiri, kemudian direktori semasa, kemudian akar repositori — jadi profil yang disertakan berfungsi di mana-mana sahaja anda menjalankannya.

**Satu profil untuk setahun.** `template` ialah satu pola: `{minggu}` digantikan dengan nombor minggu yang diselesaikan, dan wildcard `*`/`?` mencari fail tersebut. Profil yang disertakan justeru menemui `01. JANUARY/M1.xlsx`, `02. FEBRUARY/M4.xlsx` dan `07. TMP-NEW/M33.xlsx` daripada satu baris, manakala jadual waktu sudah dipetakan oleh kalendar (`jadual_siri` + `jadual`).

Jika sesuatu minggu tidak dapat ditentukan secara automatik, `ranse fill` akan memberitahu dan menyenaraikan calonnya — kemudian tetapkan dengan `templates`:

```text
Error: 'assets/…/2026/*/M18.xlsx' matches 2 workbooks for minggu 18:
…/06. JUNE/M18.xlsx, …/07. TMP-NEW/M18.xlsx
— add an explicit 'inputs.templates' entry to the profile
```

```yaml
inputs:
  templates:
    18: "assets/ALI BIN ABU/12. ERPH/2026/07. TMP-NEW/M18.xlsx"
```

### `context`

Nilai yang dikongsi oleh beberapa handler. `subjects` memetakan kod subjek kepada nama yang ditulis ke dalam templat; kod yang tidak tersenarai ditulis seadanya.

```yaml
context:
  subjects:
    BC: "BAHASA CINA 华 文"
    BI: "ENGLISH"
```

### `handlers`

Senarai eksplisit dan tersusun. Hanya handler terbina dalam boleh dinamakan — nama yang tidak dikenali ialah ralat, dan setiap handler mengesahkan `params`nya sendiri sebelum apa-apa ditulis.

| Handler | Fasa | Apa yang dilakukannya |
|---|---|---|
| `week` | resolve | tarikh → minggu/siri → laluan jadual waktu (minggu cuti ialah ralat) |
| `menu` | fill | Baris MENU: kelas, waktu dengan akhiran PAGI/TGH/TPTG, nama subjek, tingkatan |
| `fixed_cells` | fill | menulis `params.cells` — senarai `[sheet, range, value]` |
| `dskp` | fill | Blok DSKP: `entries` manual dahulu, kemudian pasangan automatik mengikut minggu |

#### Param `fixed_cells`

```yaml
- name: fixed_cells
  params:
    cells:
      - [MENU, "B3:C3", "ALI BIN ABU"]   # menulis ke sudu kiri atas julat
      - [MENU, "B4", 2026]                # nombor kekal nombor
```

#### Param `dskp`

```yaml
- name: dskp
  params:
    mode: auto                            # auto (lalai) | static
    entries:                              # entri manual, ditulis dahulu
      - {sheet: ISNIN, class: 1, file: t1.json,
         selection: [1, 1, 1], col_start: 2}
    file: "assets/bc-dskp/t{tingkatan}.txt"  # sumber bagi pasangan automatik
    match_codes: [BC]                     # kod subjek dalam jadual waktu xlsx
    match_names: ["BAHASA CINA", "华文"]   # dipadankan semasa membaca CSV
    cs: 1                                 # standard kandungan dalam sesuatu seksyen
    ls: 1                                 # standard pembelajaran
    left_col: 2                           # separuh kiri  = lajur B
    right_col: 5                          # separuh kanan = lajur E
```

`file` menerima pemegang tempat `{tingkatan}` (T1 → `t1.txt`, T2 → `t2.txt`, …), peta bagi setiap tingkatan, atau tiada langsung — dalam kes itu jadual terbina dalam `assets/bc-dskp/t1.txt` … `t5.txt` digunakan. Format sumber yang sama seperti entri manual disokong: fail txt, atau JSON yang dihasilkan oleh `ranse dskp`.

Entri automatik ditambah **selepas** entri manual, jadi pada sel yang sama entri automatik menang. `--no-dskp-auto` (atau `mode: static`) mematikan bahagian automatik untuk satu jalan.

## Kalendar minggu (`config/jadual-minggu.yaml`)

Mod sedar minggu dipandu oleh kalendar yang dirujuk daripada `inputs.jadual`:

```yaml
jadual:                 # nombor siri → fail jadual waktu
  1: assets/timetable/jadual-waktu-2026-siri-1.xlsx
  7: assets/timetable/jadual-waktu-2026-siri-7.xlsx

jadual_siri:            # minggu → siri (isi bahagian ini)
  33: 1
  34: 7

minggu:                 # setiap rekod berkuat kuasa dari tarikh mula
  - start: 2026-09-20
    minggu: 33
  - start: 2026-09-27
    minggu: 34
```

- Rekod `minggu` telah diisi awal daripada kalendar sekolah (M01…M43); minggu cuti ditandakan dengan `cuti` dan menghasilkan ralat yang jelas dan bukannya mengisi minggu yang salah secara senyap.
- `jadual_siri` ialah jadual minggu → siri; anda juga boleh meletakkan `siri: 7` terus di dalam rekod `minggu` (ia menang atas `jadual_siri`).
- Minggu tanpa siri yang dikonfigurasi ialah ralat melainkan `inputs.timetable` / `inputs.csv` ditetapkan dalam profil.

## Standard kandungan automatik

Untuk setiap pelajaran bergabung bagi subjek yang dipadankan, dua seksyen **peringkat induk** DSKP (tajuk `X.0`) ditulis bersebelahan — lajur kiri dahulu, lajur kanan kemudian:

```
minggu 1 → 1.0 听说技能  |  2.0 阅读技能
minggu 2 → 2.0 阅读技能  |  3.0 书写技能
minggu 3 → 3.0 书写技能  |  4.0 趣味语文
...
tiada seksyen seterusnya → pusing balik ke 1.0 + 2.0
```

Pasangan itu dikira daripada nombor minggu sahaja, jadi menjalankan semula mana-mana minggu sentiasa menghasilkan keputusan yang sama. Setiap bahagian menulis tajuk seksyen (baris 技能), baris standard kandungan, dan baris standard pembelajaran blok kelasnya.

## Bagaimana Ia Berfungsi

Ranse memintas pustaka seperti `openpyxl` dan bekerja terus dengan XML dalaman fail xlsx. Fail xlsx sebenarnya ialah arkib ZIP yang mengandungi fail XML. Ranse:

1. **Membuka zip** fail xlsx
2. **Menghurai** XML helaian menggunakan `xml.etree.ElementTree` terbina dalam Python
3. **Mengubah suai** hanya nilai sel (`<v>`) sambil mengekalkan setiap atribut asal (gaya, format nombor, dsb.) dengan sempurna
4. **Semula zip** semuanya kembali menjadi fail xlsx yang sah

Enjin buku kerja ini sengaja tulis-sahaja — ia tiada cara untuk membaca nilai sel — dan tidak mengetahui apa-apa tentang minggu sekolah, subjek atau susun atur. Semua itu berada dalam handler, yang menulis melalui enjin tersebut. Helaian yang tidak ditulis oleh sesiapa disalin terus bait demi bait, jadi bahagian templat yang tidak disentuh tidak boleh berubah.

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

Lajur Jumaat dan Sabtu diabaikan: templat hanya mempunyai helaian untuk Ahad–Khamis.

### Format csv

CSV harus mempunyai lajur ini:

```
Date,Class,Start Time,End Time,Subject,Tingkatan
```

## Pembangunan

```bash
pip install -e ".[dev]"
pytest
```

`tests/golden/` menyimpan baseline XML setiap helaian; ujian regresi mengisi salinan sementara templat dan membandingkan XML helaian bait demi bait. Ia dilangkau apabila `assets/` (diabaikan oleh git) tiada, jadi klon baharu masih menjalankan ujian unit.

## Lesen

Projek ini dilesenkan di bawah [Lesen Awam Umum GNU v2.0](LICENSE).
