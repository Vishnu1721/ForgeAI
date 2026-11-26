import os, sqlite3, json, re, uuid, hmac, hashlib, urllib.request, difflib
from decimal import Decimal, ROUND_HALF_UP
from contextlib import contextmanager
from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pathlib import Path
from ingestion import document_text, MAX_BYTES
from extraction import extract_request
from matching import resolve, rank
from pricing import price, PricingPolicy, requires_approval
ROOT=Path(__file__).parent
DB=os.getenv('FORGE_DB',str(ROOT/'forge.db'))
app=FastAPI(title='ForgeAI')
@contextmanager
def db():
    c=sqlite3.connect(DB,timeout=20); c.row_factory=sqlite3.Row
    try:
        c.execute('BEGIN IMMEDIATE'); yield c; c.commit()
    except: c.rollback(); raise
    finally: c.close()
def init():
    with db() as c:
        for table in ['products','customers','quotes','audit','orders','inbox','outbox','settings']:
            c.execute(f'CREATE TABLE IF NOT EXISTS {table}(tenant TEXT,id TEXT,data TEXT,PRIMARY KEY(tenant,id))')
        for tenant in ['demo','other']:
            for i,(name,unit,cost) in enumerate([('Sodium chloride industrial grade','kg',120),('Ethanol 99%','L',240),('Steel sheet 304','kg',450),('Acetone technical grade','L',180),('Copper wire','m',320)]):
                c.execute('INSERT OR IGNORE INTO products VALUES(?,?,?)',(tenant,f'SKU-{i+1:03}',json.dumps(dict(name=name,unit=unit,cost=cost,stock=10000))))
            for i,name in enumerate(['Acme Manufacturing','Midwest Chemicals','Globex Industries']):
                c.execute('INSERT OR IGNORE INTO customers VALUES(?,?,?)',(tenant,f'C{i+1}',json.dumps(dict(name=name,discount=5+i*5,contract={}))))
def get(c,t,tenant,id):
    r=c.execute(f'SELECT data FROM {t} WHERE tenant=? AND id=?',(tenant,id)).fetchone()
    if not r: raise HTTPException(404,f'{t} record not found')
    return json.loads(r[0])
def put(c,t,tenant,id,data): c.execute(f'INSERT OR REPLACE INTO {t} VALUES(?,?,?)',(tenant,id,json.dumps(data)))
def rows(c,t,tenant): return [dict(id=r[0],**json.loads(r[1])) for r in c.execute(f'SELECT id,data FROM {t} WHERE tenant=?',(tenant,))]
def pricing_policy(c,t):
    row=c.execute("SELECT data FROM settings WHERE tenant=? AND id='pricing'",(t,)).fetchone()
    return PricingPolicy.model_validate_json(row[0]) if row else PricingPolicy()

def uid(): return uuid.uuid4().hex[:16]
def audit(c,t,action,record): put(c,'audit',t,uid(),dict(action=action,record=record))
init()
def auth(authorization:str=Header('')):
    tokens={os.getenv('SALES_TOKEN','demo-sales'):('demo','sales'),os.getenv('MANAGER_TOKEN','demo-manager'):('demo','manager'),os.getenv('OTHER_TOKEN','other-sales'):('other','sales')}
    if not authorization.startswith('Bearer ') or authorization[7:] not in tokens: raise HTTPException(401,'Invalid token')
    return tokens[authorization[7:]]
class RFQ(BaseModel):
    customer:str; text:str=Field(min_length=1,max_length=20000); source_id:str=Field(min_length=1,max_length=200)
@app.post('/api/documents/preview')
def preview_document(file: UploadFile = File(...), a=Depends(auth)):
    try:
        data = file.file.read(MAX_BYTES + 1)
        return {"text": document_text(file.filename or "", data)}
    except Exception as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else "Unable to read document") from exc
    finally:
        file.file.close()

@app.post('/api/rfq')
def rfq(body:RFQ,a=Depends(auth)):
    t,_=a; id=hashlib.sha256(body.source_id.encode()).hexdigest()[:24]
    with db() as c:
        existing=c.execute('SELECT data FROM quotes WHERE tenant=? AND id=?',(t,id)).fetchone()
        if existing:
            old=json.loads(existing[0]);
            if old['text']!=body.text or old['customer']!=body.customer: raise HTTPException(409,'Source ID already used')
            return dict(id=id,**old)
        customer=get(c,'customers',t,body.customer); products=rows(c,'products',t); policy=pricing_policy(c,t)
    try:
        extracted, mode = extract_request(body.text)
    except Exception as exc:
        raise HTTPException(503,'Extraction unavailable; retry safely') from exc
    lines=extracted.items; items=[]; issues=list(extracted.issues)
    if not lines: issues.append('No complete product lines extracted')
    for line in lines:
        p,candidates=resolve(line.description,line.unit,products)
        if not p: issues.append('Clarify product: '+line.description); continue
        item=price(p,line.quantity,customer,policy); items.append(item)
    for sku in {i['sku'] for i in items}:
        if sum(i['quantity'] for i in items if i['sku']==sku)>next(p['stock'] for p in products if p['id']==sku): issues.append('Insufficient stock: '+sku)
    total=sum(i['total'] for i in items); cost=sum(i['cost'] for i in items)
    q=dict(customer=body.customer,text=body.text,items=items,issues=issues,extraction_mode=mode,extracted_lines=[line.model_dump() for line in lines],total=total,cost=cost,status='clarification' if issues else 'approval' if requires_approval(items,total,policy) else 'review')
    with db() as c:
        existing=c.execute('SELECT data FROM quotes WHERE tenant=? AND id=?',(t,id)).fetchone()
        if existing: raise HTTPException(409,'Concurrent request; retry')
        put(c,'inbox',t,id,body.model_dump()); put(c,'quotes',t,id,q); audit(c,t,'draft',id)
    return dict(id=id,**q)
@app.get('/api/pricing/policy')
def read_policy(a=Depends(auth)):
    with db() as c: return pricing_policy(c,a[0])

@app.post('/api/pricing/policy')
def update_policy(policy:PricingPolicy,a=Depends(auth)):
    if a[1]!='manager': raise HTTPException(403,'Manager required')
    if policy.minimum_margin>policy.target_margin: raise HTTPException(422,'Minimum exceeds target margin')
    with db() as c:
        put(c,'settings',a[0],'pricing',policy.model_dump())
        audit(c,a[0],'pricing_policy_change','pricing')
    return policy

@app.get('/api/catalog/search')
def catalog_search(description:str,unit:str,a=Depends(auth)):
    with db() as c:
        products=rows(c,'products',a[0])
    return rank(description,unit,products)[:10]

@app.get('/api/{table}')
def listing(table:str,a=Depends(auth)):
    if table not in ['products','customers','quotes','audit','orders','inbox','outbox']: raise HTTPException(404)
    with db() as c: return rows(c,table,a[0])
@app.post('/api/quotes/{id}/{action}')
def transition(id:str,action:str,a=Depends(auth)):
    t,role=a
    with db() as c:
        q=get(c,'quotes',t,id); status=q['status']
        if action=='approve' and status in ['approval','review']:
            if status=='approval' and role!='manager': raise HTTPException(403,'Manager required')
            q['status']='approved'
        elif action=='send' and status=='approved':
            for i in q['items']:
                p=get(c,'products',t,i['sku']); customer=get(c,'customers',t,q['customer'])
                if any(price(dict(id=i['sku'],**p),i['quantity'],customer,pricing_policy(c,t)).get(k)!=v for k,v in i.items()): raise HTTPException(409,'Price changed; create new quote')
            q['status']='sent'; put(c,'outbox',t,id,dict(customer=q['customer'],quote=q,delivery='simulated'))
        elif action=='accept' and status=='sent':
            for sku in {i['sku'] for i in q['items']}:
                p=get(c,'products',t,sku); qty=sum(i['quantity'] for i in q['items'] if i['sku']==sku)
                if p['stock']<qty: raise HTTPException(409,'Insufficient inventory')
                p['stock']-=qty; put(c,'products',t,sku,p)
            q['status']='ordered'; put(c,'orders',t,id,dict(quote_id=id,total=q['total'],status='reserved'))
        elif action=='reject' and status in ['review','approval','approved']: q['status']='rejected'
        else: raise HTTPException(409,'Invalid state transition')
        put(c,'quotes',t,id,q); audit(c,t,action,id); return q
class Cost(BaseModel): cost:int=Field(gt=0)
@app.post('/api/products/{sku}/cost')
def change_cost(sku:str,b:Cost,a=Depends(auth)):
    if a[1]!='manager': raise HTTPException(403)
    with db() as c:
        p=get(c,'products',a[0],sku); old=p['cost']; p['cost']=b.cost; put(c,'products',a[0],sku,p); audit(c,a[0],'cost_change',sku)
        return dict(old=old,new=b.cost,recommended_unit_price=round(b.cost/.7),affected_quotes=[q['id'] for q in rows(c,'quotes',a[0]) if any(i['sku']==sku for i in q['items'])])
@app.get('/api/guidance/{sku}')
def guidance(sku:str,a=Depends(auth)):
    with db() as c:
        p=get(c,'products',a[0],sku); return dict(product=p,recommended_unit_price=round(p['cost']/.7),alternatives=[x for x in rows(c,'products',a[0]) if x['unit']==p['unit'] and x['id']!=sku],warning='Alternatives require specification verification')
app.mount('/',StaticFiles(directory=ROOT/'static',html=True),name='ui')
