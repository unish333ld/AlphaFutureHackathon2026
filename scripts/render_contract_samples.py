"""Render every sample page for human QA, without changing PDF source bytes."""

import argparse
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("docs/samples"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for path in sorted(args.input.glob("*.pdf")):
        document = pdfium.PdfDocument(path)
        pages = []
        for number, page in enumerate(document, 1):
            bitmap = page.render(scale=1.5)
            pixels = bitmap.to_pil().convert("RGB")
            pixels.save(args.output / f"{path.stem}-page-{number}.png")
            pages.append(pixels)
        columns = 2
        width, height = pages[0].size
        sheet = Image.new(
            "RGB", (width * columns, (height + 25) * ((len(pages) + 1) // columns)), "#dddddd"
        )
        for index, page in enumerate(pages):
            x, y = (index % columns) * width, (index // columns) * (height + 25)
            sheet.paste(page, (x, y + 25))
            ImageDraw.Draw(sheet).text((x + 8, y + 5), f"Page {index + 1}", fill="black")
        sheet.save(args.output / f"{path.stem}-all-pages.png")
        print(f"{path.name}: {len(pages)} pages rendered")


if __name__ == "__main__":
    main()
