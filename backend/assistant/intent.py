"""Conservative evidence extraction. Ambiguity stays a question, never a default."""

import re
from decimal import Decimal

from products.models import CreditProduct


def normalize(value):
    return " ".join(re.findall(r"[\w]+", value.lower().replace("ё", "е")))


def resolve_product(value):
    text = normalize(value)
    products = list(CreditProduct.objects.filter(active=True).order_by("code"))
    exact = [p for p in products if text in {normalize(p.code), normalize(p.name)}]
    if len(exact) == 1:
        return exact[0]
    codes = set()
    if re.search(r"оборот\w*", text):
        codes.add("working-capital")
    if re.search(r"оборудован\w*", text):
        codes.add("equipment")
    matches = [p for p in products if p.code in codes or normalize(p.name) in text]
    return matches[0] if len(matches) == 1 else None


def request_evidence(texts):
    result = {}
    for text in texts:
        text = text.lower().replace("ё", "е").replace("\u00a0", " ")
        if re.search(
            r"доллар|евро|usd|eur|[$€]|\bили\b|\bот\b.+\bдо\b|\d\s*[-–—]\s*\d|[-−]\s*\d", text
        ):
            # A later unambiguous message can resolve the ambiguity.
            result = {"ambiguous": True}
            continue
        # A request to calculate a payment is not a statement of existing debt.
        # Strip only the explicit request phrase, never financial field values.
        requested_amount = re.sub(
            r"\b(?:рассчитай|посчитай|рассчитать|посчитать|какой\s+(?:будет\s+)?)\s*"
            r"(?:(?:предварительн|ежемесячн|месячн)\w*\s+)?платеж\b",
            "",
            text,
        )
        amount_text = " ".join(
            part
            for part in re.split(r"[!?;]|\.(?!\d)", requested_amount)
            if not re.search(r"выруч|расход|доход|долг|обязательств|плат[её]ж", part)
        )
        if amount_text:
            amounts = []
            for match in re.finditer(
                r"(?<![\w.,])(?P<number>\d[\d ]*(?:[.,]\d{1,2})?)\s*(?P<unit>млн|миллион\w*|тыс\w*|руб\w*|₽)",
                amount_text,
            ):
                raw = match["number"].replace(" ", "").replace(",", ".")
                if len(raw) > 19:
                    result = {"ambiguous": True}
                    amounts = []
                    break
                number = Decimal(raw)
                unit = match["unit"]
                multiplier = (
                    1000000
                    if unit.startswith(("млн", "миллион"))
                    else 1000
                    if unit.startswith("тыс")
                    else 1
                )
                if number * multiplier >= Decimal("10000000000000000"):
                    result = {"ambiguous": True}
                    amounts = []
                    break
                amounts.append(number * multiplier)
            for word, number in (
                ("миллион", 1000000),
                ("два миллиона", 2000000),
                ("полмиллиона", 500000),
            ):
                if re.search(rf"(?<!\w){word}(?!\w)", amount_text):
                    amounts.append(Decimal(number))
            if len(set(amounts)) == 1:
                result.pop("ambiguous", None)
                result["amount"] = str(amounts[0].quantize(Decimal("0.01")))
            elif len(set(amounts)) > 1:
                result = {"ambiguous": True}
                continue
        terms = []
        for match in re.finditer(r"(?<!\d)(\d+)\s*(месяц\w*|мес\.?|год\w*|лет)(?!\w)", text):
            terms.append(int(match[1]) * (12 if match[2].startswith(("год", "лет")) else 1))
        if re.search(r"\bна год\b", text):
            terms.append(12)
        if re.search(r"\bна полгода\b", text):
            terms.append(6)
        if re.search(r"\bна два года\b", text):
            terms.append(24)
        if len(set(terms)) == 1:
            result.pop("ambiguous", None)
            result["term_months"] = terms[0]
        elif len(set(terms)) > 1:
            result = {"ambiguous": True}
        if re.search(r"закупк\w*\s+товар", text):
            result["purpose"] = "Закупка товара"
        elif re.search(r"(?:покупк|приобретени)\w*\s+оборудован", text):
            result["purpose"] = "Приобретение оборудования"
    return result
