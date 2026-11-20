import sys

def expand_range(range_str):
    if '-' in range_str:
        start, end = map(int, range_str.split('-'))
        return list(range(start, end + 1))
    else:
        return [int(range_str)]

def main():
    try:
        line = sys.stdin.readline().strip()
        if not line:
            return

        items = line.split(',')
        result = []
        for item in items:
            result.extend(expand_range(item))
        
        print(*(result))
    except (ValueError, IndexError):
        # Handle malformed input gracefully if needed, 
        # though the problem statement assumes valid input.
        pass

if __name__ == "__main__":
    main()
