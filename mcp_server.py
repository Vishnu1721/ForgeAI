import os
from mcp.server.fastmcp import FastMCP
from app import db, erp, crm, pricing_policy
from matching import rank
from pricing import price

server=FastMCP("ForgeAI")
# Local stdio server: tenant fixed by operator, never by tool arguments.
TENANT=os.environ.get("FORGE_MCP_TENANT","demo")
if TENANT not in {"demo","other"}:
    raise ValueError("Unknown tenant")

@server.tool()
def search_catalog(description:str,unit:str):
    """Find compatible catalog products; suggestions require verification."""
    with db() as c:
        products=erp(c,TENANT).catalog()
    return rank(description,unit,products)[:5]

@server.tool()
def inventory(sku:str):
    """Read stock for an exact SKU."""
    with db() as c:
        p=erp(c,TENANT).product(sku)
    return {"sku":sku,"stock":p["stock"],"unit":p["unit"]}

@server.tool()
def estimate_price(sku:str,customer_id:str,quantity:int):
    """Estimate price without creating or approving a quote."""
    if not 0<quantity<=1000000:
        raise ValueError("Invalid quantity")
    with db() as c:
        return price(dict(id=sku,**erp(c,TENANT).product(sku)),quantity,crm(c,TENANT).account(customer_id),pricing_policy(c,TENANT))

if __name__=="__main__":
    server.run(transport="stdio")
