import argparse
import csv
import json
import re
import os
from typing import List, Dict, Optional

# Regex tolerantes (Hybrid approach)
# Matches http, https, android, or just domain.com
# Regex tolerantes (Hybrid approach)
# Matches http, https, android, or just domain.com
# STRICTER: Excludes common delimiters (:;|,) from the URL tail to prevent capturing creditors
URL_REGEX = re.compile(
    r'(https?://[^\s\'"<>:;|,]+(?::\d+)?(?:/[^\s\'"<>:;|,]*)*|android://[^\s\'"<>:;|,]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?::\d+)?(?:/[^\s\'"<>:;|,]*)*)',
    re.IGNORECASE
)

def normalize_line(line: str, last_url: str) -> Dict[str, any]:
    """
    Returns a dict with:
    - 'creds': list of dicts {url, username, password} (if any found)
    - 'new_url': str (if a new URL was discovered to update state)
    """
    line = line.strip()
    if not line:
        return {'creds': [], 'new_url': None}

    found_url = None
    
    # 1. Attempt to find URL
    match = URL_REGEX.search(line)
    if match:
        raw_url = match.group(1)
        # Basic validation to avoid matching "user@domain.com" as a URL (domain.com) completely
        # If the match starts at index > 0 and char before is '@', ignores it
        start, end = match.span()
        if start > 0 and line[start-1] == '@':
            pass # It is likely an email
        else:
            found_url = raw_url
            if not found_url.startswith(('http', 'android')):
                found_url = 'https://' + found_url
            
            # Remove URL from line to process user/pass
            line = line.replace(raw_url, "", 1)

    # Update state if we found a URL
    current_url_context = found_url if found_url else last_url
    
    # 2. Parse Credentials
    # Clean up leftovers
    line = line.strip()
    line = line.strip(':;|, ') # Remove common separators from ends
    
    creds = []
    
    if line:
        # User:Pass parsing logic (Manual split is often safer/flexible than Regex for passwords)
        delimiter = ':'
        if '|' in line: delimiter = '|'
        elif ';' in line: delimiter = ';'
        elif ',' in line: delimiter = ','
        
        parts = line.split(delimiter)
        
        # We need at least 2 parts for User:Pass
        # BUT, if we have a URL context, maybe the line is just "User:Pass"
        if len(parts) >= 2:
            username = parts[0].strip()
            
            # GARBAGE FILTER: Check if the last part is actually a URL (Referer Source)
            # If so, remove it from the password parts
            last_part = parts[-1].strip()
            if URL_REGEX.match(last_part) or last_part.startswith("http"):
                parts.pop() # Remove garbage URL
            
            # Re-join whatever is left as password
            password = delimiter.join(parts[1:]).strip() 
            
            # Basic sanity check: User shouldn't be empty
            if username and password and current_url_context:
                creds.append({
                    "url": current_url_context,
                    "domain": current_url_context, # Placeholder, domain extraction handles cleaning later if needed
                    "username": username,
                    "password": password
                })
    
    return {
        'creds': creds,
        'new_url': found_url
    }

def process_file(input_path: str) -> List[Dict[str, str]]:
    results = []
    last_url = None
    
    try:
        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                try:
                    outcome = normalize_line(line, last_url)
                    
                    # Update State
                    if outcome['new_url']:
                        last_url = outcome['new_url']
                        
                    # Add found creds
                    if outcome['creds']:
                        results.extend(outcome['creds'])
                        
                except Exception as e:
                    # print(f"Debug error line: {e}") 
                    continue
    except Exception as e:
        print(f"Error reading file {input_path}: {e}")
        
    return results

def main():
    parser = argparse.ArgumentParser(description="Normalize leak files to CSV and JSON.")
    parser.add_argument("input", type=str, help="Input file or directory path") # Positional
    parser.add_argument("--output-dir", "-o", type=str, default="outputs", help="Output directory")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
        
    all_creds = []
    
    if os.path.isfile(args.input):
        print(f"Processing file: {args.input}")
        all_creds.extend(process_file(args.input))
    elif os.path.isdir(args.input):
        print(f"Processing directory: {args.input}")
        for root, _, files in os.walk(args.input):
            for file in files:
                file_path = os.path.join(root, file)
                print(f"  Reading {file_path}...")
                all_creds.extend(process_file(file_path))
    else:
        print("Invalid input path")
        return

    print(f"Found {len(all_creds)} potential credentials.")
    
    # Deduplicate
    # Convert list of dicts to set of tuples for dedup
    unique_creds = set()
    final_list = []
    for c in all_creds:
        # Create tuple (url, user, pass)
        t = (c['url'], c['username'], c['password'])
        if t not in unique_creds:
            unique_creds.add(t)
            final_list.append(c) # Keep dictionary format
    
    # Determine basename
    basename = "normalized"
    if os.path.isfile(args.input):
        basename = os.path.splitext(os.path.basename(args.input))[0]
    
    print(f"Unique credentials: {len(final_list)}")
    
    csv_path = os.path.join(args.output_dir, f"{basename}.csv")
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["url", "username", "password", "domain"])
        writer.writeheader()
        writer.writerows(final_list)
    print(f"Saved CSV to {csv_path}")
    
    json_path = os.path.join(args.output_dir, f"{basename}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(final_list, f, indent=4)
    print(f"Saved JSON to {json_path}")

if __name__ == "__main__":
    main()
