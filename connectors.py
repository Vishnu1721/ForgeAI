from typing import Protocol

class ERP(Protocol):
    def catalog(self): ...
    def product(self,sku): ...
    def reserve(self,quote_id,items,total): ...

class CRM(Protocol):
    def accounts(self): ...
    def account(self,customer_id): ...

class SQLiteERP:
    def __init__(self,connection,tenant,get,put,rows):
        self.c,self.tenant,self.get,self.put,self.rows=connection,tenant,get,put,rows
    def catalog(self):
        return self.rows(self.c,"products",self.tenant)
    def product(self,sku):
        return self.get(self.c,"products",self.tenant,sku)
    def reserve(self,quote_id,items,total):
        from fastapi import HTTPException
        quantities={}
        for item in items:
            sku=item["sku"]
            quantities[sku]=quantities.get(sku,0)+item["quantity"]
        for sku,qty in quantities.items():
            product=self.product(sku)
            if product["stock"]<qty:
                raise HTTPException(409,"Insufficient inventory")
            product["stock"]-=qty
            self.put(self.c,"products",self.tenant,sku,product)
        self.put(self.c,"orders",self.tenant,quote_id,dict(quote_id=quote_id,total=total,status="reserved"))

class SQLiteCRM:
    def __init__(self,connection,tenant,get,rows):
        self.c,self.tenant,self.get,self.rows=connection,tenant,get,rows
    def accounts(self):
        return self.rows(self.c,"customers",self.tenant)
    def account(self,customer_id):
        return self.get(self.c,"customers",self.tenant,customer_id)
