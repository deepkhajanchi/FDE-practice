import sys
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

def normalize_decimal(d):
    return d.normalize()

def merge_intervals(intervals):
    if not intervals:
        return []
    intervals.sort()
    merged = []
    curr_start, curr_end = intervals[0]
    for next_start, next_end in intervals[1:]:
        if next_start <= curr_end:
            curr_end = max(curr_end, next_end)
        else:
            merged.append((curr_start, curr_end))
            curr_start, curr_end = next_start, next_end
    merged.append((curr_start, curr_end))
    return merged

def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python src/intervals.py <command> [args]\n")
        sys.exit(2)

    command = sys.argv[1]
    
    intervals = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            sys.stderr.write("Error: Malformed input\n")
            sys.exit(2)
        try:
            start = Decimal(parts[0])
            end = Decimal(parts[1])
            if start > end:
                raise ValueError
            intervals.append((start, end))
        except (InvalidOperation, ValueError):
            sys.stderr.write("Error: Malformed input\n")
            sys.exit(2)

    merged = merge_intervals(intervals)

    if command == 'merge':
        for start, end in merged:
            print(f"{normalize_decimal(start)} {normalize_decimal(end)}")
    elif command == 'count':
        print(len(merged))
    elif command == 'length':
        total_length = sum((end - start for start, end in merged), Decimal('0'))
        # The requirement says "exactly two decimals, rounded half-up"
        # Using format string with .2f will do rounding, but let's be explicit with quantize
        print(f"{total_length.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}")
    elif command == 'covers':
        if len(sys.argv) < 3:
            sys.stderr.write("Error: Missing argument for covers\n")
            sys.exit(2)
        try:
            x = Decimal(sys.argv[2])
        except InvalidOperation:
            sys.stderr.write("Error: Invalid argument for covers\n")
            sys.exit(2)
        
        covered = any(start <= x <= end for start, end in merged)
        print("yes" if covered else "no")
    else:
        sys.stderr.write("Error: Unknown command\n")
        sys.exit(2)

if __name__ == "__main__":
    main()
