import sqlite3
import os

# Build the path to the database file
db_path = os.path.join(os.path.dirname(__file__), '..', 'db.sqlite3')

def upgrade():
    """Adds the payment_capture_url column to the orders table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print("Adding 'payment_capture_url' column to 'orders' table...")
        cursor.execute("ALTER TABLE orders ADD COLUMN payment_capture_url TEXT")
        conn.commit()
        print("Column added successfully.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("Column 'payment_capture_url' already exists.")
        else:
            raise
    finally:
        conn.close()

def downgrade():
    """Removes the payment_capture_url column from the orders table."""
    # SQLite does not support dropping columns directly in a simple way.
    # This would require creating a new table and copying data.
    # For this case, we'll just print a message.
    print("Downgrade for this migration is not automatically supported in SQLite.")
    print("You would need to manually recreate the 'orders' table without the 'payment_capture_url' column.")

if __name__ == "__main__":
    # This allows running the script directly for testing or manual migration
    print("Running migration to add 'payment_capture_url'...")
    upgrade()
