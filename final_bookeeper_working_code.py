#env set up
#pip install sqlite3 langchain openai pydantic python-decouple pandas reportlab


#dbase set up
import sqlite3

# Set up the database connection
def setup_database():
    conn = sqlite3.connect("invoices.db")
    cursor = conn.cursor()

    # Create vendors table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vendors (
        vendor_id TEXT PRIMARY KEY,
        vendor_email TEXT,
        active INTEGER
    )
    """)

    # Create invoices table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        invoice_id TEXT PRIMARY KEY,
        vendor_id TEXT,
        amount REAL,
        entered_date TEXT,
        FOREIGN KEY(vendor_id) REFERENCES vendors(vendor_id)
    )
    """)

    conn.commit()
    conn.close()

setup_database()

#tool set up
import sqlite3

def vendor_lookup_tool(vendor_id):
    conn = sqlite3.connect("invoices.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM vendors WHERE vendor_id = ?", (vendor_id,))
    vendor = cursor.fetchone()
    conn.close()

    if vendor:
        return {
            "vendor_id": vendor[0],
            "vendor_email": vendor[1],
            "active": bool(vendor[2])
        }
    else:
        return {"error": "Vendor not found"}

def invoice_lookup_tool(invoice_id):
    conn = sqlite3.connect("invoices.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM invoices WHERE invoice_id = ?", (invoice_id,))
    invoice = cursor.fetchone()
    conn.close()

    if invoice:
        return {
            "invoice_id": invoice[0],
            "vendor_id": invoice[1],
            "amount": invoice[2],
            "entered_date": invoice[3]
        }
    else:
        return {"error": "Invoice not found"}

def process_invoice_tool(invoice):
    conn = sqlite3.connect("invoices.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO invoices (invoice_id, vendor_id, amount, entered_date)
    VALUES (?, ?, ?, ?)
    """, (invoice["invoice_id"], invoice["vendor_id"], invoice["amount"], invoice["entered_date"]))

    conn.commit()
    conn.close()
    return f"Invoice {invoice['invoice_id']} processed successfully."

def forward_to_human_tool(issue, invoice):
    return {
        "action": "forward_to_human",
        "issue": issue,
        "invoice": invoice
    }

#agent set up
from langchain.agents import initialize_agent, Tool
from langchain.chat_models import ChatOpenAI
from decouple import config

# Load OpenAI API key
OPENAI_API_KEY = config("OPENAI_API_KEY")

# Initialize OpenAI ChatGPT model
llm = ChatOpenAI(
    temperature=0,
    openai_api_key=OPENAI_API_KEY,
    model="gpt-4"
)

# Define tools for the agent
tools = [
    Tool(name="Vendor Lookup", func=vendor_lookup_tool, description="Retrieve vendor details."),
    Tool(name="Invoice Lookup", func=invoice_lookup_tool, description="Validate invoices."),
    Tool(name="Process Invoice", func=process_invoice_tool, description="Process valid invoices."),
    Tool(name="Forward to Human", func=forward_to_human_tool, description="Forward invalid invoices to a human.")
]

# Initialize the agent
agent = initialize_agent(tools, llm, agent="zero-shot-react-description", verbose=True)

#agent workflow
import json
from datetime import datetime

# Sample email data
email_samples = [
    {
        "vendor_id": "vendor_001",
        "invoice_id": "invoice_001",
        "amount": 1000.50,
        "sender_email": "vendor001@example.com",
        "attachment": "PDF_BINARY_DATA"
    },
    {
        "vendor_id": "vendor_002",
        "invoice_id": "invoice_002",
        "amount": 200.75,
        "sender_email": "vendor002@example.com",
        "attachment": "PDF_BINARY_DATA"
    }
]

# Process each email with the agent
for email in email_samples:
    email["entered_date"] = datetime.now().isoformat()  # Add entered date to each email
    print("\nProcessing email...")
    result = agent.run(email)
    print(f"Result: {result}")





