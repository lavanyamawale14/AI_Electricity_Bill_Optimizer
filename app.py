from flask import Flask, request, jsonify, render_template, redirect, session
import joblib
import pandas as pd
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Secret key for login sessions
app.secret_key = "voltaI_secret_key_2026"

# Load trained ML model
model = joblib.load("models/electricity_bill_model.pkl")


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    return conn


def create_database():

    conn = get_db()

    # Users table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Prediction history table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            prediction_date TEXT NOT NULL,
            month INTEGER NOT NULL,
            city TEXT,
            company TEXT,
            predicted_bill REAL NOT NULL,
            total_energy REAL NOT NULL,
            highest_appliance TEXT,
            highest_energy REAL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


create_database()


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()

        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]

            return redirect("/")

        return render_template(
            "login.html",
            error="Invalid email or password."
        )

    return render_template("login.html")


# =========================================================
# SIGNUP
# =========================================================

@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # Check passwords
        if password != confirm_password:

            return render_template(
                "signup.html",
                error="Passwords do not match."
            )

        # Hash password
        hashed_password = generate_password_hash(password)

        try:

            conn = get_db()

            conn.execute(
                """
                INSERT INTO users
                (name, email, password)
                VALUES (?, ?, ?)
                """,
                (
                    name,
                    email,
                    hashed_password
                )
            )

            conn.commit()
            conn.close()

            return redirect("/login")

        except sqlite3.IntegrityError:

            return render_template(
                "signup.html",
                error="An account with this email already exists."
            )

    return render_template("signup.html")


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# =========================================================
# HOME / DASHBOARD
# =========================================================

@app.route("/")
def home():

    # User must be logged in
    if "user_id" not in session:
        return redirect("/login")

    return render_template(
        "index.html",
        user_name=session.get("user_name")
    )


# =========================================================
# PREDICTION
# =========================================================

@app.route("/predict", methods=["POST"])
def predict():

    # Protect prediction API
    if "user_id" not in session:
        return jsonify({
            "error": "Please login first."
        }), 401

    data = request.get_json()

    # -----------------------------------
    # ML MODEL INPUT
    # -----------------------------------

    input_data = pd.DataFrame([{
        "Fan": data["Fan"],
        "Refrigerator": data["Refrigerator"],
        "AirConditioner": data["AirConditioner"],
        "Television": data["Television"],
        "Monitor": data["Monitor"],
        "MotorPump": data["MotorPump"],
        "Month": data["Month"],
        "City": data["City"],
        "Company": data["Company"],
        "MonthlyHours": data["MonthlyHours"],
        "TariffRate": data["TariffRate"]
    }])

    # Predict electricity bill
    prediction = model.predict(input_data)[0]

    # -----------------------------------
    # APPLIANCE POWER VALUES
    # -----------------------------------

    appliance_power = {
        "Fan": 75,
        "Refrigerator": 150,
        "Air Conditioner": 1500,
        "Television": 100,
        "Monitor": 50,
        "Motor Pump": 750
    }

    # -----------------------------------
    # CALCULATE ESTIMATED ENERGY USAGE
    # -----------------------------------

    monthly_hours = float(data["MonthlyHours"])

    appliance_counts = {
        "Fan": float(data["Fan"]),
        "Refrigerator": float(data["Refrigerator"]),
        "Air Conditioner": float(data["AirConditioner"]),
        "Television": float(data["Television"]),
        "Monitor": float(data["Monitor"]),
        "Motor Pump": float(data["MotorPump"])
    }

    energy_usage = {}

    for appliance, count in appliance_counts.items():

        power = appliance_power[appliance]

        energy = (count * power * monthly_hours) / 1000

        energy_usage[appliance] = round(energy, 2)

    # -----------------------------------
    # TOTAL ENERGY
    # -----------------------------------

    total_energy = sum(energy_usage.values())

    # -----------------------------------
    # ENERGY PERCENTAGES
    # -----------------------------------

    if total_energy > 0:

        energy_percentages = {
            appliance: round(
                (energy / total_energy) * 100,
                1
            )
            for appliance, energy in energy_usage.items()
        }

    else:

        energy_percentages = {
            appliance: 0
            for appliance in energy_usage
        }

    # -----------------------------------
    # FIND HIGHEST ENERGY APPLIANCE
    # -----------------------------------

    highest_appliance = max(
        energy_usage,
        key=energy_usage.get
    )

    highest_energy = energy_usage[highest_appliance]

    highest_percentage = energy_percentages[highest_appliance]

    # -----------------------------------
    # PERSONALIZED RECOMMENDATIONS
    # -----------------------------------

    recommendations = []

    if highest_appliance == "Air Conditioner":

        recommendations.append({
            "icon": "❄️",
            "title": "Optimize AC Usage",
            "text": "Your air conditioner is your largest estimated energy consumer. Try maintaining the temperature around 24–26°C and avoid unnecessary usage."
        })

    elif highest_appliance == "Fan":

        recommendations.append({
            "icon": "🌀",
            "title": "Optimize Fan Usage",
            "text": "Fans are contributing significantly to your estimated usage. Turn them off when rooms are unoccupied and use appropriate speed settings."
        })

    elif highest_appliance == "Refrigerator":

        recommendations.append({
            "icon": "🧊",
            "title": "Improve Refrigerator Efficiency",
            "text": "Your refrigerator is a significant energy consumer. Avoid frequent door opening and ensure proper ventilation around the appliance."
        })

    elif highest_appliance == "Television":

        recommendations.append({
            "icon": "📺",
            "title": "Reduce TV Usage",
            "text": "Switch off your television completely when it is not being used instead of leaving it on standby."
        })

    elif highest_appliance == "Monitor":

        recommendations.append({
            "icon": "🖥️",
            "title": "Manage Monitor Usage",
            "text": "Turn off your monitor when it is not needed and enable automatic sleep settings."
        })

    elif highest_appliance == "Motor Pump":

        recommendations.append({
            "icon": "💧",
            "title": "Optimize Motor Pump Usage",
            "text": "Avoid running the motor pump longer than necessary and check for leakage or inefficient operation."
        })

    # General recommendation
    recommendations.append({
        "icon": "⚡",
        "title": "Monitor Your Monthly Usage",
        "text": "Keep track of your monthly electricity consumption and focus on reducing usage from your highest-energy appliances."
    })

    # -----------------------------------
    # SEND RESULT TO FRONTEND
    # -----------------------------------
    # -----------------------------------
    # SAVE PREDICTION HISTORY
    # -----------------------------------

    from datetime import datetime

    conn = get_db()

    conn.execute("""
        INSERT INTO predictions (
            user_id,
            prediction_date,
            month,
            city,
            company,
            predicted_bill,
            total_energy,
            highest_appliance,
            highest_energy
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        data["Month"],
        data["City"],
        data["Company"],
        round(float(prediction), 2),
        round(total_energy, 2),
        highest_appliance,
        highest_energy
    ))

    conn.commit()
    conn.close()
    return jsonify({

        "predicted_bill": round(
            float(prediction),
            2
        ),

        "total_energy": round(
            total_energy,
            2
        ),

        "highest_appliance": highest_appliance,

        "highest_energy": highest_energy,

        "highest_percentage": highest_percentage,

        "energy_usage": energy_usage,

        "energy_percentages": energy_percentages,

        "recommendations": recommendations

    })

# =========================================================
# PREDICTION HISTORY
# =========================================================
@app.route("/history")
def history():

    # User must be logged in
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()

    # =========================================
    # USER'S PREDICTION HISTORY
    # =========================================

    predictions = conn.execute("""
        SELECT *
        FROM predictions
        WHERE user_id = ?
        ORDER BY prediction_date DESC
    """, (session["user_id"],)).fetchall()


    # =========================================
    # YEARLY SUMMARY
    # =========================================

    yearly_summary = conn.execute("""
        SELECT
            strftime('%Y', prediction_date) AS year,
            COUNT(*) AS predictions,
            SUM(predicted_bill) AS total_bill,
            AVG(predicted_bill) AS average_bill,
            SUM(total_energy) AS total_energy
        FROM predictions
        WHERE user_id = ?
        GROUP BY strftime('%Y', prediction_date)
        ORDER BY year ASC
    """, (session["user_id"],)).fetchall()


    # =========================================
    # MONTHLY SUMMARY
    # =========================================

    # =========================================
    # MONTHLY SUMMARY
    # =========================================

    monthly_summary = conn.execute("""
        SELECT
            strftime('%Y', prediction_date) AS year,
            month AS month_number,
            COUNT(*) AS predictions,
            SUM(predicted_bill) AS total_bill,
            AVG(predicted_bill) AS average_bill,
            SUM(total_energy) AS total_energy
        FROM predictions
        WHERE user_id = ?
        GROUP BY strftime('%Y', prediction_date), month
        ORDER BY year ASC, month_number ASC
    """, (session["user_id"],)).fetchall()


    conn.close()


    # =========================================
    # CHART DATA
    # =========================================

    chart_months = []

    monthly_bills = []

    # =========================================
    # CHART DATA
    # =========================================

    month_names = {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December"
    }

    chart_months = []
    monthly_bills = []

    for row in monthly_summary:
        month_number = int(row["month_number"])

        chart_months.append(
            month_names[month_number]
        )

        monthly_bills.append(
            round(float(row["total_bill"]), 2)
        )


    chart_years = []

    yearly_bills = []

    for row in yearly_summary:

        chart_years.append(
            row["year"]
        )

        yearly_bills.append(
            round(float(row["total_bill"]), 2)
        )


    # =========================================
    # SEND EVERYTHING TO HISTORY.HTML
    # =========================================

    return render_template(

        "history.html",

        predictions=predictions,

        yearly_summary=yearly_summary,

        monthly_summary=monthly_summary,

        chart_months=chart_months,

        monthly_bills=monthly_bills,

        chart_years=chart_years,

        yearly_bills=yearly_bills,

        user_name=session.get("user_name")
    )

# =========================================================
# YEARLY SUMMARY
# =========================================================

@app.route("/summary")
def summary():

    # User must be logged in
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()

    predictions = conn.execute("""
        SELECT *
        FROM predictions
        WHERE user_id = ?
        ORDER BY month ASC
    """, (session["user_id"],)).fetchall()

    conn.close()

    # No predictions yet
    if not predictions:
        return render_template(
            "summary.html",
            user_name=session.get("user_name"),
            total_predictions=0,
            total_bill=0,
            average_bill=0,
            highest_bill=0,
            total_energy=0,
            monthly_data=[]
        )

    # Convert database rows
    bills = [
        float(p["predicted_bill"])
        for p in predictions
    ]

    energies = [
        float(p["total_energy"])
        for p in predictions
    ]

    # Basic statistics
    total_predictions = len(predictions)

    total_bill = sum(bills)

    average_bill = total_bill / total_predictions

    highest_bill = max(bills)

    total_energy = sum(energies)

    # Month names
    month_names = {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December"
    }

    # Month-wise data
    monthly_data = []

    for month_number in range(1, 13):

        month_predictions = [
            p for p in predictions
            if int(p["month"]) == month_number
        ]

        if month_predictions:

            month_bill = sum(
                float(p["predicted_bill"])
                for p in month_predictions
            )

            month_energy = sum(
                float(p["total_energy"])
                for p in month_predictions
            )

        else:

            month_bill = 0
            month_energy = 0

        monthly_data.append({
            "month": month_names[month_number],
            "bill": round(month_bill, 2),
            "energy": round(month_energy, 2)
        })

    return render_template(
        "summary.html",
        user_name=session.get("user_name"),
        total_predictions=total_predictions,
        total_bill=round(total_bill, 2),
        average_bill=round(average_bill, 2),
        highest_bill=round(highest_bill, 2),
        total_energy=round(total_energy, 2),
        monthly_data=monthly_data
    )
# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)