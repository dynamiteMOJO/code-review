import sys
from pyspark.sql import SparkSession

def process_data():
    # 1. Hardcoded Secret (Should trigger Security Check)
    db_password = "my_secret_password_123"
    
    # 2. Print Statement (Should trigger Logger Warning)
    print(f"Connecting to DB with {db_password}")

    # 3. Hardcoded IP (Should trigger Config Warning)
    db_host = "192.168.1.15"
    
    spark = SparkSession.builder.appName("Test").getOrCreate()
    
    # 4. toPandas usage (Should trigger Performance Warning)
    df = spark.read.csv("data.csv")
    pdf = df.toPandas()
    
    if pdf.empty:
        # 5. sys.exit (Should trigger Exit Code Check)
        print("No data found")
        sys.exit(1)

    return pdf

if __name__ == "__main__":
    process_data()
