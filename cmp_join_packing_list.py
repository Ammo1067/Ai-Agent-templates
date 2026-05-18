"""Join CMP packing list (Excel) with scraped catalog data to produce a CSV
where each packing list line gets its matching EAN-13 and product details.

Usage:
  python3 cmp_join_packing_list.py <packing_list.xlsx> <scraped.csv> <output.csv>
"""
import sys, csv
import openpyxl
from collections import defaultdict

IT_TO_EN = {
    'NERO': ['Black', 'NERO'],
    'BIANCO': ['B.CO', 'BIANCO', 'White'],
    'ANTRACITE': ['Anthracite', 'ANTRACITE', 'Antracite'],
    'CORDA': ['Corda', 'CORDA'],
    'GRIGIO': ['Grey', 'GREY'],
    'BLU': ['Blue'],
    'BLU SCURO': ['Blu Scuro', 'Navy'],
    'VERDE': ['Green'],
    'ROSSO': ['Red'],
    'GIALLO': ['Yellow'],
    'ARANCIO': ['Orange'],
    'FUXIA FLUO': ['FUXIA', 'FUCSIA', 'Pink', 'Fluo Pink'],
    'PETROLEUM': ['Petrol', 'PETROLEUM'],
    'OLIVE': ['Olive', 'OLIVE', 'Militare'],
    'SAGE': ['SAGE', 'Sage'],
    'CEMENTO': ['CEMENTO'],
    'GHIACCIO': ['Ice', 'GHIACCIO'],
}

EU_TO_UK = {
    '39': '5,5', '40': '6,5', '41': '7', '42': '8',
    '43': '9', '44': '9,5', '45': '10,5', '46': '11', '47': '12',
}


def normalize_size(packing_size, sku_sizes):
    ps = packing_size.strip()
    if ps in sku_sizes:
        return ps
    if ps.upper() in ('U', 'UNI', 'UNICA') and 'ONE SIZE' in sku_sizes:
        return 'ONE SIZE'
    if ps in EU_TO_UK and EU_TO_UK[ps] in sku_sizes:
        return EU_TO_UK[ps]
    return None


def expand_colors(color_var):
    parts = [p.strip() for p in color_var.split('-')]
    expanded = [color_var, color_var.replace(' ', '-')]
    for p in parts:
        if p in IT_TO_EN:
            for tr in IT_TO_EN[p]:
                expanded.append(color_var.replace(p, tr))
    if len(parts) == 2:
        expanded.append(f'{parts[1]}-{parts[0]}')
        for p1 in IT_TO_EN.get(parts[0], [parts[0]]):
            for p2 in IT_TO_EN.get(parts[1], [parts[1]]):
                expanded.append(f'{p1}-{p2}')
                expanded.append(f'{p2}-{p1}')
    return list(set(expanded))


def color_match(pc, sc):
    pc, sc = pc.upper().strip(), sc.upper().strip()
    if pc == sc:
        return True
    if pc and sc and (pc in sc or sc in pc):
        return True
    for cand in expand_colors(pc):
        cu = cand.upper()
        if cu == sc or cu in sc or sc in cu:
            return True
    if '-' in pc and '-' in sc:
        pc_parts = set(p.strip() for p in pc.split('-'))
        sc_parts = set(p.strip() for p in sc.split('-'))
        if len(pc_parts) == 2 and pc_parts == sc_parts:
            return True
        translated = set()
        for p in pc_parts:
            translated.add(p)
            for tr in IT_TO_EN.get(p, []):
                translated.add(tr.upper())
        if translated >= sc_parts or sc_parts >= translated:
            return True
    return False


def main(packing_xlsx, scraped_csv, output_csv):
    scraped_by_sku = defaultdict(list)
    seen_eans = set()
    with open(scraped_csv, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['EAN'] in seen_eans:
                continue
            seen_eans.add(r['EAN'])
            scraped_by_sku[r['Parent SKU'].upper().strip()].append(r)

    wb = openpyxl.load_workbook(packing_xlsx, data_only=True)
    packing = []
    for row in wb['Inventory Detail'].iter_rows(min_row=2, values_only=True):
        if row[0]:
            packing.append({
                'doc_number': str(row[0]),
                'doc_date': str(row[1]),
                'order_ref': str(row[2]),
                'product_code': str(row[3]).strip().upper(),
                'color_code': str(row[4]).strip() if row[4] else '',
                'description': row[5] or '',
                'color_variant': (row[6] or '').strip().upper(),
                'size': str(row[7]).strip() if row[7] else '',
                'qty': row[8],
            })

    OUT_FIELDS = [
        'Doc Number', 'Doc Date', 'Order Reference', 'Qty',
        'Product Code', 'Color Code', 'Color / Variant', 'Size (Packing List)',
        'EAN', 'Product Name', 'Price EUR', 'Gender',
        'Category', 'Composition', 'Description', 'Features', 'Weight',
        'Matched Color (from scrape)', 'Matched Size (from scrape)', 'URL', 'Match Status',
    ]

    joined = []
    match_stats = defaultdict(int)
    for p in packing:
        candidates = scraped_by_sku.get(p['product_code'], [])
        sku_sizes = set(c['Size'].strip() for c in candidates)
        target_size = normalize_size(p['size'], sku_sizes)
        match = None
        if target_size is None:
            status = 'SKU NOT IN SCRAPE' if not candidates else 'SIZE NOT AVAILABLE'
        else:
            size_matches = [c for c in candidates if c['Size'].strip() == target_size]
            for c in size_matches:
                if c['Color'].upper() == p['color_variant']:
                    match = c; status = 'exact'; break
            if not match:
                for c in size_matches:
                    if color_match(p['color_variant'], c['Color']):
                        match = c; status = 'fuzzy color'; break
            if not match and len(size_matches) == 1:
                match = size_matches[0]; status = 'size-only (1 color avail)'
            if not match:
                status = 'COLOR NOT FOUND'

        match_stats[status] += 1
        joined.append({
            'Doc Number': p['doc_number'], 'Doc Date': p['doc_date'], 'Order Reference': p['order_ref'],
            'Qty': p['qty'], 'Product Code': p['product_code'], 'Color Code': p['color_code'],
            'Color / Variant': p['color_variant'], 'Size (Packing List)': p['size'],
            'EAN': match['EAN'] if match else '',
            'Product Name': match['Product Name'] if match else p['description'],
            'Price EUR': match['Price EUR'] if match else '',
            'Gender': match['Gender'] if match else '',
            'Category': match['Category'] if match else '',
            'Composition': match['Composition'] if match else '',
            'Description': match['Description'] if match else '',
            'Features': match['Features'] if match else '',
            'Weight': match['Weight'] if match else '',
            'Matched Color (from scrape)': match['Color'] if match else '',
            'Matched Size (from scrape)': match['Size'] if match else '',
            'URL': match['URL'] if match else '',
            'Match Status': status,
        })

    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        w.writerows(joined)

    print(f'Total: {len(joined)} | With EAN: {sum(1 for r in joined if r["EAN"])}')
    for k, v in sorted(match_stats.items(), key=lambda x: -x[1]):
        print(f'  {k}: {v}')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
