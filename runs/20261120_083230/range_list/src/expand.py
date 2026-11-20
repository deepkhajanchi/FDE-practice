import sys

def expand_range(item):
    """Expands a range 'a-b' into a list of integers or returns [n] for a single integer."""
    if '-' in item:
        try:
            start, end = map(int, item.split('-'))
            return list(range(start, end + 1))
        except ValueError:
            return []
    else:
        try:
            return [int(item)]
        except ValueError:
            return []

def main():
    # Read one line from stdin
    input_data = sys.stdin.read().strip()
    
    if not input_data:
        return

    # Split by comma to get individual items
    items = input_data.split(',')
    
    results = []
    for item in items:
        results.extend(expand_range(item.strip()))
    
    # Print results space-separated
    print(*(results))

if __name__ == "__main__":
    main()
