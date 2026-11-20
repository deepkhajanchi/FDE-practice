import sys
import decimal
import argparse

def format_decimal(d):
    """
    Format a decimal number:
    - Remove trailing zeros.
    - Remove trailing decimal point if unnecessary.
    """
    if d == d.to_integral_value():
        return str(d.to_integral_value())
    return d.normalize().to_eng_string()

def parse_intervals():
    intervals = []
    for line_num, line in enumerate(sys.stdin, 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            print(f"Error: Malformed line {line_num}: expected 2 numbers.", file=sys.stderr)
            sys.exit(2)
        try:
            start = decimal.Decimal(parts[0])
            end = decimal.Decimal(parts[1])
        except decimal.InvalidOperation:
            print(f"Error: Malformed line {line_num}: invalid numbers.", file=sys.stderr)
            sys.exit(2)
        
        if start > end:
            print(f"Error: Malformed line {line_num}: start > end.", file=sys.stderr)
            sys.exit(2)
        intervals.append((start, end))
    return intervals

def merge_intervals(intervals):
    if not intervals:
        return []
    
    # Sort by start time
    intervals.sort(key=lambda x: x[0])
    
    merged = []
    curr_start, curr_end = intervals[0]
    
    for i in range(1, len(intervals)):
        next_start, next_end = intervals[i]
        
        # Merge if they overlap or touch (next_start <= curr_end)
        if next_start <= curr_end:
            curr_end = max(curr_end, next_end)
        else:
            merged.append((curr_start, curr_end))
            curr_start, curr_end = next_start, next_end
            
    merged.append((curr_start, curr_end))
    return merged

def main():
    if len(sys.argv) < 2:
        print("Usage: python src/intervals.py <command> [args]", file=sys.stderr)
        sys.exit(2)

    command = sys.argv[1]
    intervals = parse_intervals()
    merged = merge_intervals(intervals)

    if command == 'merge':
        for start, end in merged:
            print(f"{format_decimal(start)} {format_decimal(end)}")
            
    elif command == 'count':
        print(len(merged))
        
    elif command == 'length':
        total = sum((end - start for start, end in merged), decimal.Decimal(0))
        # Round half-up to 2 decimal places
        quantized = total.quantize(decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP)
        print(f"{quantized:.2f}")
        
    elif command == 'covers':
        if len(sys.argv) != 3:
            print("Usage: python src/intervals.py covers <number>", file=sys.stderr)
            sys.exit(2)
        try:
            x = decimal.Decimal(sys.argv[2])
        except decimal.InvalidOperation:
            print(f"Error: '{sys.argv[2]}' is not a valid number.", file=sys.stderr)
            sys.exit(2)
            
        found = False
        for start, end in merged:
            if start <= x <= end:
                found = True
                break
        print("yes" if found else "no")
        
    else:
        print(f"Error: Unknown command '{command}'", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
