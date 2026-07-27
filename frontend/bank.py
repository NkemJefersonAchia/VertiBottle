balance = 1000

print("Welcome to the Pyland Bank")
print("You can deposit money, withdraw money, or check your current balance.")
print("You have received 1000 as a first-time user.\n")


def deposit():
    global balance

    amount = int(input("How much would you like to deposit? "))

    if amount <= 0:
        print("Amount must be greater than 0.")
    else:
        balance += amount
        print(f"You have successfully deposited {amount}.")
        print(f"Your new balance is {balance}.")


def withdraw():
    global balance

    amount = int(input("Enter amount to withdraw: "))

    if amount <= 0:
        print("Amount must be greater than 0.")
    elif amount > balance:
        print("Insufficient funds.")
    else:
        balance -= amount
        print(f"You have successfully withdrawn {amount}.")
        print(f"Your new balance is {balance}.")


def check_balance():
    print(f"Your current balance is {balance}.")


while True:
    print("\n===== Pyland Bank Menu =====")
    print("1. Deposit cash")
    print("2. Withdraw cash")
    print("3. Check balance")
    print("4. Exit")

    choice = input("Select an option (1-4): ")

    if choice == "1":
        deposit()

    elif choice == "2":
        withdraw()

    elif choice == "3":
        check_balance()

    elif choice == "4":
        print("Thanks for banking with Pyland. Goodbye!")
        break

    else:
        print("Invalid option. Please try again.")