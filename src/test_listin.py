"""
test_listin.py — Prueba end-to-end del módulo listin_guia.

Uso:
    python test_listin.py                 # fecha de hoy
    python test_listin.py 2026-05-16      # fecha específica
"""
import sys
import logging
from datetime import date, datetime
from pathlib import Path

from listin_guia import fetch_guia

OUT_DIR = Path("./out_listin")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    target = datetime.now().date()
    if len(sys.argv) > 1:
        target = date.fromisoformat(sys.argv[1])

    OUT_DIR.mkdir(exist_ok=True)
    print(f"\n{'='*60}")
    print(f"TEST GUIA DEPORTIVA — {target}")
    print(f"{'='*60}\n")

    result = fetch_guia(target_date=target, work_dir=OUT_DIR)

    print(f"\n--- RESUMEN ---")
    print(f"Fecha:         {result.fecha}")
    print(f"Artículo:      {result.article_url or '(no encontrado)'}")
    print(f"Yumpu hash:    {result.yumpu_hash or '(no extraído)'}")
    print(f"Numeric ID:    {result.yumpu_numeric_id or '(no extraído)'}")
    print(f"Páginas:       {result.pages_downloaded}")
    print(f"Error:         {result.error or 'ninguno'}")
    print(f"OCR chars:     {len(result.ocr_text)}")
    print(f"Picks MLB:     {sum(1 for p in result.picks if p.sport == 'MLB')}")
    print(f"Picks NBA:     {sum(1 for p in result.picks if p.sport == 'NBA')}")

    if result.ocr_text:
        ocr_file = OUT_DIR / f"ocr_{target.isoformat()}.txt"
        ocr_file.write_text(result.ocr_text, encoding="utf-8")
        print(f"\nOCR completo guardado en: {ocr_file}")

    if result.picks:
        print(f"\n--- PICKS EXTRAÍDOS ---")
        for i, p in enumerate(result.picks, 1):
            print(f"{i:2}. [{p.sport}] {p.matchup}")
            print(f"     → {p.pick[:140]}")

    sys.exit(0 if result.error is None else 1)


if __name__ == "__main__":
    main()
