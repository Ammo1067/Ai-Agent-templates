import re, json, csv, os, sys

FIELDNAMES = [
    'Product Name', 'Parent SKU', 'EAN', 'Color', 'Size',
    'Price EUR', 'Gender', 'Category', 'Composition',
    'Description', 'Features', 'Weight', 'URL'
]

def extract_from_html_file(filepath, url):
    try:
        with open(filepath) as f:
            data = json.load(f)
        html = data.get('rawHtml', data.get('html', ''))
    except Exception as e:
        return [{'Product Name': '', 'Parent SKU': '', 'EAN': '', 'Color': '',
                 'Size': '', 'Price EUR': '', 'Gender': '', 'Category': '',
                 'Composition': f'ERROR: {e}', 'Description': '', 'Features': '',
                 'Weight': '', 'URL': url}]

    simples = {}
    m = re.search(r'AEC\.CONFIGURABLE_SIMPLES\s*=\s*(\{.*?\});', html)
    if m:
        try:
            simples = json.loads(m.group(1))
        except:
            pass

    simple_ean = ''
    sm = re.search(r'AEC\.SIMPLE_PRODUCT\s*=\s*(\{.*?\});', html)
    if sm:
        try:
            sp = json.loads(sm.group(1))
            simple_ean = sp.get('id', '')
        except:
            pass

    product_name = ''
    parent_sku = ''
    category = ''
    price_default = 0
    for ld in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL):
        try:
            obj = json.loads(ld.group(1).strip())
            if isinstance(obj, dict) and obj.get('@type') == 'Product':
                product_name = obj.get('name', '')
                parent_sku = obj.get('sku', '')
                category = obj.get('category', '')
                offers = obj.get('offers', {})
                price_default = offers.get('price', 0)
                break
        except:
            pass

    composition = ''
    cp = html.find('Composition')
    if cp > 0:
        snip = html[cp:cp+1200]
        items = re.findall(r'<li[^>]*>(.*?)</li>', snip, re.DOTALL)
        items = [re.sub(r'<[^>]+>', '', i).strip() for i in items if i.strip() and len(i.strip()) < 200]
        composition = '; '.join(items[:8])

    description = ''
    dm = re.search(r'property="og:description"\s+content="([^"]*)"', html)
    if not dm:
        dm = re.search(r'content="([^"]*?)"\s+property="og:description"', html)
    if dm:
        description = dm.group(1)

    features = ''
    fp = html.find('>Features<')
    if fp > 0:
        snip = html[fp:fp+2000]
        items = re.findall(r'<li[^>]*>(.*?)</li>', snip, re.DOTALL)
        items = [re.sub(r'<[^>]+>', '', i).strip() for i in items if i.strip() and len(i.strip()) < 200]
        features = '; '.join(items[:10])

    weight = ''
    wm = re.search(r'Weight \(single shoe\).*?<li[^>]*>(.*?)</li>', html, re.DOTALL)
    if not wm:
        wm = re.search(r'Weight.*?<li[^>]*>(.*?)</li>', html, re.DOTALL)
    if wm:
        weight = re.sub(r'<[^>]+>', '', wm.group(1)).strip()

    base = {
        'Product Name': product_name,
        'Parent SKU': parent_sku,
        'Category': category,
        'Composition': composition,
        'Description': description,
        'Features': features,
        'Weight': weight,
        'URL': url
    }

    rows = []
    if simples:
        for vid, vdata in simples.items():
            price = vdata.get('price', price_default)
            price_eur = f'{price/100:.2f}' if price > 100 else f'{price:.2f}'
            row = dict(base)
            row['Product Name'] = vdata.get('name', product_name)
            row['EAN'] = vdata.get('id', '')
            row['Color'] = vdata.get('variant', '')
            row['Size'] = vdata.get('size', '')
            row['Price EUR'] = price_eur
            row['Gender'] = vdata.get('gender', '')
            rows.append(row)
    else:
        price_eur = f'{price_default/100:.2f}' if price_default > 100 else f'{price_default:.2f}'
        base['EAN'] = simple_ean
        base['Color'] = ''
        base['Size'] = ''
        base['Price EUR'] = price_eur
        base['Gender'] = ''
        rows.append(base)

    return rows


def process_batch(batch_file, output_csv):
    with open(batch_file) as f:
        urls = [u.strip() for u in f if u.strip()]

    all_rows = []
    for i, url in enumerate(urls):
        print(f'[{i+1}/{len(urls)}] {url}', flush=True)
        # Signal the agent to scrape this URL and provide the file path back
        # The agent reads this output and knows which URL to process next
        print(f'SCRAPE_URL: {url}', flush=True)

    return all_rows


if __name__ == '__main__':
    # Called with: python cmp_extractor.py <html_file> <url> <output_csv> [append]
    html_file = sys.argv[1]
    url = sys.argv[2]
    output_csv = sys.argv[3]
    mode = sys.argv[4] if len(sys.argv) > 4 else 'append'

    rows = extract_from_html_file(html_file, url)

    file_exists = os.path.exists(output_csv)
    write_mode = 'a' if (mode == 'append' and file_exists) else 'w'
    with open(output_csv, write_mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_mode == 'w' or not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    print(f'Wrote {len(rows)} rows. EANs found: {sum(1 for r in rows if r["EAN"])}')
