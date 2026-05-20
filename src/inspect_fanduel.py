"""
Script temporal: descarga el HTML de FanDuel Research para MLB betting odds
y lo guarda en disco para inspeccion posterior.

URL: https://www.fanduel.com/research/mlb-betting-odds-MM-DD-YYYY

Uso: python -m src.inspect_fanduel
Salida: out_fanduel/fanduel_mlb.html
"""
import os
from datetime import datetime
import pytz
import requests


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


def build_url():
    """Genera URL con la fecha de hoy en formato MM-DD-YYYY."""
    tz = pytz.timezone('America/Santo_Domingo')
    today = datetime.now(tz)
    date_str = today.strftime('%m-%d-%Y')
    return f"https://www.fanduel.com/research/mlb-betting-odds-{date_str}", date_str


def main():
    url, date_str = build_url()
    print(f"Descargando: {url}")

    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except requests.exceptions.RequestException as e:
        print(f"ERROR red: {e}")
        return 1

    print(f"Status: {r.status_code}")
    print(f"Tamano: {len(r.text)} bytes")
    print(f"Content-Type: {r.headers.get('Content-Type', '?')}")

    if r.status_code != 200:
        print(f"\n--- Body (primeros 500 chars) ---")
        print(r.text[:500])
        return 1

    os.makedirs('out_fanduel', exist_ok=True)
    out_path = 'out_fanduel/fanduel_mlb.html'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(r.text)
    print(f"\nGuardado: {out_path}")

    # Sneak peek: buscar keywords interesantes
    text_lower = r.text.lower()
    keywords = {
        'over/under': text_lower.count('over/under'),
        'over -': text_lower.count('over -'),  # tipo "over -110"
        'under -': text_lower.count('under -'),
        'moneyline': text_lower.count('moneyline'),
        'runline': text_lower.count('runline'),
        'numberfire': text_lower.count('numberfire'),
        '__NEXT_DATA__': r.text.count('__NEXT_DATA__'),
        'window.__': r.text.count('window.__'),
        '"total"': r.text.count('"total"'),
    }
    print(f"\n--- Keywords encontrados ---")
    for k, v in keywords.items():
        print(f"  {k}: {v}")

    # Mostrar primeras lineas con "over/under" (caso insensitive)
    print(f"\n--- Lineas con 'over/under' (primeras 5) ---")
    lines = r.text.split('\n')
    found = 0
    for line in lines:
        if 'over/under' in line.lower():
            stripped = line.strip()
            if stripped and len(stripped) < 400:
                print(f"  {stripped[:300]}")
                found += 1
                if found >= 5:
                    break

    return 0


if __name__ == '__main__':
    exit(main())
