import sys
import csv
import math
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict

def format_money(amount):
    """Formats a decimal amount to 2 decimal places, rounded half-up."""
    return amount.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)

def parse_input():
    """Reads from stdin and parses CSV records."""
    records = []
    try:
        reader = csv.reader(sys.stdin)
        for i, row in enumerate(reader, 1):
            if not row:
                continue
            if len(row) != 3:
                print(f"Error: malformed line {i}", file=sys.stderr)
                sys.exit(2)
            
            date, category, amount_str = row
            try:
                amount = Decimal(amount_str)
            except:
                print(f"Error: malformed amount on line {i}", file=sys.stderr)
                sys.exit(2)
            
            records.append({'category': category.strip(), 'amount': amount})
    except Exception as e:
        print(f"Error reading input: {e}", file=sys.stderr)
        sys.exit(2)
    return records

def get_category_totals(records):
    totals = defaultdict(Decimal)
    for r in records:
        totals[r['category']] += r['amount']
    return totals

def sort_categories(totals):
    # Sort by amount descending, then by category name ascending
    # Since we want descending amount, we can negate the amount for comparison
    # but since they are Decimals, we use a tuple key: (-amount, name)
    return sorted(totals.items(), key=lambda item: (-item[1], item[0]))

def main():
    if len(sys.argv) < 2:
        print("Usage error: missing command", file=sys.stderr)
        sys.exit(2)

    command = sys.argv[1]
    records = parse_input()

    if command == "total":
        total = sum((r['amount'] for r in records), Decimal(0))
        print(f"{format_money(total):.2f}")

    elif command == "count":
        print(len(records))

    elif command == "average":
        if not records:
            print("0.00")
        else:
            total = sum((r['amount'] for r in records), Decimal(0))
            avg = total / len(records)
            print(f"{format_money(avg):.2f}")

    elif command == "categories":
        totals = get_category_totals(records)
        sorted_cats = sort_categories(totals)
        for cat, amt in sorted_cats:
            print(f"{cat}: {format_money(amt):.2f}")

    elif command == "top":
        if len(sys.argv) < 3:
            print("Usage error: missing N for top command", file=sys.stderr)
            sys.exit(2)
        try:
            n = int(sys.argv[2])
        except ValueError:
            print("Usage error: N must be an integer", file=sys.stderr)
            sys.exit(2)
        
        totals = get_category_totals(records)
        sorted_cats = sort_categories(totals)
        for cat, amt in sorted_cats[:n]:
            print(f"{cat}: {format_money(amt):.2f}")

    elif command == "category":
        if len(sys.argv) < 3:
            print("Usage error: missing category name", file=sys.stderr)
            sys.exit(2)
        target_cat = sys.argv[2]
        totals = get_category_totals(records)
        if target_cat not in totals:
            print(f"Error: category '{target_cat}' not found", file=sys.stderr)
            sys.exit(1)
        print(f"{format_money(totals[target_cat]):.2f}")

    else:
        print(f"Usage error: unknown command '{command}'", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
