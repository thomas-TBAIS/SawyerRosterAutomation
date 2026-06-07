# Sawyer Roster Billing & Automation Tool

A Windows desktop application built to automate downloading camp rosters from the Sawyer Portal, cleaning check-in/out times, calculating pre-camp and post-camp billable hours, and generating structured Weekly Excel Billing Reports.

Designed specifically for Camp Mirage owners to streamline weekly billing workflows.

---

## Key Features

1. **Automated Scraper**: Automatically navigates the Sawyer calendar, handles login/2FA, downloads all daily rosters, and compiles them into a single report.
2. **Billing Math Automation**:
   * **Before Camp (9:00 AM start)**: Checks in <= 8:45 AM are rounded down to the previous 15-minute mark and billed.
   * **After Camp (12:00 PM end)**: Checks out > 12:15 PM are rounded up to the next 15-minute mark and billed.
   * **Deduplication**: Identifies and removes duplicate student attendance records resulting from multiple calendar links for the same camp.
3. **Structured Excel Output**: Generates a 3-tab workbook:
   * `Weekly Summary`: Total pre-camp, post-camp, and overall billed hours per student/parent.
   * `Extended Care (Billed)`: Rows containing students with extra billable hours.
   * `Standard Hours`: Rows containing students who checked in/out during standard times.
4. **Offline Processing Fallback**: Allows manual directory selection to parse and process pre-downloaded roster CSV files instantly without logging in.

---

## How to Get Started

### 1. Requirements
* **Operating System**: Windows (10 or 11).
* **Dependencies**: None. The app runs as a standalone `.exe` and does not require Python, Node.js, or any pre-installed database/browser drivers.

### 2. Running the Tool
1. Double-click the executable file: **`SawyerRosterAutomation_v21.exe`**.
2. If Windows Defender shows a *"Windows protected your PC"* smart screen, click **More info** and select **Run anyway** (this is normal for custom-compiled applications).

### 3. Using the Automated Scraper
1. **Enter Credentials**: Fill in your Sawyer Portal email and password. Check **Remember credentials** to save them locally for next time.
2. **Specify Dates**: Enter a date range using the `YYYY-MM-DD` format (e.g. `2026-06-01` to `2026-06-05`).
3. **Set Output Path**: Choose where you want to save the final Excel report (defaults to your Windows **Downloads** folder).
4. **Run the Scraping**: Click **Start Download & Processing**.

**First-Time Setup**: The very first time you trigger a scrape, the app will automatically download a secure, isolated Chromium browser driver in the background. Progress will be displayed in the **System Log** panel at the bottom. This process takes 1–2 minutes and only occurs once.

### 4. Handling Login & Multi-Factor Authentication (2FA)
* When the scraper launches, it will open a browser window and automatically attempt to sign you in.
* If Sawyer prompts for **2FA (Email Verification Code)**, complete the verification in the open browser window and make sure to check **Remember this computer**.
* Once authenticated, your browser session cookies are saved securely in your local AppData directory. For all future runs, the app will scrape in the background without needing you to input codes or sign in.

### 5. Using the Process Local Folder Tab
If you prefer not to use the automated scraper:
1. Download your roster CSVs manually from Sawyer.
2. Put all the files into a single folder.
3. Go to the **Process Local Folder** tab in the app, select that folder, and click **Process & Clean CSVs**.
4. The app will immediately run the billing calculations and output the Excel spreadsheet in that same folder.

---

## Where Settings and Files are Saved
* **User Config & Cookies**: Saved at `%USERPROFILE%\AppData\Local\SawyerRosterAutomation` (isolated privately to your computer user profile).
* **Temporary Downloads**: Saved under `sawyer_temp_downloads` in your selected output directory. These files are automatically cleaned up upon successful Excel generation.

---

*Created for Camp Mirage Owners.*
