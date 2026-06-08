import os
import pandas as pd
from datetime import datetime, time, timedelta

def round_down_time(dt_time):
    """Round time down to the previous 15-minute increment."""
    if pd.isna(dt_time):
        return None
    minutes = dt_time.hour * 60 + dt_time.minute
    rounded_minutes = (minutes // 15) * 15
    return rounded_minutes / 60.0

def round_up_time(dt_time):
    """Round time up to the next 15-minute increment."""
    if pd.isna(dt_time):
        return None
    minutes = dt_time.hour * 60 + dt_time.minute
    # If not exactly on a 15-minute mark, round up
    if minutes % 15 != 0:
        rounded_minutes = ((minutes + 14) // 15) * 15
    else:
        rounded_minutes = minutes
    return rounded_minutes / 60.0

def parse_time(time_str):
    """Parse time string like '7:35 AM' into datetime.time object."""
    if not isinstance(time_str, str) or not time_str.strip():
        return None
    try:
        return datetime.strptime(time_str.strip(), "%I:%M %p").time()
    except ValueError:
        try:
            return datetime.strptime(time_str.strip(), "%H:%M").time()
        except ValueError:
            return None

def calculate_billing(row):
    checkin_str = row['Check-in Time']
    checkout_str = row['Check-out Time']
    
    checkin = parse_time(checkin_str)
    checkout = parse_time(checkout_str)
    
    before_hours = 0.0
    after_hours = 0.0
    
    # 1. Before Camp (official start at 9:00 AM)
    if checkin is not None:
        cutoff_in = time(8, 45)
        # Billed from check-in to 9:00 AM if checked in on or before 8:45 AM
        if checkin <= cutoff_in:
            checkin_hour_val = round_down_time(checkin)
            before_hours = 9.0 - checkin_hour_val
            
    # 2. After Camp (official end at 12:00 PM)
    if checkout is not None:
        cutoff_out = time(12, 15)
        # Billed from 12:00 PM to check-out if checked out after 12:15 PM
        if checkout > cutoff_out:
            checkout_hour_val = round_up_time(checkout)
            after_hours = checkout_hour_val - 12.0
            
    total_hours = before_hours + after_hours
    return pd.Series([before_hours, after_hours, total_hours])

def process_roster(filepaths, log_callback=None):
    """Process multiple roster CSVs, calculate billing, and merge them."""
    all_dfs = []
    for filepath in filepaths:
        filename = os.path.basename(filepath)
        try:
            df = pd.read_csv(filepath)
            # Clean whitespace from headers
            df.columns = [col.strip() for col in df.columns]
            
            # If 'Date' column is missing from CSV, extract it dynamically
            if 'Date' not in df.columns:
                import re
                # Look for a YYYY-MM-DD pattern at the beginning of the filename
                date_match = re.search(r'(\d{4})[-_](\d{2})[-_](\d{2})', filename)
                if date_match:
                    file_date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                    df['Date'] = file_date
                else:
                    # Fallback: Use file modification date
                    try:
                        mtime = os.path.getmtime(filepath)
                        file_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                        df['Date'] = file_date
                    except Exception:
                        df['Date'] = datetime.now().strftime("%Y-%m-%d")
            
            # If 'Camp Name' column is missing from CSV, extract it dynamically from the filename
            if 'Camp Name' not in df.columns:
                parts = filename.split('_')
                if len(parts) >= 3:
                    roster_idx = -1
                    for i, p in enumerate(parts):
                        if 'roster' in p or '62792' in p or (p.isdigit() and len(p) > 5):
                            roster_idx = i
                            break
                    if roster_idx > 1:
                        camp_label = " ".join(parts[1:roster_idx])
                    else:
                        camp_label = " ".join(parts[1:-1])
                    df['Camp Name'] = camp_label.replace('_', ' ')
                else:
                    df['Camp Name'] = "Unknown Camp"
            
            # Verify required columns exist
            required = ['Date', 'Student Name', 'Parent Name', 'Check-in Time', 'Check-out Time']
            missing = [r for r in required if r not in df.columns]
            if missing:
                msg = f"Skipping {filename}: Missing columns: {missing}"
                if log_callback:
                    log_callback(msg)
                else:
                    print(msg)
                continue
                
            all_dfs.append(df)
            msg = f"Parsed {len(df)} rows from {filename}"
            if log_callback:
                log_callback(msg)
            else:
                print(msg)
        except Exception as e:
            msg = f"Error reading {filename}: {e}"
            if log_callback:
                log_callback(msg)
            else:
                print(msg)
            
    if not all_dfs:
        return None, None
        
    combined_df = pd.concat(all_dfs, ignore_index=True)
    
    # Drop duplicate student records for the same day to prevent double-billing.
    # This happens when Sawyer provides duplicate calendar links for the same camp.
    dedup_cols = ['Date', 'Student Name', 'Parent Name', 'Check-in Time', 'Check-out Time']
    existing_dedup_cols = [c for c in dedup_cols if c in combined_df.columns]
    if existing_dedup_cols:
        combined_df = combined_df.drop_duplicates(subset=existing_dedup_cols)
    
    # Calculate hours for each record
    combined_df[['Calc Before Hours', 'Calc After Hours', 'Calc Total Hours']] = combined_df.apply(calculate_billing, axis=1)
    
    # Clean up column names and formats
    # Sort by Parent Name then Student Name then Date
    combined_df = combined_df.sort_values(by=['Parent Name', 'Student Name', 'Date'])
    
    # Generate summary: Group by Parent Name and Student Name
    summary_df = combined_df.groupby(['Parent Name', 'Student Name']).agg({
        'Calc Before Hours': 'sum',
        'Calc After Hours': 'sum',
        'Calc Total Hours': 'sum'
    }).reset_index()
    
    # Rename for readability
    summary_df.columns = ['Parent Name', 'Student Name', 'Total Before Camp Hours', 'Total After Camp Hours', 'Total Billed Hours']
    summary_df = summary_df.sort_values(by=['Parent Name', 'Student Name'])
    
    return combined_df, summary_df

def save_to_excel(combined_df, summary_df, output_path):
    """Save the results into a formatted Excel spreadsheet with three sheets."""
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Weekly Summary', index=False)
        
        # Select columns of interest for detailed view to keep it clean
        detail_cols = [
            'Date', 'Camp Name', 'Student Name', 'Parent Name', 
            'Check-in Time', 'Check-out Time', 
            'Calc Before Hours', 'Calc After Hours', 'Calc Total Hours'
        ]
        existing_cols = [c for c in detail_cols if c in combined_df.columns]
        
        # Split combined_df into Extended Care (billable hours > 0) and Standard Hours (billable hours == 0)
        extended_df = combined_df[combined_df['Calc Total Hours'] > 0]
        standard_df = combined_df[combined_df['Calc Total Hours'] == 0]
        
        # Save both detailed views
        extended_df[existing_cols].to_excel(writer, sheet_name='Extended Care (Billed)', index=False)
        standard_df[existing_cols].to_excel(writer, sheet_name='Standard Hours', index=False)
        
        # Auto-adjust column widths for readability
        workbook = writer.book
        for sheet_name in workbook.sheetnames:
            worksheet = workbook[sheet_name]
            for col in worksheet.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                col_letter = col[0].column_letter
                worksheet.column_dimensions[col_letter].width = max(max_len + 3, 10)

if __name__ == "__main__":
    test_file = r"C:\Users\thoma\Downloads\62792-roster-17396502-1780774504.csv"
    if os.path.exists(test_file):
        combined, summary = process_roster([test_file])
        print("Summary results:")
        print(summary)
        
        output_excel = r"C:\Users\thoma\.gemini\antigravity\scratch\sawyer_automation\test_output.xlsx"
        save_to_excel(combined, summary, output_excel)
        print(f"\nSaved test output to: {output_excel}")
    else:
        print(f"Test file not found at {test_file}")

