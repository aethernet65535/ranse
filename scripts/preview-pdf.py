import pdfplumber
import sys

def get_page_text(file_path, page_num):
    """Get text content of a page. page_num is 1-based human page number."""
    with pdfplumber.open(file_path) as pdf:
        if page_num < 1 or page_num > len(pdf.pages):
            print(f"Error: page {page_num} out of range (1-{len(pdf.pages)})")
            return ""
        page = pdf.pages[page_num - 1]
        return page.extract_text() or ""

def get_page_tables(file_path, page_num):
    """Get table content of a page. page_num is 1-based human page number."""
    with pdfplumber.open(file_path) as pdf:
        if page_num < 1 or page_num > len(pdf.pages):
            return []
        page = pdf.pages[page_num - 1]
        return page.extract_tables() or []

def format_cell(cell):
    """Clean up a cell value."""
    if not cell:
        return ""
    return cell.replace("\n", " ").replace("\uf0b7", "\u2022").strip()

def print_page(file_path, page_num, show_tables=True):
    """Print the content of a page by human page number."""
    print(f"--- Page {page_num} ---")
    text = get_page_text(file_path, page_num)
    print(text)
    if show_tables:
        tables = get_page_tables(file_path, page_num)
        if tables:
            for table in tables:
                for row in table:
                    cleaned = [format_cell(c) for c in row]
                    print("  | " + " | ".join(cleaned) + " |")
    print()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python preview-pdf.py <file_path> [page_number]")
        print("  page_number: 1-based human page number (default: print all pages)")
        sys.exit(1)

    file_path = sys.argv[1]
    if len(sys.argv) >= 3:
        try:
            page_num = int(sys.argv[2])
        except ValueError:
            print(f"Error: '{sys.argv[2]}' is not a valid page number")
            sys.exit(1)
        print_page(file_path, page_num)
    else:
        with pdfplumber.open(file_path) as pdf:
            for i in range(1, len(pdf.pages) + 1):
                print_page(file_path, i)
