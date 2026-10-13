from flask import Flask, request, jsonify, render_template, redirect, session
import os
import joblib
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)

# Secret key for login sessions
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "voltai-local-development-key-change-this"
)

# Load trained ML model
model = joblib.load("models/electricity_bill_model.pkl")

# =========================================================
# DATABASE
# =========================================================

def get_db():
    return psycopg2.connect(
        os.environ.get("DATABASE_URL"),
        cursor_factory=RealDictCursor
    )


def create_database():
    conn = get_db()
    try:
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)

        # Keep the existing prediction history schema unchanged
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                prediction_date TIMESTAMP NOT NULL,
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
        cursor.close()
    finally:
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
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )
            user = cursor.fetchone()
            cursor.close()
        finally:
            conn.close()

        if user and check_password_hash(user["password"], password):
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

        if password != confirm_password:
            return render_template(
                "signup.html",
                error="Passwords do not match."
            )

        hashed_password = generate_password_hash(password)
        conn = None

        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (name, email, password)
                VALUES (%s, %s, %s)
                """,
                (name, email, hashed_password)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return redirect("/login")

        except psycopg2.IntegrityError:
            if conn is not None:
                conn.rollback()
                conn.close()

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
    if "user_id" not in session:
        return jsonify({"error": "Please login first."}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid or missing JSON request body."}), 400

    try:
        # -----------------------------------
        # ML MODEL INPUT
        # Keep these original model features unchanged
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

        prediction = float(model.predict(input_data)[0])


        print("\n========== VOLTAI DEBUG ==========")
        print("INPUT DATA:")
        print(input_data.to_string(index=False))
        print("MODEL PREDICTION:", prediction)
        print("==================================\n", flush=True)


        # -----------------------------------
        # APPLIANCE POWER VALUES (watts)
        # -----------------------------------
        appliance_power = {
            "Fan": 75,
            "Refrigerator": 150,
            "Air Conditioner": 1500,
            "Television": 100,
            "Monitor": 50,
            "Motor Pump": 750,
            "Smartphones": 10,
            "Laptops": 60,
            "Tablets": 15,
            "Smart TVs": 100,
            "Wi-Fi Routers": 10
        }

        # -----------------------------------
        # STANDARD APPLIANCES + GADGETS
        # -----------------------------------
        monthly_hours = float(data["MonthlyHours"])
        tariff_rate = float(data["TariffRate"])

        if monthly_hours < 0 or tariff_rate < 0:
            return jsonify({
                "error": "Monthly hours and tariff rate cannot be negative."
            }), 400

        appliance_counts = {
            "Fan": float(data["Fan"]),
            "Refrigerator": float(data["Refrigerator"]),
            "Air Conditioner": float(data["AirConditioner"]),
            "Television": float(data["Television"]),
            "Monitor": float(data["Monitor"]),
            "Motor Pump": float(data["MotorPump"]),
            "Smartphones": float(data.get("Smartphones", 0)),
            "Laptops": float(data.get("Laptops", 0)),
            "Tablets": float(data.get("Tablets", 0)),
            "Smart TVs": float(data.get("SmartTVs", 0)),
            "Wi-Fi Routers": float(data.get("WiFiRouters", 0))
        }

        for appliance, count in appliance_counts.items():
            if count < 0:
                return jsonify({
                    "error": f"The quantity for {appliance} cannot be negative."
            }), 400

        # Assumed monthly usage hours for gadgets
        gadget_hours = {
             "Smartphones": 120,
             "Laptops": 120,
             "Tablets": 60,
             "Smart TVs": 120,
             "Wi-Fi Routers": 720
        }

        energy_usage = {}
        for appliance, count in appliance_counts.items():
            power = appliance_power[appliance]
            hours = gadget_hours.get(appliance, monthly_hours)
            energy = (count * power * hours) / 1000
            energy_usage[appliance] = round(energy, 2)

        # -----------------------------------
        # USER-ADDED CUSTOM APPLIANCES
        # -----------------------------------
        custom_appliances = data.get("custom_appliances", [])

        if not isinstance(custom_appliances, list):
            return jsonify({
                "error": "custom_appliances must be a list."
            }), 400

        for item in custom_appliances:
            if not isinstance(item, dict):
                continue

            name = str(item.get("name", "")).strip()

            try:
                quantity = float(item.get("quantity", 0))
                watts = float(item.get("watts", 0))
                hours_per_day = float(item.get("hours_per_day", 0))

            except (TypeError, ValueError):
                continue

            # Ignore incomplete or invalid entries
            if (
                    not name
                    or quantity <= 0
                    or watts <= 0
                    or not 0 <= hours_per_day <= 24
            ):
                continue

            # Estimated monthly energy in kWh (30-day month)
            energy = quantity * watts * hours_per_day * 30 / 1000

            # Keep duplicate appliance names from overwriting each other
            display_name = name
            suffix = 2
            while display_name in energy_usage:
                display_name = f"{name} ({suffix})"
                suffix += 1

            energy_usage[display_name] = round(energy, 2)

        # -----------------------------------
        # TOTAL ENERGY + ESTIMATED COST
        # -----------------------------------
        total_energy = round(sum(energy_usage.values()), 2)
        estimated_appliance_cost = round(total_energy * tariff_rate, 2)

        # -----------------------------------
        # ENERGY PERCENTAGES
        # -----------------------------------
        if total_energy > 0:
            energy_percentages = {
                appliance: round((energy / total_energy) * 100, 1)
                for appliance, energy in energy_usage.items()
            }
        else:
            energy_percentages = {
                appliance: 0 for appliance in energy_usage
            }

        # -----------------------------------
        # HIGHEST ENERGY APPLIANCE
        # -----------------------------------
        highest_appliance = max(
            energy_usage,
            key=energy_usage.get,
            default="No appliance usage"
        )
        highest_energy = energy_usage.get(highest_appliance, 0)
        highest_percentage = energy_percentages.get(highest_appliance, 0)

        # -----------------------------------
        # PERSONALIZED RECOMMENDATIONS
        # -----------------------------------
        recommendations = []

        appliance_recommendations = {
            "Air Conditioner": {
                "icon": "❄️",
                "title": "Optimize AC Usage",
                "text": "Try maintaining your AC around 24–26°C and avoid unnecessary usage."
            },
            "Fan": {
                "icon": "🌀",
                "title": "Optimize Fan Usage",
                "text": "Turn off fans in unoccupied rooms and use appropriate speed settings."
            },
            "Refrigerator": {
                "icon": "🧊",
                "title": "Improve Refrigerator Efficiency",
                "text": "Avoid frequent door opening and ensure proper ventilation around your refrigerator."
            },
            "Television": {
                "icon": "📺",
                "title": "Reduce TV Usage",
                "text": "Switch off your television completely when it is not being used."
            },
            "Monitor": {
                "icon": "🖥️",
                "title": "Manage Monitor Usage",
                "text": "Turn off your monitor when it is not needed and enable automatic sleep settings."
            },
            "Motor Pump": {
                "icon": "💧",
                "title": "Optimize Motor Pump Usage",
                "text": "Avoid running the motor pump longer than necessary and check for leaks."
            }
        }

        if highest_appliance in appliance_recommendations:
            recommendations.append(
                appliance_recommendations[highest_appliance]
            )
        elif highest_energy > 0:
            recommendations.append({
                "icon": "⚡",
                "title": f"Optimize {highest_appliance} Usage",
                "text": (
                    f"{highest_appliance} is your highest estimated energy "
                    "consumer. Consider reducing unnecessary usage."
                )
            })

        recommendations.append({
            "icon": "📊",
            "title": "Monitor Your Monthly Usage",
            "text": (
                "Track your estimated monthly energy consumption and focus "
                "on reducing usage from your highest-energy appliances."
            )
        })

        # Household-aware recommendations
        def non_negative_int(value):
            try:
                return max(int(value or 0), 0)
            except (TypeError, ValueError):
                return 0

        family_size = non_negative_int(data.get("FamilySize", 0))
        adults = non_negative_int(data.get("Adults", 0))
        children = non_negative_int(data.get("Children", 0))
        senior_citizens = non_negative_int(data.get("SeniorCitizens", 0))

        if family_size > 0 and family_size != (
                adults + children + senior_citizens
        ):
            recommendations.append({
                "icon": "👨‍👩‍👧‍👦",
                "title": "Review Household Details",
                "text": (
                    "Your family size does not match the sum of adults, "
                    "children and senior citizens. Check your household details."
                )
            })

        if family_size > 0 and total_energy > 0:
            energy_per_person = total_energy / family_size
            recommendations.append({
                "icon": "🏠",
                "title": "Household Energy Insight",
                "text": (
                    f"Your estimated usage is {energy_per_person:.2f} kWh "
                    "per person per month."
                )
            })

        # -----------------------------------
        # SAVE PREDICTION HISTORY
        # Existing database columns and history behavior retained
        # -----------------------------------
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("""
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
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                session["user_id"],
                datetime.now(),
                data["Month"],
                data["City"],
                data["Company"],
                round(prediction, 2),
                total_energy,
                highest_appliance,
                highest_energy
            ))
            conn.commit()
            cursor.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        # -----------------------------------
        # SEND RESULT TO FRONTEND
        # -----------------------------------
        return jsonify({
            "predicted_bill": round(prediction, 2),
            "total_energy": total_energy,
            "estimated_appliance_cost": estimated_appliance_cost,
            "highest_appliance": highest_appliance,
            "highest_energy": highest_energy,
            "highest_percentage": highest_percentage,
            "energy_usage": energy_usage,
            "energy_percentages": energy_percentages,
            "recommendations": recommendations
        })
    except (KeyError, TypeError, ValueError) as error:
        return jsonify({
                    "error": f"Please check the submitted prediction values: {error}"
                }), 400

# =========================================================
# PREDICTION HISTORY
# =========================================================

@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    try:
        cursor = conn.cursor()

        cursor.execute("""
                   SELECT *
                   FROM predictions
                   WHERE user_id = %s
                   ORDER BY prediction_date DESC
               """, (session["user_id"],))
        predictions = cursor.fetchall()

        # Yearly summary
        cursor.execute("""
                   SELECT
                       EXTRACT(YEAR FROM prediction_date)::INTEGER AS year,
                       COUNT(*) AS predictions,
                       SUM(predicted_bill) AS total_bill,
                       AVG(predicted_bill) AS average_bill,
                       SUM(total_energy) AS total_energy
                   FROM predictions
                   WHERE user_id = %s
                   GROUP BY EXTRACT(YEAR FROM prediction_date)
                   ORDER BY year ASC
               """, (session["user_id"],))
        yearly_summary = cursor.fetchall()

        # Monthly summary
        cursor.execute("""
                   SELECT
                       EXTRACT(YEAR FROM prediction_date)::INTEGER AS year,
                       month AS month_number,
                       COUNT(*) AS predictions,
                       SUM(predicted_bill) AS total_bill,
                       AVG(predicted_bill) AS average_bill,
                       SUM(total_energy) AS total_energy
                   FROM predictions
                   WHERE user_id = %s
                   GROUP BY EXTRACT(YEAR FROM prediction_date), month
                   ORDER BY year ASC, month_number ASC
               """, (session["user_id"],))
        monthly_summary = cursor.fetchall()
    finally:
        conn.close()

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
        chart_months.append(month_names[month_number])
        monthly_bills.append(round(float(row["total_bill"] or 0), 2))

    chart_years = []
    yearly_bills = []

    for row in yearly_summary:
        chart_years.append(row["year"])
        yearly_bills.append(round(float(row["total_bill"] or 0), 2))

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
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT *
            FROM predictions
            WHERE user_id = %s
            ORDER BY month ASC
        """, (session["user_id"],))
        predictions = cursor.fetchall()
    finally:
        conn.close()

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

    bills = [float(p["predicted_bill"]) for p in predictions]
    energies = [float(p["total_energy"]) for p in predictions]

    total_predictions = len(predictions)
    total_bill = sum(bills)
    average_bill = total_bill / total_predictions
    highest_bill = max(bills)
    total_energy = sum(energies)

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
