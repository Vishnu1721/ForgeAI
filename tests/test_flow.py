import os,tempfile
os.environ['FORGE_DB']=tempfile.mktemp(suffix='.db')
os.environ.pop('OPENAI_API_KEY',None)
from app import app
from fastapi.testclient import TestClient
c=TestClient(app); h={'Authorization':'Bearer demo-sales'}
def test_flow():
    b={'customer':'C1','text':'500 kg of Sodium chloride industrial grade','source_id':'one'}
    q=c.post('/api/rfq',json=b,headers=h).json(); assert q['status']=='review'; id=q['id']
    assert c.post('/api/rfq',json=b,headers=h).json()==q
    for a in ['approve','send','accept']: assert c.post(f'/api/quotes/{id}/{a}',headers=h).status_code==200
    assert c.post(f'/api/quotes/{id}/accept',headers=h).status_code==409
    assert c.get('/api/orders',headers={'Authorization':'Bearer other-sales'}).json()==[]
def test_unknown():
    q=c.post('/api/rfq',json={'customer':'C1','text':'10 kg of unknown','source_id':'two'},headers=h).json(); assert q['status']=='clarification'
def test_auth(): assert c.get('/api/products').status_code==401
