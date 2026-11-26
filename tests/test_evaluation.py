from evaluate import evaluate
from analytics import summarize

def test_baseline():
    result=evaluate()
    assert result["precision"]==1
    assert result["recall"]==1
    assert result["clarification_accuracy"]==1
    assert result["matching_accuracy"]==1

def test_analytics():
    result=summarize([{"status":"ordered","total":1000,"cost":700},{"status":"rejected","total":500,"cost":400}])
    assert result["booked_order_value"]==1000
    assert result["gross_profit"]==300
    assert result["closed_quote_conversion_percent"]==50
