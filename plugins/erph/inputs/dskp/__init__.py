"""Generate structured DSKP content from txt or pdf files.

Outputs JSON with sections containing titles, content standards,
and learning standards. Number-based detection works for any language.

Usage (standalone module — the top-level ``ranse`` CLI stays framework-only):

    python -m erph.inputs.dskp --txt <file.txt> [-o output.json]
    python -m erph.inputs.dskp --txt <file.txt> --select 1 1 1
    python -m erph.inputs.dskp --pdf <file.pdf> --pages 35-45 [-o output.json]
    python -m erph.inputs.dskp --list
"""

import argparse
import json
import re
import sys

# ---------------------------------------------------------------------------
# DSKP txt/pdf file paths (easy to modify)
# ---------------------------------------------------------------------------

DSKP_FILES = {
    "T1": "assets/bc-dskp/t1.txt",
    "T2": "assets/bc-dskp/t2.txt",
    "T3": "assets/bc-dskp/t3.txt",
    "T4": "assets/bc-dskp/t4.txt",
    "T5": "assets/bc-dskp/t5.txt",
}

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

SEC_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+)$")


def parse_dskp_txt(content):
    """Parse a DSKP txt file into structured sections.

    Returns: { "1": { "title": "1.0 Listening and Speaking",
                       "content_standards": {
                           "1": {"id":"1.1", "content":"...",
                                  "learning_standards": {
                                      "1": {"id":"1.1.1","content":"..."}
                                  }}
                       } } }
    """
    sections = {}
    current_sec = None
    pending_ref = None  # (dict, key) for multi-line continuation
    pending_ref_key = None

    # Two-pass approach: collect all entries, then associate learning standards
    raw_entries = []  # (type, sec_num, num_parts, full_num, title_text)

    for line in content.splitlines():
        stripped = line.strip()

        # Skip separators, headers, and empty lines
        if stripped.startswith("=") or stripped.startswith("-"):
            continue
        if stripped.startswith("KSSM") or stripped.startswith("DSKP"):
            continue
        if stripped.startswith("【"):
            pending_ref = None
            pending_ref_key = None
            continue

        m = SEC_RE.match(stripped)

        if m:
            # New numbered line — flush any pending continuation
            pending_ref = None
            pending_ref_key = None

            full_num = m.group(1)
            title_text = m.group(2)
            num_parts = full_num.split(".")
            first_num = num_parts[0]

            # Section header: "1.0 Title"
            if len(num_parts) == 2 and num_parts[1] == "0":
                current_sec = first_num
                sections[current_sec] = {
                    "title": f"{full_num} {title_text}",
                    "content_standards": {},
                }
                raw_entries.append(("section", first_num, num_parts, full_num, title_text))
                continue

            if current_sec is None:
                continue

            # Content standard: "1.1 ..."
            if len(num_parts) == 2 and num_parts[1] != "0":
                idx = num_parts[1]
                sections[current_sec]["content_standards"][idx] = {
                    "id": full_num,
                    "content": title_text,
                    "learning_standards": {},
                }
                raw_entries.append(("cs", current_sec, num_parts, full_num, title_text))
                pending_ref = ("cs", current_sec, idx)
                continue

            # Learning standard: "1.1.1 ..."
            if len(num_parts) == 3:
                cs_idx = num_parts[1]
                ls_idx = num_parts[2]
                cs = sections[current_sec]["content_standards"].get(cs_idx)
                if cs:
                    cs["learning_standards"][ls_idx] = {
                        "id": full_num,
                        "content": title_text,
                    }
                    raw_entries.append(("ls", current_sec, num_parts, full_num, title_text))
                    pending_ref = ("ls", current_sec, cs_idx, ls_idx)
                    continue
        elif stripped:
            # Non-empty continuation line — append to pending entry
            if pending_ref:
                if pending_ref[0] == "cs":
                    _, sec_num, idx = pending_ref
                    sections[sec_num]["content_standards"][idx]["content"] += " " + stripped
                elif pending_ref[0] == "ls":
                    _, sec_num, cs_idx, ls_idx = pending_ref
                    cs = sections[sec_num]["content_standards"].get(cs_idx)
                    if cs and ls_idx in cs["learning_standards"]:
                        cs["learning_standards"][ls_idx]["content"] += " " + stripped
        else:
            # Empty line — break continuation
            pending_ref = None

    return sections


def parse_pdf_pages(file_path, pages):
    """Extract text from pdf pages and parse as DSKP."""
    try:
        import pdfplumber
    except ImportError:
        print("Error: pdfplumber required for PDF input", file=sys.stderr)
        sys.exit(1)

    texts = []
    with pdfplumber.open(file_path) as pdf:
        for p in pages:
            if p < 1 or p > len(pdf.pages):
                continue
            text = pdf.pages[p - 1].extract_text()
            if text:
                texts.append(text)

    return parse_dskp_txt("\n".join(texts))


def parse_page_range(page_str):
    """Parse '35-45' or '35,36,37' into a list of page numbers."""
    pages = []
    for part in page_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return sorted(set(pages))


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def resolve_selection(sections, selection):
    """Resolve a selection like [1, 1, 1] to (title, content_std, learning_std).

    Input: list of ints, e.g. [1, 1, 1]
    Returns: dict with keys title, content_standard, learning_standard
             or None if not found.
    """
    if not selection:
        return None

    sec_num = str(selection[0])
    if sec_num not in sections:
        print(f"Error: section {sec_num}.0 not found", file=sys.stderr)
        return None

    sec = sections[sec_num]
    result = {"title": sec["title"]}

    if len(selection) >= 2:
        cs_idx = str(selection[1])
        if cs_idx not in sec["content_standards"]:
            print(f"Error: content standard {sec_num}.{cs_idx} not found",
                  file=sys.stderr)
            return None
        result["content_standard"] = sec["content_standards"][cs_idx]

    if len(selection) >= 3:
        ls_idx = str(selection[2])
        cs = sec["content_standards"].get(str(selection[1]), {})
        ls = cs.get("learning_standards", {}).get(ls_idx)
        if ls is None:
            print(f"Error: learning standard {sec_num}.{selection[1]}.{ls_idx} not found",
                  file=sys.stderr)
            return None
        result["learning_standard"] = ls

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def add_arguments(parser):
    """Register the ``dskp`` options (used by ``main``)."""
    parser.add_argument("--txt", help="Path to DSKP txt file")
    parser.add_argument("--pdf", help="Path to DSKP pdf file")
    parser.add_argument("--pages", help="Page range for PDF (e.g. 35-45 or 35,37,39)")
    parser.add_argument("-o", "--output", help="Output JSON file (default: stdout)")
    parser.add_argument("--select", nargs="+", type=int, metavar="N",
                        help="Select specific section (e.g. --select 1 1 1 for 1.0/1.1/1.1.1)")
    parser.add_argument("--list", action="store_true",
                        help="List configured DSKP file paths and exit")


def run(args, parser):
    """Execute a parsed ``dskp`` invocation."""
    if args.list:
        for name, path in DSKP_FILES.items():
            print(f"  {name}: {path}")
        return

    if not args.txt and not args.pdf:
        parser.error("Either --txt or --pdf is required (or use --list)")

    if args.txt:
        with open(args.txt, encoding="utf-8") as f:
            sections = parse_dskp_txt(f.read())
    else:
        if not args.pages:
            parser.error("--pages is required with --pdf")
        pages = parse_page_range(args.pages)
        sections = parse_pdf_pages(args.pdf, pages)

    if args.select:
        result = resolve_selection(sections, args.select)
        if result is None:
            sys.exit(1)
        output = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        output = json.dumps(sections, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Done: {args.output} ({len(sections)} sections)", file=sys.stderr)
    else:
        print(output)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate structured DSKP content from txt or pdf files")
    add_arguments(parser)
    run(parser.parse_args(argv), parser)


if __name__ == "__main__":
    main()
