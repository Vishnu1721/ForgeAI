import re
import os
import json
import math
import urllib.request
from difflib import SequenceMatcher

def normalize(s):
    return " ".join(re.findall(r"[a-z0-9]+%?", s.casefold()))

def specifications(s):
    return set(re.findall(r"\d+(?:\.\d+)?%?", s.casefold()))

def embeddings(texts):
    key=os.getenv("OPENAI_API_KEY")
    if not key or os.getenv("FORGE_SEMANTIC_SEARCH")!="1":
        return None
    payload={"model":os.getenv("OPENAI_EMBEDDING_MODEL","text-embedding-3-small"),"input":texts}
    req=urllib.request.Request("https://api.openai.com/v1/embeddings",json.dumps(payload).encode(),{"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=10) as response:
            data=sorted(json.load(response)["data"],key=lambda x:x["index"])
        return [x["embedding"] for x in data] if len(data)==len(texts) else None
    except Exception:
        return None

def cosine(a,b):
    return sum(x*y for x,y in zip(a,b))/(math.sqrt(sum(x*x for x in a))*math.sqrt(sum(y*y for y in b)) or 1)

def rank(description,unit,products):
    query=normalize(description)
    unit={"liter":"l","liters":"l"}.get(unit.lower(),unit.lower())
    eligible=[p for p in products if p["unit"].lower()==unit]
    exact=[p for p in eligible if query in (normalize(p["id"]),normalize(p["name"]))]
    if exact:
        return [{"product":p,"score":1.0,"method":"exact"} for p in exact]
    if re.fullmatch(r"sku\s*\d+",query):
        return []
    candidates=[]
    for p in eligible:
        name=normalize(p["name"])
        if specifications(description)!=specifications(p["name"]):
            continue
        a,b=set(query.split()),set(name.split())
        score=max(SequenceMatcher(None,query,name).ratio(),len(a&b)/max(len(a|b),1))
        candidates.append({"product":p,"score":score,"method":"lexical"})
    vectors=embeddings([description]+[x["product"]["name"] for x in candidates]) if candidates and len(candidates)<=100 else None
    if vectors:
        for x,v in zip(candidates,vectors[1:]):
            x["semantic_score"]=round(cosine(vectors[0],v),4)
    return sorted(candidates,key=lambda x:(x["score"],x.get("semantic_score",0)),reverse=True)

def resolve(description,unit,products):
    ranked=rank(description,unit,products)
    if not ranked or ranked[0]["score"]<.85 or (len(ranked)>1 and ranked[0]["score"]-ranked[1]["score"]<.1):
        return None,ranked[:5]
    return ranked[0]["product"],ranked[:5]
