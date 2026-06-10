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
import subprocess


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
        self.update_cookie_status()
        
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
            
        # Row 3: Cookies status
        ttk.Label(cred_frame, text="Login Session:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.cookie_status_label = ttk.Label(cred_frame, text="Checking status...")
        self.cookie_status_label.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Row 4: Refresh button
        self.refresh_session_btn = ttk.Button(cred_frame, text="Log in / Refresh Session", command=self.refresh_login_session)
        self.refresh_session_btn.grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        
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
                
                # Check if email is enabled or SMS is enabled
                email_enabled = self.config.get("email_enabled", False)
                sms_enabled = self.config.get("sms_enabled", False) and self.config.get("sms_recipients")
                
                if email_enabled or sms_enabled:
                    email_body = generate_operational_email_body(combined, "Sawyer_Billing", start_date)
                    
                    if email_enabled:
                        self.log("Emailing billing report...")
                        try:
                            send_billing_email(
                                sender_email=self.config.get("sender_email"),
                                sender_password=self.config.get("sender_password"),
                                smtp_server=self.config.get("smtp_server"),
                                smtp_port=self.config.get("smtp_port"),
                                recipient_email=self.config.get("recipient_email"),
                                subject=f"Sawyer Billing Report ({start_date} to {end_date})",
                                body=email_body,
                                attachment_path=out_path
                            )
                            self.log("SUCCESS: Billing report emailed successfully!")
                        except Exception as email_err:
                            self.log(f"WARNING: Report saved locally, but failed to email: {email_err}")
                            
                    if sms_enabled:
                        self.log("Sending SMS notifications...")
                        try:
                            sms_body = generate_operational_sms_body(combined, "Sawyer_Billing", start_date)
                            from email_sender import send_sms_notification
                            send_sms_notification(
                                sender_email=self.config.get("sender_email"),
                                sender_password=self.config.get("sender_password"),
                                smtp_server=self.config.get("smtp_server"),
                                smtp_port=self.config.get("smtp_port"),
                                phone_numbers=self.config.get("sms_recipients"),
                                body=sms_body
                            )
                            self.log("SUCCESS: SMS notifications sent successfully!")
                        except Exception as sms_err:
                            self.log(f"WARNING: Failed to send SMS: {sms_err}")
                
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
        self.email_enabled_cb = ttk.Checkbutton(toggle_frame, text="Enable Automated Notifications (Email / SMS)", variable=self.email_enabled_var, command=self.toggle_email_fields)
        self.email_enabled_cb.pack(side=tk.LEFT, padx=5)
        
        # 2. Settings Inputs
        settings_frame = ttk.LabelFrame(frame, text="SMTP & SMS Configuration", padding=10)
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
        
        ttk.Label(settings_frame, text="SMS Recipients:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=5)
        self.sms_recipients_entry = ttk.Entry(settings_frame, width=40)
        self.sms_recipients_entry.grid(row=5, column=1, padx=5, pady=5)
        
        self.sms_enabled_var = tk.BooleanVar(value=self.config.get("sms_enabled", False))
        self.sms_enabled_cb = ttk.Checkbutton(settings_frame, text="Enable SMS / Text Notifications (T-Mobile)", variable=self.sms_enabled_var)
        self.sms_enabled_cb.grid(row=6, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Load values from config
        self.sender_email_entry.insert(0, self.config.get("sender_email", ""))
        self.sender_password_entry.insert(0, self.config.get("sender_password", ""))
        self.smtp_server_entry.insert(0, self.config.get("smtp_server", "smtp.gmail.com"))
        self.smtp_port_entry.insert(0, self.config.get("smtp_port", "587"))
        self.recipient_email_entry.insert(0, self.config.get("recipient_email", ""))
        self.sms_recipients_entry.insert(0, self.config.get("sms_recipients", ""))
        
        # Controls Frame
        ctrl_frame = ttk.Frame(frame, padding=5)
        ctrl_frame.pack(fill=tk.X, pady=10)
        
        self.save_email_btn = ttk.Button(ctrl_frame, text="Save Settings", command=self.save_email_settings)
        self.save_email_btn.pack(side=tk.LEFT, padx=5)
        
        self.test_email_btn = ttk.Button(ctrl_frame, text="Send Test Email/SMS", command=self.send_test_email)
        self.test_email_btn.pack(side=tk.LEFT, padx=5)
        
        self.toggle_email_fields()
        
    def toggle_email_fields(self):
        state = tk.NORMAL if self.email_enabled_var.get() else tk.DISABLED
        self.sender_email_entry.config(state=state)
        self.sender_password_entry.config(state=state)
        self.smtp_server_entry.config(state=state)
        self.smtp_port_entry.config(state=state)
        self.recipient_email_entry.config(state=state)
        self.sms_recipients_entry.config(state=state)
        self.sms_enabled_cb.config(state=state)
        
    def save_email_settings(self):
        enabled = self.email_enabled_var.get()
        sender = self.sender_email_entry.get().strip()
        pwd = self.sender_password_entry.get()
        server = self.smtp_server_entry.get().strip()
        port = self.smtp_port_entry.get().strip()
        recipient = self.recipient_email_entry.get().strip()
        sms_recipients = self.sms_recipients_entry.get().strip()
        sms_enabled = self.sms_enabled_var.get()
        
        self.save_config(
            email_enabled=enabled,
            sender_email=sender,
            sender_password=pwd,
            smtp_server=server,
            smtp_port=port,
            recipient_email=recipient,
            sms_recipients=sms_recipients,
            sms_enabled=sms_enabled
        )
        self.log("Email & SMS settings saved.")
        messagebox.showinfo("Success", "Email & SMS settings saved successfully.")
        
    def send_test_email(self):
        sender = self.sender_email_entry.get().strip()
        pwd = self.sender_password_entry.get()
        server = self.smtp_server_entry.get().strip()
        port = self.smtp_port_entry.get().strip()
        recipient = self.recipient_email_entry.get().strip()
        sms_recipients = self.sms_recipients_entry.get().strip()
        
        if not sender or not pwd:
            messagebox.showerror("Error", "Please fill in Sender Email and Password before testing.")
            return
            
        if not recipient and not sms_recipients:
            messagebox.showerror("Error", "Please fill in either Recipient Email or SMS Recipients before testing.")
            return
            
        self.log("Sending test notifications...")
        try:
            from email_sender import send_sms_notification
            
            if recipient:
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
                
            if sms_recipients:
                send_sms_notification(
                    sender_email=sender,
                    sender_password=pwd,
                    smtp_server=server,
                    smtp_port=port,
                    phone_numbers=sms_recipients,
                    body="Sawyer Test Text: SMTP/SMS Connection working!"
                )
                self.log("SUCCESS: Test text message sent successfully!")
                
            messagebox.showinfo("Success", "Test notifications sent successfully!")
        except Exception as e:
            self.log(f"FAILED to send test notifications: {e}")
            messagebox.showerror("Error", f"Failed to send:\n{e}")

    def refresh_login_session(self):
        # Find msedge.exe
        edge_paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"),
        ]
        edge_path = None
        for p in edge_paths:
            if os.path.exists(p):
                edge_path = p
                break
                
        if not edge_path:
            messagebox.showerror("Error", "Microsoft Edge installation not found.\nPlease make sure Edge is installed on your Windows system.")
            return
            
        profile_dir = os.path.expandvars(r"%USERPROFILE%\AppData\Local\SawyerRosterAutomation\edge_browser_profile")
        os.makedirs(profile_dir, exist_ok=True)
        
        cmd = [
            edge_path,
            f"--user-data-dir={profile_dir}",
            "https://www.hisawyer.com/portal"
        ]
        
        self.log("Opening Edge for manual Sawyer login...")
        try:
            # Run Edge natively as a separate process (unautomated)
            proc = subprocess.Popen(cmd)
            
            # Show interactive dialog instructions
            messagebox.showinfo(
                "Action Required",
                "A Microsoft Edge window has been opened.\n\n"
                "1. Please log into your Sawyer account in that Edge window.\n"
                "2. Check 'Remember this computer' and complete any 2FA/checks.\n"
                "3. Once you see your daily calendar / dashboard, close the Edge window completely.\n\n"
                "Click OK in this dialog AFTER you have successfully logged in and closed the Edge window."
            )
            
            # Update status
            self.update_cookie_status()
            self.log("Sawyer login session refreshed.")
        except Exception as e:
            self.log(f"ERROR: Failed to launch Edge: {e}")
            messagebox.showerror("Error", f"Failed to launch Microsoft Edge:\n{e}")

    def update_cookie_status(self):
        cookies_db = os.path.expandvars(r"%USERPROFILE%\AppData\Local\SawyerRosterAutomation\edge_browser_profile\Default\Network\Cookies")
        if not os.path.exists(cookies_db):
            cookies_db = os.path.expandvars(r"%USERPROFILE%\AppData\Local\SawyerRosterAutomation\edge_browser_profile\Cookies")
            
        if os.path.exists(cookies_db):
            temp_db = os.path.expandvars(r"%USERPROFILE%\AppData\Local\SawyerRosterAutomation\Cookies_status_temp.db")
            try:
                # Copy to temp file to avoid lock
                with open(cookies_db, "rb") as f_src:
                    with open(temp_db, "wb") as f_dst:
                        f_dst.write(f_src.read())
                        
                import sqlite3
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                cursor.execute("SELECT expires_utc FROM cookies WHERE host_key LIKE ? AND name = ?", ("%hisawyer%", "_sawyer_session"))
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    expires_utc = row[0]
                    if expires_utc > 0:
                        timestamp = (expires_utc - 11644473600000000) / 1000000.0
                        exp_dt = datetime.fromtimestamp(timestamp)
                        if exp_dt < datetime.now():
                            self.cookie_status_label.config(text=f"Expired on {exp_dt.strftime('%Y-%m-%d %H:%M')}", foreground="red")
                        else:
                            self.cookie_status_label.config(text=f"Active (Expires: {exp_dt.strftime('%Y-%m-%d %H:%M')})", foreground="green")
                    else:
                        self.cookie_status_label.config(text="Active (Session cookie)", foreground="green")
                else:
                    self.cookie_status_label.config(text="Session expired (Login required)", foreground="red")
            except Exception as e:
                self.cookie_status_label.config(text=f"Status: Error ({e})", foreground="red")
            finally:
                if os.path.exists(temp_db):
                    try:
                        os.remove(temp_db)
                    except:
                        pass
        else:
            self.cookie_status_label.config(text="No active session (Login required)", foreground="blue")

def generate_operational_email_body(combined_df, report_name, date_str):
    """Generates a mobile-friendly text summary for the email body."""
    import pandas as pd
    report_name_lower = (report_name or "").lower()
    
    # 1. DROP OFF (9:20 AM)
    if "drop" in report_name_lower or "920" in report_name_lower or "morning" in report_name_lower:
        body_lines = []
        body_lines.append(f"=== Drop Off Attendance Summary ({date_str}) ===")
        
        total_reg = len(combined_df)
        is_checked_in = combined_df['Check-in Time'].notna() & (combined_df['Check-in Time'].astype(str).str.strip() != '')
        total_in = is_checked_in.sum()
        
        body_lines.append(f"Total Kids at Camp: {total_reg}")
        body_lines.append(f"Total Checked In: {total_in}")
        body_lines.append("")
        
        camp_col = 'Camp Name' if 'Camp Name' in combined_df.columns else None
        if camp_col:
            grouped = combined_df.groupby(camp_col)
            for camp, group in grouped:
                group = group.sort_values(by='Student Name')
                in_group_mask = group['Check-in Time'].notna() & (group['Check-in Time'].astype(str).str.strip() != '')
                in_count = in_group_mask.sum()
                reg_count = len(group)
                
                body_lines.append(f"{camp} ({in_count}/{reg_count} checked in):")
                for _, row in group.iterrows():
                    student_name = row['Student Name']
                    checked_in_val = row['Check-in Time']
                    has_checked_in = pd.notna(checked_in_val) and str(checked_in_val).strip() != ''
                    
                    if has_checked_in:
                        body_lines.append(f"  - [x] {student_name}")
                    else:
                        body_lines.append(f"  - [ ] {student_name} (Absent)")
                body_lines.append("")
        else:
            body_lines.append("Camps Breakdown:")
            combined_df = combined_df.sort_values(by='Student Name')
            for _, row in combined_df.iterrows():
                student_name = row['Student Name']
                checked_in_val = row['Check-in Time']
                has_checked_in = pd.notna(checked_in_val) and str(checked_in_val).strip() != ''
                
                if has_checked_in:
                    body_lines.append(f"  - [x] {student_name}")
                else:
                    body_lines.append(f"  - [ ] {student_name} (Absent)")
                    
        return "\n".join(body_lines).strip()
        
    # 2. PICK UP (12:20 PM)
    elif "pick" in report_name_lower or "1220" in report_name_lower or "midday" in report_name_lower:
        body_lines = []
        body_lines.append(f"=== Pick Up Attendance Summary ({date_str}) ===")
        
        is_checked_in = combined_df['Check-in Time'].notna() & (combined_df['Check-in Time'].astype(str).str.strip() != '')
        is_checked_out = combined_df['Check-out Time'].notna() & (combined_df['Check-out Time'].astype(str).str.strip() != '')
        still_in_df = combined_df[is_checked_in & ~is_checked_out]
        
        camp_col = 'Camp Name' if 'Camp Name' in still_in_df.columns else None
        if camp_col:
            still_in_df = still_in_df.sort_values(by=[camp_col, 'Student Name'])
        else:
            still_in_df = still_in_df.sort_values(by=['Student Name'])
            
        total_still_in = len(still_in_df)
        body_lines.append(f"Kids Still Checked In: {total_still_in}")
        body_lines.append("")
        
        if total_still_in > 0:
            for idx, (_, row) in enumerate(still_in_df.iterrows(), 1):
                student_name = row['Student Name']
                body_lines.append(f"{idx}. {student_name}")
        else:
            body_lines.append("All kids have been checked out successfully!")
            
        return "\n".join(body_lines).strip()
        
    # 3. DEFAULT (End of Day/Other)
    else:
        return (f"Hello,\n\nPlease find attached the automatically generated {report_name or 'Sawyer Billing'} report "
                f"compiled on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} for {date_str}.")

def generate_operational_sms_body(combined_df, report_name, date_str):
    """Generates a highly compact, carrier-friendly summary for SMS/Text notifications to fit carrier limits."""
    report_name_lower = (report_name or "").lower()
    
    # 1. DROP OFF (9:20 AM)
    if "drop" in report_name_lower or "920" in report_name_lower or "morning" in report_name_lower:
        total_reg = len(combined_df)
        is_checked_in = combined_df['Check-in Time'].notna() & (combined_df['Check-in Time'].astype(str).str.strip() != '')
        total_in = is_checked_in.sum()
        
        body = f"Drop Off ({date_str}): Total {total_reg} | Present {total_in}.\r\n"
        
        camp_col = 'Camp Name' if 'Camp Name' in combined_df.columns else None
        if camp_col:
            grouped = combined_df.groupby(camp_col)
            camp_summaries = []
            for camp, group in grouped:
                in_group_mask = group['Check-in Time'].notna() & (group['Check-in Time'].astype(str).str.strip() != '')
                in_count = in_group_mask.sum()
                reg_count = len(group)
                absent_group = group[~in_group_mask]
                
                absent_names = ", ".join(absent_group['Student Name'].tolist()) if len(absent_group) > 0 else "None"
                absent_names = absent_names.replace('"', "'")
                camp_summaries.append(f"{camp} ({in_count}/{reg_count} present). Absent: {absent_names}")
            body += "\r\n".join(camp_summaries)
        else:
            absent_df = combined_df[~is_checked_in]
            absent_names = ", ".join(absent_df['Student Name'].tolist()) if len(absent_df) > 0 else "None"
            absent_names = absent_names.replace('"', "'")
            body += f"Absent: {absent_names}"
            
        return body.strip()
        
    # 2. PICK UP (12:20 PM)
    elif "pick" in report_name_lower or "1220" in report_name_lower or "midday" in report_name_lower:
        is_checked_in = combined_df['Check-in Time'].notna() & (combined_df['Check-in Time'].astype(str).str.strip() != '')
        is_checked_out = combined_df['Check-out Time'].notna() & (combined_df['Check-out Time'].astype(str).str.strip() != '')
        still_in_df = combined_df[is_checked_in & ~is_checked_out]
        
        total_still_in = len(still_in_df)
        body = f"Pick Up ({date_str}): Still checked in: {total_still_in}.\r\n"
        
        if total_still_in > 0:
            camp_col = 'Camp Name' if 'Camp Name' in still_in_df.columns else None
            if camp_col:
                still_in_df = still_in_df.sort_values(by=[camp_col, 'Student Name'])
            else:
                still_in_df = still_in_df.sort_values(by=['Student Name'])
            
            kids_list = []
            for _, row in still_in_df.iterrows():
                student_name = row['Student Name'].replace('"', "'")
                kids_list.append(student_name)
            body += "Names: " + ", ".join(kids_list)
        else:
            body += "All checked out successfully!"
            
        return body.strip()
        
    # 3. DEFAULT (End of Day/Other)
    else:
        return f"Sawyer report compiled for {report_name or 'Billing'} on {date_str}."

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
            # Custom report naming
            report_label = args.report_name or "Sawyer_Billing"
            safe_label = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in report_label)
            
            if start_date == end_date:
                filename = f"{safe_label}_{start_date}.xlsx"
            else:
                filename = f"{safe_label}_{start_date}_to_{end_date}.xlsx"
                
            out_path = os.path.join(output_dir, filename)
            save_to_excel(combined, summary, out_path)
            print(f"SUCCESS: Report saved to: {out_path}")
            
            # Send Email/SMS notifications if enabled
            email_enabled = args.send_email or config.get("email_enabled", False)
            sms_enabled = args.send_sms or config.get("sms_enabled", False)
            
            if email_enabled or sms_enabled:
                sender = config.get("sender_email")
                pwd = config.get("sender_password")
                smtp_srv = config.get("smtp_server", "smtp.gmail.com")
                smtp_prt = config.get("smtp_port", "587")
                recipient = config.get("recipient_email")
                sms_recipients = args.sms_recipients or config.get("sms_recipients")
                
                if sender and pwd:
                    body = generate_operational_email_body(combined, report_label, start_date)
                    
                    if email_enabled and recipient:
                        print("Sending email...")
                        subject = f"Sawyer Report - {report_label} ({start_date})"
                        try:
                            send_billing_email(
                                sender_email=sender,
                                sender_password=pwd,
                                smtp_server=smtp_srv,
                                smtp_port=smtp_prt,
                                recipient_email=recipient,
                                subject=subject,
                                body=body,
                                attachment_path=out_path
                            )
                            print("SUCCESS: Email sent successfully!")
                        except Exception as email_err:
                            print(f"ERROR: Email failed to send: {email_err}")
                            
                    if sms_enabled and sms_recipients:
                        print("Sending SMS notifications...")
                        try:
                            sms_body = generate_operational_sms_body(combined, report_label, start_date)
                            from email_sender import send_sms_notification
                            send_sms_notification(
                                sender_email=sender,
                                sender_password=pwd,
                                smtp_server=smtp_srv,
                                smtp_port=smtp_prt,
                                phone_numbers=sms_recipients,
                                body=sms_body
                            )
                            print("SUCCESS: SMS notifications sent successfully!")
                        except Exception as sms_err:
                            print(f"ERROR: SMS failed to send: {sms_err}")
                else:
                    print("ERROR: SMTP sender settings are incomplete in config.json. Cannot send notifications.")
            
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
    parser.add_argument("--send-sms", action="store_true", help="Send report summary via SMS text message")
    parser.add_argument("--sms-recipients", help="Comma-separated phone numbers to send SMS texts to")
    parser.add_argument("--report-name", "-n", help="Custom name for the report (e.g. 'Drop Off', 'Pick Up', 'End of Day')")
    
    if len(sys.argv) > 1 and ("--cli" in sys.argv or "-h" in sys.argv or "--help" in sys.argv):
        args = parser.parse_args()
        if "--headless" not in sys.argv:
            args.headless = True
        run_silent_cli(args)
    else:
        root = tk.Tk()
        app = SawyerApp(root)
        root.mainloop()
