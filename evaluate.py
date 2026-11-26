import argparse
import json
from collections import Counter
from extraction import deterministic, extract_request
from matching import resolve

CASES=[
("500 kg of SKU-001; 200 L of SKU-002", [("sku-001",500,"kg"),("sku-002",200,"l")],False),
("5 kg of Copper wire", [("copper wire",5,"kg")],False),
("Need ethanol", [],True),
("-5 kg of SKU-001", [],True),
("10 gallons of ethanol", [],True),
("10 kg of SKU-001; need copper wire", [("sku-001",10,"kg")],True),
]
PRODUCTS=[{"id":"SKU-001","name":"Sodium chloride industrial grade","unit":"kg"},{"id":"SKU-002","name":"Ethanol 99%","unit":"L"}]
MATCH_CASES=[("SKU-001","kg","SKU-001"),("Ethanol 99%","L","SKU-002"),("Ethanol 95%","L",None),("SKU-999","kg",None),("SKU-001","L",None)]

def evaluate(live=False):
    tp=fp=fn=clarification=0
    details=[]
    for text,expected,issue in CASES:
        result=extract_request(text)[0] if live else deterministic(text)
        actual=Counter((x.description.casefold(),x.quantity,x.unit) for x in result.items)
        gold=Counter(expected)
        tp+=sum((actual&gold).values()); fp+=sum((actual-gold).values()); fn+=sum((gold-actual).values())
        clarification+=bool(result.issues)==issue
        details.append({"input":text,"exact":actual==gold,"clarification_correct":bool(result.issues)==issue})
    matched=0
    for query,unit,expected in MATCH_CASES:
        product,_=resolve(query,unit,PRODUCTS)
        matched+=(product["id"] if product else None)==expected
    return {"precision":tp/(tp+fp) if tp+fp else 0,"recall":tp/(tp+fn) if tp+fn else 0,"unexpected_lines":fp,"clarification_accuracy":clarification/len(CASES),"matching_accuracy":matched/len(MATCH_CASES),"cases":details}

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--live",action="store_true")
    args=parser.parse_args()
    if args.live:
        import os
        if not os.getenv("OPENAI_API_KEY"): parser.error("--live requires OPENAI_API_KEY")
    print(json.dumps(evaluate(args.live),indent=2))
