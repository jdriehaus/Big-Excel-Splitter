import streamlit as st
import csv
from io import TextIOWrapper, BytesIO
import tempfile

st.set_page_config(page_title="CSV Splitter", page_icon="🪓", layout="centered")
st.title("🪓 CSV Splitter — Split a Big CSV into Two Equal Halves")

st.write(
    "Upload a large **.csv** file. This app will split it into two CSVs, each with half the data rows. "
    "It preserves quoting, delimiters, and embedded newlines using Python’s `csv` module."
)

uploaded = st.file_uploader("Upload CSV", type=["csv"])
has_header = st.checkbox("First row is a header", value=True)
encoding = st.selectbox("File encoding", ["utf-8", "utf-8-sig", "latin-1"], index=0)

st.caption(
    "Tip: On Streamlit Cloud you can raise the upload limit by adding `.streamlit/config.toml` with:\n\n"
    "[server]\nmaxUploadSize = 1000\n\n(in MB)"
)

def sniff_dialect(sample_text):
    try:
        return csv.Sniffer().sniff(sample_text, delimiters=[",", ";", "\t", "|"])
    except Exception:
        # Fallback to comma-delimited RFC style
        dialect = csv.excel
        dialect.delimiter = ","
        return dialect

def count_records(file_obj, enc, dialect, header):
    # Wrap bytes → text for csv.reader without loading whole file
    file_obj.seek(0)
    txt = TextIOWrapper(file_obj, encoding=enc, newline="")
    reader = csv.reader(txt, dialect=dialect)
    total = 0
    first = True
    for _row in reader:
        if first and header:
            first = False
            continue
        total += 1
        first = False
    # IMPORTANT: detach to avoid closing the underlying uploaded buffer
    txt.detach()
    return total

def split_csv(file_obj, enc, dialect, header, total_rows):
    half = total_rows // 2  # first file gets floor half; second gets the rest

    # Prepare two temp files to avoid holding everything in memory
    tmp1 = tempfile.NamedTemporaryFile(mode="w", encoding=enc, newline="", delete=False, suffix=".csv")
    tmp2 = tempfile.NamedTemporaryFile(mode="w", encoding=enc, newline="", delete=False, suffix=".csv")

    w1 = csv.writer(tmp1, dialect=dialect)
    w2 = csv.writer(tmp2, dialect=dialect)

    # Second pass: write rows
    file_obj.seek(0)
    txt = TextIOWrapper(file_obj, encoding=enc, newline="")
    reader = csv.reader(txt, dialect=dialect)

    wrote_header = False
    if header:
        try:
            header_row = next(reader)
            w1.writerow(header_row)
            w2.writerow(header_row)
            wrote_header = True
        except StopIteration:
            pass  # empty file

    written = 0
    for row in reader:
        if written < half:
            w1.writerow(row)
        else:
            w2.writerow(row)
        written += 1

    # Clean up wrappers
    txt.detach()
    tmp1.flush(); tmp1.close()
    tmp2.flush(); tmp2.close()

    # Read back as bytes for download buttons
    with open(tmp1.name, "rb") as f1:
        data1 = f1.read()
    with open(tmp2.name, "rb") as f2:
        data2 = f2.read()

    return data1, data2, half, total_rows - half, wrote_header

if uploaded:
    try:
        with st.spinner("Analyzing file and splitting… ⏳"):
            # Small initial sample for dialect sniffing (don’t consume the stream permanently)
            uploaded.seek(0)
            sample_bytes = uploaded.read(64 * 1024)  # 64KB sample
            sample_text = sample_bytes.decode(encoding, errors="replace")
            dialect = sniff_dialect(sample_text)

            # Rewind to start for counting
            uploaded.seek(0)
            total = count_records(uploaded, encoding, dialect, has_header)

            if total == 0:
                st.warning("No data rows found (after the header). Nothing to split.")
            else:
                # Split into two CSVs
                uploaded.seek(0)
                part1_bytes, part2_bytes, a, b, header_written = split_csv(
                    uploaded, encoding, dialect, has_header, total
                )

                st.success(f"Done! Split **{total:,}** data rows → Part 1: **{a:,}** rows, Part 2: **{b:,}** rows.")
                if has_header and not header_written:
                    st.info("Note: Header was enabled but not found (file may be empty).")

                st.download_button(
                    "⬇️ Download Part 1 (CSV)",
                    data=part1_bytes,
                    file_name="part1.csv",
                    mime="text/csv",
                )
                st.download_button(
                    "⬇️ Download Part 2 (CSV)",
                    data=part2_bytes,
                    file_name="part2.csv",
                    mime="text/csv",
                )

                st.caption(
                    "This app performs two streaming passes: one to count records accurately (handling embedded newlines), "
                    "and one to write out two balanced CSVs. It does not load the entire file into memory."
                )

    except Exception as e:
        st.error(f"⚠️ Error: {e}")
else:
    st.info("Upload a CSV to begin.")
