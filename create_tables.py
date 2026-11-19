
from database import Base, engine
import models

def create_database():
    Base.metadata.create_all(bind=engine)
    print("Pillistan database created successfully!")
    print("Product table is ready.")
print("Supplier table is ready.")
print("Purchase table is ready.")
print("Purchase item table is ready.")
print("Supplier payment table is ready.")
if __name__ == "__main__":
    create_database()
