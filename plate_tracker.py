VERSION = "1.0.0"
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkcalendar import DateEntry
from tksheet import Sheet
import pandas as pd
import os
import json
from datetime import datetime, timedelta
from plyer import notification # For system notifications

class PlateTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Fleet License Plate Tracker")
        self.root.geometry("1100x800")

        # --- File Paths ---
        self.data_file = "plate_data.json"
        self.settings_file = "plate_settings.json"

        # --- Data Storage ---
        self.df = pd.DataFrame() # Holds the plate data
        self.settings = {}
        
        # Load Data & Settings
        self.load_settings()
        self.load_data()

        # --- UI Setup ---
        self.setup_ui()
        
        # --- Notification Loop ---
        # Check immediately on startup, then schedule periodic checks
        self.check_expirations()
        self.schedule_notification_check()

    def load_settings(self):
        """Load settings or create defaults."""
        defaults = {
            "van_list": ["EDV 1", "EDV 2", "Ram 1", "Ram 2", "Step Van 1"],
            "notify_days_before": 30, # Notify if expiring within 30 days
            "notify_hours_freq": 4,   # Check every 4 hours while app is open
            "last_check": ""
        }
        
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    self.settings = {**defaults, **json.load(f)}
            except:
                self.settings = defaults
        else:
            self.settings = defaults
            self.save_settings()

    def save_settings(self):
        with open(self.settings_file, 'w') as f:
            json.dump(self.settings, f, indent=4)

    def load_data(self):
        """Load plate data from JSON into Pandas DataFrame."""
        if os.path.exists(self.data_file):
            try:
                self.df = pd.read_json(self.data_file, orient='records')
                # Ensure date columns are datetime objects
                if not self.df.empty:
                    self.df['Expiration'] = pd.to_datetime(self.df['Expiration'])
                    self.df['Date Added'] = pd.to_datetime(self.df['Date Added'])
            except Exception as e:
                print(f"Error loading data: {e}")
                self.df = pd.DataFrame(columns=["Van Number", "Plate", "State", "Expiration", "Status", "Date Added"])
        else:
            self.df = pd.DataFrame(columns=["Van Number", "Plate", "State", "Expiration", "Status", "Date Added"])

    def save_data(self):
        """Save DataFrame to JSON."""
        # Convert dates to strings for JSON serialization
        save_df = self.df.copy()
        save_df['Expiration'] = save_df['Expiration'].dt.strftime('%Y-%m-%d')
        save_df['Date Added'] = save_df['Date Added'].dt.strftime('%Y-%m-%d')
        save_df.to_json(self.data_file, orient='records', indent=4)

    def setup_ui(self):
        # --- 1. INPUT SECTION ---
        input_frame = ttk.LabelFrame(self.root, text="Add / Update Plate")
        input_frame.pack(fill="x", padx=10, pady=5)

        # Grid layout for inputs
        ttk.Label(input_frame, text="Van Number:").grid(row=0, column=0, padx=5, pady=10)
        self.van_var = tk.StringVar()
        self.van_dropdown = ttk.Combobox(input_frame, textvariable=self.van_var, values=self.settings["van_list"], state="readonly")
        self.van_dropdown.grid(row=0, column=1, padx=5)

        ttk.Label(input_frame, text="Plate Number:").grid(row=0, column=2, padx=5)
        self.plate_entry = ttk.Entry(input_frame, width=15)
        self.plate_entry.grid(row=0, column=3, padx=5)

        ttk.Label(input_frame, text="State:").grid(row=0, column=4, padx=5)
        self.state_entry = ttk.Entry(input_frame, width=5)
        self.state_entry.grid(row=0, column=5, padx=5)

        ttk.Label(input_frame, text="Expiration:").grid(row=0, column=6, padx=5)
        self.cal_expire = DateEntry(input_frame, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='yyyy-mm-dd')
        self.cal_expire.grid(row=0, column=7, padx=5)

        add_btn = ttk.Button(input_frame, text="SAVE / UPDATE VAN", command=self.add_entry)
        add_btn.grid(row=0, column=8, padx=15, sticky="e")

        # --- 2. CONTROLS (Sort & Settings) ---
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill="x", padx=10, pady=5)

        # Sort Controls
        sort_lbl_frame = ttk.LabelFrame(control_frame, text="Sort Viewport")
        sort_lbl_frame.pack(side="left", padx=5)
        
        self.sort_var = tk.StringVar(value="van_asc")
        
        ttk.Radiobutton(sort_lbl_frame, text="Van (A-Z)", variable=self.sort_var, value="van_asc", command=self.update_viewport).pack(side="left", padx=5)
        ttk.Radiobutton(sort_lbl_frame, text="Expiration (Soonest)", variable=self.sort_var, value="exp_asc", command=self.update_viewport).pack(side="left", padx=5)
        ttk.Radiobutton(sort_lbl_frame, text="Expiration (Latest)", variable=self.sort_var, value="exp_desc", command=self.update_viewport).pack(side="left", padx=5)

        # Settings & Export Buttons
        btn_box = ttk.Frame(control_frame)
        btn_box.pack(side="right", padx=5)
        
        ttk.Button(btn_box, text="Export History CSV 📄", command=self.export_history).pack(side="left", padx=5)
        ttk.Button(btn_box, text="Settings ⚙️", command=self.open_settings).pack(side="left", padx=5)

        # --- 3. VIEWPORT ---
        view_frame = ttk.Frame(self.root)
        view_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.sheet = Sheet(view_frame,
                           headers=["Van Number", "Plate", "State", "Expiration Date", "Days Remaining"],
                           data=[[]],
                           theme="light blue",
                           empty_horizontal=0, empty_vertical=0,
                           header_font=("Arial", 10, "bold"))
        self.sheet.enable_bindings(("single_select", "row_select", "column_width_resize", "arrowkeys", "copy"))
        self.sheet.pack(fill="both", expand=True)

        # --- 4. STATUS BAR ---
        self.status_var = tk.StringVar()
        self.status_var.set("Ready.")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w")
        status_bar.pack(fill="x")

        # Initial Load
        self.update_viewport()

    def add_entry(self):
        van = self.van_var.get()
        plate = self.plate_entry.get().upper().strip()
        state = self.state_entry.get().upper().strip()
        expire_date = pd.to_datetime(self.cal_expire.get_date())
        today = pd.to_datetime(datetime.now().date())

        if not van or not plate:
            messagebox.showerror("Error", "Van Number and Plate Number are required.")
            return

        # LOGIC: If this Van already has an 'Active' plate, mark it as 'Archived'
        if not self.df.empty:
            mask = (self.df["Van Number"] == van) & (self.df["Status"] == "Active")
            self.df.loc[mask, "Status"] = "Archived"

        # Create new record
        new_row = {
            "Van Number": van,
            "Plate": plate,
            "State": state,
            "Expiration": expire_date,
            "Status": "Active",
            "Date Added": today
        }

        # Append and Save
        self.df = pd.concat([self.df, pd.DataFrame([new_row])], ignore_index=True)
        self.save_data()
        
        # Clear inputs
        self.plate_entry.delete(0, tk.END)
        self.state_entry.delete(0, tk.END)
        
        self.update_viewport()
        self.status_var.set(f"Added plate {plate} to {van}.")
        
        # Re-check notifications just in case the new one is expiring
        self.check_expirations()

    def update_viewport(self):
        if self.df.empty:
            self.sheet.set_sheet_data([[]])
            return

        # Filter for Active only
        active_df = self.df[self.df["Status"] == "Active"].copy()
        
        if active_df.empty:
            self.sheet.set_sheet_data([[]])
            return

        # Calculate Days Remaining for display
        today = pd.to_datetime(datetime.now().date())
        active_df["Days Remaining"] = (active_df["Expiration"] - today).dt.days

        # Apply Sorting
        sort_mode = self.sort_var.get()
        if sort_mode == "van_asc":
            active_df = active_df.sort_values(by="Van Number", ascending=True)
        elif sort_mode == "exp_asc":
            active_df = active_df.sort_values(by="Expiration", ascending=True)
        elif sort_mode == "exp_desc":
            active_df = active_df.sort_values(by="Expiration", ascending=False)

        # Format Dates for Display
        active_df["Expiration Date"] = active_df["Expiration"].dt.strftime('%Y-%m-%d')

        # Prepare Data for Sheet
        cols_to_show = ["Van Number", "Plate", "State", "Expiration Date", "Days Remaining"]
        display_data = active_df[cols_to_show].values.tolist()

        self.sheet.set_sheet_data(display_data)

        # Highlight Expiring Soon
        threshold = self.settings["notify_days_before"]
        
        # Reset highlights
        self.sheet.dehighlight_all()
        
        for row_idx, row_data in enumerate(display_data):
            days_left = row_data[4] # Index 4 is Days Remaining
            try:
                if int(days_left) < 0:
                    # Expired: Red
                    self.sheet.highlight_rows(rows=[row_idx], bg="#ff9999")
                elif int(days_left) <= threshold:
                    # Warning: Orange/Yellow
                    self.sheet.highlight_rows(rows=[row_idx], bg="#fff2cc")
            except:
                pass

    def open_settings(self):
        """Settings for Van List and Notifications."""
        top = tk.Toplevel(self.root)
        top.title("Settings")
        top.geometry("500x500")

        # --- Tabbed Interface ---
        tabs = ttk.Notebook(top)
        tabs.pack(expand=1, fill="both")

        # TAB 1: Van Management
        tab_vans = ttk.Frame(tabs)
        tabs.add(tab_vans, text="Manage Vans")

        lbl = ttk.Label(tab_vans, text="Manage Van List (used in dropdown)")
        lbl.pack(pady=5)

        # Listbox with Scrollbar
        frm_list = ttk.Frame(tab_vans)
        frm_list.pack(pady=5, padx=10, fill="both", expand=True)
        
        listbox = tk.Listbox(frm_list)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(frm_list, orient="vertical", command=listbox.yview)
        scrollbar.pack(side="right", fill="y")
        listbox.config(yscrollcommand=scrollbar.set)

        # Populate Listbox
        for v in self.settings["van_list"]:
            listbox.insert(tk.END, v)

        # Buttons
        def add_van():
            new_v = simpledialog.askstring("Add Van", "Enter Van Name/Number:")
            if new_v and new_v not in self.settings["van_list"]:
                self.settings["van_list"].append(new_v)
                self.settings["van_list"].sort()
                listbox.insert(tk.END, new_v)
                self.van_dropdown['values'] = self.settings["van_list"] # Update main UI
                self.save_settings()

        def remove_van():
            sel = listbox.curselection()
            if sel:
                val = listbox.get(sel[0])
                confirm = messagebox.askyesno("Confirm", f"Remove {val} from list? (History will be kept)")
                if confirm:
                    listbox.delete(sel[0])
                    if val in self.settings["van_list"]:
                        self.settings["van_list"].remove(val)
                        self.van_dropdown['values'] = self.settings["van_list"] # Update main UI
                        self.save_settings()

        btn_frm = ttk.Frame(tab_vans)
        btn_frm.pack(pady=10)
        ttk.Button(btn_frm, text="Add Van", command=add_van).pack(side="left", padx=5)
        ttk.Button(btn_frm, text="Remove Selected", command=remove_van).pack(side="left", padx=5)


        # TAB 2: Notifications
        tab_notif = ttk.Frame(tabs)
        tabs.add(tab_notif, text="Notifications")

        ttk.Label(tab_notif, text="System Notification Settings", font=("Arial", 11, "bold")).pack(pady=15)

        # Days Threshold
        frm_n1 = ttk.Frame(tab_notif)
        frm_n1.pack(fill="x", padx=20, pady=5)
        ttk.Label(frm_n1, text="Notify when expiration is within (days):").pack(side="left")
        
        days_var = tk.IntVar(value=self.settings["notify_days_before"])
        spin_days = ttk.Spinbox(frm_n1, from_=1, to=365, textvariable=days_var, width=5)
        spin_days.pack(side="right")

        # Frequency
        frm_n2 = ttk.Frame(tab_notif)
        frm_n2.pack(fill="x", padx=20, pady=5)
        ttk.Label(frm_n2, text="How often to check/notify (hours):").pack(side="left")
        
        freq_var = tk.IntVar(value=self.settings["notify_hours_freq"])
        spin_freq = ttk.Spinbox(frm_n2, from_=1, to=168, textvariable=freq_var, width=5)
        spin_freq.pack(side="right")

        def save_notif():
            self.settings["notify_days_before"] = days_var.get()
            self.settings["notify_hours_freq"] = freq_var.get()
            self.save_settings()
            messagebox.showinfo("Saved", "Notification settings updated.")
            # Reset the check timer
            self.check_expirations() 

        ttk.Button(tab_notif, text="Save Notification Settings", command=save_notif).pack(pady=20)

    def export_history(self):
        """Export all data (active and archived) to CSV."""
        if self.df.empty:
            messagebox.showinfo("Info", "No data to export.")
            return

        fp = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if fp:
            # Sort by Van then Date Added for cleaner history
            export_df = self.df.sort_values(by=["Van Number", "Date Added"], ascending=[True, False])
            export_df.to_csv(fp, index=False)
            messagebox.showinfo("Success", f"Full history exported to {fp}")

    def schedule_notification_check(self):
        """Re-runs the check based on frequency settings."""
        hours = self.settings.get("notify_hours_freq", 24)
        ms = hours * 60 * 60 * 1000
        self.root.after(ms, self.check_expirations)
        self.root.after(ms, self.schedule_notification_check) # Schedule next one

    def check_expirations(self):
        """Checks for expiring plates and sends a system notification."""
        if self.df.empty: return
        
        today = pd.to_datetime(datetime.now().date())
        threshold = self.settings["notify_days_before"]
        
        # Filter: Active plates only
        active = self.df[self.df["Status"] == "Active"].copy()
        if active.empty: return

        # Find expiring
        active["days_left"] = (active["Expiration"] - today).dt.days
        expiring = active[active["days_left"] <= threshold]

        if not expiring.empty:
            count = len(expiring)
            
            # Construct message
            msg_body = f"You have {count} van(s) with expiring plates.\n"
            
            # List top 3 for brevity
            preview = expiring.head(3)
            for _, row in preview.iterrows():
                d_str = row["Expiration"].strftime('%Y-%m-%d')
                msg_body += f"{row['Van Number']}: {row['Plate']} (Exp: {d_str})\n"
            
            if count > 3:
                msg_body += "...and more."

            # Send Notification
            try:
                notification.notify(
                    title="License Plate Expiration Warning",
                    message=msg_body,
                    app_name="Plate Tracker",
                    timeout=10 # seconds
                )
                self.status_var.set(f"System Notification sent: {count} expiring soon.")
            except Exception as e:
                print(f"Notification error: {e}")
        else:
            self.status_var.set("Checked expirations: All good.")

def main():
    root = tk.Tk()
    app = PlateTrackerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()