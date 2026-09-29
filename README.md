# Laya Playground — Typed Decisions

[![pages](https://img.shields.io/badge/docs-GitHub%20Pages-4f9cf9)](https://github.com/adyoi/laya-playground)
[![python](https://img.shields.io/badge/python-3.10%2B-3776ab)](https://www.python.org/)
[![laya](https://img.shields.io/badge/laya-0.3.20-CE1126)](https://github.com/NandhaKishorM/laya)
[![tests](https://img.shields.io/badge/tests-3%20file%20hijau-37b978)](README.md#test)
[![license](https://img.shields.io/badge/license-ISC-blue.svg)](LICENSE)

Contoh aplikasi web memakai [laya](https://github.com/NandhaKishorM/laya): *non-autoregressive
System 1 decision engine*. Satu forward pass menjawab banyak pertanyaan **typed**
(`choice`, `score`, `noul`) atas state apa pun — teks, email, tiket, atau dokumen JSON —
tanpa text generation, jadi tidak ada parsing dan tidak ada hallucination.

| Halaman | URL |
|---|---|
| **Playground (live, API jalan)** | <https://laya-playground-jvrv57wjrcpp57-8000.app.github.dev> |
| Dokumentasi (GitHub Pages, statis) | <https://adyoi.github.io/laya-playground/> |

Playground butuh proses FastAPI di belakang, jadi tidak bisa hidup di GitHub Pages. Yang di
hosting di Codespace dengan port 8000 dibuat `public`; dokumentasinya tetap|Pages supaya
tetap hidup tanpa server.

> **Auto-stop.** Codespace ini punya *idle timeout* 30 menit. Setelah idle, GitHub
> mematikannya dan URL publik ikut mati. Ada dua lapis perlindungan:
>
> 1. `postStartCommand` menjalankan `start.sh` setiap kali container hidup, dan
>    `supervise.sh` menyalakan ulang aplikasi kalau prosesnya mati. Ini menutup crash dan
>    restart container.
> 2. Workflow `keep-alive.yml` memanggil endpoint `/health` tiap 15 menit. Kalau mati, ia
>    menyalakan codespace lagi lewat API dan menunggu sampai `/health` 200.
>
> Yang **tidak** bisa ditutup workflow: setiap codespace di-*stop* lalu *start*, port 8000
> kembali jadi `private`. GitHub mengelola itu lewat dev tunnels API
> (`tunnels.api.visualstudio.com`), bukan REST API, jadi Actions tidak bisa mengaturnya.
> Akibatnya setelah bangun dari tidur you'll sering melihat 404.
>
> **Perbaikan manual** (beberapa detik):
>
> ```powershell
> gh codespace ports visibility -c laya-playground-jvrv57wjrcpp57 8000:public
> ```
>
> Satu-satunya cara menutup celah ini sepenuhnya adalah mengubah *retention period* di
> **Settings → Codespaces** dari "stop after idle" ke always-on. Itu berbayar, dan jauh lebih
> murah daripada membiarkan mesin 4-core/16 GB menyala terus.

## Identitas repo GitHub

| | |
|---|---|
| **Nama** | `laya-playground` |
| **Deskripsi** | Example web app for laya, a non-autoregressive decision engine. One forward pass answers typed questions (choice / score / noul) over any state — no text generation, no parsing, no hallucination. FastAPI playground with JSON-Schema output, PII redaction, guardrails, and multi-checkpoint language routing. |
| **Topics** | `laya` `non-autoregressive` `decision-engine` `structured-output` `fastapi` `pydantic` `pii-redaction` `guardrails` `nlp` |
| **Lisensi** | ISC — lihat [`LICENSE`](LICENSE) |
| **Hosting** | Codespace (API) + GitHub Pages (dokumentasi) |

Deskripsi memakai bahasa Inggris karena audiens GitHub jauh lebih luas; narasi README tetap
bahasa Indonesia. Panjangnya 339 dari batas 350 karakter GitHub.

## Isi

```
laya-playground/
├── app.py                FastAPI: 11 endpoint, error envelope, request id
├── presets.py            5 preset bawaan laya + 2 preset contoh
├── redact.py             Redaction PII (regex + validasi Luhn) dan Router hook
├── static/index.html     Playground web: 4 endpoint lewat menu link
├── docs/index.html       GitHub Pages, tema "light modern futuristik"
├── docs/.nojekyll         Mencegah Pages memproses docs/ lewat Jekyll
├── unit_test.py          Test cepat tanpa model (redaction, normalisasi score)
├── feature_test.py       Test end-to-end endpoint baru
├── smoke_test.py         Test semua preset bawaan + validasi
├── lint_docs.py          Konsistensi tema HTML: token sama, title sama, tag balance
├── .devcontainer/         Codespace: devcontainer.json, setup.sh, start.sh, supervise.sh
├── .github/workflows/     CI test + keep-alive Codespace
├── requirements.txt      Dependensi runtime
├── requirements-test.txt httpx, hanya untuk file test
└── LICENSE               ISC
```

### Codespace

`.devcontainer/setup.sh` berjalan otomatis saat Codespace dibuat: membuat `.venv`,
 memasang dependensi, menjalankan server di `0.0.0.0:8000`, lalu memanaskan checkpoint di
background supaya pengunjung pertama tidak menunggu unduhan model. Port 8000 sudah
di-declare sebagai `forwardPorts`.

Jalankan ulang manual:

```bash
bash .devcontainer/start.sh
```

`start.sh` aman dipanggil berulang kali: kalau server sudah hidup dia keluar tanpa
melakukan apa-apa, kalau belum dia menyalakan `supervise.sh` yang menjaga aplikasi tetap
hidup dan me-restart-nya kalau keluar. `postStartCommand` memanggilnya otomatis setiap
container hidup. `postCreateCommand` (install dependensi) hanya jalan sekali saat codespace
dibuat.

`--host 0.0.0.0` wajib: default `127.0.0.1` tidak terjangkau dari proxy Codespace.

Mesin 4-core/16 GB dipakai karena 2-core/8 GB pernah kehabisan memori saat memuat
dua checkpoint. `LAYA_MAX_LOADED=1` juga membatasi hanya satu checkpoint resident.

### GitHub Pages

`docs/` disajikan otomatis sebagai Pages site (branch → `/docs`). Tidak ada Jekyll,
tidak ada build step — `docs/index.html` adalah satu file mandiri. Ilustrasi di halaman itu
digambar dengan CSS, jadi tidak ada aset gambar yang perlu disimpan di repo.

## Instalasi

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Butuh Python 3.10+ (batasnya `huggingface_hub` 1.x, `transformers` 5.x, `torch` 2.14).
Versi yang terverifikasi terpasang di mesin uji:

| Paket | Versi |
|---|---|
| laya | 0.3.20 |
| torch | 2.14.0+cpu |
| transformers | 5.17.0 |
| fastapi | 0.141.1 |
| starlette | 1.7.0 |
| pydantic | 2.13.5 |
| uvicorn | 0.54.0 |
| numpy | 2.5.3 |

Untuk menjalankan file test: `.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt`

### Extras opsional

| Extra | Guna | Syarat |
|---|---|---|
| `laya[fast]` | Fast path TileLang (kernel fused + CUDA graph) | GPU CUDA |
| `laya[onnx]` | ONNX Runtime, lebih kecil untuk CPU | — |
| `laya[langchain]` | `LayaTriage`, `LayaRouter`, `LayaEvaluator`, `embed_fn_from_agent` | memori lega |
| `laya[mcp]` | Binary MCP server | — |

`LayaGuardrail` **tetap berfungsi tanpa** `laya[langchain]` — yang dinonaktifkan hanya
integrasi Runnable-nya. Jangan pasang extra itu di mesin yang memorinya sudah pas,
karena menarik seluruh `langchain-core` di atas torch + transformers.

Fitur yang **tidak** diimplementasikan di contoh ini dan alasannya: `laya[fast]` dan
`laya[onnx]` butuh GPU atau rebuild torch; MCP dan adapter LangChain butuh dependensi
tambahan yang tidak dibenarkan scope.

## Menjalankan

```powershell
.\.venv\Scripts\python.exe app.py --device cpu --port 8000
```

Buka <http://127.0.0.1:8000>. Checkpoint diunduh dari Hugging Face pada request
pertama yang membutuhkannya (english ±1.7 GB, multilingual ±1.3 GB).

Default-nya **lazy load, satu checkpoint pada satu waktu** (`LAYA_MAX_LOADED=1`),
karena dua checkpoint 421M di CPU boros RAM. Untuk produksi, preload:

```powershell
$env:LAYA_PRELOAD = "english,multilingual"
$env:LAYA_MAX_LOADED = "2"
.\.venv\Scripts\python.exe app.py --device cuda
```

Kalau preload gagal (mis. `OSError: The paging file is too small`, error Windows 1455),
aplikasi tetap jalan dalam mode lazy dan alasannya muncul di `GET /health` →
`config.warnings`.

Opsi CLI: `--host`, `--port`, `--device {cpu,cuda,mps,xpu}`, `--reload`.
Konfigurasi lewat env var: `LAYA_HOST`, `LAYA_PORT`, `LAYA_DEVICE`, `LAYA_PRELOAD`,
`LAYA_DEFAULT_MODEL`, `LAYA_MAX_LOADED`, `LAYA_THREADS`, `LAYA_REDACT`.

## Endpoint

| Method | Path | Guna |
|---|---|---|
| POST | `/predict` | Satu state + satu question set, auto-route bahasa |
| POST | `/predict/batch` | Banyak state, dikelompokkan per checkpoint (maks 64) |
| POST | `/structured/questions` | Lihat pertanyaan apa yang dipetakan dari sebuah JSON Schema |
| POST | `/structured/decide` | Jawab terhadap JSON Schema, hasil diproyeksikan ke tipe schema |
| POST | `/shortlist` | Persempit choice beroption banyak ke top-k via embedding |
| POST | `/guardrail` | Screening sebelum request diteruskan ke model lain |
| GET | `/health`, `/models`, `/qtypes`, `/presets`, `/redaction/kinds` | Metadata |

`GET /models` mengembalikan `repos` sebagai objek per checkpoint:

```json
{"english": {"repo": "convaiinnovations/laya", "revision": null},
 "multilingual": {"repo": "convaiinnovations/laya", "revision": "multilingual"}}
```

`GET /health` ikut melaporkan batas request sebagai `max_questions`, `max_state_chars`, dan
`max_states_per_batch`, supaya klien bisa tahu batasnya tanpa menebak.

### Prediksi dasar

```powershell
curl -s localhost:8000/predict -H 'content-type: application/json' -d '{
  "state": {"body": "We were billed twice for March. Please refund it today."},
  "questions": {
    "department": {"type": "choice", "instructions": "Which team?",
                   "criteria": {"billing": "refunds, invoices", "tech": "bugs"}},
    "urgency":    {"type": "score", "instructions": "How urgent?",
                   "criteria": ["not urgent", "soon", "blocking"]}
  }
}' | python -m json.tool
```

`state` boleh `string`, `object`, atau `array`. `model` opsional
(`english` | `multilingual` | `typed-decisions`); bila dihilangkan, router memilih
checkpoint berdasarkan script/bahasa. `lang` memaksa kode bahasa, `lang_guess`
menerima kode atau callable LID sendiri.

`POST /predict/batch` memakai `Router.predict_batch`, jadi request dikelompokkan per
checkpoint lalu dikembalikan dalam urutan input.

### Schema-driven

`/structured/decide` menerima `schema` (JSON Schema) **atau** `questions`, bukan keduanya.
Dengan `schema`, `values` mengikuti tipe aslinya: string enum untuk `choice`, `int` untuk
`score`, `bool` untuk `noul`.

```json
{"values": {"intent": "bug", "blocking": true}, "confidence": {"intent": 0.21, "blocking": 0.88}}
```

Dengan `questions`, `values` berisi raw answer per field — bukan scalar — sesuai perilaku
`laya.structured.decide`. Pakai `schema` kalau butuh output yang sudah ter-tipikalisasi.

### Shortlist

Untuk choice dengan option banyak (di atas ~126 label, checkpoint mulai trimming), persempit
dulu ke top-k. Embedding diambil dari encoder checkpoint yang sudah dimuat
(`laya.embed_fn_from_agent`), jadi tidak ada model tambahan.

```json
{"state": "Customer in Yokohama needs a refund",
 "questions": {"branch": {"type": "choice", "instructions": "Which city?",
                          "criteria": {"Tokyo": "…", "Yokohama": "…"}}},
 "k": 6}
```

Respons memuat `shortlist.branch.labels` (urutan rank), `scores` (cosine), `n`, dan `k`.
Question dengan option ≤ k diteruskan tanpa memanggil embedding sama sekali
(`passthrough: true`).

### Guardrail

`/guardrail` menjalankan `laya.LayaGuardrail` sebelum request dikirim ke model lain.
Tanpa `questions`, memakai `laya.guard_questions()`.

| `action` | Efek |
|---|---|
| `annotate` (default) | selalu 200, `blocked` + `violations` |
| `filter` | 200, `output` = state asli bila aman, pesan penolakan bila tidak |
| `raise` | **403** dengan `violations`, untuk proxy yang menegakkan kebijakan |

**False positive yang diketahui**: pada checkpoint `english`, teks operasional
pendek yang memuat PII (mis. "Please refund invoice 4411, reach me at bob@acme.com or
4111 1111 1111 1111") mendapat `jailbreak` ≈ 0.84, sehingga terblokir meski bukan jailbreak.
Teks netral tanpa PII diberi 0.00, dan jailbreak sungguhan 1.00. Dua jalan keluar:

- Pakai checkpoint `typed-decisions`, yang dilatih untuk workflow typed-decisions
  (akurasi 0.766 vs 0.362 untuk checkpoint english pada benchmark yang sama). Tidak bisa
  diverifikasi di mesin uji ini — RAM 8 GB dengan 1,2 GB bebas tidak cukup memuat dua
  checkpoint sekaligus.
- Jangan pakai `blocked` sebagai satu-satunya sinyal; baca `answers` dan
  `answer_confidence` untuk scaffolding dua tahap.

### Redaction PII

Kirim `"redact": ["email", "credit_card"]` di `/predict` atau `/structured/decide`, atau
pasang hook permanen lewat `LAYA_REDACT=email,credit_card,nik`.

Jenis: `email`, `phone`, `credit_card`, `nik`, `ipv4`, `iban`, `jwt`, `aws_key`,
`api_key`, `private_key`. Urutan dan validator-nya disengaja:

- `nik` dicek sebelum `credit_card` — 16 digit adalah bentuk NIK.
- `credit_card` hanya cocok bila 13–19 digit **dan** lolos Luhn, jadi nomor telepon atau
  nomor invoice panjang tidak ikut tertelan.
- `phone`minimal 7 digit.
- Nomor invoice (`20260927`) dan nominal (`1234567`) dibiarkan utuh.

Respons menyertakan `redaction.counts` per jenis. Arahkan `LAYA_REDACT` ke gateway agar
PII tidak pernah sampai ke checkpoint.

## Kontrak error

Semua error memakai satu bentuk, dengan `request_id` yang juga dikembalikan di header
`x-request-id` dan di body setiap sukses:

```json
{"error": {"status": 422, "detail": "...", "request_id": "e1bf664d62ec"}}
```

Untuk error validasi, `detail` adalah daftar `{loc, msg, type}` dengan `input` **dibuang
sengaja**: FastAPI memantulkan nilai yang offending, sehingga menolak state 5 MB akan
mengembalikan body error 5 MB dan membuat batas ukuran jadi amplifier.

Setiap respons sukses memuat `request_id`; kirim `X-Request-Id` sendiri untuk melacak
request tertentu.

`GET /health` tidak pernah menyentuh lock router. `Router.loaded` mengambil `self._lock`
yang juga dipegang saat inferensi, jadi field `loaded_checkpoints` dibaca lewat timeout 1
detik: router yang sibuk atau macet menurunkan field itu ke `null` alih-alih menggantung
endpoint yang dipantau supervisor.

## Konflik threshold pada `score`

`LayaGuardrail` memakai satu `threshold` untuk semua tipe question, dan membandingkan
`answer.score >= threshold`. Padahal `score` adalah **nilai harapan pada skala 0..N-1**,
bukan probabilitas. Pada preset bawaan, `harm_severity` punya 4 level, jadi threshold 0.5
menyala untuk ekspektasi haram sekecil apa pun — teks yang dinilai model "harmless" tetap
skor 1.0.

Karena itu `/guardrail` menulis ulang question `score` multi-level menjadi `noul` batas
("ya hanya jika di level 2 atau lebih buruk") sebelum meneruskannya ke guardrail. Skala
kembali ke probabilitas, threshold jadi berarti sama untuk `score` dan `noul`. Question
asli bertingkat tetap dijawab dan dikembalikan di `answers`, jadi tidak ada informasi yang
hilang. Transformation dicatat di `score_questions_rewritten`; matikan dengan
`"normalize_scores": false`.

## Catatan confidence

- `confidence` = 1 − entropi ternormalisasi: seberapa tajam distribusinya. Tidak terkalibrasi.
- `answer_confidence` = probabilitas jawaban yang dilaporkan, terkalibrasi. Ini yang dipakai
  untuk gating (mis. `flag_review` bila < 0.6).
- `routing.reason` menjelaskan kenapa checkpoint tertentu dipilih.
- Checkpoint `english` mengirim `choice:11+` dengan temperature 0.10, di luar rentang
  [0.5, 5]; laya menormalkan ke 0.5 dan memperingatkan bahwa confidence field itu
  uncalibrated. Muncul sebagai `RuntimeWarning` saat checkpoint dibangun.

## Performa di CPU

Terukur di mesin ini (4-core, tanpa GPU, torch 2.14+cpu, `LAYA_THREADS` kosong = semua core):

| Situasi | Waktu |
|---|---|
| Request pertama (termasuk unduh + build checkpoint) | 100–135 s |
| Request berikutnya, 3–4 pertanyaan, checkpoint sudah warm | 13–30 s |
| Batch 3 state | ±100 s |

Angka ini jauh di bawah klaim README upstream (33 ms) karena angka itu diukur di GPU T4.
Untuk CPU, biarkan `LAYA_THREADS` kosong agar semua core dipakai, atau pakai
`--device cuda` untuk produksi. `LAYA_MAX_LOADED=1` menjaga hanya satu checkpoint
resident supaya RAM tidak habis.

## Test

```powershell
.\.venv\Scripts\python.exe lint_docs.py         # < 1 detik, tanpa model
.\.venv\Scripts\python.exe unit_test.py         # < 1 detik, tanpa model
.\.venv\Scripts\python.exe feature_test.py       # endpoint baru, ±10 menit di CPU
.\.venv\Scripts\python.exe smoke_test.py         # semua preset, ±15 menit di CPU
```

`lint_docs.py` dan `unit_test.py` tidak butuh server maupun checkpoint — jalankan kapan
saja. Dua file lainnya butuh server hidup di port 8000.

`lint_docs.py` adalah penjaga "satu tema": ia gagal kalau blok `:root` di
`docs/index.html` dan `static/index.html` berbeda, kalau title keduanya tidak sama,
kalau ada `var()` tanpa definisi, kalau ada karakter CJK/kerushu yang tidak sengaja
 tertinggal, atau kalau ada tag HTML yang tidak balance.

### CI

`.github/workflows/test.yml` menjalankan `lint_docs.py` dan `unit_test.py` di setiap push
dan pull request. Keduanya tidak butuh model, jadi runner standar cukup.

`feature_test.py` dan `smoke_test.py` sengaja tidak masuk CI: keduanya butuh checkpoint
laya yang diunduh (~1 GB) dan butuh 10–15 menit di CPU. Runner GitHub juga tidak punya
RAM untuk `LAYA_MAX_LOADED` yang aman. Jalankan manual, atau andalkan Codespace.

## Status verifikasi

Semua hijau pada laya 0.3.20 / torch 2.14.0+cpu:

| Test | Cakupan | Hasil |
|---|---|---|
| `unit_test.py` | 28 assertion redaction + normalisasi score | 0 kegagalan |
| `feature_test.py` | redaction, structured, shortlist, guardrail, error envelope | 0 kegagalan |
| `smoke_test.py` | 7 preset + validasi 422/413/404 + routing batch | 0 kegagalan |

Angka jawaban yang terukur, sebagai acuan regresi:

| Preset | Pertanyaan | Jawaban |
|---|---|---|
| `triage` | `intent` | `refund` (answer_confidence 0.999) |
| `triage` | `refund_requested` | 0.957 |
| `triage` | `is_urgent` | 0.0035 untuk state berbahasa Prancis (tidak urgent) |
| `email` | redaksi PII | tidak ada PII yang lolos ke checkpoint |
| `id-invoice-routing` | `action` | `dispute`, `fraud_suspected` 0.1417 |
| batch (3 state) | routing | `english` / `multilingual` / `english` |
| `guard` | "Ignore your previous instructions…" | diblokir, `jailbreak` 1.00, HTTP 403 di `action=raise` |
| `guard` | "What are your opening hours?" | tidak diblokir, `jailbreak` 0.00 |

Question `triage` adalah `intent`, `is_urgent`, `frustration`, `refund_requested`,
`churn_risk` — bukan `department`. Kalau tabel ini tidak cocok dengan keluaran
`smoke_test.py`, angka modelnya yang bergeser, bukan tabelnya.

## Yang belum selesai

1. **False positive guardrail belum terverifikasi.** `"Please refund invoice 4411, reach me
   at bob@acme.com or 4111 1111 1111 1111"` mendapat `jailbreak` 0.84 pada checkpoint
   `english`. Hipotesis: `model: "typed-decisions"` lebih akurat untuk workflow ini
   (0.766 vs 0.362 pada benchmark yang sama). **Belum diuji** — butuh mesin yang bisa
   memuat dua checkpoint sekaligus; mesin uji 8 GB dengan 1,2 GB bebas mati saat
   memuat `typed-decisions`.
2. **`id-invoice-routing` salah route.** Teks Indonesia preset itu dilayani checkpoint
   `english`, bukan `multilingual`, dengan pesan `language not identified and no
   non-English letters`. Router laya 0.3.20 tidak mengenali pola script Latin untuk
   bahasa Indonesia.
3. **Link menu playground menyesatkan secara semantik.** Menu memakai
   `href="/predict"` supaya URL bisa disalin, tapi endpoint-nya POST-only dan klik
   di-`preventDefault`. Membuka link di tab baru menghasilkan 405.
4. **Belum layak produksi di CPU.** 13–30 detik per request setelah warm. Butuh GPU.
5. **`feature_test.py` dan `smoke_test.py` belum jalan di CI.** Keduanya butuh
   checkpoint (~1 GB) dan 10–15 menit di CPU, sedangkan runner GitHub tidak punya RAM
   untuk itu. `lint_docs.py` dan `unit_test.py` sudah jalan di `test.yml`.
6. **Belum diimplementasi**: `laya[fast]`, `laya[onnx]`, MCP, adapter LangChain — lihat
   bagian Extras.
7. **`predict_long` tidak ada di 0.3.20** meski didokumentasikan di README upstream
   (nol referensi di paket terpasang). Jangan andalkan.

## Catatan operasional

Server dijalankan dari sesi Kilo sebagai proses background, jadi **ikut mati saat sesi
ditutup**. Untuk pemakaian permanen jalankan di terminal terpisah:

```powershell
cd laya-playground
.\.venv\Scripts\python.exe app.py --device cpu --port 8000
```
