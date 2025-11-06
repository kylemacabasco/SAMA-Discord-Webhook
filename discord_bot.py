#!/usr/bin/env python3
"""
Discord Bot for Personal Task Reminders
Responds to commands like !kyle to show personalized task summaries
"""

import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import requests
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# Get environment variables
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DATABASE_ID = os.getenv("DATABASE_ID")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Get Discord ID mappings
DISCORD_ID_KYLE = os.getenv("DISCORD_ID_KYLE")
DISCORD_ID_GABRIEL = os.getenv("DISCORD_ID_GABRIEL")
DISCORD_ID_MELISSA = os.getenv("DISCORD_ID_MELISSA")
DISCORD_ID_KENNY = os.getenv("DISCORD_ID_KENNY")
DISCORD_ID_NIKKI = os.getenv("DISCORD_ID_NIKKI")

# Validate required environment variables
if not all([NOTION_API_KEY, DATABASE_ID, DISCORD_BOT_TOKEN]):
    raise ValueError("Missing required environment variables. Please check your .env file.")

# Create Discord ID to Notion name mapping
DISCORD_TO_NOTION = {}
if DISCORD_ID_KYLE:
    DISCORD_TO_NOTION[DISCORD_ID_KYLE] = "Kyle"
if DISCORD_ID_GABRIEL:
    DISCORD_TO_NOTION[DISCORD_ID_GABRIEL] = "Gabriel"
if DISCORD_ID_MELISSA:
    DISCORD_TO_NOTION[DISCORD_ID_MELISSA] = "Melissa"
if DISCORD_ID_KENNY:
    DISCORD_TO_NOTION[DISCORD_ID_KENNY] = "Kenny"
if DISCORD_ID_NIKKI:
    DISCORD_TO_NOTION[DISCORD_ID_NIKKI] = "Nikki"

# Headers for Notion API
HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# Get date ranges
today = datetime.now().date()
tomorrow = today + timedelta(days=1)
week_end = today + timedelta(days=7)

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


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


def get_user_tasks(person_name):
    """Get tasks for a specific person"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    
    try:
        response = requests.post(url, headers=HEADERS)
        response.raise_for_status()
        
        results = response.json().get("results", [])
        user_tasks = {
            "overdue": [],
            "due_this_week": [],
            "due_tomorrow": []
        }

        for page in results:
            try:
                props = page["properties"]

                # Extract task info
                name = extract_task_name(props)
                assigned_people = extract_assigned_people(props)
                status = extract_task_status(props)
                
                # Check if this person is assigned to the task
                if person_name.lower() not in [person.lower() for person in assigned_people]:
                    continue
                
                # Check due date
                date_prop = props.get("Due Date", {}).get("date")
                if date_prop and date_prop.get("start"):
                    due_date = datetime.fromisoformat(date_prop["start"]).date()
                    
                    task_info = {
                        "name": name,
                        "due_date": due_date,
                        "status": status,
                        "assigned_people": assigned_people
                    }
                    
                    # Categorize tasks
                    if due_date < today and status in ["To do", "In progress"]:
                        user_tasks["overdue"].append(task_info)
                    elif due_date == tomorrow:
                        user_tasks["due_tomorrow"].append(task_info)
                    elif today <= due_date <= week_end:
                        user_tasks["due_this_week"].append(task_info)
                        
            except (KeyError, IndexError, ValueError) as e:
                print(f"⚠️ Error processing task: {e}")
                continue
                
        return user_tasks
                
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to get user tasks: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None


def format_task_summary(discord_user, tasks):
    """Format task summary for Discord message"""
    user_mention = discord_user.mention
    
    if not tasks:
        return f"❌ Could not retrieve tasks for {user_mention}"
    
    # Count tasks
    overdue_count = len(tasks["overdue"])
    tomorrow_count = len(tasks["due_tomorrow"])
    week_count = len(tasks["due_this_week"])
    
    if overdue_count == 0 and tomorrow_count == 0 and week_count == 0:
        return f"✅ {user_mention} has no upcoming or overdue tasks!"
    
    # Build message
    message_parts = [f"📋 **Task Summary for {user_mention}**\n"]
    
    # Overdue tasks
    if overdue_count > 0:
        message_parts.append(f"🚨 **OVERDUE ({overdue_count})**")
        for task in tasks["overdue"][:5]:  # Limit to 5 tasks
            message_parts.append(f"• **{task['name']}** (due {task['due_date']}) - *{task['status']}*")
        if overdue_count > 5:
            message_parts.append(f"• ... and {overdue_count - 5} more overdue tasks")
        message_parts.append("")
    
    # Due tomorrow
    if tomorrow_count > 0:
        message_parts.append(f"⏰ **DUE TOMORROW ({tomorrow_count})**")
        for task in tasks["due_tomorrow"]:
            message_parts.append(f"• **{task['name']}** - *{task['status']}*")
        message_parts.append("")
    
    # Due this week
    if week_count > 0:
        message_parts.append(f"📅 **DUE THIS WEEK ({week_count})**")
        for task in tasks["due_this_week"][:5]:  # Limit to 5 tasks
            message_parts.append(f"• **{task['name']}** (due {task['due_date']}) - *{task['status']}*")
        if week_count > 5:
            message_parts.append(f"• ... and {week_count - 5} more tasks this week")
    
    return "\n".join(message_parts)


@bot.event
async def on_ready():
    print(f'✅ {bot.user} is now online!')
    print(f'📋 Ready to respond to personal task commands: !me, !tasks, !mytasks')
    print(f'👥 Registered users: {len(DISCORD_TO_NOTION)} ({", ".join(DISCORD_TO_NOTION.values())})')


@bot.event
async def on_command_error(ctx, error):
    """Suppress CommandNotFound errors for name commands"""
    if isinstance(error, commands.CommandNotFound):
        # Ignore CommandNotFound errors (these are expected for name commands)
        pass
    else:
        # Log other errors
        print(f"❌ Bot error: {error}")


@bot.event
async def on_message(message):
    # Don't respond to bot messages
    if message.author == bot.user:
        return
    
    # Check for personal task commands
    if message.content.lower() in ['!me', '!tasks', '!mytasks']:
        user_discord_id = str(message.author.id)
        
        # Look up user's Notion name
        notion_name = DISCORD_TO_NOTION.get(user_discord_id)
        
        if not notion_name:
            await message.channel.send("❌ You're not registered in the system. Contact an admin to add your Discord ID.")
            return
        
        # Send "typing" indicator
        async with message.channel.typing():
            # Get tasks for this person
            tasks = get_user_tasks(notion_name)
            
            # Format and send response
            response = format_task_summary(message.author, tasks)
            
            # Split long messages if needed (Discord has 2000 char limit)
            if len(response) > 2000:
                # Send in chunks
                chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                for chunk in chunks:
                    await message.channel.send(chunk)
            else:
                await message.channel.send(response)
    
    # Process other commands
    await bot.process_commands(message)


@bot.command(name='helpme')
async def tasks_help(ctx):
    """Show help information"""
    help_text = """
📋 **SAMA Task Bot Commands**

**Personal Task Summary:**
• `!me` - Show your personal tasks (overdue, tomorrow, this week)
• `!tasks` - Same as !me, show your tasks
• `!mytasks` - Same as !me, show your tasks

**Examples:**
• `!me` → Shows your task summary
• `!tasks` → Shows your task summary
• `!help` → Shows this help message

**Note:** You must be registered in the system to use this bot.
    """
    await ctx.send(help_text)


if __name__ == "__main__":
    print("Starting SAMA Task Bot...")
    bot.run(DISCORD_BOT_TOKEN)
