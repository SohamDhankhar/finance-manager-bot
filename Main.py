import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime, date
import json
import os
import sys
import ttkbootstrap as ttkb
from PIL import Image  # Removed ImageTk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import requests
from dotenv import load_dotenv
import schedule
import time
import threading
import calendar  # <-- Add this for monthrange
import subprocess
import shutil
import ctypes  # <-- Add this for admin check
import telegram_bot  # <-- Add this import

# Remove this block (not needed anymore):
# try:
#     from telegram_bot import main as telegram_bot_main
# except ImportError:
#     telegram_bot_main = None

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

DATA_FILE = "finance_data.json"
CATEGORIES_FILE = "expense_categories.json"
RECURRING_FILE = "recurring_expenses.json"
GOALS_FILE = "goals.json"
CONFIG_PATH = "config.json"

# Load or initialize data
def load_or_create_data():
    data_file = resource_path(DATA_FILE)
    if os.path.exists(data_file):
        with open(data_file, "r") as f:
            data = json.load(f)
            # Ensure settings exist with valid theme
            if "settings" not in data or data["settings"].get("theme") not in ["darkly", "cosmo"]:
                data["settings"] = {"theme": "darkly", "pin": None}
                with open(data_file, "w") as f:
                    json.dump(data, f, indent=4)
            return data
    
    # Create new data structure with valid theme
    data = {
        "monthly_income": 0,
        "breakdown": {},
        "expenses": {},
        "deposits": {},
        "settings": {
            "theme": "darkly",  # Default theme
            "pin": None
        }
    }
    with open(data_file, "w") as f:
        json.dump(data, f, indent=4)
    return data

# Load or initialize expense categories
if os.path.exists(CATEGORIES_FILE):
    with open(CATEGORIES_FILE, "r") as f:
        expense_categories = json.load(f)
else:
    expense_categories = {
        "needs": [],  # Empty list for needs
        "wants": []   # Empty list for wants
    }
    with open(CATEGORIES_FILE, "w") as f:
        json.dump(expense_categories, f, indent=4)

SERVICE_NAME = "FinanceTelegramBot"

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def is_service_installed(service_name):
    try:
        result = subprocess.run(
            ["sc", "query", service_name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return "STATE" in result.stdout
    except Exception:
        return False

def install_telegram_bot_service():
    nssm_path = shutil.which("nssm") or os.path.join(os.path.dirname(__file__), "nssm.exe")
    if not os.path.exists(nssm_path):
        messagebox.showerror(
            "NSSM Not Found",
            "nssm.exe is required to install the Telegram bot as a service.\n"
            "Please download it from https://nssm.cc/download and place it in the app folder."
        )
        return False

    if not is_admin():
        messagebox.showerror(
            "Admin Rights Required",
            "You must run this program as administrator to install a Windows service.\n"
            "Right-click and choose 'Run as administrator'."
        )
        return False

    python_path = sys.executable
    bot_path = os.path.join(os.path.dirname(__file__), "telegram_bot.py")
    service_dir = os.path.dirname(bot_path)

    # Install the service
    try:
        subprocess.check_call([
            nssm_path, "install", SERVICE_NAME,
            python_path, bot_path
        ])
        subprocess.check_call([
            nssm_path, "set", SERVICE_NAME, "AppDirectory", service_dir
        ])
        subprocess.check_call([
            nssm_path, "start", SERVICE_NAME
        ])
        messagebox.showinfo(
            "Telegram Bot Service",
            "Telegram bot service installed and started successfully!\n"
            "You can manage it from Windows Services."
        )
        return True
    except subprocess.CalledProcessError as e:
        messagebox.showerror(
            "Service Install Failed",
            f"Failed to install/start Telegram bot service (error code {e.returncode}).\n"
            "Try running this program as administrator."
        )
        return False
    except Exception as e:
        messagebox.showerror(
            "Service Install Failed",
            f"Failed to install/start Telegram bot service:\n{e}"
        )
        return False

class FinanceManager:
    def __init__(self):
        try:
            # Load environment variables
            load_dotenv()
            self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
            
            self.root = ttkb.Window()
            self.data = load_or_create_data()
            self.categories = expense_categories
            
            # Initialize history for undo/redo
            self.history = [json.dumps(self.data)]  # Initial state
            self.current_index = 0
            self.max_history = 50  # Maximum number of states to keep
            
            if not self.check_pin():
                sys.exit()
            
            if not self.check_telegram_config():
                messagebox.showwarning(
                    "Telegram Config", 
                    "Telegram notifications disabled. Create .env file with bot token and chat ID."
                )
                
            self.setup_main_window()
            self.create_widgets()
            self.update_balance_display()
            
            # Schedule daily summary
            self.schedule_daily_summary()
            
            # Install Telegram bot as a service on first run if not present
            if not is_service_installed(SERVICE_NAME):
                if messagebox.askyesno(
                    "Telegram Bot Service",
                    "Telegram bot is not running as a service.\n"
                    "Do you want to install and run it as a background service now?"
                ):
                    install_telegram_bot_service()
            
            self.telegram_thread = None  # Track background bot thread

            # Start Telegram bot automatically in background
            self.start_telegram_bot()
            
            # Check for first launch
            if self.is_first_launch():
                if messagebox.askyesno(
                    "Welcome",
                    "Welcome to Finance Manager!\n\n"
                    "Would you like to start the Telegram bot as a service now?"
                ):
                    install_telegram_bot_service()
                self.save_first_launch()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to initialize application: {str(e)}")
            sys.exit(1)

    def check_telegram_config(self):
        """Check if Telegram bot is properly configured"""
        token = self.bot_token.strip('"') if isinstance(self.bot_token, str) else None
        chat_id = self.chat_id.strip('"') if isinstance(self.chat_id, str) else None
        return bool(token and chat_id)

    def get_daily_summary(self):
        """Generate daily summary text"""
        try:
            today = date.today()
            today_str = today.strftime("%Y-%m-%d")
            month_str = today.strftime("%Y-%m")
            
            # Get today's expenses
            today_expenses = self.data.get("expenses", {}).get(month_str, {}).get(today_str, [])
            total_today = sum(expense["amount"] for expense in today_expenses)
            
            # Get current balance and remaining amounts
            current_month = datetime.now().strftime("%Y-%m")
            income = self.data.get("monthly_income", 0)
            month_expenses = self.data.get("expenses", {}).get(current_month, {})
            month_deposits = self.data.get("deposits", {}).get(current_month, {})
            
            total_expenses = sum(
                expense["amount"] 
                for day_expenses in month_expenses.values()
                for expense in day_expenses
            )
            total_deposits = sum(month_deposits.values()) if month_deposits else 0
            current_balance = income + total_deposits - total_expenses
            
            # Calculate remaining amounts
            bd = self.data.get("breakdown", {})
            needs_total = bd.get("needs", 0)
            wants_total = bd.get("wants", 0)
            savings_total = bd.get("savings", 0)
            
            needs_spent = sum(
                expense["amount"] 
                for day_expenses in month_expenses.values()
                for expense in day_expenses 
                if expense["category"].lower() == "needs"
            )
            wants_spent = sum(
                expense["amount"] 
                for day_expenses in month_expenses.values()
                for expense in day_expenses 
                if expense["category"].lower() == "wants"
            )
            savings_deposited = total_deposits
            
            needs_remaining = max(needs_total - needs_spent, 0)
            wants_remaining = max(wants_total - wants_spent, 0)
            savings_remaining = max(savings_total - savings_deposited, 0)
            
            # Format summary
            summary = (
                f"📅 Date: {today.strftime('%B %d, %Y')}\n"
                f"💸 Today's Spend: ₹{total_today:,.2f}\n"
                f"💰 Balance: ₹{current_balance:,.2f}\n"
                f"🧾 Needs Remaining: ₹{needs_remaining:,.2f}\n"
                f"🎁 Wants Remaining: ₹{wants_remaining:,.2f}\n"
                f"🏦 Savings Remaining: ₹{savings_remaining:,.2f}"
            )
            
            return summary
            
        except Exception as e:
            print(f"Error generating summary: {str(e)}")
            return None

    def send_daily_summary(self):
        """Send daily summary via Telegram"""
        if not self.check_telegram_config():
            print("Telegram notifications disabled - missing config")
            return

        try:
            summary = self.get_daily_summary()
            if not summary:
                return

            token = self.bot_token.strip('"') if isinstance(self.bot_token, str) else ""
            chat_id = self.chat_id.strip('"') if isinstance(self.chat_id, str) else ""
            url = f"https://api.telegram.org/bot{token}/sendMessage"

            data = {
                "chat_id": chat_id,
                "text": summary,
                "parse_mode": "HTML"
            }

            response = requests.post(url, data=data)
            response.raise_for_status()

            if response.ok:
                print("Daily summary sent successfully")
                print(response.json())
            else:
                print(f"Failed to send message: {response.text}")

        except Exception as e:
            print(f"Failed to send Telegram message: {str(e)}")
            messagebox.showerror("Error", "Failed to send Telegram message")

    def schedule_daily_summary(self):
        """Schedule daily summary at 9:00 PM"""
        def run_scheduler():
            schedule.every().day.at("21:00").do(self.send_daily_summary)
            while True:
                schedule.run_pending()
                time.sleep(60)
                
        # Run scheduler in background thread
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()

    def check_pin(self):
        stored_pin = self.data["settings"].get("pin")
        if not stored_pin:
            self.setup_initial_pin()
            return True
            
        attempts = 3
        while attempts > 0:
            pin = self.show_pin_dialog()
            if pin is None:  # User clicked Cancel
                return False
            if self.verify_pin(pin, stored_pin):
                return True
            attempts -= 1
            if attempts > 0:
                messagebox.showerror("Error", f"Incorrect PIN. {attempts} attempts remaining.")
            else:
                messagebox.showerror("Error", "Too many failed attempts. Application will close.")
        return False
        
    def verify_pin(self, entered_pin, stored_pin):
        # Simple verification for now
        return str(entered_pin) == str(stored_pin)
        
    def setup_initial_pin(self):
        dialog = ttkb.Toplevel()
        dialog.title("Set PIN")
        dialog.geometry("300x150")
        
        ttk.Label(dialog, text="Set a 4-digit PIN for app security:").pack(pady=10)
        pin_entry = ttk.Entry(dialog, show="*")
        pin_entry.pack(pady=5)
        
        def save_pin():
            pin = pin_entry.get()
            if len(pin) != 4 or not pin.isdigit():
                messagebox.showerror("Error", "Please enter a 4-digit PIN")
                return
            self.data["settings"]["pin"] = pin
            with open(DATA_FILE, "w") as f:
                json.dump(self.data, f, indent=4)
            dialog.destroy()
            
        ttk.Button(dialog, text="Save PIN", command=save_pin).pack(pady=10)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.wait_window()
        
    def show_pin_dialog(self):
        dialog = ttkb.Toplevel()
        dialog.title("Enter PIN")
        dialog.geometry("300x150")
        
        pin_var = tk.StringVar()
        ttk.Label(dialog, text="Enter your 4-digit PIN:").pack(pady=10)
        pin_entry = ttk.Entry(dialog, textvariable=pin_var, show="*")
        pin_entry.pack(pady=5)
        
        result = [None]  # type: list
        
        def submit():
            result[0] = pin_var.get()
            dialog.destroy()
            
        ttk.Button(dialog, text="Submit", command=submit).pack(pady=10)
        
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.wait_window()
        
        return result[0]
        
    def setup_main_window(self):
        self.root.title("Finance Manager")
        self.root.geometry("1000x800")
        self.root._style.theme_use(self.data["settings"]["theme"])
        
        # Create canvas and scrollbar
        self.canvas = tk.Canvas(self.root)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        
        # Create main frame inside canvas
        self.main_frame = ttk.Frame(self.canvas, padding="20")
        
        # Configure scrolling
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack scrollbar and canvas
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Add main frame to canvas
        self.canvas_frame = self.canvas.create_window((0, 0), window=self.main_frame, anchor="nw")
        
        # Configure canvas scrolling
        self.main_frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        
        # Enable mousewheel scrolling
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        
    def on_frame_configure(self, event=None):
        """Reset the scroll region to encompass the inner frame"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
    def on_canvas_configure(self, event=None):
        """When canvas is resized, resize the inner frame to match"""
        min_width = self.main_frame.winfo_reqwidth() if self.main_frame else 0
        if event and event.width and event.width > min_width:
            self.canvas.itemconfig(self.canvas_frame, width=event.width)

    def on_mousewheel(self, event):
        """Handle mousewheel scrolling"""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def show_charts(self):
        try:
            current_month = datetime.now().strftime("%Y-%m")
            spending = {"needs": 0, "wants": 0}
            custom_spending = {}

            month_data = self.data["expenses"].get(current_month, {})
            for day_expenses in month_data.values():
                for expense in day_expenses:
                    amount = expense["amount"]
                    category = expense["category"].lower()
                    description = expense["description"]

                    # Add to main category (needs/wants)
                    if category in spending:
                        spending[category] += amount

                    # Add to custom category
                    if description not in custom_spending:
                        custom_spending[description] = 0
                    custom_spending[description] += amount

            # Use color maps from matplotlib.colors
            import matplotlib
            # Generate color lists from colormaps for the number of categories
            main_cmap = matplotlib.colormaps['Set2']
            custom_cmap = matplotlib.colormaps['Pastel1']
            main_colors = [main_cmap(i / max(1, len(spending)-1)) for i in range(len(spending))]
            custom_colors = [custom_cmap(i / max(1, len(custom_spending)-1)) for i in range(len(custom_spending))]

            # Create new window for charts
            chart_window = tk.Toplevel(self.root)
            chart_window.title("Spending Analysis")
            chart_window.geometry("900x650")

            # Create notebook for tabs
            notebook = ttk.Notebook(chart_window)
            notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            # --- Main Categories Chart ---
            main_frame = ttk.Frame(notebook)
            notebook.add(main_frame, text="Main Categories")

            # Add summary table for main categories
            summary_frame1 = ttk.Frame(main_frame)
            summary_frame1.pack(fill=tk.X, pady=(5, 0))
            ttk.Label(summary_frame1, text="Main Category Spending Summary", font=("", 10, "bold")).pack()
            for category, amount in spending.items():
                ttk.Label(summary_frame1, text=f"{category.title()}: ₹{amount:,.2f}").pack(anchor="w")

            fig1, ax1 = plt.subplots(figsize=(7.5, 5.5), dpi=110)
            main_labels = []
            main_values = []

            for category, amount in spending.items():
                if amount > 0:
                    main_labels.append(category.title())
                    main_values.append(amount)

            if main_values:
                pie_result = ax1.pie(
                    main_values, labels=main_labels, autopct='%1.1f%%',
                    startangle=90, pctdistance=0.85, colors=main_colors
                )
                # Handle both 2-tuple and 3-tuple returns
                if len(pie_result) == 3:
                    wedges, texts, autotexts = pie_result
                else:
                    wedges, texts = pie_result
                    autotexts = []
                # Donut hole using patches.Circle
                from matplotlib.patches import Circle
                centre_circle = Circle((0, 0), 0.70, fc='white')
                fig1.gca().add_artist(centre_circle)
                ax1.set_title("Spending by Main Category", fontsize=14, fontweight='bold')
                for text in texts:
                    text.set_fontsize(10)
                for autotext in autotexts:
                    autotext.set_fontsize(9)
                    autotext.set_color('black')
                ax1.legend(wedges, main_labels, title="Categories", loc="center left", bbox_to_anchor=(1, 0.5))
            else:
                ax1.text(0.5, 0.5, "No spending data available", ha='center', va='center', fontsize=12, color='gray')
                ax1.axis('off')

            canvas1 = FigureCanvasTkAgg(fig1, master=main_frame)
            canvas1.draw()
            canvas1.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            # --- Custom Categories Chart ---
            custom_frame = ttk.Frame(notebook)
            notebook.add(custom_frame, text="Custom Categories")

            # Add summary table for custom categories
            summary_frame2 = ttk.Frame(custom_frame)
            summary_frame2.pack(fill=tk.X, pady=(5, 0))
            ttk.Label(summary_frame2, text="Custom Category Spending Summary", font=("", 10, "bold")).pack()
            for category, amount in custom_spending.items():
                ttk.Label(summary_frame2, text=f"{category}: ₹{amount:,.2f}").pack(anchor="w")

            # Use tk.Frame for better centering
            chart_center_frame = tk.Frame(custom_frame)
            chart_center_frame.pack(fill=tk.BOTH, expand=True)
            
            fig2, ax2 = plt.subplots(figsize=(18.92, 10.41), dpi=100)
            custom_labels = []
            custom_values = []

            for category, amount in custom_spending.items():
                if amount > 0:
                    custom_labels.append(category)
                    custom_values.append(amount)

            if custom_values:
                pie_result = ax2.pie(
                    custom_values, labels=custom_labels, autopct='%1.1f%%',
                    startangle=90, pctdistance=0.85, colors=custom_colors
                )
                if len(pie_result) == 3:
                    wedges, texts, autotexts = pie_result
                else:
                    wedges, texts = pie_result
                    autotexts = []
                from matplotlib.patches import Circle
                centre_circle = Circle((0, 0), 0.70, fc='white')
                fig2.gca().add_artist(centre_circle)
                ax2.set_title("Spending by Custom Category", fontsize=14, fontweight='bold')
                for text in texts:
                    text.set_fontsize(10)
                for autotext in autotexts:
                    autotext.set_fontsize(9)
                    autotext.set_color('black')
                ax2.legend(wedges, custom_labels, title="Categories", loc="center left", bbox_to_anchor=(1, 0.5))
            else:
                ax2.text(0.5, 0.5, "No spending data available", ha='center', va='center', fontsize=12, color='gray')
                ax2.axis('off')

            canvas2 = FigureCanvasTkAgg(fig2, master=chart_center_frame)
            canvas2.draw()
            canvas2.get_tk_widget().pack(expand=True, anchor="center")

            def on_close():
                plt.close('all')
                for widget in chart_window.winfo_children():
                    widget.destroy()
                chart_window.destroy()

            chart_window.protocol("WM_DELETE_WINDOW", on_close)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to display charts: {str(e)}")
            plt.close('all')

    def create_widgets(self):
        # Create menu bar
        self.create_menu()
        
        # Create history control buttons
        history_frame = ttk.Frame(self.main_frame)
        history_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(history_frame, text="↶ Undo", command=self.undo).pack(side=tk.LEFT, padx=5)
        ttk.Button(history_frame, text="↷ Redo", command=self.redo).pack(side=tk.LEFT, padx=5)
        ttk.Button(history_frame, text="Clear Data", command=self.clear_data).pack(side=tk.LEFT, padx=5)
        
        # Create main sections
        self.create_income_section()
        self.create_balance_display()
        self.create_progress_bars()
        self.create_expense_section()
        self.create_deposit_section()
        self.create_recurring_section()
        self.create_goals_section()
        self.create_calendar_section()
        
    def create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Export Backup", command=self.export_backup)
        file_menu.add_command(label="Import Backup", command=self.import_backup)
        file_menu.add_separator()
        file_menu.add_command(label="Send Status to Telegram", command=self.send_daily_summary)
        file_menu.add_separator()
        # Add .env editor option
        file_menu.add_command(label="Edit .env (Telegram Config)", command=self.edit_env_file)
        # Add menu option to start Telegram bot interactively
        file_menu.add_command(label="Start Telegram Bot", command=self.start_telegram_bot)
        # Add menu option to install/start Telegram bot as a service
        file_menu.add_command(label="Start Telegram Bot Service", command=self.try_install_telegram_service)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Show Charts", command=self.show_charts)
        view_menu.add_separator()
        
        # Fix theme menu
        current_theme = self.data["settings"]["theme"]
        self.theme_var = tk.StringVar(value=current_theme)
        view_menu.add_radiobutton(
            label="Light Theme (Cosmo)", 
            command=lambda: self.toggle_theme("cosmo"),
            variable=self.theme_var,
            value="cosmo"
        )
        view_menu.add_radiobutton(
            label="Dark Theme (Darkly)", 
            command=lambda: self.toggle_theme("darkly"),
            variable=self.theme_var,
            value="darkly"
        )

    def toggle_theme(self, theme):
        """Toggle between light and dark themes"""
        self.data["settings"]["theme"] = theme
        self.theme_var.set(theme)
        try:
            with open(DATA_FILE, "w") as f:
                json.dump(self.data, f, indent=4)
            self.add_to_history()
            self.root._style.theme_use(theme)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save theme: {str(e)}")

    def export_backup(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            title="Export Backup"
        )
        if file_path:
            try:
                with open(file_path, "w") as f:
                    json.dump(self.data, f, indent=4)
                messagebox.showinfo("Success", "Backup exported successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export backup: {str(e)}")

    def import_backup(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json")],
            title="Import Backup"
        )
        if file_path:
            try:
                with open(file_path, "r") as f:
                    self.data = json.load(f)
                with open(DATA_FILE, "w") as f:
                    json.dump(self.data, f, indent=4)
                self.update_balance_display()
                messagebox.showinfo("Success", "Backup imported successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to import backup: {str(e)}")

    def create_income_section(self):
        income_frame = ttk.LabelFrame(self.main_frame, text="Income Settings", padding="10")
        income_frame.pack(fill=tk.X, pady=(0, 20))

        ttk.Label(income_frame, text="Monthly Income (₹):").pack(side=tk.LEFT, padx=5)
        self.entry_income = ttk.Entry(income_frame)
        self.entry_income.pack(side=tk.LEFT, padx=5)
        self.entry_income.insert(0, str(self.data.get("monthly_income", 0)))

        ttk.Button(income_frame, text="Set Income", command=self.set_income).pack(side=tk.LEFT, padx=5)
        
    def create_balance_display(self):
        self.balance_label = ttk.Label(self.main_frame, text="Current Balance: ₹0", 
                                     font=("", 12, "bold"))
        self.balance_label.pack(pady=(0, 20))
        
    def create_progress_bars(self):
        self.progress_frame = ttk.LabelFrame(self.main_frame, text="Budget Categories", 
                                           padding="10")
        self.progress_frame.pack(fill=tk.X, pady=(0, 20))

        # Needs Progress
        self.needs_label = ttk.Label(self.progress_frame, text="Needs (50%): ₹0 remaining")
        self.needs_label.pack(fill=tk.X)
        self.needs_progress = ttk.Progressbar(self.progress_frame, length=300, 
                                            mode='determinate')
        self.needs_progress.pack(fill=tk.X, pady=(0, 10))

        # Wants Progress
        self.wants_label = ttk.Label(self.progress_frame, text="Wants (30%): ₹0 remaining")
        self.wants_label.pack(fill=tk.X)
        self.wants_progress = ttk.Progressbar(self.progress_frame, length=300, 
                                            mode='determinate')
        self.wants_progress.pack(fill=tk.X, pady=(0, 10))

        # Savings Progress
        self.savings_label = ttk.Label(self.progress_frame, text="Savings (20%): ₹0 remaining")
        self.savings_label.pack(fill=tk.X)
        self.savings_progress = ttk.Progressbar(self.progress_frame, length=300, 
                                              mode='determinate')
        self.savings_progress.pack(fill=tk.X, pady=(0, 10))
        
    def create_expense_section(self):
        expense_frame = ttk.LabelFrame(self.main_frame, text="Add Expense", padding="10")
        expense_frame.pack(fill=tk.X, pady=(0, 20))

        # Amount
        ttk.Label(expense_frame, text="Amount (₹):").pack(fill=tk.X)
        self.entry_amount = ttk.Entry(expense_frame)
        self.entry_amount.pack(fill=tk.X, pady=(0, 10))

        # Category
        ttk.Label(expense_frame, text="Category:").pack(fill=tk.X)
        category_frame = ttk.Frame(expense_frame)
        category_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.category_var = tk.StringVar(value="needs")
        ttk.Radiobutton(category_frame, text="Needs", variable=self.category_var, 
                       value="needs").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(category_frame, text="Wants", variable=self.category_var, 
                       value="wants").pack(side=tk.LEFT, padx=5)

        # Description
        ttk.Label(expense_frame, text="Description:").pack(fill=tk.X)
        self.expense_desc_combo = ttk.Combobox(expense_frame)
        self.expense_desc_combo.pack(fill=tk.X, pady=(0, 10))
        
        # Update descriptions when category changes
        def update_descriptions(*args):
            category = self.category_var.get()
            self.expense_desc_combo['values'] = self.categories[category]
            self.expense_desc_combo.set("")  # Clear current selection
            
        self.category_var.trace('w', update_descriptions)
        update_descriptions()  # Initial update

        # Note
        ttk.Label(expense_frame, text="Note (optional):").pack(fill=tk.X)
        self.expense_note = ttk.Entry(expense_frame)
        self.expense_note.pack(fill=tk.X, pady=(0, 10))

        # Image attachment
        ttk.Button(expense_frame, text="Attach Receipt", 
                  command=self.attach_receipt).pack(fill=tk.X, pady=(0, 10))
        self.receipt_label = ttk.Label(expense_frame, text="No receipt attached")
        self.receipt_label.pack(fill=tk.X)

        ttk.Button(expense_frame, text="Add Expense", 
                  command=self.add_expense).pack(fill=tk.X, pady=(10, 0))
                  
        self.attached_image_path = None
        
    def create_deposit_section(self):
        deposit_frame = ttk.LabelFrame(self.main_frame, text="Add Deposit", padding="10")
        deposit_frame.pack(fill=tk.X, pady=(0, 20))

        ttk.Label(deposit_frame, text="Amount (₹):").pack()
        self.deposit_entry = ttk.Entry(deposit_frame)
        self.deposit_entry.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(deposit_frame, text="Add Deposit", 
                  command=self.add_deposit).pack(fill=tk.X)
                  
    def create_recurring_section(self):
        self.recurring_frame = ttk.LabelFrame(self.main_frame, text="Recurring Expenses", 
                                        padding="10")
        self.recurring_frame.pack(fill=tk.X, pady=(0, 20))
        
        header_frame = ttk.Frame(self.recurring_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(header_frame, text="Add Recurring Expense", 
                   command=self.show_recurring_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(header_frame, text="Process Recurring", 
                   command=self.process_recurring_expenses).pack(side=tk.LEFT, padx=5)
        
        # Container for recurring expenses list
        self.recurring_list = ttk.Frame(self.recurring_frame)
        self.recurring_list.pack(fill=tk.BOTH, expand=True)
        
        self.update_recurring_display()

    def create_goals_section(self):
        goals_frame = ttk.LabelFrame(self.main_frame, text="Savings Goals", padding="10")
        goals_frame.pack(fill=tk.X, pady=(0, 20))

        # Add goal button
        ttk.Button(goals_frame, text="Add New Goal", 
                  command=self.show_goal_dialog).pack(fill=tk.X)

        # Goals display
        self.goals_display = ttk.Frame(goals_frame)
        self.goals_display.pack(fill=tk.X, pady=(10, 0))
        self.update_goals_display()
        
    def create_calendar_section(self):
        calendar_frame = ttk.LabelFrame(self.main_frame, text="Calendar View", padding="10")
        calendar_frame.pack(fill=tk.X, pady=(0, 20))

        # Calendar header with month/year navigation
        header_frame = ttk.Frame(calendar_frame)
        header_frame.pack(fill=tk.X, pady=5)
        
        self.prev_month_btn = ttk.Button(header_frame, text="◀", width=3, command=self.prev_month)
        self.prev_month_btn.pack(side=tk.LEFT, padx=5)
        
        self.month_year_label = ttk.Label(header_frame, text="", font=("", 10, "bold"))
        self.month_year_label.pack(side=tk.LEFT, expand=True)
        
        self.next_month_btn = ttk.Button(header_frame, text="▶", width=3, command=self.next_month)
        self.next_month_btn.pack(side=tk.LEFT, padx=5)

        # Calendar grid
        self.calendar_frame = ttk.Frame(calendar_frame)
        self.calendar_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Current date
        self.current_date = datetime.now()
        self.selected_date = self.current_date
        self.update_calendar()

    def update_calendar(self):
        # Clear previous calendar
        for widget in self.calendar_frame.winfo_children():
            widget.destroy()

        # Update month/year label
        self.month_year_label.config(
            text=self.current_date.strftime("%B %Y")
        )

        # Create weekday headers
        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i, day in enumerate(weekdays):
            ttk.Label(
                self.calendar_frame, 
                text=day, 
                anchor="center",
                style="Calendar.TLabel"
            ).grid(row=0, column=i, sticky="nsew", padx=1, pady=1)

        # Calculate first day of month and number of days
        first_day = self.current_date.replace(day=1)
        # month_days = (first_day.replace(month=first_day.month % 12 + 1) - first_day).days
        year = first_day.year
        month = first_day.month
        month_days = calendar.monthrange(year, month)[1]  # <-- Use calendar.monthrange

        # Calculate starting position (0 = Monday, 6 = Sunday)
        start_pos = first_day.weekday()

        # Create calendar buttons
        for i in range(42):  # 6 weeks × 7 days
            row = (i + start_pos) // 7 + 1
            col = (i + start_pos) % 7
            
            if i < start_pos or i >= start_pos + month_days:
                btn = ttk.Label(self.calendar_frame, text="")
                btn.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
            else:
                day = i - start_pos + 1
                date = self.current_date.replace(day=day)
                
                # Check if date has expenses
                date_str = date.strftime("%Y-%m-%d")
                month_str = date.strftime("%Y-%m")
                has_expense = (month_str in self.data["expenses"] and 
                             date_str in self.data["expenses"][month_str])
                
                btn = ttk.Button(
                    self.calendar_frame,
                    text=str(day),
                    style="Calendar.TButton" if not has_expense else "CalendarHighlight.TButton",
                    command=lambda d=date: self.on_date_select(d)
                )
                btn.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
                
                # Highlight current day
                if date.date() == datetime.now().date():
                    btn.configure(style="CalendarToday.TButton")

        # Make columns expand evenly
        for i in range(7):
            self.calendar_frame.columnconfigure(i, weight=1)

    def prev_month(self):
        if self.current_date.month == 1:
            self.current_date = self.current_date.replace(year=self.current_date.year - 1, month=12)
        else:
            self.current_date = self.current_date.replace(month=self.current_date.month - 1)
        self.update_calendar()

    def next_month(self):
        if self.current_date.month == 12:
            self.current_date = self.current_date.replace(year=self.current_date.year + 1, month=1)
        else:
            self.current_date = self.current_date.replace(month=self.current_date.month + 1)
        self.update_calendar()

    def on_date_select(self, date):
        """Show expenses for selected date"""
        date_str = date.strftime("%Y-%m-%d")
        month_str = date.strftime("%Y-%m")
        
        expenses = self.data["expenses"].get(month_str, {}).get(date_str, [])
        if not expenses:
            messagebox.showinfo("Expenses", "No expenses on this date.")
            return
            
        # Create a detail window
        detail_window = tk.Toplevel(self.root)
        detail_window.title(f"Expenses for {date_str}")
        detail_window.geometry("400x300")
        
        # Create a text widget with scrollbar
        text_frame = ttk.Frame(detail_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_widget = tk.Text(text_frame, wrap=tk.WORD, yscrollcommand=scrollbar.set)
        text_widget.pack(fill=tk.BOTH, expand=True)
        
        scrollbar.config(command=text_widget.yview)
        
        for expense in expenses:
            text_widget.insert(tk.END, 
                             f"Amount: ₹{expense['amount']:,.2f}\n"
                             f"Category: {expense['category'].title()}\n"
                             f"Description: {expense['description']}\n")
            if "note" in expense:
                text_widget.insert(tk.END, f"Note: {expense['note']}\n")
            if "image_path" in expense:
                text_widget.insert(tk.END, f"Receipt: {expense['image_path']}\n")
            text_widget.insert(tk.END, "-" * 40 + "\n")
        
        text_widget.config(state=tk.DISABLED)

    def set_income(self):
        try:
            income = float(self.entry_income.get())
            if income < 0:
                raise ValueError("Income cannot be negative")
                
            self.data["monthly_income"] = income
            self.data["breakdown"] = {
                "needs": round(income * 0.50),
                "wants": round(income * 0.30),
                "savings": round(income * 0.20)
            }
            
            with open(DATA_FILE, "w") as f:
                json.dump(self.data, f, indent=4)
                
            self.update_balance_display()
            self.add_to_history()
            messagebox.showinfo("Success", "Income and breakdown updated successfully!")
            
        except ValueError as ve:
            messagebox.showerror("Error", str(ve))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to set income: {str(e)}")

    def attach_receipt(self):
        """Handle receipt image attachment for expenses"""
        try:
            file_path = filedialog.askopenfilename(
                title="Select Receipt Image",
                filetypes=[
                    ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp"),
                    ("All files", "*.*")
                ]
            )
            
            if file_path:
                # Store file path and update label
                self.attached_image_path = file_path
                filename = os.path.basename(file_path)
                self.receipt_label.config(text=f"Receipt attached: {filename}")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to attach receipt: {str(e)}")
            self.attached_image_path = None
            self.receipt_label.config(text="No receipt attached")

    def add_expense(self):
        """Add a new expense entry"""
        try:
            amount = float(self.entry_amount.get())
            if amount <= 0:
                raise ValueError("Amount must be positive")
                
            # Add new category to list if it doesn't exist
            category = self.category_var.get()
            description = self.expense_desc_combo.get().strip()
            
            if description and description not in self.categories[category]:
                self.categories[category].append(description)
                self.expense_desc_combo['values'] = self.categories[category]
                # Save updated categories
                with open(CATEGORIES_FILE, "w") as f:
                    json.dump(self.categories, f, indent=4)
            
            if not description:
                raise ValueError("Description is required")
                
            current_date = datetime.now()
            date_str = current_date.strftime("%Y-%m-%d")
            month_str = current_date.strftime("%Y-%m")
            
            if month_str not in self.data["expenses"]:
                self.data["expenses"][month_str] = {}
            if date_str not in self.data["expenses"][month_str]:
                self.data["expenses"][month_str][date_str] = []
                
            expense = {
                "amount": amount,
                "category": category,
                "description": description,
                "note": self.expense_note.get().strip()
            }
            
            if self.attached_image_path:
                expense["image_path"] = self.attached_image_path
                
            self.data["expenses"][month_str][date_str].append(expense)
            
            with open(DATA_FILE, "w") as f:
                json.dump(self.data, f, indent=4)
                
            self.update_balance_display()
            self.update_calendar()  # Refresh calendar to show new expense
            
            # Clear inputs
            self.entry_amount.delete(0, tk.END)
            self.expense_desc_combo.set("")
            self.expense_note.delete(0, tk.END)
            self.attached_image_path = None
            self.receipt_label.config(text="No receipt attached")
            
            messagebox.showinfo("Success", "Expense added successfully!")
            
            self.add_to_history()
            
        except ValueError as ve:
            messagebox.showerror("Error", str(ve))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add expense: {str(e)}")

    def add_deposit(self):
        """Add a new deposit entry"""
        try:
            amount = float(self.deposit_entry.get())
            if amount <= 0:
                raise ValueError("Amount must be positive")
                
            current_date = datetime.now()
            date_str = current_date.strftime("%Y-%m-%d")
            month_str = current_date.strftime("%Y-%m")
            
            if month_str not in self.data["deposits"]:
                self.data["deposits"][month_str] = {}
                
            self.data["deposits"][month_str][date_str] = amount
            
            with open(DATA_FILE, "w") as f:
                json.dump(self.data, f, indent=4)
                
            self.update_balance_display()
            self.add_to_history()
            self.deposit_entry.delete(0, tk.END)
            messagebox.showinfo("Success", "Deposit added successfully!")
            
        except ValueError as ve:
            messagebox.showerror("Error", str(ve))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add deposit: {str(e)}")

    def update_recurring_display(self):
        """Update the recurring expenses display"""
        for widget in self.recurring_list.winfo_children():
            widget.destroy()
            
        if not self.data.get("recurring_expenses"):
            ttk.Label(self.recurring_list, text="No recurring expenses set up").pack(pady=10)
            return
            
        # Create headers
        headers = ["Description", "Amount", "Frequency", "Day", "Last Added", ""]
        header_frame = ttk.Frame(self.recurring_list)
        header_frame.pack(fill=tk.X, pady=(0, 5))
        
        for i, header in enumerate(headers):
            ttk.Label(header_frame, text=header, font=("", 9, "bold")).grid(
                row=0, column=i, padx=5, sticky="w")
        
        # Add expenses
        for i, expense in enumerate(self.data["recurring_expenses"]):
            row = ttk.Frame(self.recurring_list)
            row.pack(fill=tk.X, pady=2)
            
            ttk.Label(row, text=expense["description"]).grid(row=0, column=0, padx=5)
            ttk.Label(row, text=f"₹{expense['amount']:,.2f}").grid(row=0, column=1, padx=5)
            ttk.Label(row, text=expense["frequency"].title()).grid(row=0, column=2, padx=5)
            ttk.Label(row, text=expense["day"]).grid(row=0, column=3, padx=5)
            ttk.Label(row, text=expense.get("last_added", "Never")).grid(row=0, column=4, padx=5)
            
            ttk.Button(row, text="Delete", 
                      command=lambda idx=i: self.delete_recurring(idx)).grid(
                          row=0, column=5, padx=5)

    def delete_recurring(self, index):
        if messagebox.askyesno("Confirm", "Delete this recurring expense?"):
            self.data["recurring_expenses"].pop(index)
            with open(DATA_FILE, "w") as f:
                json.dump(self.data, f, indent=4)
            self.update_recurring_display()
            self.add_to_history()

    def process_recurring_expenses(self):
        """Process due recurring expenses"""
        if not self.data.get("recurring_expenses"):
            messagebox.showinfo("Info", "No recurring expenses to process")
            return
        
        today = datetime.now()
        current_weekday = today.strftime("%A")
        current_day = today.day
        current_date = today.strftime("%Y-%m-%d")
        current_month = today.strftime("%Y-%m")
        
        expenses_added = 0
        
        for expense in self.data["recurring_expenses"]:
            last_added = expense.get("last_added")
            if last_added == current_date:
                continue
            
            should_add = False
            if expense["frequency"] == "monthly" and current_day == int(expense["day"]):
                should_add = True
            elif expense["frequency"] == "weekly" and current_weekday == expense["day"]:
                should_add = True
            
            if should_add:
                if current_month not in self.data["expenses"]:
                    self.data["expenses"][current_month] = {}
                if current_date not in self.data["expenses"][current_month]:
                    self.data["expenses"][current_month][current_date] = []
                
                self.data["expenses"][current_month][current_date].append({
                    "amount": expense["amount"],
                    "category": expense["category"],
                    "description": expense["description"],
                    "note": "Recurring expense"
                })
                
                expense["last_added"] = current_date
                expenses_added += 1
        
        if expenses_added > 0:
            with open(DATA_FILE, "w") as f:
                json.dump(self.data, f, indent=4)
            self.update_balance_display()
            self.update_recurring_display()
            self.update_calendar()
            self.add_to_history()
            messagebox.showinfo("Success", f"Added {expenses_added} recurring expense(s)")
        else:
            messagebox.showinfo("Info", "No recurring expenses due today")

    def highlight_expense_dates(self):
        """Update calendar to highlight dates with expenses"""
        self.update_calendar()

    def show_recurring_dialog(self):
        """Show dialog to add recurring expense"""
        dialog = ttkb.Toplevel(master=self.root)
        dialog.title("Add Recurring Expense")
        dialog.geometry("400x450")
        
        # Amount
        ttk.Label(dialog, text="Amount (₹):").pack(fill=tk.X, padx=10, pady=(10,0))
        amount_entry = ttk.Entry(dialog)
        amount_entry.pack(fill=tk.X, padx=10, pady=(5,10))
        
        # Description
        ttk.Label(dialog, text="Description:").pack(fill=tk.X, padx=10)
        # Only show a flat list of all categories for the combobox
        all_categories = [desc for cat in self.categories.values() for desc in cat]
        desc_combo = ttk.Combobox(dialog, values=all_categories)
        desc_combo.pack(fill=tk.X, padx=10, pady=(5,10))
        
        # Category
        ttk.Label(dialog, text="Category:").pack(fill=tk.X, padx=10)
        category_var = tk.StringVar(value="needs")
        category_frame = ttk.Frame(dialog)
        category_frame.pack(fill=tk.X, padx=10, pady=(5,10))
        ttk.Radiobutton(category_frame, text="Needs", variable=category_var, 
                       value="needs").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(category_frame, text="Wants", variable=category_var, 
                       value="wants").pack(side=tk.LEFT, padx=5)
        
        # Frequency
        ttk.Label(dialog, text="Frequency:").pack(fill=tk.X, padx=10)
        freq_var = tk.StringVar(value="monthly")
        freq_frame = ttk.Frame(dialog)
        freq_frame.pack(fill=tk.X, padx=10, pady=(5,10))
        ttk.Radiobutton(freq_frame, text="Monthly", variable=freq_var, 
                       value="monthly").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(freq_frame, text="Weekly", variable=freq_var, 
                       value="weekly").pack(side=tk.LEFT, padx=5)
        
        # Day selector
        day_frame = ttk.Frame(dialog)
        day_frame.pack(fill=tk.X, padx=10, pady=(5,10))
        ttk.Label(day_frame, text="Day:").pack(side=tk.LEFT, padx=5)
        day_var = tk.StringVar()
        day_combo = ttk.Combobox(day_frame, textvariable=day_var, width=15)
        day_combo.pack(side=tk.LEFT, padx=5)

        def update_day_options(*args):
            if freq_var.get() == "monthly":
                days = [str(i) for i in range(1, 32)]
                day_combo["values"] = days
                day_combo.set("1")
            else:
                days = ["Monday", "Tuesday", "Wednesday", "Thursday",
                        "Friday", "Saturday", "Sunday"]
                day_combo["values"] = days
                day_combo.set("Monday")

        freq_var.trace("w", update_day_options)
        update_day_options()
        
        def save_recurring():
            try:
                amount = float(amount_entry.get())
                if amount <= 0:
                    raise ValueError("Amount must be positive")
                
                description = desc_combo.get().strip()
                if not description:
                    raise ValueError("Description is required")
                
                category = category_var.get()
                frequency = freq_var.get()
                day = day_var.get()
                
                recurring_expense = {
                    "amount": amount,
                    "description": description,
                    "category": category,
                    "frequency": frequency,
                    "day": day,
                    "last_added": None
                }
                
                if "recurring_expenses" not in self.data:
                    self.data["recurring_expenses"] = []
                
                self.data["recurring_expenses"].append(recurring_expense)
                with open(DATA_FILE, "w") as f:
                    json.dump(self.data, f, indent=4)
                
                self.update_recurring_display()
                self.add_to_history()
                dialog.destroy()
                messagebox.showinfo("Success", "Recurring expense added!")
                
            except ValueError as ve:
                messagebox.showerror("Error", str(ve))
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {str(e)}")
        
        ttk.Button(dialog, text="Save", command=save_recurring).pack(pady=20)
        
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.focus_set()

    def show_goal_dialog(self):
        """Show dialog to add savings goal"""
        dialog = ttkb.Toplevel(master=self.root)
        dialog.title("Add Savings Goal")
        dialog.geometry("400x450")
        
        # Goal Name
        ttk.Label(dialog, text="Goal Name:").pack(fill=tk.X, padx=10, pady=(10,0))
        name_entry = ttk.Entry(dialog)
        name_entry.pack(fill=tk.X, padx=10, pady=(5,10))
        
        # Target Amount
        ttk.Label(dialog, text="Target Amount (₹):").pack(fill=tk.X, padx=10)
        amount_entry = ttk.Entry(dialog)
        amount_entry.pack(fill=tk.X, padx=10, pady=(5,10))
        
        # Target Date
        ttk.Label(dialog, text="Target Date:").pack(fill=tk.X, padx=10)
        date_frame = ttk.Frame(dialog)
        date_frame.pack(fill=tk.X, padx=10, pady=(5,10))
        
        current_date = datetime.now()
        
        # Month selector
        months = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
        month_var = tk.StringVar(value=months[current_date.month-1])
        month_combo = ttk.Combobox(date_frame, textvariable=month_var,
                                  values=months, width=15)
        month_combo.pack(side=tk.LEFT, padx=5)
        
        # Year selector (current year + next 10 years)
        years = list(range(current_date.year, current_date.year + 11))
        year_var = tk.StringVar(value=str(current_date.year))
        year_combo = ttk.Combobox(date_frame, textvariable=year_var,
                                 values=[str(y) for y in years], width=10)
        year_combo.pack(side=tk.LEFT, padx=5)
        
        def save_goal():
            try:
                name = name_entry.get().strip()
                if not name:
                    raise ValueError("Goal name is required")
                
                amount = float(amount_entry.get())
                if amount <= 0:
                    raise ValueError("Target amount must be positive")
                
                month_idx = months.index(month_var.get()) + 1
                year = int(year_var.get())
                
                # Create goal structure
                goal = {
                    "name": name,
                    "target_amount": amount,
                    "target_date": f"{year}-{month_idx:02d}",
                    "current_amount": 0,
                    "created_date": current_date.strftime("%Y-%m-%d")
                }
                
                # Initialize goals list if not exists
                if "savings_goals" not in self.data:
                    self.data["savings_goals"] = []
                
                self.data["savings_goals"].append(goal)
                with open(DATA_FILE, "w") as f:
                    json.dump(self.data, f, indent=4)
                
                self.update_goals_display()
                self.add_to_history()
                dialog.destroy()
                messagebox.showinfo("Success", "Savings goal added successfully!")
                
            except ValueError as ve:
                messagebox.showerror("Error", str(ve))
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save goal: {str(e)}")
        
        ttk.Button(dialog, text="Save Goal", command=save_goal).pack(pady=20)
        
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.focus_set()

    def update_goals_display(self):
        """Update the savings goals display"""
        for widget in self.goals_display.winfo_children():
            widget.destroy()
        
        if not self.data.get("savings_goals"):
            ttk.Label(self.goals_display, text="No savings goals set up").pack(pady=10)
            return
        
        # Create headers
        headers = ["Goal", "Target", "Current", "Progress", "Target Date", "", ""]  # Add column for update
        header_frame = ttk.Frame(self.goals_display)
        header_frame.pack(fill=tk.X, pady=(0, 5))
        
        for i, header in enumerate(headers):
            ttk.Label(header_frame, text=header, font=("", 9, "bold")).grid(
                row=0, column=i, padx=5, sticky="w")
        
        # Add goals
        for i, goal in enumerate(self.data["savings_goals"]):
            row = ttk.Frame(self.goals_display)
            row.pack(fill=tk.X, pady=2)
            
            progress = (goal["current_amount"] / goal["target_amount"]) * 100 if goal["target_amount"] > 0 else 0
            
            ttk.Label(row, text=goal["name"]).grid(row=0, column=0, padx=5)
            ttk.Label(row, text=f"₹{goal['target_amount']:,.2f}").grid(row=0, column=1, padx=5)
            ttk.Label(row, text=f"₹{goal['current_amount']:,.2f}").grid(row=0, column=2, padx=5)
            ttk.Label(row, text=f"{progress:.1f}%").grid(row=0, column=3, padx=5)
            ttk.Label(row, text=goal["target_date"]).grid(row=0, column=4, padx=5)
            
            delete_btn = ttk.Button(row, text="Delete", 
                                  command=lambda idx=i: self.delete_goal(idx))
            delete_btn.grid(row=0, column=5, padx=5)

            # Add update button for current_amount
            def make_update_goal(idx):
                def update_goal_amount():
                    goal = self.data["savings_goals"][idx]
                    new_amt = simpledialog.askfloat(
                        "Update Progress",
                        f"Enter new saved amount for '{goal['name']}' (Target: ₹{goal['target_amount']:,.2f}):",
                        initialvalue=goal["current_amount"],
                        minvalue=0,
                        maxvalue=goal["target_amount"]
                    )
                    if new_amt is not None:
                        self.data["savings_goals"][idx]["current_amount"] = new_amt
                        with open(DATA_FILE, "w") as f:
                            json.dump(self.data, f, indent=4)
                        self.update_goals_display()
                        self.add_to_history()
                return update_goal_amount

            update_btn = ttk.Button(row, text="Update", command=make_update_goal(i))
            update_btn.grid(row=0, column=6, padx=5)

    def delete_goal(self, index):
        """Delete a savings goal"""
        if messagebox.askyesno("Confirm", "Delete this savings goal?"):
            self.data["savings_goals"].pop(index)
            with open(DATA_FILE, "w") as f:
                json.dump(self.data, f, indent=4)
            self.update_goals_display()
            self.add_to_history()

    def update_balance_display(self):
        """Update balance display and progress bars"""
        try:
            current_month = datetime.now().strftime("%Y-%m")
            income = self.data.get("monthly_income", 0)
            
            # Get all expenses and deposits for current month
            month_expenses = self.data.get("expenses", {}).get(current_month, {})
            month_deposits = self.data.get("deposits", {}).get(current_month, {})
            
            # Calculate totals
            total_expenses = sum(
                expense["amount"] 
                for day_expenses in month_expenses.values()
                for expense in day_expenses
            )
            
            total_deposits = sum(month_deposits.values()) if month_deposits else 0
            
            # Calculate balance
            current_balance = income + total_deposits - total_expenses
            
            # Update balance label with color coding
            if current_balance >= 0:
                balance_color = "green"
            else:
                balance_color = "red"
                
            self.balance_label.config(
                text=f"Current Balance: ₹{current_balance:,.2f}",
                foreground=balance_color
            )

            # Update progress bars
            bd = self.data.get("breakdown", {})
            needs_total = bd.get("needs", 0)
            wants_total = bd.get("wants", 0)
            savings_total = bd.get("savings", 0)

            # Calculate category spending
            needs_spent = sum(
                expense["amount"] 
                for day_expenses in month_expenses.values()
                for expense in day_expenses 
                if expense["category"].lower() == "needs"
            )
            
            wants_spent = sum(
                expense["amount"] 
                for day_expenses in month_expenses.values()
                for expense in day_expenses 
                if expense["category"].lower() == "wants"
            )
            
            savings_deposited = total_deposits
            
            # Update progress bars with percentage and remaining amounts
            if needs_total > 0:
                needs_percent = min((needs_spent / needs_total) * 100, 100)
                self.needs_progress["value"] = needs_percent
                needs_remaining = max(needs_total - needs_spent, 0)
                self.needs_label.config(
                    text=f"Needs (50%): ₹{needs_remaining:,.2f} remaining ({needs_percent:.1f}% used)"
                )
            
            if wants_total > 0:
                wants_percent = min((wants_spent / wants_total) * 100, 100)
                self.wants_progress["value"] = wants_percent
                wants_remaining = max(wants_total - wants_spent, 0)
                self.wants_label.config(
                    text=f"Wants (30%): ₹{wants_remaining:,.2f} remaining ({wants_percent:.1f}% used)"
                )
            
            if savings_total > 0:
                savings_percent = min((savings_deposited / savings_total) * 100, 100)
                self.savings_progress["value"] = savings_percent
                savings_remaining = max(savings_total - savings_deposited, 0)
                self.savings_label.config(
                    text=f"Savings (20%): ₹{savings_remaining:,.2f} remaining ({savings_percent:.1f}% used)"
                )

        except Exception as e:
            messagebox.showerror("Error", f"Failed to update balance display: {str(e)}")

    def add_to_history(self):
        """Add current state to history"""
        # Remove any future states if we're not at the end
        self.history = self.history[:self.current_index + 1]
        
        # Add new state
        current_state = json.dumps(self.data)
        if current_state != self.history[-1]:  # Only add if state changed
            self.history.append(current_state)
            self.current_index += 1
            
            # Trim history if too long
            if len(self.history) > self.max_history:
                self.history.pop(0)
                self.current_index -= 1

    def undo(self):
        """Restore previous state"""
        if self.current_index > 0:
            self.current_index -= 1
            self.data = json.loads(self.history[self.current_index])
            self.save_data()
            self.update_all_displays()

    def redo(self):
        """Restore next state"""
        if self.current_index < len(self.history) - 1:
            self.current_index += 1
            self.data = json.loads(self.history[self.current_index])
            self.save_data()
            self.update_all_displays()

    def clear_data(self):
        """Clear all financial data"""
        if messagebox.askyesno("Confirm Clear", 
                             "Are you sure you want to clear all financial data? This cannot be undone."):
            # Keep settings and PIN
            settings = self.data["settings"]
            self.data = {
                "monthly_income": 0,
                "breakdown": {},
                "expenses": {},
                "deposits": {},
                "settings": settings,
                "recurring_expenses": [],
                "savings_goals": []
            }
            self.add_to_history()
            self.save_data()
            self.update_all_displays()
            messagebox.showinfo("Success", "All financial data has been cleared.")

    def save_data(self):
        """Save current data to file"""
        with open(DATA_FILE, "w") as f:
            json.dump(self.data, f, indent=4)

    def update_all_displays(self):
        """Update all UI displays"""
        self.update_balance_display()
        self.update_recurring_display()
        self.update_goals_display()
        self.update_calendar()
        self.entry_income.delete(0, tk.END)
        self.entry_income.insert(0, str(self.data.get("monthly_income", 0)))

    def edit_env_file(self):
        """Open a dialog to edit the .env file with Telegram config guide"""
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        # Read or create .env file
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                env_content = f.read()
        else:
            env_content = (
                "# Telegram Bot Configuration\n"
                "TELEGRAM_BOT_TOKEN=\n"
                "TELEGRAM_CHAT_ID=\n"
            )

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit .env (Telegram Config)")
        dialog.geometry("600x400")

        guide = (
            "Guide for Telegram Bot Setup:\n"
            "1. Create a Telegram bot via @BotFather and get the token.\n"
            "2. Get your chat ID (search 'userinfobot' in Telegram).\n"
            "3. Enter values below as:\n"
            "   TELEGRAM_BOT_TOKEN=your_bot_token_here\n"
            "   TELEGRAM_CHAT_ID=your_chat_id_here\n"
            "4. Save and restart the app if needed.\n"
            "Tip: This file is portable and works on any device."
        )
        ttk.Label(dialog, text=guide, wraplength=580, justify="left").pack(padx=10, pady=(10, 5))

        text = tk.Text(dialog, wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        text.insert(tk.END, env_content)

        def save_env():
            try:
                with open(env_path, "w") as f:
                    f.write(text.get("1.0", tk.END).strip() + "\n")
                load_dotenv(env_path, override=True)
                # Reload bot token and chat id
                self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
                self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
                messagebox.showinfo("Saved", ".env file saved!\nIf you changed Telegram config, restart the app.")
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save .env: {str(e)}")

        ttk.Button(dialog, text="Save", command=save_env).pack(pady=10)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.focus_set()

    def start_telegram_bot(self):
        """Start the Telegram bot in a background thread (interactive mode)"""
        if hasattr(self, 'telegram_thread') and self.telegram_thread and self.telegram_thread.is_alive():
            # Already running
            return
        def run_bot():
            try:
                telegram_bot.main()
            except Exception as e:
                print(f"Telegram bot error: {e}")
        import threading
        self.telegram_thread = threading.Thread(target=run_bot, daemon=True)
        self.telegram_thread.start()
        # Optionally, you can print or log that the bot started
        # print("Telegram bot started in background.")

    def try_install_telegram_service(self):
        """Try to install/start the Telegram bot as a Windows service."""
        if is_service_installed(SERVICE_NAME):
            messagebox.showinfo("Service", "Telegram bot service is already installed and running.")
            return
        if messagebox.askyesno(
            "Telegram Bot Service",
            "Telegram bot is not running as a service.\n"
            "Do you want to install and run it as a background service now?"
        ):
            install_telegram_bot_service()

    def is_first_launch(self):
        return not os.path.exists(CONFIG_PATH)

    def save_first_launch(self):
        with open(CONFIG_PATH, "w") as f:
            json.dump({"first_launch": False}, f)

    def prompt_start_telegram_bot(self):
        choice = messagebox.askyesno(
            "Welcome",
            "Welcome to Finance Manager!\n\n"
            "Would you like to start the Telegram bot as a service now?"
        )
        if choice:
            install_telegram_bot_service()

def main():
    # Start the Telegram bot in a background thread
    import threading
    telegram_thread = threading.Thread(target=telegram_bot.main, daemon=True)
    telegram_thread.start()
    # Start the FinanceManager GUI
    app = FinanceManager()
    app.root.mainloop()

if __name__ == "__main__":
    main()

# -------------------------------
# How to create an EXE for this program:
#
# 1. Install PyInstaller:
#    pip install pyinstaller
#
# 2. Open a terminal in this folder.
#
# 3. Run:
#    pyinstaller --onefile --noconsole --add-data "finance_data.json;." --add-data "expense_categories.json;." --add-data "recurring_expenses.json;." --add-data "goals.json;." --add-data ".env;." --add-data "nssm.exe;." --hidden-import=telegram_bot Main.py
#
# 4. The EXE will be in the 'dist' folder.
#
# 5. Add any other files you use with --add-data.
# -------------------------------