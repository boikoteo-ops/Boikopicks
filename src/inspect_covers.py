"""
Script temporal: descarga el HTML de Covers Consensus para Over/Under MLB
y lo guarda en disco para inspeccion posterior.

Uso: python -m src.inspect_covers
Salida: out_covers/covers_ou.html
"""
import os
import requests

URL_OU = "https://contests.covers.com/consensus/topoverunderconsensus/mlb/overall"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}


def main():
    print(f"Descargando: {URL_OU}")

    try:
        r = requests.get(URL_OU, headers=HEADERS, timeout=20)
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

    os.makedirs('out_covers', exist_ok=True)
    out_path = 'out_covers/covers_ou.html'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(r.text)
    print(f"\nGuardado: {out_path}")

    # Sneak peek: mostrar primeras lineas con keywords utiles
    print(f"\n--- Lineas con 'over' o 'under' (primeras 10) ---")
    lines = r.text.split('\n')
    found = 0
    for line in lines:
        if 'over' in line.lower() or 'under' in line.lower():
            stripped = line.strip()
            if stripped and len(stripped) < 300:
                print(f"  {stripped[:200]}")
                found += 1
                if found >= 10:
                    break
    print(f"\n(Lineas con over/under encontradas en muestra: {found})")
    return 0


if __name__ == '__main__':
    exit(main())
