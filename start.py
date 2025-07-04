import sys

def main():
    print("Choose:")
    print("[1] Start Finance Manager GUI")
    print("[2] Start Telegram Bot")
    choice = input("Enter 1 or 2: ").strip()
    if choice == "1":
        import Main
    elif choice == "2":
        import telegram_bot
        telegram_bot.main()
    else:
        print("Invalid choice.")

if __name__ == "__main__":
    main()
