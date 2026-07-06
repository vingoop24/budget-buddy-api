# Import FastAPI framework
from fastapi import FastAPI
from fastapi import UploadFile, File
import shutil
import os
from fastapi.responses import FileResponse
import pytesseract
from PIL import Image
import re
from openai import OpenAI
from dotenv import load_dotenv
import os
import base64
import json
load_dotenv()
from fastapi.middleware.cors import CORSMiddleware

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)
from database import create_db_and_tables, get_session

# Import tools for data validation
from pydantic import BaseModel
from typing import Optional
from sqlmodel import SQLModel, Field
class ChatRequest(BaseModel):
    question: str

# Create the FastAPI app
app = FastAPI()
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/test-openai")
def test_openai():
    return {
        "key_loaded": os.getenv("OPENAI_API_KEY") is not None
    }

def extract_receipt_with_ai(image_path):
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """
                Extract receipt information and return ONLY valid JSON:
                {
                    "merchant": "",
                    "amount": 0,
                    "currency": "",
                    "category": "",
                    "date": ""
                }
                """
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract the receipt data."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        temperature=0
    )

    result = response.choices[0].message.content

    # Clean OpenAI response in case it returns markdown formatting
    result = result.replace("```json", "").replace("```", "").strip()

    return json.loads(result)

# -----------------------------
# BASIC ROUTES
# -----------------------------

# Home route (what users see at base URL)
@app.get("/")
def home():
    return {"message": "Welcome to Budget Friend!"}

# Health check route
# Used to confirm backend is running
@app.get("/health")
def health_check():
    return {"status": "running"}

# About route
# Describes what this app does
@app.get("/about")
def about():
    return {
        "app": "Budget Friend",
        "nickname": "BF",
        "purpose": "AI budgeting assistant"
    }

# -----------------------------
# EXPENSE DATA MODEL
# -----------------------------

# Defines what an expense should look like
class Expense(BaseModel):
    id: Optional[int] = None              # Unique expense ID
    merchant: str                        # Real store/restaurant name
    charge_name: Optional[str] = None     # Name shown on bank statement
    amount: float                        # Amount spent
    currency: str = "USD"                # USD, EUR, GBP, etc.
    category: str                        # Food, Travel, Shopping, etc.
    date: str                            # Purchase date
    payment_method: Optional[str] = None  # Visa, Apple Pay, Cash, etc.
    receipt_image: Optional[str] = None   # Later: receipt photo path/link
    notes: Optional[str] = None           # Extra details

class ExpenseDB(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant: str
    charge_name: Optional[str] = None
    amount: float
    currency: str = "USD"
    category: str
    date: str
    payment_method: Optional[str] = None
    receipt_image: Optional[str] = None
    notes: Optional[str] = None
# Temporary storage
# Later this becomes a database
expenses = []
# Folder where uploaded receipt images will be stored
RECEIPT_FOLDER = "receipts"

# Create the receipts folder if it does not already exist
os.makedirs(RECEIPT_FOLDER, exist_ok=True)

monthly_budget = {"amount": 1500}

# -----------------------------
# EXPENSE ROUTES
# -----------------------------

# Add new expense
@app.post("/expenses")
def add_expense(expense: Expense):
    with get_session() as session:
        db_expense = ExpenseDB(
            merchant=expense.merchant,
            charge_name=expense.charge_name,
            amount=expense.amount,
            currency=expense.currency,
            category=expense.category,
            date=expense.date,
            payment_method=expense.payment_method,
            receipt_image=expense.receipt_image,
            notes=expense.notes
        )

        session.add(db_expense)
        session.commit()
        session.refresh(db_expense)

        return {
            "message": "Expense added successfully",
            "expense": db_expense
        }
# Get all expenses
@app.get("/expenses")
def get_expenses():
    with get_session() as session:
        expenses = session.query(ExpenseDB).all()
        return expenses

# Upload a receipt image and link it to an expense
@app.post("/expenses/{expense_id}/upload-receipt")
def upload_receipt(expense_id: int, receipt: UploadFile = File(...)):
    with get_session() as session:
        matching_expense = session.get(ExpenseDB, expense_id)

        if not matching_expense:
            return {"error": "Expense not found"}

        file_path = f"{RECEIPT_FOLDER}/expense_{expense_id}_{receipt.filename}"

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(receipt.file, buffer)

        matching_expense.receipt_image = file_path

        session.add(matching_expense)
        session.commit()
        session.refresh(matching_expense)

        return {
            "message": "Receipt uploaded and linked successfully",
            "expense_id": expense_id,
            "receipt_image": file_path,
            "expense": matching_expense
        }

@app.get("/expenses/{expense_id}/receipt")
def view_receipt(expense_id: int):
    with get_session() as session:
        matching_expense = session.get(ExpenseDB, expense_id)

        if not matching_expense:
            return {"error": "Expense not found"}

        if not matching_expense.receipt_image:
            return {"error": "No receipt linked to this expense"}

        return FileResponse(matching_expense.receipt_image)

# Scan receipt route
# Later this will use OCR/AI to read the receipt automatically
@app.post("/scan-receipt")
def scan_receipt(receipt: UploadFile = File(...)):
    # Save uploaded receipt image
    file_path = f"{RECEIPT_FOLDER}/scan_{receipt.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(receipt.file, buffer)

# OCR: read text from receipt image
    img = Image.open(file_path)

    # Convert to grayscale for better OCR
    img = img.convert("L")

    # Increase image size to help OCR read small text
    width, height = img.size
    img = img.resize((width * 2, height * 2))

    text = pytesseract.image_to_string(img)
    
    print("OCR TEXT:")
    print(text)

    # Extract merchant (first non-empty line)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    merchant = lines[0] if lines else "Unknown Merchant"

    # Extract all decimal numbers like 17.50
    amounts = re.findall(r'\d+\.\d{2}', text)
    amount = max([float(a) for a in amounts], default=0.0)

    extracted_data = {
        "merchant": merchant,
        "amount": amount,
        "currency": "EUR",
        "category": "Food / Drinks",
        "date": "Unknown",
        "receipt_image": file_path,
        "raw_text": text
    }

    return {
            "message": "Receipt scanned successfully",
            "extracted_data": extracted_data
        }

# Scan receipt and automatically save it as an expense
@app.post("/scan-and-save-receipt")
def scan_and_save_receipt(receipt: UploadFile = File(...)):
    # Save uploaded receipt image
    file_path = f"{RECEIPT_FOLDER}/scan_save_{receipt.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(receipt.file, buffer)

    # Use OpenAI Vision to extract receipt data
    ai_data = extract_receipt_with_ai(file_path)

    merchant = ai_data.get("merchant", "Unknown Merchant")
    amount = ai_data.get("amount", 0)
    currency = ai_data.get("currency", "EUR")
    category = ai_data.get("category", "Food / Drinks")
    date = ai_data.get("date", "Unknown")

    with get_session() as session:
        new_expense = ExpenseDB(
            merchant=merchant,
            charge_name=None,
            amount=amount,
            currency=currency,
            category=category,
            date=date,
            payment_method=None,
            receipt_image=file_path,
            notes="Created from AI receipt scan"
        )

        session.add(new_expense)
        session.commit()
        session.refresh(new_expense)

        return {
            "message": "Receipt scanned and saved as expense",
            "expense": new_expense,
            "ai_data": ai_data
        }

# Budget alert route
# Shows how close the user is to their monthly budget
@app.get("/budget-alert")
def budget_alert():
    total_spent = sum(expense.amount for expense in expenses)
    remaining = monthly_budget["amount"] - total_spent
    percent_used = (total_spent / monthly_budget["amount"]) * 100

    if percent_used >= 100:
        status = "Over budget"
        advice = "You have passed your monthly budget. Try to pause non-essential spending."
    elif percent_used >= 80:
        status = "Warning"
        advice = "You are close to your monthly budget. Be careful with extra purchases."
    elif percent_used >= 50:
        status = "Moderate"
        advice = "You are halfway through your budget. Keep tracking your spending."
    else:
        status = "Healthy"
        advice = "You are in a good budget range right now."

    return {
        "monthly_budget": monthly_budget["amount"],
        "total_spent": total_spent,
        "remaining": remaining,
        "percent_used": round(percent_used, 2),
        "status": status,
        "advice": advice
    }

@app.post("/set-budget")
def set_budget(amount: float):
    monthly_budget["amount"] = amount

    return {
        "message": "Budget updated successfully",
        "monthly_budget": monthly_budget["amount"]
    }

@app.get("/ai-insights")
def ai_insights():
    with get_session() as session:
        expenses = session.query(ExpenseDB).all()

    if not expenses:
        return {
            "message": "No expenses yet",
            "insights": []
        }

    total_spent = sum(expense.amount for expense in expenses)

    category_totals = {}
    for expense in expenses:
        category_totals[expense.category] = category_totals.get(expense.category, 0) + expense.amount

    top_category = max(category_totals, key=category_totals.get)
    top_category_amount = category_totals[top_category]

    remaining = monthly_budget["amount"] - total_spent
    percent_used = (total_spent / monthly_budget["amount"]) * 100

    insights = [
        f"Your highest spending category is {top_category} at {round(top_category_amount, 2)}.",
        f"You have spent {round(percent_used, 2)}% of your monthly budget.",
        f"You have {round(remaining, 2)} remaining this month."
    ]

    if percent_used >= 80:
        insights.append("You are getting close to your monthly limit. Consider slowing down non-essential spending.")

    return {
        "total_spent": round(total_spent, 2),
        "monthly_budget": monthly_budget["amount"],
        "remaining": round(remaining, 2),
        "category_totals": category_totals,
        "insights": insights,
        "recent_expenses": expenses[-5:][::-1],
    }
@app.post("/ai-assistant")
def ai_assistant(chat: ChatRequest):
    with get_session() as session:
        expenses = session.query(ExpenseDB).all()

    total_spent = sum(expense.amount for expense in expenses)
    remaining = monthly_budget["amount"] - total_spent

    expense_summary = [
        {
            "merchant": expense.merchant,
            "amount": expense.amount,
            "currency": expense.currency,
            "category": expense.category,
            "date": expense.date,
        }
        for expense in expenses[-10:]
    ]

    prompt = f"""
You are Budget Buddy, a helpful financial assistant for a personal budgeting app.

User budget:
- Monthly budget: {monthly_budget["amount"]}
- Total spent: {round(total_spent, 2)}
- Remaining: {round(remaining, 2)}

Recent expenses:
{expense_summary}

User question:
{chat.question}

Answer clearly, briefly, and practically. Do not give investment, tax, or legal advice.
"""

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a friendly budgeting assistant."},
            {"role": "user", "content": prompt},
        ],
    )

    response = completion.choices[0].message.content

    return {
        "question": chat.question,
        "response": response
    }

@app.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int):
    with get_session() as session:
        expense = session.get(ExpenseDB, expense_id)

        if not expense:
            return {"error": "Expense not found"}

        session.delete(expense)
        session.commit()

        return {
            "message": "Expense deleted successfully",
            "expense_id": expense_id
        }

# -----------------------------
# BUDGET CALCULATIONS
# -----------------------------

# Budget summary route
@app.get("/budget-summary")
def budget_summary():
    budget_amount = monthly_budget["amount"]

    # Add all expense amounts
    total_spent = sum(expense.amount for expense in expenses)

    # Calculate remaining budget
    remaining = monthly_budget - total_spent

    return {
        "monthly_budget": budget_amount,
        "total_spent": total_spent,
        "remaining": remaining
    }

# Category summary route
# Shows how much the user spent in each category
@app.get("/category-summary")
def category_summary():
    category_totals = {}

    for expense in expenses:
        category = expense.category

        if category not in category_totals:
            category_totals[category] = 0

        category_totals[category] += expense.amount

    return {
        "category_totals": category_totals
    }
