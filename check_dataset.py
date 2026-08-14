import pandas as pd

# Load dataset
df = pd.read_csv("dataset/electricity_bill_dataset.csv")

# Display first 5 rows
print("First 5 rows:")
print(df.head())

# Display column names
print("\nColumn names:")
print(df.columns.tolist())

# Display dataset shape
print("\nDataset shape:")
print(df.shape)

# Display data types
print("\nData types:")
print(df.dtypes)

# Check missing values
print("\nMissing values:")
print(df.isnull().sum())