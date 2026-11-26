import pytest
from extraction import deterministic, extract_request

def test_valid():
    result = deterministic("500 kg of SKU-001; 200 L of SKU-002")
    assert [x.quantity for x in result.items] == [500,200]
    assert not result.issues

@pytest.mark.parametrize("text", ["-5 kg of SKU-001","1.5 kg of SKU-001","0 kg of SKU-001","1000001 kg of SKU-001","SKU-001","5 gallons of SKU-001"])
def test_invalid(text):
    result = deterministic(text)
    assert not result.items
    assert result.issues

def test_partial():
    result = deterministic("500 kg of SKU-001; ethanol")
    assert len(result.items)==1
    assert result.issues

def test_no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    result, mode = extract_request("5 liters of SKU-002")
    assert mode=="deterministic"
    assert result.items[0].unit=="l"
