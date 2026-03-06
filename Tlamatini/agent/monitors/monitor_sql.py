import pyodbc
import time
import sys

# CONFIGURATION
# Windows typically uses the "ODBC Driver 17 for SQL Server"
# Ensure you have installed the driver from Microsoft.
CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;"      # OR IP address like 192.168.1.100
    "DATABASE=master;"
    "UID=WatcherUser;"       # The account doing the supervising
    "PWD=WatcherPassword;"
)

TARGET_ACCOUNT = "TheAccountToWatch"
CHECK_INTERVAL = 60  # Check every 60 seconds

def get_password_set_time(cursor, account_name):
    try:
        query = """
        SELECT LOGINPROPERTY(name, 'PasswordLastSetTime') as LastSet
        FROM sys.sql_logins 
        WHERE name = ?
        """
        cursor.execute(query, (account_name,))
        row = cursor.fetchone()
        if row:
            return row.LastSet
        return None
    except pyodbc.Error as e:
        print(f"SQL Error: {e}")
        return None

def main():
    # Force stdout to flush immediately so logs appear in real-time
    sys.stdout.reconfigure(line_buffering=True)
    print(f"Starting Windows SQL Monitor for: {TARGET_ACCOUNT}")
    
    last_known_time = None
    
    # Initial connection
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        last_known_time = get_password_set_time(cursor, TARGET_ACCOUNT)
        print(f"Baseline password time: {last_known_time}")
        conn.close()
    except Exception as e:
        print(f"Initial connection failed: {e}")
        # We don't exit; we let the loop retry in case server is starting up
    
    while True:
        try:
            conn = pyodbc.connect(CONN_STR)
            cursor = conn.cursor()
            
            current_set_time = get_password_set_time(cursor, TARGET_ACCOUNT)
            
            if current_set_time and last_known_time and current_set_time != last_known_time:
                print(f"[ALERT] Password changed! Old: {last_known_time}, New: {current_set_time}")
                # TODO: Add Windows Notification or Email Alert here
                
                last_known_time = current_set_time
            
            conn.close()
            
        except Exception as e:
            print(f"Error checking status: {e}")
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()