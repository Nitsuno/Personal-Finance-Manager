import pandas as pd
import pdfplumber
import os
import sqlite3

def get_master_lists(pdf_path):
    all_desc = []
    all_amounts = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table and len(table) > 1:
                # table[1][0] is the column for Descriptions
                # table[1][1] is the column for Amounts
                # We split by \n and extend our master lists
                raw_desc = table[1][0].split('\n') if table[1][0] else []
                raw_amt = table[1][1].split('\n') if table[1][1] else []
                
                all_desc.extend(raw_desc)
                all_amounts.extend(raw_amt)
                
    return all_desc, all_amounts

def clean_desc_robust(desc_list, amount_list):
    records = []
    amt_ptr = 0
    current_tx = None

    TRIGGERS = {
        "SALE DEBIT", "PYMT FROM A/C", "FUND TRANSFER TO A/", 
        "IBK FUND TFR FR A/C", "TRANSFER FROM A/C", "IBK FUND TFR TO A/C", 
        "FPX PAYMENT FR A/", "PAYMENT VIA MYDEBIT", "PRE-AUTH REFUND"}

    def is_ref_number(line):
        return line.isdigit() or (len(line) > 5 and line[-1] == 'Q')

    def is_location(line):
        return ", MY" in line  

    for i, line in enumerate(desc_list):
        line = line.strip()
        if not line or line == "BEGINNING BALANCE" or "BALANCE :" in line:
            continue

        if line in TRIGGERS:
            if line == "SALE DEBIT" and i + 1 < len(desc_list):
                next_line = desc_list[i+1].strip()
                if next_line in TRIGGERS:
                    continue

            if line == "PAYMENT VIA MYDEBIT" and i + 1 < len(desc_list):
                next_line = desc_list[i+1].strip()
                if next_line in TRIGGERS:
                    continue

            if line == "PRE-AUTH REFUND" and i + 1 < len(desc_list):
                next_line = desc_list[i+1].strip()
                if next_line in TRIGGERS:
                    continue

            if current_tx and (current_tx["Vendor"] or current_tx["Account"] or current_tx["Location"]):
                records.append(current_tx)

            current_tx = {"Sale Type": line, "Vendor": "", "Location": "", "Account": "", "Amount": None}

            if amt_ptr < len(amount_list):
                current_tx['Amount'] = amount_list[amt_ptr]
                amt_ptr += 1
            continue

        if not current_tx:
            continue

        if is_location(line):
            current_tx["Location"] = line
        elif is_ref_number(line):
            current_tx["Account"] = line
        else:
            # Fallback: treat as vendor (append if multiple vendor lines)
            if current_tx["Vendor"]:
                current_tx["Vendor"] += f" {line}"
            else:
                current_tx["Vendor"] = line

    if current_tx:
        records.append(current_tx)

    return pd.DataFrame(records)

month_map = {
    "Jan" : "01",
    "Feb" : "02",
    "Mar" : "03",
    "Apr" : "04",
    "May" : "05",
    "Jun" : "06",
    "Jul" : "07",
    "Aug" : "08",
    "Sep" : "09",
    "Oct" : "10",
    "Nov" : "11",
    "Dec" : "12",
}

def save_to_db(df, month_label, db_path):
    df = df.copy()
    df["month"] = month_label
    with sqlite3.connect(db_path) as conn:
        try:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE month = ?", (month_label,)
            )
            if cursor.fetchone()[0] > 0:
                return 0          # month already loaded — skip silently
        except sqlite3.OperationalError:
            pass                  # table doesn't exist yet; first-ever insert
        df.to_sql("transactions", conn, if_exists="append", index=False)
        return len(df)

if __name__ == "__main__":
    month = "Dec"
    year = "2025"
    filename = "/home/nitsuno/Desktop/Bank statements/2025/" + month + " " + year + ".pdf"
    desc_list, amount_list = get_master_lists(filename)

    summary_data = {}
    if len(amount_list) >= 3 and len(desc_list) >= 3:
        debit_amt = amount_list.pop()
        debit_label = desc_list.pop()
        credit_amt = amount_list.pop()
        credit_label = desc_list.pop()
        balance_amt = amount_list.pop()
        balance_label = desc_list.pop()
        summary_data[balance_label.replace(':', '').strip()] = balance_amt
        summary_data[credit_label.replace(':', '').strip()] = credit_amt
        summary_data[debit_label.replace(':', '').strip()] = debit_amt

    df = clean_desc_robust(desc_list, amount_list)
    print("--- Transaction Table ---")
    print(df.tail(20))
    print("\n--- Statement Summary ---")
    for key, value in summary_data.items():
        print(f"{key}: {value}")

    save_to_db(df, month_label=f"{year}-{month_map[month]}", db_path="db/statements.db")