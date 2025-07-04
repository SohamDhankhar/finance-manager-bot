import json
import os
import base64
import bcrypt
from datetime import datetime, timedelta

class DataManager:
    def __init__(self, base_path):
        self.base_path = base_path
        self.data_file = os.path.join(base_path, "finance_data.json")
        self.categories_file = os.path.join(base_path, "expense_categories.json")
        self.recurring_file = os.path.join(base_path, "recurring_expenses.json")
        self.goals_file = os.path.join(base_path, "goals.json")
        self.load_all_data()

    def load_all_data(self):
        # Load main finance data
        if os.path.exists(self.data_file):
            with open(self.data_file, "r") as f:
                self.data = json.load(f)
        else:
            self.data = {
                "monthly_income": 0,
                "breakdown": {},
                "expenses": {},
                "deposits": {},
                "settings": {
                    "theme": "darkly",
                    "pin": None
                }
            }

        # Load expense categories
        if os.path.exists(self.categories_file):
            with open(self.categories_file, "r") as f:
                self.categories = json.load(f)
        else:
            self.categories = ["Groceries", "Transport", "Entertainment", "Food", "Shopping"]
            self.save_categories()

        # Load recurring expenses
        if os.path.exists(self.recurring_file):
            with open(self.recurring_file, "r") as f:
                self.recurring = json.load(f)
        else:
            self.recurring = []
            self.save_recurring()

        # Load goals
        if os.path.exists(self.goals_file):
            with open(self.goals_file, "r") as f:
                self.goals = json.load(f)
        else:
            self.goals = []
            self.save_goals()

        # Process any pending recurring expenses
        self.process_recurring_expenses()

    def save_data(self):
        with open(self.data_file, "w") as f:
            json.dump(self.data, f, indent=4)

    def save_categories(self):
        with open(self.categories_file, "w") as f:
            json.dump(self.categories, f, indent=4)

    def save_recurring(self):
        with open(self.recurring_file, "w") as f:
            json.dump(self.recurring, f, indent=4)

    def save_goals(self):
        with open(self.goals_file, "w") as f:
            json.dump(self.goals, f, indent=4)

    def export_backup(self, backup_path):
        backup_data = {
            "finance_data": self.data,
            "categories": self.categories,
            "recurring": self.recurring,
            "goals": self.goals
        }
        with open(backup_path, "w") as f:
            json.dump(backup_data, f, indent=4)

    def import_backup(self, backup_path):
        with open(backup_path, "r") as f:
            backup_data = json.load(f)
        
        self.data = backup_data.get("finance_data", self.data)
        self.categories = backup_data.get("categories", self.categories)
        self.recurring = backup_data.get("recurring", self.recurring)
        self.goals = backup_data.get("goals", self.goals)
        
        self.save_data()
        self.save_categories()
        self.save_recurring()
        self.save_goals()

    def set_pin(self, pin):
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(str(pin).encode('utf-8'), salt)
        self.data["settings"]["pin"] = hashed.decode('utf-8')
        self.save_data()

    def verify_pin(self, pin):
        stored_hash = self.data["settings"].get("pin")
        if not stored_hash:
            return True
        return bcrypt.checkpw(str(pin).encode('utf-8'), stored_hash.encode('utf-8'))

    def set_theme(self, theme):
        self.data["settings"]["theme"] = theme
        self.save_data()

    def get_theme(self):
        return self.data["settings"].get("theme", "darkly")

    def process_recurring_expenses(self):
        today = datetime.now()
        current_month = today.strftime("%Y-%m")
        
        for expense in self.recurring:
            if not expense.get("active", True):
                continue
                
            last_processed = datetime.strptime(expense.get("last_processed", "2000-01-01"), "%Y-%m-%d")
            frequency = expense["frequency"]
            
            if frequency == "monthly" and current_month > last_processed.strftime("%Y-%m"):
                self.add_expense(
                    expense["amount"],
                    expense["category"],
                    f"[Recurring] {expense['description']}",
                    None,
                    None
                )
                expense["last_processed"] = today.strftime("%Y-%m-%d")
                
            elif frequency == "weekly":
                weeks_diff = (today - last_processed).days // 7
                if weeks_diff >= 1:
                    self.add_expense(
                        expense["amount"],
                        expense["category"],
                        f"[Recurring] {expense['description']}",
                        None,
                        None
                    )
                    expense["last_processed"] = today.strftime("%Y-%m-%d")
        
        self.save_recurring()

    def add_expense(self, amount, category, description, note=None, image_path=None):
        current_month = datetime.now().strftime("%Y-%m")
        today = datetime.now().strftime("%Y-%m-%d")
        
        if current_month not in self.data["expenses"]:
            self.data["expenses"][current_month] = {}
        if today not in self.data["expenses"][current_month]:
            self.data["expenses"][current_month][today] = []
            
        expense_entry = {
            "amount": amount,
            "category": category,
            "description": description
        }
        
        if note:
            expense_entry["note"] = note
            
        if image_path:
            # If the image path is relative, make it absolute
            if not os.path.isabs(image_path):
                image_path = os.path.join(self.base_path, image_path)
            expense_entry["image_path"] = image_path
            
        self.data["expenses"][current_month][today].append(expense_entry)
        self.save_data()

    def get_category_spending(self, month=None):
        if not month:
            month = datetime.now().strftime("%Y-%m")
            
        spending = {"needs": 0, "wants": 0}
        custom_categories = {}
        
        month_data = self.data["expenses"].get(month, {})
        for day_expenses in month_data.values():
            for expense in day_expenses:
                amount = expense["amount"]
                category = expense["category"].lower()
                description = expense["description"]
                
                # Add to main category (needs/wants)
                if category in spending:
                    spending[category] += amount
                    
                # Add to custom category
                if description not in custom_categories:
                    custom_categories[description] = 0
                custom_categories[description] += amount
                
        return spending, custom_categories

    def check_budget_warnings(self):
        current_month = datetime.now().strftime("%Y-%m")
        spending, _ = self.get_category_spending(current_month)
        warnings = []
        
        breakdown = self.data.get("breakdown", {})
        
        for category in ["needs", "wants"]:
            budget = breakdown.get(category, 0)
            spent = spending.get(category, 0)
            if budget > 0:
                percentage = (spent / budget) * 100
                if percentage >= 90:
                    warnings.append(f"Warning: You've spent {percentage:.1f}% of your {category.title()} budget!")
                    
        # Check savings
        savings_budget = breakdown.get("savings", 0)
        if savings_budget > 0:
            savings_deposited = sum(
                amount for date, amount in self.data["deposits"].get(current_month, {}).items()
            )
            if savings_deposited < savings_budget * 0.1:  # Less than 10% saved
                warnings.append("Warning: You're behind on your savings goal for this month!")
                
        return warnings
