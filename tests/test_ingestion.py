import io
import pytest
from ingestion import document_text, MAX_BYTES

def test_csv():
    assert document_text("rfq.csv", b"description,quantity,unit\nSKU-001,500,kg\nSKU-002,200,L") == "500 kg of SKU-001\n200 L of SKU-002"

def test_email():
    assert document_text("rfq.eml", b"Subject: RFQ\r\nContent-Type: text/plain\r\n\r\n500 kg of SKU-001") == "500 kg of SKU-001"

@pytest.mark.parametrize("name,data", [("a.exe",b"x"),("a.txt",b""),("a.txt",b"x"*(MAX_BYTES+1)),("a.csv",b"description,quantity,unit\nSKU-001,-1,kg")])
def test_invalid(name,data):
    with pytest.raises(ValueError):
        document_text(name,data)

def test_xlsx():
    from openpyxl import Workbook
    book=Workbook()
    book.active.append(["description","quantity","unit"])
    book.active.append(["SKU-001",500,"kg"])
    buf=io.BytesIO()
    book.save(buf)
    assert document_text("rfq.xlsx",buf.getvalue())=="500 kg of SKU-001"
