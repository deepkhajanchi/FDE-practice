import sys
import csv
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict

def format_money(amount):
    # Quantize to 2 decimal places with ROUND_HALF_UP
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def parse_records():
    records = []
    for line_num, line in enumerate(sys.stdin, start=1):
        line = line.strip()
        if not line:
            continue
        
        parts = line.split(',')
        if len(parts) != 3:
            sys.stderr.write(f"Error: Malformed line {line_num}\n")
            sys.exit(2)
        
        date, category, amount_str = parts
        try:
            amount = Decimal(amount_str)
        except:
            sys.stderr.write(f"Error: Malformed amount on line {line_num}\n")
            sys.exit(2)
            
        records.append({'category': category, 'amount': amount})
    return records

def get_category_totals(records):
    totals = defaultdict(Decimal)
    for r in records:
        totals[r['category']] += r['amount']
    return totals

def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python src/ledger.py <command> [args]\n")
        sys.exit(2)

    records = parse_records()
    command = sys.argv[1]

    if command == 'total':
        total = sum((r['amount'] for r in records), Decimal('0'))
        print(f"{format_money(total):.2f}")

    elif command == 'count':
        print(len(records))

    elif command == 'average':
        if not records:
            print("0.00")
        else:
            total = sum((r['amount'] for r in records), Decimal('0'))
            avg = total / len(records)
            print(f"{format_money(avg):.2f}")

    elif command == 'categories':
        totals = get_category_totals(records)
        # Sort: amount descending, name ascending
        sorted_cats = sorted(totals.items(), key=lambda x: (-x[1], x[0]))
        for cat, amt in sorted_cats:
            print(f"{cat}: {format_money(amt):.2f}")

    elif command == 'top':
        if len(sys.argv) != 3:
            sys.stderr.write("Usage: python src/ledger.py top <N>\n")
            sys.exit(2)
        try:
            n = int(sys.argv[2])
        except ValueError:
             sys.stderr.write("Error: N must be an integer\n")
             sys.exit(2)
        
        totals = get_category_totals(records)
        sorted_cats = sorted(totals.items(), key=lambda x: (-x[1], x[0]))
        for cat, amt in sorted_cats[:n]:
            print(f"{cat}: {format_money(amt):.2f}")

    elif command == 'category':
        if len(sys.argv) != 3:
            sys.stderr.write("Usage: python src/ledger.py category <NAME>\n")
            sys.exit(2)
        
        cat_name = sys.argv[2]
        totals = get_category_totals(records)
        if cat_name not in totals:
            sys.stderr.write(f"Error: Category '{cat_name}' not found\n")
            sys.exit(1)
        
        print(f"{format_money(totals[cat_name]):.2f}")

    else:
        sys.stderr.write(f"Error: Unknown command '{command}'\n")
        sys.exit(2)

if __name__ == "__main__":
    main()
