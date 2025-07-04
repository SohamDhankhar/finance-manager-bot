import os
import sys
import json
import time
import requests
from datetime import datetime, date
from dotenv import load_dotenv

def resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

DATA_FILE = resource_path("finance_data.json")
STATE_FILE = resource_path("bot_state.json")  # To store user conversation state

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)

def send_telegram_message(token, chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Failed to send Telegram message: {str(e)}")

def get_daily_summary(data):
    try:
        today = date.today()
        today_str = today.strftime("%Y-%m-%d")
        month_str = today.strftime("%Y-%m")

        today_expenses = data.get("expenses", {}).get(month_str, {}).get(today_str, [])
        total_today = sum(expense["amount"] for expense in today_expenses)

        current_month = datetime.now().strftime("%Y-%m")
        income = data.get("monthly_income", 0)
        month_expenses = data.get("expenses", {}).get(current_month, {})
        month_deposits = data.get("deposits", {}).get(current_month, {})

        total_expenses = sum(
            expense["amount"]
            for day_expenses in month_expenses.values()
            for expense in day_expenses
        )
        total_deposits = sum(month_deposits.values()) if month_deposits else 0
        current_balance = income + total_deposits - total_expenses

        bd = data.get("breakdown", {})
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

def get_today_expenses(data):
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    month_str = today.strftime("%Y-%m")
    return data.get("expenses", {}).get(month_str, {}).get(today_str, [])

def get_balance(data):
    current_month = datetime.now().strftime("%Y-%m")
    income = data.get("monthly_income", 0)
    month_expenses = data.get("expenses", {}).get(current_month, {})
    month_deposits = data.get("deposits", {}).get(current_month, {})
    total_expenses = sum(
        expense["amount"]
        for day_expenses in month_expenses.values()
        for expense in day_expenses
    )
    total_deposits = sum(month_deposits.values()) if month_deposits else 0
    return income + total_deposits - total_expenses

def get_categories():
    cat_file = resource_path("expense_categories.json")
    if os.path.exists(cat_file):
        with open(cat_file, "r") as f:
            categories = json.load(f)
        return categories
    return {"needs": [], "wants": []}

def process_user_message(token, chat_id, text, state, data):
    user_state = state.get(str(chat_id), {})
    text = text.strip()
    # If user is in the middle of adding an expense
    if user_state.get("action") == "add_expense":
        step = user_state.get("step", 1)
        if step == 1:
            # Expecting amount
            try:
                amount = float(text)
                if amount <= 0:
                    raise ValueError
                user_state["amount"] = amount
                user_state["step"] = 2
                state[str(chat_id)] = user_state
                save_state(state)
                reply_markup = {
                    "keyboard": [["Needs"], ["Wants"]],
                    "one_time_keyboard": True,
                    "resize_keyboard": True
                }
                return "Is this a 'Needs' or 'Wants' expense?", reply_markup
            except Exception:
                return "Please enter a valid positive amount.", None
        elif step == 2:
            # Expecting category
            cat = text.lower()
            if cat not in ["needs", "wants"]:
                return "Please reply with 'Needs' or 'Wants'.", None
            user_state["category"] = cat
            user_state["step"] = 3
            state[str(chat_id)] = user_state
            save_state(state)
            cats = get_categories()
            suggestions = cats.get(cat, [])
            if suggestions:
                return f"Enter a description for this expense (e.g. {suggestions[0]}):", None
            else:
                return "Enter a description for this expense:", None
        elif step == 3:
            # Expecting description
            desc = text.strip()
            if not desc:
                return "Description cannot be empty. Please enter a description:", None
            # Save expense
            amount = user_state["amount"]
            category = user_state["category"]
            description = desc
            current_date = datetime.now()
            date_str = current_date.strftime("%Y-%m-%d")
            month_str = current_date.strftime("%Y-%m")
            if month_str not in data["expenses"]:
                data["expenses"][month_str] = {}
            if date_str not in data["expenses"][month_str]:
                data["expenses"][month_str][date_str] = []
            expense = {
                "amount": amount,
                "category": category,
                "description": description,
                "note": "[Added via Telegram]"
            }
            data["expenses"][month_str][date_str].append(expense)
            save_data(data)
            # Optionally update categories file with new description
            cats = get_categories()
            if description and description not in cats.get(category, []):
                cats[category].append(description)
                cat_file = resource_path("expense_categories.json")
                with open(cat_file, "w") as f:
                    json.dump(cats, f, indent=4)
            # Clear state
            state.pop(str(chat_id), None)
            save_state(state)
            return f"Expense added: ₹{amount:.2f} ({category}) - {description}", None
    # Not in a multi-step action
    if text.lower() in ["/start", "hi", "hello"]:
        return (
            "👋 Hi! I'm your Finance Bot.\n"
            "You can:\n"
            "• Type 'add expense' to add a new expense\n"
            "• Type 'today' to see today's expenses\n"
            "• Type 'balance' to see your current balance\n"
            "• Type 'summary' for a daily summary\n"
            "• Type 'help' for more options"
        , None)
    elif text.lower() in ["add expense", "add", "expense"]:
        user_state = {"action": "add_expense", "step": 1}
        state[str(chat_id)] = user_state
        save_state(state)
        return "Let's add a new expense! How much did you spend? (Enter amount in ₹)", None
    elif text.lower() in ["today"]:
        expenses = get_today_expenses(data)
        if not expenses:
            return "No expenses for today.", None
        msg = "Today's Expenses:\n"
        for e in expenses:
            msg += f"₹{e['amount']:.2f} - {e['category'].title()} - {e['description']}\n"
        return msg, None
    elif text.lower() in ["balance"]:
        bal = get_balance(data)
        return f"Current balance: ₹{bal:.2f}", None
    elif text.lower() in ["summary", "status"]:
        summary = get_daily_summary(data)
        return summary if summary else "No data available.", None
    elif text.lower() in ["help"]:
        return (
            "You can use these commands:\n"
            "• add expense - Add a new expense\n"
            "• today - Show today's expenses\n"
            "• balance - Show your current balance\n"
            "• summary - Show today's summary\n"
            "Just type what you want to do!"
        , None)
    else:
        return (
            "Sorry, I didn't understand that. Type 'help' for options or 'add expense' to add a new expense."
        , None)

def main():
    load_dotenv()
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("Telegram bot token or chat ID not set in .env")
        return
    print("Finance Telegram Bot started. Polling for messages...")
    last_update_id = None
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params = {"timeout": 60}
            if last_update_id:
                params["offset"] = last_update_id + 1
            resp = requests.get(url, params=params, timeout=65)
            if resp.ok:
                updates = resp.json().get("result", [])
                for update in updates:
                    last_update_id = update["update_id"]
                    msg = update.get("message")
                    if not msg:
                        continue
                    from_id = str(msg["from"]["id"])
                    if str(chat_id).strip() != from_id:
                        continue  # Only respond to configured chat
                    text = msg.get("text", "")
                    data = load_data()
                    state = load_state()
                    reply, reply_markup = process_user_message(token, chat_id, text, state, data)
                    if reply:
                        send_telegram_message(token, chat_id, reply, reply_markup)
            time.sleep(2)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
