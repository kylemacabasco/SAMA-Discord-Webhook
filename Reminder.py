from dotenv import load_dotenv
import os
import requests
from datetime import datetime, timedelta

load_dotenv()

# Load environment variables
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DATABASE_ID = os.getenv("DATABASE_ID")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_USER_ID = os.getenv("DISCORD_USER_ID")

# Validate required environment variables
if not all([NOTION_API_KEY, DATABASE_ID, DISCORD_WEBHOOK_URL]):
    raise ValueError("Missing required environment variables. Please check your .env file.")

# Headers for Notion API
HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# Get today's date and 24 hours from now (using local timezone)
today = datetime.now().date()
tomorrow = today + timedelta(days=1)


def extract_task_name(props):
    """Extract task name from the 'Task' property"""
    task_prop = props.get("Task", {})
    
    if task_prop.get("title") and len(task_prop["title"]) > 0:
        first_block = task_prop["title"][0]
        if first_block.get("text", {}).get("content"):
            name = first_block["text"]["content"].strip()
            if name:
                return name
    
    return "Unnamed Task"


def extract_assigned_people(props):
    """Extract assigned people from the 'Assign' property (handles both people and multi_select types)"""
    assign_prop = props.get("Assign", {})
    assigned_names = []
    
    # Handle people property type
    if assign_prop.get("people") and isinstance(assign_prop["people"], list):
        for person in assign_prop["people"]:
            if person.get("name"):
                assigned_names.append(person["name"])
    
    # Handle multi_select property type (your case)
    elif assign_prop.get("multi_select") and isinstance(assign_prop["multi_select"], list):
        for option in assign_prop["multi_select"]:
            if option.get("name"):
                assigned_names.append(option["name"])
    
    return assigned_names


def extract_task_status(props):
    """Extract task status from the 'Status' property"""
    status_prop = props.get("Status", {})
    
    # Handle status property type (Notion's dedicated status property)
    if status_prop.get("status") and status_prop["status"].get("name"):
        return status_prop["status"]["name"]
    
    # Handle select property type (single select) - fallback
    elif status_prop.get("select") and status_prop["select"].get("name"):
        return status_prop["select"]["name"]
    
    # Handle multi_select property type (if Status is multi-select) - fallback
    elif status_prop.get("multi_select") and len(status_prop["multi_select"]) > 0:
        return status_prop["multi_select"][0].get("name")
    
    return None


def get_discord_user_id(name):
    """Map Notion names to Discord user IDs using environment variables"""
    # Convert name to environment variable format
    env_key = f"DISCORD_ID_{name.upper().replace(' ', '_')}"
    return os.getenv(env_key)


def send_discord_alert(task_name, due_date, assigned_people=None, is_overdue=False):
    # Build the message with assigned people info and Discord tags
    assigned_text = ""
    discord_tags = ""
    
    if assigned_people:
        # Show assigned people names
        if len(assigned_people) == 1:
            assigned_text = f" | Assigned to: **{assigned_people[0]}**"
        else:
            assigned_text = f" | Assigned to: **{', '.join(assigned_people)}**"
        
        # Create Discord tags for assigned people
        discord_mentions = []
        for person in assigned_people:
            discord_id = get_discord_user_id(person)
            if discord_id:
                discord_mentions.append(f"<@{discord_id}>")
        
        if discord_mentions:
            discord_tags = f" {' '.join(discord_mentions)}"
    
    # Different message format for overdue vs tomorrow reminders
    if is_overdue:
        message = {
            "content": f"🚨 **OVERDUE!** **{task_name}** was due on **{due_date}**{discord_tags}"
        }
    else:
        message = {
            "content": f"⏰ Reminder! **{task_name}** is due on **{due_date}** — that's tomorrow! {discord_tags}"
        }
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=message)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to send Discord alert: {e}")


def check_overdue_tasks():
    """Check for overdue tasks that are still 'To do' or 'In progress'"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    
    try:
        response = requests.post(url, headers=HEADERS)
        response.raise_for_status()
        
        results = response.json().get("results", [])
        overdue_count = 0

        for page in results:
            try:
                props = page["properties"]

                # Extract task info
                name = extract_task_name(props)
                assigned_people = extract_assigned_people(props)
                status = extract_task_status(props)
                
                # Check if task is overdue and still incomplete
                date_prop = props.get("Due Date", {}).get("date")
                if date_prop and date_prop.get("start"):
                    due_date = datetime.fromisoformat(date_prop["start"]).date()
                    
                    # Check if overdue and status is still "To do" or "In progress"
                    if (due_date < today and 
                        status and 
                        status in ["To do", "In progress"]):
                        
                        send_discord_alert(name, due_date, assigned_people, is_overdue=True)
                        overdue_count += 1
                        
            except (KeyError, IndexError, ValueError) as e:
                print(f"⚠️ Error processing overdue task: {e}")
                continue
                
        if overdue_count > 0:
            print(f"🚨 Found {overdue_count} overdue task(s)")
        else:
            print("✅ No overdue tasks found")
                
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to check overdue tasks: {e}")
    except Exception as e:
        print(f"❌ Unexpected error checking overdue tasks: {e}")


def check_due_tasks():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    
    try:
        response = requests.post(url, headers=HEADERS)
        response.raise_for_status()
        
        results = response.json().get("results", [])

        for page in results:
            try:
                props = page["properties"]

                # Extract task name and assigned people
                name = extract_task_name(props)
                assigned_people = extract_assigned_people(props)
                
                # Check due date
                date_prop = props.get("Due Date", {}).get("date")
                if date_prop and date_prop.get("start"):
                    due_date = datetime.fromisoformat(date_prop["start"]).date()
                    if due_date == tomorrow:
                        send_discord_alert(name, due_date, assigned_people)
                        
            except (KeyError, IndexError, ValueError) as e:
                print(f"⚠️ Error processing task: {e}")
                continue
                
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to connect to Notion API: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


# Run both functions
check_due_tasks()
check_overdue_tasks()
