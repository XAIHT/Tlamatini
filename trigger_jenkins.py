import requests

# Configuration - REPLACE THESE WITH YOUR VALUES
JENKINS_URL = 'http://localhost:9090'
JOB_NAME = 'XHAAIT'
USER = 'blackangy'
# You can generate an API Token in Jenkins: User -> Configure -> API Token
API_TOKEN = '11f6f15329593aafc051150e725094a644' 

def trigger_build():
    # Construct the build URL
    # If your job has parameters, use /buildWithParameters instead of /build
    build_url = f"{JENKINS_URL}/job/{JOB_NAME}/build"
    
    auth = (USER, API_TOKEN)
    
    try:
        # First, try to get a CSRF crumb (required for most modern Jenkins setups)
        crumb_url = f"{JENKINS_URL}/crumbIssuer/api/json"
        crumb_response = requests.get(crumb_url, auth=auth)
        
        headers = {}
        if crumb_response.status_code == 200:
            crumb_data = crumb_response.json()
            headers[crumb_data['crumbRequestField']] = crumb_data['crumb']
            print("Successfully retrieved CSRF crumb.")
        else:
            print(f"Could not retrieve crumb (Status: {crumb_response.status_code}). Trying without...")

        # Trigger the build
        response = requests.post(build_url, auth=auth, headers=headers)
        
        if response.status_code in [200, 201]:
            print(f"Successfully triggered build for job '{JOB_NAME}'.")
        else:
            print(f"Failed to trigger build. Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    trigger_build()
