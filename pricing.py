from decimal import Decimal, ROUND_HALF_UP
from pydantic import BaseModel, Field

class PricingPolicy(BaseModel):
    target_margin: int = Field(default=30,ge=1,le=90)
    minimum_margin: int = Field(default=20,ge=0,le=90)
    volume_threshold: int = Field(default=1000,gt=0)
    volume_discount: int = Field(default=5,ge=0,le=50)
    approval_total: int = Field(default=2000000,gt=0)

def price(product,qty,customer,policy=None):
    policy=policy or PricingPolicy()
    cost=product["cost"]*qty
    discount=customer["discount"]+(policy.volume_discount if qty>=policy.volume_threshold else 0)
    if not 0<=discount<100:
        raise ValueError("Invalid combined discount")
    total=int((Decimal(cost)/(1-Decimal(policy.target_margin)/100)*(1-Decimal(discount)/100)).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
    contract=customer.get("contract",{}).get(product["id"])
    if contract is not None:
        if not isinstance(contract,int) or contract<=0:
            raise ValueError("Invalid contract price")
        total=contract*qty
    margin=round((total-cost)/total*100,2) if total else -100
    return dict(sku=product["id"],name=product["name"],quantity=qty,unit=product["unit"],cost=cost,total=total,margin=margin,pricing=dict(method="contract" if contract is not None else "cost_plus",discount_percent=0 if contract is not None else discount,target_margin=policy.target_margin,minimum_margin=policy.minimum_margin,approval_required=margin<policy.minimum_margin))

def requires_approval(items,total,policy):
    return total>policy.approval_total or any(i["margin"]<policy.minimum_margin for i in items)
