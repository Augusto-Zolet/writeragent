# Document Verification Corpus for Docling & WriterAgent

This corpus contains a curated set of test documents specifically assembled to verify **Docling** (`extract_text` / `extract_structure`) and **WriterAgent** layout reconstruction into LibreOffice Writer and Calc.

For each challenge, both vector/scanned PDFs and extracted high-resolution PNG images are provided to support testing both PDF parsing pipelines and image OCR / Vision Helper pipelines.

---

## Corpus Inventory

### Group 1: Tabular Structure & Financial Layouts (Calc / Table Insertion Tests)

#### 1. Modern SEC 10-K Filing Balance Sheet
* **Files:**
  - Full Filing: `01_sec_10k_apple.pdf`
  - Extracted Balance Sheet (Page 34): `01_sec_10k_apple_balance_sheet_page34.pdf`
  - High-Res Render: `01_sec_10k_apple_balance_sheet_page34.png`
* **Source:** SEC EDGAR / Apple Inc. FY25 Form 10-K (Item 8 Financial Statements).
* **Structure:** Multi-level indentations, borderless financial tables, parenthetical negatives `(1,234)`, alignment across fiscal years, trailing footnote markers.
* **What it tests:** Verifies whether Docling parses whitespace-delimited columns into distinct spreadsheet cells or LibreOffice tables without merging numbers into adjacent header text.

#### 2. IRS Form 1040
* **Files:**
  - Full Form: `02_irs_form_1040.pdf`
  - Page 1: `02_irs_form_1040_page1.pdf`
  - High-Res Render: `02_irs_form_1040_page1.png`
* **Source:** Internal Revenue Service (`irs.gov/pub/irs-pdf/f1040.pdf`).
* **Structure:** Boxed input grids, dotted leader lines (`...........`), bold step headers, tiny legal marginalia.
* **What it tests:** Form structure recognition. Stresses whether the layout engine separates cell field labels (e.g., *Line 1z: Other income*) from empty user data boxes.

#### 3. CORD-19 Table Sample (PubTables-1M Benchmark)
* **Files:**
  - Canonical PubTables Table: `03_pubtables_sample_table.jpg`
  - PubTables Research Paper: `03_pubtables_cord19_paper.pdf`
  - Table 1 Comparison (Page 4): `03_pubtables_cord19_table_page4.pdf`
  - High-Res Render: `03_pubtables_cord19_table_page4.png`
* **Source:** Microsoft Research PubTables-1M / PubMed Central Open Access.
* **Structure:** Multi-row spans, merged column headers (`SpanningHeader`), alternating shaded background fills.
* **What it tests:** Complex spanning logic. Evaluates whether sub-columns are correctly associated with their overarching category.

---

### Group 2: Multi-Column & Academic Layouts (Writer Flow Tests)

#### 4. ArXiv CS/ML Two-Column Preprint ("Attention Is All You Need")
* **Files:**
  - Full Paper: `04_arxiv_attention_is_all_you_need.pdf`
  - Page 1 (Title, Abstract, 2-Column Body): `04_arxiv_attention_is_all_you_need_page1.pdf`
  - High-Res Render: `04_arxiv_attention_is_all_you_need_page1.png`
* **Source:** arXiv:1706.03762.
* **Structure:** Symmetrical two-column body text, inline LaTeX mathematical notations, floating figure captions, cross-column spanning abstracts.
* **What it tests:** Reading order. Ensures the agent doesn't read across columns horizontally (e.g., reading line 1 of Column A, then line 1 of Column B).

#### 5. Multi-Column Newspaper Page
* **Files:**
  - Newspaper Front Page PDF: `05_newspaper_the_tech_front_page.pdf`
  - High-Res Render: `05_newspaper_the_tech_front_page.png`
* **Source:** *The Tech* (MIT's campus newspaper, Volume 127, Number 5).
* **Structure:** Clean multi-column layout (3–4 columns), bold primary headlines ("Class of ’09 Brass Rat Revealed", "Sherley Calls Hunger Strike Off After Day"), bylines, weather box, and photo captioning.
* **What it tests:** Multi-column reading order (ensuring the model reads vertically down each column rather than horizontally across columns) and headline/byline hierarchy.

#### 6. Technical Manual Page with Callouts & Sidebars
* **Files:**
  - Full Hardware Datasheet: `06_raspberry_pi_4_datasheet.pdf`
  - Block Diagram & Specs (Page 1): `06_raspberry_pi_4_datasheet_page1.pdf` / `06_raspberry_pi_4_datasheet_page1.png`
  - Callout Box ("Caution!") (Page 8): `06_raspberry_pi_4_datasheet_page8.pdf` / `06_raspberry_pi_4_datasheet_page8.png`
* **Source:** Raspberry Pi Foundation Hardware Documentation.
* **Structure:** Mixed prose with callout boxes (Caution / Warning / Note), monospaced code blocks, and floating pinned diagrams.
* **What it tests:** Verifies whether callouts break the main flow of paragraphs and tests formatting of monospaced blocks versus standard body text.

---

### Group 3: Real-World Scans, Receipts & Edge Cases

#### 7. SROIE Dataset Retail Receipts
* **Files:**
  - Sample Receipt 000: `07_sroie_receipt_000.jpg`
  - Ground Truth Metadata: `07_sroie_receipt_000_ground_truth.json`
  - Sample Receipt 001: `07_sroie_receipt_001.jpg`
* **Source:** ICDAR 2019 SROIE Dataset (`zzzDavid/ICDAR-2019-SROIE`).
* **Structure:** Narrow thermal paper format, low-contrast ink fading, right-aligned prices, compressed dot-matrix or thermal fonts, paper creases.
* **What it tests:** OCR thresholding on low-DPI/grainy text, character spacing, and vertical drift.

#### 8. Complex Commercial Invoice & Purchase Order
* **Files:**
  - QR Bill / Invoice: `08_docling_qr_bill_invoice.jpg`
  - FUNSD Scanned Purchase Order Form: `08_funsd_purchase_order_00922237.png`
  - FUNSD Ground Truth Annotations: `08_funsd_purchase_order_00922237_ground_truth.json`
* **Source:** Docling test suite & FUNSD dataset (`guillaumejaume/FUNSD`).
* **Structure:** Vendor header blocks, nested metadata (Order #, Date, Price, Terms), followed by itemized tables.
* **What it tests:** Key-value pair extraction (`Order No:` -> value, `Date Wanted:` -> value) coupled with tabular line-item arrays.

#### 9. Legacy Technical Data Sheet
* **Files:**
  - Complete Vintage Datasheet: `09_vintage_ti_tms8080_datasheet.pdf`
  - Pinout & Logic Diagram (Page 1): `09_vintage_ti_tms8080_page1.pdf`
  - High-Res Render: `09_vintage_ti_tms8080_page1.png`
* **Source:** Texas Instruments TMS 8080 Microprocessor Data Book (Bitsavers Archive).
* **Structure:** Scanned typewritten text, pinout diagrams, schematic fragments, and logic truth tables.
* **What it tests:** How the layout parser isolates embedded diagram artwork from surrounding ASCII/textual tabular data.

#### 10. Rotated, Skewed & Declassified Documents
* **Files:**
  - CIA Declassified Memo (Project FUBELT): `10_declassified_foia_cia_project_fubelt.pdf` / `10_declassified_foia_cia_project_fubelt_page1.png`
  - White House Declassified Taiwan Memo: `10_declassified_reagan_taiwan_memo.pdf` / `10_declassified_reagan_taiwan_memo_page1.png`
  - Docling 90° Rotated Dense Text: `10_docling_rotated_90_dense_text.png`
  - Docling Rotation Mismatch Sample: `10_docling_sample_rotation_mismatch.pdf`
* **Source:** National Security Archive / Presidential Library Declassified Records / Docling OCR test fixtures.
* **Structure:** Real declassified scans with high textual legibility, visible classification & case stamps (`SECRET`, `NLF MR Case No. 71-38`), blacked-out/obfuscated redaction blocks (`[1.3(a)(4)]`), slight scan skew (~2–3°), alongside 90°/180° page rotation mismatches.
* **What it tests:** Auto-deskew capabilities, orientation detection, background suppression, and handling of obfuscated/redacted zones without hallucinating tokens.
