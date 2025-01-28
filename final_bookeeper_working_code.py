###############################################################################################################
#set up code
#this is to set up our toy erp system the bookeeper will query with tools
import sqlite3
import os
from faker import Faker
import random

# Step 1: Set up the database

def setup_database():
    """Initializes the SQLite database and populates it with sample data."""
    conn = sqlite3.connect("bookkeeping.db")
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Vendors (
        vendor_id INTEGER PRIMARY KEY,
        name TEXT,
        email TEXT,
        active INTEGER
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Invoices (
        invoice_id INTEGER PRIMARY KEY,
        vendor_id INTEGER,
        amount REAL,
        paid INTEGER,
        date_entered TEXT,
        FOREIGN KEY (vendor_id) REFERENCES Vendors(vendor_id)
    );
    """)

    # Populate sample vendors
    fake = Faker()
    for vendor_id in range(1, 21):
        name = fake.company()
        email = fake.email()
        active = random.choices([0, 1], weights=[0.2, 0.8])[0]  # 20% inactive
        cursor.execute("INSERT INTO Vendors (vendor_id, name, email, active) VALUES (?, ?, ?, ?)",
                       (vendor_id, name, email, active))

    # Populate sample invoices
    for _ in range(10):
        vendor_id = random.randint(1, 20)
        amount = round(random.uniform(100, 1000), 2)
        paid = random.choice([0, 1])
        date_entered = fake.date_this_year().isoformat()
        cursor.execute("INSERT INTO Invoices (vendor_id, amount, paid, date_entered) VALUES (?, ?, ?, ?)",
                       (vendor_id, amount, paid, date_entered))

    conn.commit()
    conn.close()

# Step 2: Generate PDF invoices (utility function)

def generate_fake_invoice_pdf(vendor_id, invoice_id, amount):
    """Generates a fake invoice PDF content as binary data."""
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Invoice #{invoice_id}", ln=True, align='C')
    pdf.cell(200, 10, txt=f"Vendor ID: {vendor_id}", ln=True)
    pdf.cell(200, 10, txt=f"Amount Due: ${amount:.2f}", ln=True)
    pdf.cell(200, 10, txt="Thank you for your business!", ln=True)

    # Save to binary
    pdf_output = os.path.join(os.getcwd(), f"invoice_{invoice_id}.pdf")
    pdf.output(pdf_output)
    with open(pdf_output, "rb") as f:
        pdf_binary = f.read()
    os.remove(pdf_output)
    return pdf_binary

# Step 3: Generate and simulate incoming emails

def generate_sample_emails():
    """Generates sample email data with invoices, including random errors."""
    conn = sqlite3.connect("bookkeeping.db")
    cursor = conn.cursor()
    
    # Fetch all vendors
    cursor.execute("SELECT vendor_id, name, email, active FROM Vendors")
    vendors = cursor.fetchall()

    emails = []
    faker = Faker()

    for i in range(100):
        vendor = random.choice(vendors)
        vendor_id, _, email, active = vendor

        # Randomly introduce errors
        if random.random() < 0.1:
            vendor_id += random.randint(1, 10)  # Mismatched vendor ID
        if random.random() < 0.05:
            active = 0  # Inactive vendor

        invoice_id = random.randint(1000, 9999)
        amount = round(random.uniform(100, 1000), 2)

        if random.random() < 0.05:
            # Add existing invoice to database
            cursor.execute("INSERT INTO Invoices (vendor_id, amount, paid, date_entered) VALUES (?, ?, ?, ?)",
                           (vendor_id, amount, 0, faker.date_this_year().isoformat()))

        # Generate PDF
        attachment = generate_fake_invoice_pdf(vendor_id, invoice_id, amount)

        # Construct email
        email_data = {
            "sender": email,
            "body": f"Invoice {invoice_id} for services rendered. Total due: ${amount}",
            "attachment": attachment,
            "vendor_id": vendor_id,
            "invoice_id": invoice_id,
            "amount": amount
        }
        emails.append(email_data)

    conn.commit()
    conn.close()
    return emails

# Step 4: Execute setup steps
if __name__ == "__main__":
    setup_database()
    print("Database has been set up.")

    sample_emails = generate_sample_emails()
    print(f"Generated {len(sample_emails)} sample emails.")




###############################################################################################################
#actual agentic code
import sqlite3
import random
from datetime import datetime
from typing import List, Dict
from langchain.agents import initialize_agent, Tool
from langchain.agents import ZeroShotAgent, AgentExecutor
from langchain.prompts import StringPromptTemplate
from langchain.tools import tool

# Tool: Vendor Lookup
@tool
def vendor_lookup_tool(vendor_id: int) -> str:
    """
    Look up a vendor by vendor_id in the database.
    Returns vendor details (ID, name, email, and active status) or a 'not found' message.
    """
    conn = sqlite3.connect("bookkeeping.db")
    cursor = conn.cursor()

    cursor.execute("SELECT vendor_id, name, email, active FROM Vendors WHERE vendor_id = ?;", (vendor_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        return {
            "vendor_id": result[0],
            "name": result[1],
            "email": result[2],
            "active": "Yes" if result[3] else "No",
        }
    else:
        return "Vendor not found."

# Tool: Invoice Lookup
@tool
def invoice_lookup_tool(vendor_id: int, invoice_id: int) -> str:
    """
    Look up an invoice in the database by vendor_id and invoice_id.
    Returns whether the invoice exists and its payment status.
    """
    conn = sqlite3.connect("bookkeeping.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT invoice_id, vendor_id, paid FROM Invoices WHERE vendor_id = ? AND invoice_id = ?;",
        (vendor_id, invoice_id),
    )
    result = cursor.fetchone()
    conn.close()

    if result:
        return {
            "vendor_id": result[1],
            "invoice_id": result[0],
            "paid": "Yes" if result[2] else "No",
        }
    else:
        return "Invoice not found."

# Tool: Forward to Human
@tool
def forward_to_human_tool(email_json: Dict) -> str:
    """
    Forward an email to a human for review. Collects and stores details for review.
    """
    review_data = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sender": email_json.get("sender"),
        "attachment": email_json.get("attachment"),
        "body": email_json.get("body"),
        "problem": email_json.get("problem", "Unknown issue"),
    }
    return f"Forwarded to human for review: {review_data}"

# Core Agent Logic
def process_email(email_json: Dict):
    """
    Process an incoming email JSON object using LangChain tools and agent logic.
    """
    try:
        # Extract email fields
        vendor_id = email_json["vendor_id"]
        invoice_id = email_json["invoice_id"]
        sender_email = email_json["sender"]
        attachment = email_json["attachment"]

        # Vendor Lookup
        vendor_details = vendor_lookup_tool(vendor_id)
        if isinstance(vendor_details, str):
            email_json["problem"] = "Vendor not found."
            return forward_to_human_tool(email_json)

        if vendor_details["active"] != "Yes":
            email_json["problem"] = "Vendor is inactive."
            return forward_to_human_tool(email_json)

        if vendor_details["email"] != sender_email:
            email_json["problem"] = "Sender email does not match vendor record."
            return forward_to_human_tool(email_json)

        # Invoice Lookup
        invoice_details = invoice_lookup_tool(vendor_id, invoice_id)
        if isinstance(invoice_details, dict) and invoice_details.get("paid") == "Yes":
            email_json["problem"] = "Invoice already exists and is paid."
            return forward_to_human_tool(email_json)

        # Process Valid Invoice
        processed_data = {
            "vendor_id": vendor_id,
            "invoice_id": invoice_id,
            "sender_email": sender_email,
            "amount": email_json["amount"],
            "entered_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "attachment": attachment,
        }
        print(f"Valid Invoice Processed: {processed_data}")
        return processed_data

    except Exception as e:
        email_json["problem"] = f"Error during processing: {str(e)[:100]}"
        return forward_to_human_tool(email_json)

# Sample Email Processing
if __name__ == "__main__":
    # Example email JSON
    sample_email = {
        "vendor_id": 1,
        "invoice_id": 101,
        "sender": "vendor1@example.com",
        "attachment": b"%PDF-1.4 Fake PDF binary data",
        "body": "Invoice 101 for services rendered. Total due: $500",
        "amount": 500,
    }

    # Process the sample email
    result = process_email(sample_email)
    print(result)
