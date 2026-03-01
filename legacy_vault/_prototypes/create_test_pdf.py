from reportlab.pdfgen import canvas
from pathlib import Path

def create_dummy_pdf(filename):
    c = canvas.Canvas(filename)
    c.drawString(100, 750, "Position: Software Engineer")
    c.drawString(100, 730, "Applicant: John Doe")
    c.save()

if __name__ == "__main__":
    create_dummy_pdf("test_job.pdf")
    print("Created test_job.pdf")
