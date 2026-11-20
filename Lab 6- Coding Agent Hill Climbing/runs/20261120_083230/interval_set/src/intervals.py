import sys
from decimal import Decimal, ROUND_HALF_UP

def format_decimal(d):
    """
    Formats a Decimal by trimming trailing zeros and the decimal point if necessary.
    Example: 4.0 -> '4', 1.50 -> '1.5', 2.675 -> '2.675'
    """
    s = "{:f}".format(d.normalize())
    return s

def merge_intervals(intervals):
    if not intervals:
        return []
    
    # Sort by start, then end
    sorted_intervals = sorted(intervals, key=lambda x: (x[0], x[1]))
    
    merged = []
    if not sorted_intervals:
        return merged
        
    curr_start, curr_end = sorted_intervals[0]
    
    for next_start, next_end in sorted_intervals[1:]:
        # If the next interval overlaps or touches (next_start <= curr_end)
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
    
    # Read intervals
    intervals = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            parts = line.split()
            if len(parts) != 2:
                raise ValueError
            start, end = Decimal(parts[0]), Decimal(parts[1])
            if start > end:
                raise ValueError
            intervals.append((start, end))
        except Exception:
            sys.stderr.write(f"Invalid input line: {line}\n")
            sys.exit(2)
            
    merged = merge_intervals(intervals)
    
    if command == "merge":
        for start, end in merged:
            print(f"{format_decimal(start)} {format_decimal(end)}")
            
    elif command == "count":
        print(len(merged))
        
    elif command == "length":
        total_length = sum((end - start for start, end in merged), Decimal('0'))
        # Round half-up to 2 decimals
        # Quantize works well for this
        rounded = total_length.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        print(f"{rounded:.2f}")
        
    elif command == "covers":
        if len(sys.argv) < 3:
            sys.stderr.write("Usage: covers <number>\n")
            sys.exit(2)
        try:
            target = Decimal(sys.argv[2])
        except Exception:
            sys.stderr.write("Invalid number for covers\n")
            sys.exit(2)
            
        found = False
        for start, end in merged:
            if start <= target <= end:
                found = True
                break
        print("yes" if found else "no")
        
    else:
        sys.stderr.write(f"Unknown command: {command}\n")
        sys.exit(2)

if __name__ == "__main__":
    main()
