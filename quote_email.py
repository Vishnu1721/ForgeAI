def compose(quote_id,quote,customer):
    def money(cents):
        return f"${cents/100:,.2f}"
    lines=[f"Hello {customer['name']},","","Thank you for your request. Please review the following quotation:",""]
    for item in quote["items"]:
        lines.append(f"{item['sku']} | {item['name']} | {item['quantity']} {item['unit']} | {money(item['total'])}")
    lines.extend(["",f"Total: {money(quote['total'])}","Please confirm if you would like to proceed.","","ForgeAI Sales"])
    return {"subject":f"Quotation {quote_id}","body":"\n".join(lines)}
