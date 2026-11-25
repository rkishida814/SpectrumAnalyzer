import numpy as np

def parse_xrd_file(filepath: str):
    """
    Parses an XRD text or CSV file.
    Assumes two columns: X and Y.
    Skips headers and rows that cannot be cast to float.
    Handles scientific notation automatically via Python's float().
    """
    x_data = []
    y_data = []

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            # Replace commas with spaces to handle CSV, then split by whitespace
            parts = line.replace(',', ' ').split()
            
            if len(parts) >= 2:
                try:
                    x_val = float(parts[0])
                    y_val = float(parts[1])
                    x_data.append(x_val)
                    y_data.append(y_val)
                except ValueError:
                    # Ignore lines with text (headers, etc.)
                    continue

    return np.array(x_data, dtype=float), np.array(y_data, dtype=float)
