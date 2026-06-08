import os
# Force Playwright to use the global browser directory instead of the PyInstaller temp folder
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.expandvars(r"%USERPROFILE%\AppData\Local\ms-playwright")

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import asyncio
from datetime import datetime, timedelta
import glob
import json


# Import core logic
from data_processor import process_roster, save_to_excel
from scraper import run_scraper
from email_sender import send_billing_email

class SawyerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Sawyer Roster Billing & Automation")
        self.root.geometry("650x650")
        self.root.minsize(500, 500)
        
        # Style layout
        self.style = ttk.Style()
        self.style.theme_use('vista') # Use clean native theme
        
        self.config_dir = os.path.expandvars(r"%USERPROFILE%\AppData\Local\SawyerRosterAutomation")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.config = self.load_config()
        
        self.create_widgets()
        
    def load_config(self):
        default_config = {
            "remember": True, 
            "email": "", 
            "password": "", 
            "email_enabled": False,
            "sender_email": "",
            "sender_password": "",
            "smtp_server": "smtp.gmail.com",
            "smtp_port": "587",
            "recipient_email": ""
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    loaded = json.load(f)
                    default_config.update(loaded)
            except Exception:
                pass
        return default_config
        
    def save_config(self, **kwargs):
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            current_config = self.load_config()
            current_config.update(kwargs)
            with open(self.config_file, 'w') as f:
                json.dump(current_config, f, indent=4)
            self.config = current_config
        except Exception:
            pass
        
    def create_widgets(self):
        # Notebook for Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Tab 1: Scraper & Processor
        self.tab_auto = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_auto, text="Automated Scraper")
        
        # Tab 2: Process Local Folder Only
        self.tab_local = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_local, text="Process Local Folder")
        
        # Tab 3: Email Settings
        self.tab_email = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_email, text="Email Settings")
        
        self.setup_auto_tab()
        self.setup_local_tab()
        self.setup_email_tab()
        
        # Log console (common at bottom)
        log_frame = ttk.LabelFrame(self.root, text="System Log")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        self.log_text = tk.Text(log_frame, height=12, state=tk.DISABLED, wrap=tk.WORD, font=("Courier", 9))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
    def log(self, message):
        """Thread-safe logging method."""
        self.root.after(0, self._log, message)
        
    def _log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
    def setup_auto_tab(self):
        # Frame
        frame = ttk.Frame(self.tab_auto, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # 1. Credentials
        cred_frame = ttk.LabelFrame(frame, text="Sawyer Credentials", padding=10)
        cred_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(cred_frame, text="Email:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.email_entry = ttk.Entry(cred_frame, width=40)
        self.email_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(cred_frame, text="Password:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.pass_entry = ttk.Entry(cred_frame, show="*", width=40)
        self.pass_entry.grid(row=1, column=1, padx=5, pady=5)
        
        self.remember_var = tk.BooleanVar(value=self.config.get("remember", True))
        self.remember_cb = ttk.Checkbutton(cred_frame, text="Remember credentials", variable=self.remember_var)
        self.remember_cb.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Populate if remember is checked
        if self.remember_var.get():
            self.email_entry.insert(0, self.config.get("email", ""))
            self.pass_entry.insert(0, self.config.get("password", ""))
        
        # 2. Date Range
        date_frame = ttk.LabelFrame(frame, text="Scraping Date Range", padding=10)
        date_frame.pack(fill=tk.X, pady=5)
        
        # Default start/end dates
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        ttk.Label(date_frame, text="Start Date (YYYY-MM-DD):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.start_date_entry = ttk.Entry(date_frame, width=15)
        self.start_date_entry.insert(0, today_str)
        self.start_date_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(date_frame, text="End Date (YYYY-MM-DD):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.end_date_entry = ttk.Entry(date_frame, width=15)
        self.end_date_entry.insert(0, today_str)
        self.end_date_entry.grid(row=1, column=1, padx=5, pady=5)
        
        # 3. Output
        out_frame = ttk.LabelFrame(frame, text="Output Directory & Settings", padding=10)
        out_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(out_frame, text="Save Results to:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.output_dir_entry = ttk.Entry(out_frame, width=35)
        self.output_dir_entry.insert(0, os.path.expanduser("~/Downloads"))
        self.output_dir_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Button(out_frame, text="Browse...", command=self.browse_output_dir).grid(row=0, column=2, padx=5, pady=5)
        
        self.headless_var = tk.BooleanVar(value=False)
        self.headless_cb = ttk.Checkbutton(out_frame, text="Run browser in background (headless)", variable=self.headless_var)
        self.headless_cb.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Action button
        self.run_btn = ttk.Button(frame, text="Start Download & Processing", command=self.start_scraping_thread)
        self.run_btn.pack(pady=15, ipady=5)
        
    def setup_local_tab(self):
        frame = ttk.Frame(self.tab_local, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        local_frame = ttk.LabelFrame(frame, text="Local CSV Processing", padding=10)
        local_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(local_frame, text="CSV Folder Path:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.local_dir_entry = ttk.Entry(local_frame, width=35)
        self.local_dir_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Button(local_frame, text="Browse...", command=self.browse_local_dir).grid(row=0, column=2, padx=5, pady=5)
        
        # Action button
        self.process_local_btn = ttk.Button(frame, text="Process & Clean CSVs", command=self.run_local_processing)
        self.process_local_btn.pack(pady=20, ipady=5)
        
    def browse_output_dir(self):
        dir_selected = filedialog.askdirectory()
        if dir_selected:
            self.output_dir_entry.delete(0, tk.END)
            self.output_dir_entry.insert(0, dir_selected)
            
    def browse_local_dir(self):
        dir_selected = filedialog.askdirectory()
        if dir_selected:
            self.local_dir_entry.delete(0, tk.END)
            self.local_dir_entry.insert(0, dir_selected)
            
    def start_scraping_thread(self):
        email = self.email_entry.get().strip()
        password = self.pass_entry.get()
        start_date = self.start_date_entry.get().strip()
        end_date = self.end_date_entry.get().strip()
        output_dir = self.output_dir_entry.get().strip()
        
        if not email or not password:
            messagebox.showerror("Error", "Please enter Sawyer email and password.")
            return
            
        # Save credentials based on checkbox
        self.save_config(
            email=email if self.remember_var.get() else "",
            password=password if self.remember_var.get() else "",
            remember=self.remember_var.get()
        )
            
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Error", "Dates must be in YYYY-MM-DD format.")
            return
            
        self.run_btn.config(state=tk.DISABLED)
        self.log("Initializing web scraping task...")
        
        # Run in separate thread to keep GUI responsive
        t = threading.Thread(target=self.run_scraper_and_processor, args=(email, password, start_date, end_date, output_dir))
        t.daemon = True
        t.start()
        
    def run_scraper_and_processor(self, email, password, start_date, end_date, output_dir):
        # Create temp download dir
        temp_dir = os.path.join(output_dir, "sawyer_temp_downloads")
        
        try:
            # Check and install playwright browser if needed
            self.log("Verifying browser requirements...")
            import sys
            import playwright.__main__
            # Programmatically run playwright install in-process to avoid sys.executable issues in compiled EXE
            self.log("Installing/Verifying Playwright Chromium browser...")
            original_argv = sys.argv
            sys.argv = ["playwright", "install", "chromium"]
            try:
                playwright.__main__.main()
            except SystemExit:
                pass
            finally:
                sys.argv = original_argv



            # Run playwright scraper
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                run_scraper(email, password, start_date, end_date, temp_dir, self.log, headless=self.headless_var.get())
            )

            
            # Find all downloaded CSVs
            csv_files = glob.glob(os.path.join(temp_dir, "*.csv"))
            if not csv_files:
                self.log("No rosters were downloaded. Check credentials or date range.")
                return
                
            self.log(f"Downloaded {len(csv_files)} rosters. Processing hours...")
            combined, summary = process_roster(csv_files, self.log)
            
            if combined is not None:
                out_path = os.path.join(output_dir, f"Sawyer_Billing_{start_date}_to_{end_date}.xlsx")
                save_to_excel(combined, summary, out_path)
                self.log(f"SUCCESS: Billed hours successfully saved to: {out_path}")
                
                # Check if email is enabled
                if self.config.get("email_enabled", False):
                    self.log("Emailing billing report...")
                    try:
                        send_billing_email(
                            sender_email=self.config.get("sender_email"),
                            sender_password=self.config.get("sender_password"),
                            smtp_server=self.config.get("smtp_server"),
                            smtp_port=self.config.get("smtp_port"),
                            recipient_email=self.config.get("recipient_email"),
                            subject=f"Sawyer Billing Report {start_date} to {end_date}",
                            body=f"Hello,\n\nPlease find attached the Sawyer billing report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} for the range {start_date} to {end_date}.",
                            attachment_path=out_path
                        )
                        self.log("SUCCESS: Billing report emailed successfully!")
                    except Exception as email_err:
                        self.log(f"WARNING: Report saved locally, but failed to email: {email_err}")
                
                messagebox.showinfo("Success", f"Billing report created successfully at:\n{out_path}")
                
                # Only clean up temp files if processing succeeded
                for f in csv_files:
                    try:
                        os.remove(f)
                    except Exception:
                        pass
                try:
                    os.rmdir(temp_dir)
                except Exception:
                    pass
            else:
                self.log("No data was parsed from the rosters.")
                self.log(f"WARNING: The downloaded CSV files have been kept for inspection in: {temp_dir}")
                
        except Exception as e:
            self.log(f"ERROR during execution: {e}")
            messagebox.showerror("Execution Error", f"An error occurred: {e}")
        finally:
            self.root.after(0, lambda: self.run_btn.config(state=tk.NORMAL))
            
    def run_local_processing(self):
        local_dir = self.local_dir_entry.get().strip()
        if not local_dir or not os.path.exists(local_dir):
            messagebox.showerror("Error", "Please select a valid folder containing CSVs.")
            return
            
        csv_files = glob.glob(os.path.join(local_dir, "*.csv"))
        if not csv_files:
            messagebox.showerror("Error", "No CSV files found in the selected directory.")
            return
            
        self.log(f"Found {len(csv_files)} local CSVs. Starting processing...")
        
        try:
            combined, summary = process_roster(csv_files, self.log)
            if combined is not None:
                out_path = os.path.join(local_dir, "Combined_Sawyer_Billing_Report.xlsx")
                save_to_excel(combined, summary, out_path)
                self.log(f"SUCCESS: Local CSVs processed. Report saved to: {out_path}")
                messagebox.showinfo("Success", f"Billing report created successfully at:\n{out_path}")
            else:
                self.log("Could not process any records. Ensure columns format matches.")
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Error", f"Failed to process files: {e}")

    def setup_email_tab(self):
        frame = ttk.Frame(self.tab_email, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # 1. Enable Toggle
        toggle_frame = ttk.Frame(frame, padding=5)
        toggle_frame.pack(fill=tk.X, pady=5)
        self.email_enabled_var = tk.BooleanVar(value=self.config.get("email_enabled", False))
        self.email_enabled_cb = ttk.Checkbutton(toggle_frame, text="Enable Emailing Reports Automatically", variable=self.email_enabled_var, command=self.toggle_email_fields)
        self.email_enabled_cb.pack(side=tk.LEFT, padx=5)
        
        # 2. Settings Inputs
        settings_frame = ttk.LabelFrame(frame, text="SMTP Server Configuration", padding=10)
        settings_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(settings_frame, text="Sender Email:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.sender_email_entry = ttk.Entry(settings_frame, width=40)
        self.sender_email_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(settings_frame, text="Sender Password / App Password:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.sender_password_entry = ttk.Entry(settings_frame, show="*", width=40)
        self.sender_password_entry.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(settings_frame, text="SMTP Server:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.smtp_server_entry = ttk.Entry(settings_frame, width=40)
        self.smtp_server_entry.grid(row=2, column=1, padx=5, pady=5)
        
        ttk.Label(settings_frame, text="SMTP Port:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.smtp_port_entry = ttk.Entry(settings_frame, width=15)
        self.smtp_port_entry.grid(row=3, column=1, padx=5, pady=5)
        
        ttk.Label(settings_frame, text="Recipient Email:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.recipient_email_entry = ttk.Entry(settings_frame, width=40)
        self.recipient_email_entry.grid(row=4, column=1, padx=5, pady=5)
        
        # Load values from config
        self.sender_email_entry.insert(0, self.config.get("sender_email", ""))
        self.sender_password_entry.insert(0, self.config.get("sender_password", ""))
        self.smtp_server_entry.insert(0, self.config.get("smtp_server", "smtp.gmail.com"))
        self.smtp_port_entry.insert(0, self.config.get("smtp_port", "587"))
        self.recipient_email_entry.insert(0, self.config.get("recipient_email", ""))
        
        # Controls Frame
        ctrl_frame = ttk.Frame(frame, padding=5)
        ctrl_frame.pack(fill=tk.X, pady=10)
        
        self.save_email_btn = ttk.Button(ctrl_frame, text="Save Email Settings", command=self.save_email_settings)
        self.save_email_btn.pack(side=tk.LEFT, padx=5)
        
        self.test_email_btn = ttk.Button(ctrl_frame, text="Send Test Email", command=self.send_test_email)
        self.test_email_btn.pack(side=tk.LEFT, padx=5)
        
        self.toggle_email_fields()
        
    def toggle_email_fields(self):
        state = tk.NORMAL if self.email_enabled_var.get() else tk.DISABLED
        self.sender_email_entry.config(state=state)
        self.sender_password_entry.config(state=state)
        self.smtp_server_entry.config(state=state)
        self.smtp_port_entry.config(state=state)
        self.recipient_email_entry.config(state=state)
        
    def save_email_settings(self):
        enabled = self.email_enabled_var.get()
        sender = self.sender_email_entry.get().strip()
        pwd = self.sender_password_entry.get()
        server = self.smtp_server_entry.get().strip()
        port = self.smtp_port_entry.get().strip()
        recipient = self.recipient_email_entry.get().strip()
        
        self.save_config(
            email_enabled=enabled,
            sender_email=sender,
            sender_password=pwd,
            smtp_server=server,
            smtp_port=port,
            recipient_email=recipient
        )
        self.log("Email settings saved.")
        messagebox.showinfo("Success", "Email settings saved successfully.")
        
    def send_test_email(self):
        sender = self.sender_email_entry.get().strip()
        pwd = self.sender_password_entry.get()
        server = self.smtp_server_entry.get().strip()
        port = self.smtp_port_entry.get().strip()
        recipient = self.recipient_email_entry.get().strip()
        
        if not sender or not pwd or not recipient:
            messagebox.showerror("Error", "Please fill in Sender Email, Password, and Recipient Email before testing.")
            return
            
        self.log("Sending test email...")
        try:
            send_billing_email(
                sender_email=sender,
                sender_password=pwd,
                smtp_server=server,
                smtp_port=port,
                recipient_email=recipient,
                subject="Sawyer Automation - SMTP Test Email",
                body="This is a test email from the Sawyer Roster Billing & Automation tool. SMTP connection is working correctly!"
            )
            self.log("SUCCESS: Test email sent successfully!")
            messagebox.showinfo("Success", "Test email sent successfully!")
        except Exception as e:
            self.log(f"FAILED to send test email: {e}")
            messagebox.showerror("Error", f"Failed to send email:\n{e}")

def run_silent_cli(args):
    """Run the scraping and processing pipeline in command-line mode without GUI."""
    # Load configuration for credentials
    config_dir = os.path.expandvars(r"%USERPROFILE%\AppData\Local\SawyerRosterAutomation")
    config_file = os.path.join(config_dir, "config.json")
    
    config = {}
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
        except Exception:
            pass
            
    email = args.email or config.get("email")
    password = args.password or config.get("password")
    
    if not email or not password:
        print("ERROR: Sawyer credentials are required. Run the GUI once and save them, or pass --email and --password.")
        sys.exit(1)
        
    # Dates
    start_date = args.start_date
    end_date = args.end_date
    
    if not start_date or not end_date:
        today = datetime.now()
        if args.days:
            start_dt = today - timedelta(days=args.days - 1)
            start_date = start_dt.strftime("%Y-%m-%d")
        else:
            start_date = today.strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        
    output_dir = args.output_dir or os.path.expanduser("~/Downloads")
    temp_dir = os.path.join(output_dir, "sawyer_temp_downloads")
    
    print(f"Starting silent processing...")
    print(f"Date Range: {start_date} to {end_date}")
    print(f"Output Directory: {output_dir}")
    
    # 1. Verify Playwright Chromium is installed
    print("Verifying browser requirements...")
    original_argv = sys.argv
    sys.argv = ["playwright", "install", "chromium"]
    try:
        import playwright.__main__
        playwright.__main__.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
        
    # 2. Run Scraper
    print("Running scraper...")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            run_scraper(email, password, start_date, end_date, temp_dir, print, headless=args.headless)
        )
        
        # 3. Find all downloaded CSVs
        csv_files = glob.glob(os.path.join(temp_dir, "*.csv"))
        if not csv_files:
            print("No rosters were downloaded. Check credentials or date range.")
            sys.exit(1)
            
        print(f"Downloaded {len(csv_files)} rosters. Processing hours...")
        combined, summary = process_roster(csv_files, print)
        
        if combined is not None:
            out_path = os.path.join(output_dir, f"Sawyer_Billing_{start_date}_to_{end_date}.xlsx")
            save_to_excel(combined, summary, out_path)
            print(f"SUCCESS: Report saved to: {out_path}")
            
            # Send Email if enabled
            email_enabled = args.send_email or config.get("email_enabled", False)
            if email_enabled:
                sender = config.get("sender_email")
                pwd = config.get("sender_password")
                smtp_srv = config.get("smtp_server", "smtp.gmail.com")
                smtp_prt = config.get("smtp_port", "587")
                recipient = config.get("recipient_email")
                
                if sender and pwd and recipient:
                    print("Sending email...")
                    try:
                        send_billing_email(
                            sender_email=sender,
                            sender_password=pwd,
                            smtp_server=smtp_srv,
                            smtp_port=smtp_prt,
                            recipient_email=recipient,
                            subject=f"Sawyer Billing Report {start_date} to {end_date} (Automatic)",
                            body=f"Please find attached the automatically generated billing report.",
                            attachment_path=out_path
                        )
                        print("SUCCESS: Email sent successfully!")
                    except Exception as email_err:
                        print(f"ERROR: Email failed to send: {email_err}")
                else:
                    print("ERROR: Email settings are incomplete in config.json. Cannot send email.")
            
            # Clean up temp files
            for f in csv_files:
                try:
                    os.remove(f)
                except Exception:
                    pass
            try:
                os.rmdir(temp_dir)
            except Exception:
                pass
        else:
            print("No data was parsed from the rosters.")
            
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="Sawyer Roster Billing & Automation Tool")
    parser.add_argument("--cli", action="store_true", help="Run in command-line mode without GUI")
    parser.add_argument("--email", help="Sawyer account email")
    parser.add_argument("--password", help="Sawyer account password")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, help="Number of days prior to today to process (e.g. 1 for today)")
    parser.add_argument("--output-dir", help="Directory to save the Excel file")
    parser.add_argument("--headless", action="store_true", default=False, help="Run browser in background (headless)")
    parser.add_argument("--send-email", action="store_true", help="Send report via email after compilation")
    
    if len(sys.argv) > 1 and ("--cli" in sys.argv or "-h" in sys.argv or "--help" in sys.argv):
        args = parser.parse_args()
        if "--headless" not in sys.argv:
            args.headless = True
        run_silent_cli(args)
    else:
        root = tk.Tk()
        app = SawyerApp(root)
        root.mainloop()
