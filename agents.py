from matching import resolve
from pricing import price, requires_approval

def orchestrate(extracted,mode,customer_id,text,customer,products,policy):
    lines=extracted.items; items=[]; issues=list(extracted.issues)
    if not lines: issues.append('No complete product lines extracted')
    for line in lines:
        p,candidates=resolve(line.description,line.unit,products)
        if not p: issues.append('Clarify product: '+line.description); continue
        item=price(p,line.quantity,customer,policy); items.append(item)
    for sku in {i['sku'] for i in items}:
        if sum(i['quantity'] for i in items if i['sku']==sku)>next(p['stock'] for p in products if p['id']==sku): issues.append('Insufficient stock: '+sku)
    total=sum(i['total'] for i in items); cost=sum(i['cost'] for i in items)
    q=dict(customer=customer_id,text=text,items=items,issues=issues,extraction_mode=mode,extracted_lines=[line.model_dump() for line in lines],total=total,cost=cost,status='clarification' if issues else 'approval' if requires_approval(items,total,policy) else 'review')
    q['agent_trace']=['extraction','catalog_resolution','pricing','inventory_validation','approval_routing']
    return q
