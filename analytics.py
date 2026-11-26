from collections import Counter

def summarize(quotes):
    counts=Counter(q["status"] for q in quotes)
    won=[q for q in quotes if q["status"]=="ordered"]
    revenue=sum(q["total"] for q in won)
    cost=sum(q["cost"] for q in won)
    closed=counts["ordered"]+counts["rejected"]
    return {"quotes":len(quotes),"status_counts":dict(counts),"booked_order_value":revenue,"gross_profit":revenue-cost,"gross_margin_percent":round(100*(revenue-cost)/revenue,2) if revenue else None,"closed_quote_conversion_percent":round(100*len(won)/closed,2) if closed else None,"open_pipeline":sum(q["total"] for q in quotes if q["status"] in {"review","approval","approved","sent"}),"clarification_count":counts["clarification"]}
