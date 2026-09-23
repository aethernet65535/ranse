# DSKP reader — formats

DSKP (*Dokumen Standard Kurikulum Pentaksiran*) sources are parsed by this
reader, which is used both by the `ranse dskp` subcommand and by the `dskp`
handler's entries. It is a pure input: it never touches the target workbook
(decision 8, [`docs/DESIGN.md`](../../../../docs/DESIGN.md)).

---

## txt

A plain-text export where **every line starts with a number**:

| Line shape | Meaning |
|---|---|
| `1.0 Listening and Speaking` | parent section (`X.0`) — starts a new section |
| `1.1 …` | content standard inside the current section |
| `1.1.1 …` | learning standard inside the current content standard |
| any other non-empty line | continuation of the previous entry (joined with a space) |
| empty line | ends a continuation |

Lines starting with `=`, `-`, `KSSM`, `DSKP` or `【` are skipped (separators,
headers, cross-reference blocks). Number detection is language-neutral, so the
same parser works for English and Bahasa Malaysia documents.

---

## JSON

The structured output of `ranse dskp` (and the input of `dskp` entries):

```json
{
  "1": {
    "title": "1.0 Listening and Speaking",
    "content_standards": {
      "1": {
        "id": "1.1",
        "content": "…",
        "learning_standards": { "1": { "id": "1.1.1", "content": "…" } }
      }
    }
  }
}
```

Section keys are digits only — the automatic section pair relies on that
(`_section_pair` filters `str(k).isdigit()`).

---

## pdf

`ranse dskp --pdf F --pages 35-45` extracts text with **pdfplumber** (an
optional dependency — a clear error if it is missing) and parses it exactly
like txt. Page ranges accept `35-45`, `35,37,39` or a mix.

---

## Selection

`--select S CS LS` (and the handler's `selection: [S, CS, LS]`) addresses one
triple inside the structure — section `S.0`, content standard `S.CS`, learning
standard `S.CS.LS` — and resolves to
`{title, content_standard, learning_standard}`, the three rows the handler
writes into a class block.

---

## Built-in file table

`__init__.py` carries a `DSKP_FILES` table (`T1` → `assets/bc-dskp/t1.txt`
… `T5`) used when a `dskp` handler configures no `file:`; `ranse dskp --list`
prints it. The `assets/` directory itself is gitignored.
