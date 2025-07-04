# Finance Manager

A personal finance manager with a GUI and Telegram bot integration.

## Features

- **Telegram Bot**  
  - Commands: `/addexpense`, `/budgetcheck`, `/viewexpenses`, `/help`
  - Add expenses, check budget, and view expenses via Telegram
- **JSON-based Local Data Storage**
- **GUI App**  
  - Run `Main.py` for a full-featured desktop experience

## Setup

1. **Clone the repository**
2. **Install dependencies**  
   ```
   pip install -r requirements.txt
   ```
3. **Configure environment**  
   - Copy `.env.example` to `.env` and fill in your Telegram bot token.

4. **Run the app**  
   ```
   python start.py
   ```

## Telegram Bot Setup

- Create a bot with [@BotFather](https://t.me/BotFather) on Telegram and get your bot token.
- Get your chat ID (search for `userinfobot` in Telegram).
- Add your token and chat ID to the `.env` file.

## Folder Structure

```
FinanceManager/
├── telegram_bot.py
├── Main.py
├── utils/
├── tkcalendar/
├── finance_data.json
├── expense_categories.json
├── recurring_expenses.json
├── goals.json
├── .env.example
├── requirements.txt
└── README.md
```
