import os
from reportlab.pdfgen import canvas
from pathlib import Path
from datetime import datetime

def create_dummy_pdf(filename, content_lines):
    c = canvas.Canvas(str(filename))
    y = 750
    for line in content_lines:
        c.drawString(100, y, line)
        y -= 20
    c.save()

def create_test_data():
    base_dir = Path("test_run_folder")
    base_dir.mkdir(exist_ok=True)

    # 1. Job Application PDF (Z83 style approximation)
    pdf_path = base_dir / "Application_JohnDoe_Ref123.pdf"
    create_dummy_pdf(pdf_path, [
        "Z83 APPLICATION FORM",
        "Position: Software Engineer",
        "Department: PUBLIC WORKS",
        "Reference number: REF-2024-001",
        "Surname and Full names: DOE JOHN",
        "Date of Birth: 1990-01-01",
        "Address: 123 Main St"
    ])
    print(f"Created {pdf_path}")

    # 2. Another Job Application PDF
    pdf_path2 = base_dir / "Application_JaneDoe_Ref456.pdf"
    create_dummy_pdf(pdf_path2, [
        "Z83 APPLICATION FORM",
        "Position: Data Analyst",
        "Department: HUMAN SETTLEMENTS",
        "Reference number: REF-2024-002",
        "Surname and Full names: DOE JANE",
        "Date of Birth: 1992-02-02",
        "Address: 456 Elm St"
    ])
    print(f"Created {pdf_path2}")

    # 3. Random Text File (Should be ignored or categorized as 'Other')
    txt_path = base_dir / "notes.txt"
    with open(txt_path, "w") as f:
        f.write("Some random notes about the job application.")
    print(f"Created {txt_path}")

    # 4. A file that looks like a report (to test exclusion if applicable, though organized might just move it)
    report_path = base_dir / "Scan_Report.txt"
    with open(report_path, "w") as f:
        f.write("Scan Report content")
    print(f"Created {report_path}")

if __name__ == "__main__":
    create_test_data()
