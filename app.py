import streamlit as st
import csv, requests, gzip, zipfile, os, tempfile
from io import TextIOWrapper
from pathlib import Path

st.set_page_config(page_title="CSV Splitter", page_icon="🪓", layout="centered")
st.title("🪓 CSV Splitter — Half & Half")

st.write("Upload a **.csv**, **.csv.gz**, or **.zip** (containing one CSV), **or paste a URL**. "
         "The app will split it into two CSVs with half the data rows each (header copied to both).")

# Show effective upload limit (helps verify config on Cloud)
try:
    limit = st.get_option("server.maxUploadSize")
    st.caption(f"Current upload limit (server.maxUploadSize): {limit} MB")
except Exception:
    pass

uploaded = st.file_uploader("Upload file", type=["csv", "gz", "zip"])
url = st.text_input("…or paste a direct download URL to a CSV/CSV.GZ/ZIP (optional)")
has_header = st.checkbox("First row is a header", value=True)
encoding = st.selectbox("File encoding", ["utf-8", "utf-8-sig", "latin-1"], index=0)

def sniff_dialect(sample_text):
    try:
        return csv.Sniffer().sniff(sample_text, delimiters=[",",";","\t","|"])
    except Exception:
        d = csv.excel
        d.delimiter = ","
        return d

def stage_to_local(tmpdir: Path, uploaded_file, url_str: str) -> Path:
    """
    Returns a local CSV path by:
      - writing uploaded file to disk, optionally decompressing (.gz) or extracting (.zip),
      - or streaming a remote URL to disk and handling the same.
    """
    raw_path = tmpdir / "input.raw"
    csv_path = tmpdir / "input.csv"

    # Source: URL or upload
    if url_str:
        with requests.get(url_str, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(raw_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
        src_name = url_str.lower()
    else:
        # uploaded_file is a SpooledTemporaryFile-like object
        raw_bytes = uploaded_file.read()
        with open(raw_path, "wb") as f:
            f.write(raw_bytes)
        src_name = uploaded_file.name.lower()

    # Handle extension
    if src_name.endswith(".csv"):
        raw_path.replace(csv_path)
        return csv_path

    if src_name.endswith(".gz"):
        with gzip.open(raw_path, "rb") as gz, open(csv_path, "wb") as out:
            while True:
                chunk = gz.read(1024*1024)
                if not chunk:
                    break
                out.write(chunk)
        return csv_path

    if src_name.endswith(".zip"):
        with zipfile.ZipFile(raw_path) as zf:
            # pick the first *.csv
            members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
            if not members:
                raise RuntimeError("No .csv found inside the .zip.")
            with zf.open(members[0], "r") as zf_file, open(csv_path, "wb") as out:
                while True:
                    chunk = zf_file.read(1024*1024)
                    if not chunk:
                        break
                    out.write(chunk)
        return csv_path

    raise RuntimeError("Unsupported file type. Use .csv, .csv.gz, or .zip (with a CSV inside).")

def count_records(path: Path, enc: str, dialect, header: bool) -> int:
    total = 0
    with open(path, "r", encoding=enc, newline="") as f:
        reader = csv.reader(f, dialect=dialect)
        first = True
        for _ in reader:
            if first and header:
                first = False
                continue
            total += 1
            first = False
    return total

def split_csv(path: Path, enc: str, dialect, header: bool, total_rows: int):
    half = total_rows // 2
    # outputs
    tmp1 = tempfile.NamedTemporaryFile(mode="w", encoding=enc, newline="", delete=False, suffix=".csv")
    tmp2 = tempfile.NamedTemporaryFile(mode="w", encoding=enc, newline="", delete=False, suffix=".csv")
    w1, w2 = csv.writer(tmp1, dialect=dialect), csv.writer(tmp2, dialect=dialect)

    with open(path, "r", encoding=enc, newline="") as f:
        reader = csv.reader(f, dialect=dialect)
        wrote_header = False
        if header:
            try:
                header_row = next(reader)
                w1.writerow(header_row); w2.writerow(header_row)
                wrote_header = True
            except StopIteration:
                pass
        written = 0
        for row in reader:
            (w1 if written < half else w2).writerow(row)
            written += 1

    tmp1.flush(); tmp1.close()
    tmp2.flush(); tmp2.close()

    data1 = Path(tmp1.name).read_bytes()
    data2 = Path(tmp2.name).read_bytes()
    return data1, data2, half, total_rows - half, wrote_header

def prepare_dialect_sample(csv_path: Path, enc: str, sample_bytes=64*1024):
    with open(csv_path, "rb") as fb:
        sample = fb.read(sample_bytes)
    sample_text = sample.decode(enc, errors="replace")
    return sniff_dialect(sample_text)

if uploaded or url:
    try:
        with st.spinner("Staging file and splitting… ⏳"):
            with tempfile.TemporaryDirectory() as tdir:
                tdir = Path(tdir)
                local_csv = stage_to_local(tdir, uploaded, url)

                dialect = prepare_dialect_sample(local_csv, encoding)
                total = count_records(local_csv, encoding, dialect, has_header)

                if total == 0:
                    st.warning("No data rows found after the header.")
                else:
                    part1, part2, a, b, header_written = split_csv(local_csv, encoding, dialect, has_header, total)
                    st.success(f"Done! Split **{total:,}** data rows → Part 1: **{a:,}**, Part 2: **{b:,}**.")

                    st.download_button("⬇️ Download Part 1 (CSV)", data=part1, file_name="part1.csv", mime="text/csv")
                    st.download_button("⬇️ Download Part 2 (CSV)", data=part2, file_name="part2.csv", mime="text/csv")

                    if has_header and not header_written:
                        st.info("Header was enabled but not found (file may be empty).")

    except Exception as e:
        st.error(f"⚠️ Error: {e}")
else:
    st.info("Upload a file or paste a URL to begin.")
