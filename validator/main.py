import argparse
import json
import csv
import os
import sys
from agent import ValidationAgent
from datetime import datetime

def read_input(input_path):
    creds = []
    try:
        if input_path.endswith('.json'):
            with open(input_path, 'r', encoding='utf-8') as f:
                creds = json.load(f)
        elif input_path.endswith('.csv'):
            with open(input_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                creds = list(reader)
        else:
            # Fallback text handling?
            print("Warning: .txt input assumes URL:USER:PASS format without parsing logic.") 
    except Exception as e:
        print(f"Error reading input: {e}")
    return creds 

def log_result(valid_file, invalid_file, blocked_file, result_type, url, user, password, msg=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{result_type}] URL: {url} | USER: {user} | PASS: {password} | MSG: {msg}"
    print(line)
    
    if result_type in ["SUCCESS", "MFA", "CHANGE_PASSWORD"]:
        target_file = valid_file
    elif result_type == "BLOCKED":
        target_file = blocked_file
    else:
        target_file = invalid_file
    
    try:
        with open(target_file, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"Error writing to log: {e}")

def main():
    parser = argparse.ArgumentParser(description="Validate credentials using Playwright Agent.")
    parser.add_argument("input", type=str, help="Input file (JSON/CSV supported)") # Positional arg now
    parser.add_argument("--output-dir", "-o", type=str, default="outputs", help="Output directory")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode (background)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: Input file {args.input} not found.")
        return
        
    creds = read_input(args.input)
    if not creds:
        print("No credentials found or unsupported format.")
        return
        
    # Determine output filenames based on input basename
    basename = os.path.splitext(os.path.basename(args.input))[0]
    
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
        
    valid_file = os.path.join(args.output_dir, f"{basename}_valid.txt")
    invalid_file = os.path.join(args.output_dir, f"{basename}_invalid.txt")
    blocked_file = os.path.join(args.output_dir, f"{basename}_blocked.txt")
    
    print(f"Loaded {len(creds)} credentials from {basename}.")
    print(f"Valid logs: {valid_file}")
    print(f"Invalid logs: {invalid_file}")
    print(f"Blocked logs: {blocked_file}")
    
    # Create a specific subdirectory for this run's screenshots
    # e.g. outputs/screenshots/teste/
    screenshot_subdir = basename 
    print(f"Screenshots will be saved to: outputs/screenshots/{screenshot_subdir}/")
    
    agent = ValidationAgent(headless=args.headless, screenshot_subdir=screenshot_subdir)
    
    try:
        for i, cred in enumerate(creds):
            url = cred.get('url')
            user = cred.get('username')
            password = cred.get('password')
            
            if not url or not user or not password:
                print(f"Skipping incomplete credential: {cred}")
                continue
                
            print(f"\n--- Testing [{i+1}/{len(creds)}] {url} ---")
            
            agent.start_new_session()
            
            if not agent.navigate(url):
                log_result(valid_file, invalid_file, blocked_file, "ERROR", url, user, password, "Navigation Failed")
                agent.close_current()
                continue
                
            if not agent.find_and_fill_login(user, password):
                log_result(valid_file, invalid_file, blocked_file, "ERROR", url, user, password, "Fields not found or fill failed")
                agent.close_current()
                continue
                
            res = agent.check_result()
            
            if res in ["SUCCESS", "MFA", "CHANGE_PASSWORD"]:
                log_result(valid_file, invalid_file, blocked_file, res, url, user, password, "Valid credential")
                agent.keep_current_session()
            elif res == "BLOCKED":
                log_result(valid_file, invalid_file, blocked_file, "BLOCKED", url, user, password, "Host blocked")
                agent.close_current()
            else:
                log_result(valid_file, invalid_file, blocked_file, "FAILURE", url, user, password, "Login failed")
                agent.close_current()
                
    except KeyboardInterrupt:
        print("\nStopping validator...")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        print("\nAll tests completed.")
        print(f"Active successful sessions: {len(agent.active_sessions)}")
        print("Press Ctrl+C to close all open browsers and exit script (sleeping forever to keep tabs open).")
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            agent.close_all()

if __name__ == "__main__":
    main()
