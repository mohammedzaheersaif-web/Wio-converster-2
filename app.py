import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import zipfile

st.set_page_config(page_title="WIO Converter", layout="wide")
st.title("WIO Bank Statement Splitter")

uploaded_file = st.file_uploader("Upload WIO Bank Statement (PDF)", type=["pdf"])

if uploaded_file:
    data = []
    VALID_CURRENCIES = ["AED", "USD", "EUR", "GBP"]
    current_currency = None

    with pdfplumber.open(uploaded_file) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            # -------------------------------------------
            # STEP 1: ROBUST CURRENCY FINDER
            # -------------------------------------------
            found_currency = None
            
            # Search strategies
            balance_match = re.search(r"Balance.*?(" + "|".join(VALID_CURRENCIES) + r")", text, re.IGNORECASE | re.DOTALL)
            account_match = re.search(r"\b(" + "|".join(VALID_CURRENCIES) + r")\s+Account\b", text, re.IGNORECASE)
            currency_lbl_match = re.search(r"CURRENCY.*?(" + "|".join(VALID_CURRENCIES) + r")", text, re.IGNORECASE | re.DOTALL)

            if balance_match:
                found_currency = balance_match.group(1).upper()
            elif account_match:
                found_currency = account_match.group(1).upper()
            elif currency_lbl_match:
                found_currency = currency_lbl_match.group(1).upper()

            if found_currency:
                current_currency = found_currency

            # -------------------------------------------
            # STEP 2: EXTRACT TRANSACTIONS
            # -------------------------------------------
            lines = text.split("\n")
            for line in lines:
                date_match = re.match(r"(\d{2}[/-]\d{2}[/-]\d{4})\s+(.*)", line)
                
                if date_match:
                    date = date_match.group(1)
                    rest_of_line = date_match.group(2).split()
                    numbers = [p.replace(",", "") for p in rest_of_line if re.match(r"-?\d+(\.\d+)?", p)]

                    if len(numbers) >= 2:
                        try:
                            balance = float(numbers[-1])
                            amount = float(numbers[-2])
                            reference = rest_of_line[0]
                            description = " ".join(rest_of_line[1:-2])
                            row_currency = current_currency if current_currency else "UNKNOWN"

                            data.append([date, reference, description, amount, balance, row_currency])
                        except ValueError:
                            continue

    # -------------------------------------------
    # STEP 3: SMART DOWNLOAD LOGIC
    # -------------------------------------------
    df = pd.DataFrame(data, columns=["Date", "Reference", "Description", "Amount", "Balance", "Currency"])

    if not df.empty:
        st.success(f"Processed {len(df)} transactions.")
        st.dataframe(df)

        unique_currencies = df["Currency"].unique()
        
        # CASE A: Only one currency found (e.g. just AED)
        # Download directly as AED.xlsx
        if len(unique_currencies) == 1:
            currency_name = unique_currencies[0]
            
            # Create Excel in memory
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name="Transactions")
                
            st.download_button(
                label=f"Download {currency_name}.xlsx",
                data=buffer.getvalue(),
                file_name=f"{currency_name}.xlsx",
                mime="application/vnd.ms-excel"
            )

        # CASE B: Multiple currencies found
        # Download as ZIP containing AED.xlsx, USD.xlsx, etc.
        else:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for curr in unique_currencies:
                    subset_df = df[df["Currency"] == curr]
                    
                    # Create individual Excel file
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                        subset_df.to_excel(writer, index=False, sheet_name=f"{curr}")
                    
                    # Name the file inside the zip exactly as requested
                    zf.writestr(f"{curr}.xlsx", excel_buffer.getvalue())

            st.download_button(
                label="Download All (ZIP)",
                data=zip_buffer.getvalue(),
                file_name="Wio_Statements.zip",
                mime="application/zip"
            )
            
    else:
        st.warning("No transactions found. Please check the PDF.")
