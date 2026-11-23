
from sqlalchemy import create_engine, text
from config import Config

engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)

try:
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT DATABASE(), VERSION()")
        )

        database, version = result.fetchone()

        print("Connection successful!")
        print("Database:", database)
        print("MySQL version:", version)

except Exception as error:
    print("Connection failed:", error)

finally:
    engine.dispose()
