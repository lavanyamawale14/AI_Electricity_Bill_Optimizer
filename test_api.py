import requests

url = "http://127.0.0.1:5000/predict"

data = {
    "Fan": 10,
    "Refrigerator": 20,
    "AirConditioner": 2,
    "Television": 2,
    "Monitor": 1,
    "MotorPump": 1,
    "Month": 8,
    "City": "Mumbai",
    "Company": "Tata Power",
    "MonthlyHours": 400,
    "TariffRate": 8.5
}

response = requests.post(url, json=data)

print("Status Code:", response.status_code)
result = response.json()

print("Response:", result)

print("\nPredicted Bill:")
print("₹", result["predicted_bill"])

print("\nTotal Estimated Energy:")
print(result["total_energy"], "kWh")

print("\nHighest Energy Appliance:")
print(result["highest_appliance"])

print("\nHighest Energy:")
print(result["highest_energy"], "kWh")

print("\nEnergy Percentages:")
print(result["energy_percentages"])

print("\nRecommendations:")
for recommendation in result["recommendations"]:
    print("-", recommendation["title"])