import sys
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict

def format_money(amount):
    return f"{amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"

def parse_line(line):
    parts = line.strip().split(',')
    if len(parts) != 3:
        return None
    date, category, amount_str = parts
    try:
        amount = Decimal(amount_str)
    except:
        return None
    return date, category, amount

def get_category_totals(records):
    totals = defaultdict(Decimal)
    for _, category, amount in records:
        totals[category] += amount
    return totals

def main():
    records = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parsed = parse_line(line)
        if parsed is None:
            sys.stderr.write("Error: malformed line\n")
            sys.exit(2)
        records.append(parsed)

    if len(sys.argv) < 2:
        sys.stderr.write("Usage error\n")
        sys.exit(2)

    command = sys.argv[1]

    if command == 'total':
        total = sum((r[2] for r in records), Decimal('0'))
        print(format_money(total))
    elif command == 'count':
        print(len(records))
    elif command == 'average':
        if not records:
            print("0.00")
        else:
            total = sum((r[2] for r in records), Decimal('0'))
            avg = total / len(records)
            print(format_money(avg))
    elif command == 'categories':
        totals = get_category_totals(records)
        # Sort by amount descending, then category name ascending
        sorted_categories = sorted(totals.items(), key=lambda x: (-x[1], x[0]))
        for cat, amt in sorted_categories:
            print(f"{cat}: {format_money(amt)}")
    elif command == 'top':
        if len(sys.argv) < 3:
            sys.stderr.write("Usage error\n")
            sys.exit(2)
        try:
            n = int(sys.argv[2])
        except ValueError:
            sys.stderr.write("Usage error\n")
            sys.exit(2)
        
        totals = get_category_totals(records)
        sorted_categories = sorted(totals.items(), key=lambda x: (-x[1], x[0]))
        for cat, amt in sorted_categories[:n]:
            print(f"{cat}: {format_money(amt)}")
    elif command == 'category':
        if len(sys.argv) < 3:
            sys.stderr.write("Usage error\n")
            sys.exit(2)
        target_cat = sys.argv[2]
        totals = get_category_totals(records)
        if target_cat not in totals:
            sys.stderr.write(f"Error: category {target_cat} not found\n")
            sys.exit(1)
        print(format_money(totals[target_cat]))
    else:
        sys.stderr.write("Usage error\n")
        sys.exit(2)

if __name__ == '__main__':
    main()
