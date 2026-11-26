import time
import os, sqlite3, json, re, uuid, hmac, hashlib, urllib.request, difflib
from decimal import Decimal, ROUND_HALF_UP
from contextlib import contextmanager
from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pathlib import Path
from ingestion import document_text, MAX_BYTES
from extraction import extract_request
from agents import orchestrate
from analytics import summarize
from quote_email import compose
from matching import resolve, rank
from pricing import price, PricingPolicy, requires_approval
from connectors import SQLiteERP, SQLiteCRM
ROOT=Path(__file__).parent
DB=os.getenv('FORGE_DB',str(ROOT/'forge.db'))
app=FastAPI(title='ForgeAI')
if os.getenv('FORGE_ENV')=='production':
    secrets=[os.getenv(k,'') for k in ('SALES_TOKEN','MANAGER_TOKEN','OTHER_TOKEN')]
    if any(len(k)<32 or k in ('demo-sales','demo-manager','other-sales') for k in secrets) or len(set(secrets))!=3:
        raise RuntimeError('Production requires three distinct strong tokens')

@contextmanager
def db():
    c=sqlite3.connect(DB,timeout=20); c.row_factory=sqlite3.Row
    try:
        c.execute('BEGIN IMMEDIATE'); yield c; c.commit()
    except: c.rollback(); raise
    finally: c.close()
def init():
    with db() as c:
        for table in ['products','customers','quotes','audit','orders','inbox','outbox','settings','workflows']:
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
def erp(c,t): return SQLiteERP(c,t,get,put,rows)
def crm(c,t): return SQLiteCRM(c,t,get,rows)

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
        customer=crm(c,t).account(body.customer); products=erp(c,t).catalog(); policy=pricing_policy(c,t)
        row=c.execute("SELECT data FROM workflows WHERE tenant=? AND id=?",(t,id)).fetchone()
        state=json.loads(row[0]) if row else {"request":body.model_dump(),"attempts":0}
        if state["request"]!=body.model_dump(): raise HTTPException(409,'Source ID already used')
        if state.get("lease_until",0)>time.time(): raise HTTPException(409,'Workflow already running')
        state["lease_until"]=time.time()+300
        state["owner"]=uuid.uuid4().hex
        state["attempts"]+=1
        state["status"]="running"
        put(c,'workflows',t,id,state)
    try:
        if "extraction" in state:
            from extraction import Extraction
            extracted=Extraction.model_validate(state["extraction"])
            mode=state["mode"]
        else:
            extracted,mode=extract_request(body.text)
            with db() as c:
                if get(c,'workflows',t,id).get('owner')!=state['owner']: raise HTTPException(409,'Workflow lease lost')
                state.update(extraction=extracted.model_dump(),mode=mode,status="extracted")
                put(c,'workflows',t,id,state)
        q=orchestrate(extracted,mode,body.customer,body.text,customer,products,policy)
    except Exception as exc:
        with db() as c:
            if get(c,'workflows',t,id).get('owner')==state['owner']:
                state["status"]="retryable"
                state["lease_until"]=0
                put(c,'workflows',t,id,state)
        raise HTTPException(503,'Workflow unavailable; retry with same source ID') from exc
    with db() as c:
        existing=c.execute('SELECT data FROM quotes WHERE tenant=? AND id=?',(t,id)).fetchone()
        if existing: raise HTTPException(409,'Concurrent request; retry')
        if get(c,'workflows',t,id).get('owner')!=state['owner']: raise HTTPException(409,'Workflow lease lost')
        put(c,'inbox',t,id,body.model_dump()); put(c,'quotes',t,id,q); audit(c,t,'draft',id)
        state['status']='completed'; state['lease_until']=0; put(c,'workflows',t,id,state)
    return dict(id=id,**q)
@app.get('/api/workflows/{id}')
def workflow_status(id:str,a=Depends(auth)):
    with db() as c:
        state=get(c,'workflows',a[0],id)
    return {k:state[k] for k in ('status','attempts')}

@app.get('/api/integrations/status')
def integration_status(a=Depends(auth)):
    return {"erp":{"provider":"sqlite","mode":"simulated"},"crm":{"provider":"sqlite","mode":"simulated"}}

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
        products=erp(c,a[0]).catalog()
    return rank(description,unit,products)[:10]

@app.get('/api/analytics/summary')
def analytics_summary(a=Depends(auth)):
    with db() as c:
        return summarize(rows(c,'quotes',a[0]))

@app.get('/api/{table}')
def listing(table:str,a=Depends(auth)):
    if table not in ['products','customers','quotes','audit','orders','inbox','outbox']: raise HTTPException(404)
    with db() as c: return rows(c,table,a[0])
@app.get('/api/quotes/{id}/email')
def email_preview(id:str,a=Depends(auth)):
    with db() as c:
        q=get(c,'quotes',a[0],id)
        if q['status'] not in ('approved','sent','ordered'): raise HTTPException(409,'Approval required')
        return compose(id,q,crm(c,a[0]).account(q['customer']))

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
                p=erp(c,t).product(i['sku']); customer=crm(c,t).account(q['customer'])
                if any(price(dict(id=i['sku'],**p),i['quantity'],customer,pricing_policy(c,t)).get(k)!=v for k,v in i.items()): raise HTTPException(409,'Price changed; create new quote')
            q['status']='sent'; put(c,'outbox',t,id,dict(customer=q['customer'],quote=q,delivery='simulated',message=compose(id,q,crm(c,t).account(q['customer']))))
        elif action=='accept' and status=='sent':
            erp(c,t).reserve(id,q['items'],q['total'])
            q['status']='ordered'
        elif action=='reject' and status in ['review','approval','approved']: q['status']='rejected'
        else: raise HTTPException(409,'Invalid state transition')
        put(c,'quotes',t,id,q); audit(c,t,action,id); return q
class Cost(BaseModel): cost:int=Field(gt=0)
@app.post('/api/products/{sku}/cost')
def change_cost(sku:str,b:Cost,a=Depends(auth)):
    if a[1]!='manager': raise HTTPException(403)
    with db() as c:
        p=get(c,'products',a[0],sku); old=p['cost']; p['cost']=b.cost; put(c,'products',a[0],sku,p); audit(c,a[0],'cost_change',sku)
        return dict(old=old,new=b.cost,recommended_unit_price=round(b.cost/(1-pricing_policy(c,a[0]).target_margin/100)),affected_quotes=[q['id'] for q in rows(c,'quotes',a[0]) if any(i['sku']==sku for i in q['items'])])
@app.get('/api/selling/recommendations')
def recommendations(description:str,unit:str,customer_id:str,quantity:int=1,a=Depends(auth)):
    if not 0<quantity<=1000000: raise HTTPException(422,'Invalid quantity')
    with db() as c:
        products=erp(c,a[0]).catalog()
        customer=crm(c,a[0]).account(customer_id)
        policy=pricing_policy(c,a[0])
    result=[]
    for candidate in rank(description,unit,products)[:5]:
        p=candidate['product']
        result.append(dict(sku=p['id'],name=p['name'],score=candidate['score'],available=p['stock']>=quantity,stock=p['stock'],estimate=price(p,quantity,customer,policy),requires_specification_review=True))
    return {"recommendations":result,"warning":"Suggestions are not approved substitutes or binding quotations"}

@app.get('/api/guidance/{sku}')
def guidance(sku:str,a=Depends(auth)):
    with db() as c:
        p=get(c,'products',a[0],sku); return dict(product=p,recommended_unit_price=round(p['cost']/(1-pricing_policy(c,a[0]).target_margin/100)),alternatives=[x for x in rows(c,'products',a[0]) if x['unit']==p['unit'] and x['id']!=sku],warning='Alternatives require specification verification')
app.mount('/',StaticFiles(directory=ROOT/'static',html=True),name='ui')
