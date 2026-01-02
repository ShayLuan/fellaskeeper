from datetime import date, timedelta, datetime
import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DB_URL = os.getenv("DB_URL")

def get_db_connection():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

def get_user_goals_mapping(user_id):
    """Get user's goals and create a mapping from display number (1, 2, 3...) to database ID.
    Returns a tuple: (list of goal rows, mapping dict where key=display_num, value=db_id)"""
    try:
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, description, progress, total FROM goals WHERE user_id = %s ORDER BY id",
                    (user_id,)
                )
                rows = cursor.fetchall()
        connection.close()
        
        # Create mapping: display number (1-indexed) -> database ID
        mapping = {}
        for idx, row in enumerate(rows, start=1):
            mapping[idx] = row['id']
        
        return rows, mapping
    except Exception as e:
        print(f"Error getting user goals mapping: {e}")
        return [], {}

def get_user_habits_mapping(user_id):
    """Get user's habits and create a mapping from display number (1, 2, 3...) to database ID.
    Returns a tuple: (list of habit rows, mapping dict where key=display_num, value=db_id)"""
    try:
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, description, reset_period FROM habits WHERE user_id = %s ORDER BY id",
                    (user_id,)
                )
                rows = cursor.fetchall()
        connection.close()
        
        # Create mapping: display number (1-indexed) -> database ID
        mapping = {}
        for idx, row in enumerate(rows, start=1):
            mapping[idx] = row['id']
        
        return rows, mapping
    except Exception as e:
        print(f"Error getting user habits mapping: {e}")
        return [], {}

def get_current_period_start(reset_period, target_date):
    """Returns the start date of the current period for a given reset period and target date.
    - Daily: returns the target_date itself
    - Weekly: returns the Monday of the week containing target_date
    - Monthly: returns the 1st of the month containing target_date"""
    if reset_period == 'daily':
        return target_date
    elif reset_period == 'weekly':
        # Get Monday of the week (weekday() returns 0=Monday, 6=Sunday)
        days_since_monday = target_date.weekday()
        return target_date - timedelta(days=days_since_monday)
    elif reset_period == 'monthly':
        # Return the 1st of the month
        return date(target_date.year, target_date.month, 1)
    else:
        return target_date

def is_habit_completed_in_period(user_id, habit_id, reset_period, target_date):
    """Checks if habit is completed for the current period.
    Returns True if there's a completion record within the current period."""
    try:
        period_start = get_current_period_start(reset_period, target_date)
        
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                if reset_period == 'daily':
                    # For daily, check if completed on the exact date
                    cursor.execute(
                        "SELECT id FROM habit_completions WHERE user_id = %s AND habit_id = %s AND date = %s",
                        (user_id, habit_id, period_start)
                    )
                elif reset_period == 'weekly':
                    # For weekly, check if completed any day from Monday to Sunday
                    period_end = period_start + timedelta(days=6)
                    cursor.execute(
                        "SELECT id FROM habit_completions WHERE user_id = %s AND habit_id = %s AND date >= %s AND date <= %s",
                        (user_id, habit_id, period_start, period_end)
                    )
                else:  # monthly
                    # For monthly, check if completed any day in the month
                    if period_start.month == 12:
                        period_end = date(period_start.year + 1, 1, 1) - timedelta(days=1)
                    else:
                        period_end = date(period_start.year, period_start.month + 1, 1) - timedelta(days=1)
                    cursor.execute(
                        "SELECT id FROM habit_completions WHERE user_id = %s AND habit_id = %s AND date >= %s AND date <= %s",
                        (user_id, habit_id, period_start, period_end)
                    )
                result = cursor.fetchone()
        connection.close()
        return result is not None
    except Exception as e:
        print(f"Error checking habit completion: {e}")
        return False

# intents
intents = discord.Intents.default() 
intents.message_content = True  # needed to read messages
intents.members = True  # needed to see who joins/leaves

# command prefix
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Dictionary to store user goals
goals = {}

# Emojis for daily check-in ratings
mood_colors = {
    1: "🔴",  # terrible
    2: "🟠",  # bad
    3: "🟡",  # okay
    4: "🟢",  # good
    5: "🔵",  # amazing
    None: "⚪"  # no rating
}

# date and time helpers
today = date.today()
year = date.today().year
start_date = date(year, 1, 1)
end_date = date(year, 12, 31)

# Event: bot is ready
@bot.event
async def on_ready():
    print(f"Successfully logged in as {bot.user.name} ☑️")
    print("------")
    print("No need to wait for the New Year or tomorrow. Today is ready.")
    await bot.change_presence(activity=discord.Game(name="locked in an Adderall frenzy"))

# simple test command
@bot.command()
async def fellashelp(ctx):
    """Show the help menu"""
    await ctx.send("```" + "Commands:\n" + 
    "!fellashelp - Show the help menu\n" + 
    "!fellasping - Check if the bot is responsive\n" +
    "\n--- Goals ---\n" +
    "!goal <goal> <number> - Set a new goal\n" +
    "!mygoals - List all your goals\n" +
    "\n!updategoal <goal_number> <progress_increment> - Update progress on a goal\n" +
    "\tMake sure to check out your goal number with !mygoals first before updating\n" +
    "!delete <goal_number> - Delete a goal by its number\n" + 
    "\n--- Habits ---\n" +
    "!daily \"description\" [done] - Create or mark daily habit\n" +
    "!weekly \"description\" [done] - Create or mark weekly habit\n" +
    "!monthly \"description\" [done] - Create or mark monthly habit\n" +
    "!myhabits - List all your habits\n" +
    "!deletehabit <habit_number> - Delete a habit\n" +
    "!myhabityear <habit_number> - View habit progress for the year\n" +
    "\n--- Check-ins ---\n" +
    "!checkin <rating> - Rate your day from 1 (terrible) 🤢 to 5 (amazing) 🤩\n" +
    "!updatecheckin <rating> - Update today's check-in rating\n" +
    "!streak - Display your current and longest check-in streak\n" +
    "!myyear - Display your daily check-in ratings for the year\n" +
    "```")

@bot.command()
async def fellasping(ctx):
    """Pong! Check if the bot is responsive."""
    # 'ctx' is the "context" - contains message, author, channel, guild info
    await ctx.send(f'🏓 Pong! Latency: {round(bot.latency * 1000)}ms') # sends a message to the channel

@bot.command()
async def goal(ctx, *, goal_and_number):
    """Set a new goal.
    Usage: !goal <goal> <number>"""
    try:
        description, number = goal_and_number.rsplit(" ", 1)
        number = int(number) 
    except Exception:
        await ctx.send("❌ Invalid goal format. Please use !goal <goal> <number>")
        return
    
    user_id = ctx.author.id
    try:
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO goals (user_id, description, total) VALUES (%s, %s, %s)",
                    (user_id, description, number)
                )
        connection.close()
        await ctx.send(f"Goal set ✅ ***{description}***.\nCurrently at 0/{number}. Let's friggin' go! 💪")
    except Exception as e:
        await ctx.send("❌ Failed to set goal. Please contact the bot admin.")
        print(f"Error setting goal: {e}")

@bot.command()
async def mygoals(ctx):
    """List all goals by user_id from the database."""
    user_id = ctx.author.id
    try:
        rows, mapping = get_user_goals_mapping(user_id)

        if not rows:
            await ctx.send("You haven't set any goals yet.\n User !goal <goal> <number> to set one! 🚀")
            return
        
        msg = "**YOUR GOALS:**\n"
        for display_num, row in enumerate(rows, start=1):
            msg += f"- {display_num} - {row['description'].strip('\"')}: {row['progress']}/{row['total']}\n"
        await ctx.send(msg)
    except Exception as e:
        await ctx.send("❌ Failed to retrieve goals. Please contact the bot admin.")
        print(f"Error retrieving goals: {e}")

@bot.command()
async def delete(ctx, *, id: int):
    """Delete a goal by its display number. Usage: !delete <goal_number>
    Make sure user can only delete their own goals."""
    user_id = ctx.author.id
    try:
        # Get the mapping to translate display number to database ID
        rows, mapping = get_user_goals_mapping(user_id)
        
        if id not in mapping:
            await ctx.send(f"❌ Goal number {id} not found. Use !mygoals to see your goals.")
            return
        
        # Get the actual database ID from the mapping
        db_id = mapping[id]
        
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM goals WHERE id = %s AND user_id = %s RETURNING id;",
                    (db_id, user_id)
                )
                deleted = cursor.fetchone()
        connection.close()

        if deleted:
            await ctx.send(f"Goal number {id} deleted successfully ✅")
        else:
            await ctx.send("❌ Goal not found or it's not your goal.")
    except Exception as e:
        await ctx.send("❌ Failed to delete goal. Please contact the bot admin.")
        print(f"Error deleting goal: {e}")

@bot.command()
async def updategoal(ctx, *, id_and_progress):
    """Update progress on a goal. 
    Make sure to check your goal number with **!mygoals** first.
    Usage: !updategoal <goal_number> <progress_increment>"""
    try:
        id_str, progress_str = id_and_progress.rsplit(" ", 1)
        id = int(id_str)
        progress_increment = int(progress_str)
    except Exception:
        await ctx.send("❌ Invalid format. Please use **!updategoal <goal_number> <progress_increment>**")
        return
    
    user_id = ctx.author.id
    try:
        # Get the mapping to translate display number to database ID
        rows, mapping = get_user_goals_mapping(user_id)
        
        if id not in mapping:
            await ctx.send(f"❌ Goal number {id} not found. Use **!mygoals** to see your goals.")
            return
        
        # Get the actual database ID from the mapping
        db_id = mapping[id]
        
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                # Update the goal's progress
                cursor.execute(
                    "UPDATE goals SET progress = LEAST(progress + %s, total) WHERE id = %s AND user_id = %s RETURNING progress, total;",
                    (progress_increment, db_id, user_id)
                )
                updated = cursor.fetchone()
        connection.close()

        # Progress bar
        progress = updated['progress']
        total = updated['total']
        bar_length = 20
        filled_length = int(bar_length * progress // total) if total > 0 else 0
        bar = "█" * filled_length + "░" * (bar_length - filled_length)

        # Percentage completion
        percentage = (progress / total) * 100 if total > 0 else 0

        if updated:
            await ctx.send(f"Goal number {id} updated successfully ✅ Current progress: {updated['progress']}/{updated['total']}\n{bar} {percentage:.1f}% done")
        else:
            await ctx.send("❌ Goal not found or it's not your goal.")
    except Exception as e:
        await ctx.send("❌ Failed to update goal. Please contact the bot admin.")
        print(f"Error updating goal: {e}")

@bot.command()
async def daily(ctx, *, description_and_done=None):
    """Create or mark a daily habit as done.
    Usage: !daily "description" [done]"""
    if not description_and_done:
        await ctx.send("❌ Please provide a habit description. Usage: **!daily \"description\" [done]**")
        return
    
    # Parse description and optional "done" keyword
    description_and_done = description_and_done.strip()
    mark_done = False
    if description_and_done.lower().endswith(" done"):
        description = description_and_done[:-5].strip().strip('"').strip("'")
        mark_done = True
    else:
        description = description_and_done.strip('"').strip("'")
    
    if not description:
        await ctx.send("❌ Please provide a habit description. Usage: **!daily \"description\" [done]**")
        return
    
    user_id = ctx.author.id
    today = date.today()
    
    try:
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                # Check if habit exists
                cursor.execute(
                    "SELECT id FROM habits WHERE user_id = %s AND description = %s AND reset_period = 'daily'",
                    (user_id, description)
                )
                existing_habit = cursor.fetchone()
                
                habit_id = None
                if existing_habit:
                    habit_id = existing_habit['id']
                else:
                    # Create new habit
                    cursor.execute(
                        "INSERT INTO habits (user_id, description, reset_period) VALUES (%s, %s, 'daily') RETURNING id",
                        (user_id, description)
                    )
                    habit_id = cursor.fetchone()['id']
                
                # Mark as done if requested
                if mark_done:
                    # Check if already completed today
                    cursor.execute(
                        "SELECT id FROM habit_completions WHERE user_id = %s AND habit_id = %s AND date = %s",
                        (user_id, habit_id, today)
                    )
                    already_done = cursor.fetchone()
                    
                    if not already_done:
                        cursor.execute(
                            "INSERT INTO habit_completions (user_id, habit_id, date) VALUES (%s, %s, %s)",
                            (user_id, habit_id, today)
                        )
                        await ctx.send(f"✅ Daily habit **{description}** marked as done for today!")
                    else:
                        await ctx.send(f"✅ Daily habit **{description}** was already marked as done for today!")
                else:
                    if existing_habit:
                        await ctx.send(f"Daily habit **{description}** already exists 🤪 Add 'done' to mark it as completed for today.")
                    else:
                        await ctx.send(f"Daily habit **{description}** created 🤩 Use **!daily \"{description}\" done** to mark it as completed.")
        connection.close()
    except Exception as e:
        await ctx.send("❌ Failed to process daily habit. Please contact the bot admin.")
        print(f"Error processing daily habit: {e}")

@bot.command()
async def weekly(ctx, *, description_and_done=None):
    """Create or mark a weekly habit as done.
    Usage: !weekly "description" [done]"""
    if not description_and_done:
        await ctx.send("❌ Please provide a habit description. Usage: **!weekly \"description\" [done]**")
        return
    
    # Parse description and optional "done" keyword
    description_and_done = description_and_done.strip()
    mark_done = False
    if description_and_done.lower().endswith(" done"):
        description = description_and_done[:-5].strip().strip('"').strip("'")
        mark_done = True
    else:
        description = description_and_done.strip('"').strip("'")
    
    if not description:
        await ctx.send("❌ Please provide a habit description. Usage: **!weekly \"description\" [done]**")
        return
    
    user_id = ctx.author.id
    today = date.today()
    
    try:
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                # Check if habit exists
                cursor.execute(
                    "SELECT id FROM habits WHERE user_id = %s AND description = %s AND reset_period = 'weekly'",
                    (user_id, description)
                )
                existing_habit = cursor.fetchone()
                
                habit_id = None
                if existing_habit:
                    habit_id = existing_habit['id']
                else:
                    # Create new habit
                    cursor.execute(
                        "INSERT INTO habits (user_id, description, reset_period) VALUES (%s, %s, 'weekly') RETURNING id",
                        (user_id, description)
                    )
                    habit_id = cursor.fetchone()['id']
                
                # Mark as done if requested
                if mark_done:
                    # Check if already completed this week
                    period_start = get_current_period_start('weekly', today)
                    period_end = period_start + timedelta(days=6)
                    cursor.execute(
                        "SELECT id FROM habit_completions WHERE user_id = %s AND habit_id = %s AND date >= %s AND date <= %s",
                        (user_id, habit_id, period_start, period_end)
                    )
                    already_done = cursor.fetchone()
                    
                    if not already_done:
                        cursor.execute(
                            "INSERT INTO habit_completions (user_id, habit_id, date) VALUES (%s, %s, %s)",
                            (user_id, habit_id, today)
                        )
                        await ctx.send(f"✅ Weekly habit **{description}** marked as done for this week!")
                    else:
                        await ctx.send(f"✅ Weekly habit **{description}** was already marked as done for this week!")
                else:
                    if existing_habit:
                        await ctx.send(f"Weekly habit **{description}** already exists. Add 'done' to mark it as completed for this week.")
                    else:
                        await ctx.send(f"Weekly habit **{description}** created! Use **!weekly \"{description}\" done** to mark it as completed.")
        connection.close()
    except Exception as e:
        await ctx.send("❌ Failed to process weekly habit. Please contact the bot admin.")
        print(f"Error processing weekly habit: {e}")

@bot.command()
async def monthly(ctx, *, description_and_done=None):
    """Create or mark a monthly habit as done.
    Usage: !monthly "description" [done]"""
    if not description_and_done:
        await ctx.send("❌ Please provide a habit description. Usage: **!monthly \"description\" [done]**")
        return
    
    # Parse description and optional "done" keyword
    description_and_done = description_and_done.strip()
    mark_done = False
    if description_and_done.lower().endswith(" done"):
        description = description_and_done[:-5].strip().strip('"').strip("'")
        mark_done = True
    else:
        description = description_and_done.strip('"').strip("'")
    
    if not description:
        await ctx.send("❌ Please provide a habit description. Usage: **!monthly \"description\" [done]**")
        return
    
    user_id = ctx.author.id
    today = date.today()
    
    try:
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                # Check if habit exists
                cursor.execute(
                    "SELECT id FROM habits WHERE user_id = %s AND description = %s AND reset_period = 'monthly'",
                    (user_id, description)
                )
                existing_habit = cursor.fetchone()
                
                habit_id = None
                if existing_habit:
                    habit_id = existing_habit['id']
                else:
                    # Create new habit
                    cursor.execute(
                        "INSERT INTO habits (user_id, description, reset_period) VALUES (%s, %s, 'monthly') RETURNING id",
                        (user_id, description)
                    )
                    habit_id = cursor.fetchone()['id']
                
                # Mark as done if requested
                if mark_done:
                    # Check if already completed this month
                    period_start = get_current_period_start('monthly', today)
                    if period_start.month == 12:
                        period_end = date(period_start.year + 1, 1, 1) - timedelta(days=1)
                    else:
                        period_end = date(period_start.year, period_start.month + 1, 1) - timedelta(days=1)
                    cursor.execute(
                        "SELECT id FROM habit_completions WHERE user_id = %s AND habit_id = %s AND date >= %s AND date <= %s",
                        (user_id, habit_id, period_start, period_end)
                    )
                    already_done = cursor.fetchone()
                    
                    if not already_done:
                        cursor.execute(
                            "INSERT INTO habit_completions (user_id, habit_id, date) VALUES (%s, %s, %s)",
                            (user_id, habit_id, today)
                        )
                        await ctx.send(f"✅ Monthly habit **{description}** marked as done for this month!")
                    else:
                        await ctx.send(f"✅ Monthly habit **{description}** was already marked as done for this month!")
                else:
                    if existing_habit:
                        await ctx.send(f"Monthly habit **{description}** already exists. Add 'done' to mark it as completed for this month.")
                    else:
                        await ctx.send(f"Monthly habit **{description}** created! Use **!monthly \"{description}\" done** to mark it as completed.")
        connection.close()
    except Exception as e:
        await ctx.send("❌ Failed to process monthly habit. Please contact the bot admin.")
        print(f"Error processing monthly habit: {e}")

@bot.command()
async def myhabits(ctx):
    """List all user's habits with current period completion status."""
    user_id = ctx.author.id
    today = date.today()
    try:
        rows, mapping = get_user_habits_mapping(user_id)

        if not rows:
            await ctx.send("You haven't set any habits yet.\nUse **!daily**, **!weekly**, or **!monthly** to create one! 🚀")
            return
        
        msg = "**YOUR HABITS:**\n"
        for display_num, row in enumerate(rows, start=1):
            description = row['description'].strip('"')
            reset_period = row['reset_period']
            habit_id = row['id']
            
            # Check if completed in current period
            is_completed = is_habit_completed_in_period(user_id, habit_id, reset_period, today)
            status = "✅ Completed" if is_completed else "❌ Not completed"
            
            period_label = reset_period.capitalize()
            msg += f"- {display_num} - {description} ({period_label}) - {status}\n"
        await ctx.send(msg)
    except Exception as e:
        await ctx.send("❌ Failed to retrieve habits. Please contact the bot admin.")
        print(f"Error retrieving habits: {e}")

@bot.command()
async def deletehabit(ctx, habit_number: int):
    """Delete a habit by its display number. Usage: !deletehabit <habit_number>"""
    user_id = ctx.author.id
    try:
        # Get the mapping to translate display number to database ID
        rows, mapping = get_user_habits_mapping(user_id)
        
        if habit_number not in mapping:
            await ctx.send(f"❌ Habit number {habit_number} not found. Use **!myhabits** to see your habits.")
            return
        
        # Get the actual database ID from the mapping
        db_id = mapping[habit_number]
        
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM habits WHERE id = %s AND user_id = %s RETURNING id;",
                    (db_id, user_id)
                )
                deleted = cursor.fetchone()
        connection.close()

        if deleted:
            await ctx.send(f"Habit number {habit_number} deleted successfully ✅")
        else:
            await ctx.send("❌ Habit not found or it's not your habit.")
    except Exception as e:
        await ctx.send("❌ Failed to delete habit. Please contact the bot admin.")
        print(f"Error deleting habit: {e}")

@bot.command()
async def myhabityear(ctx, habit_number: int):
    """Display year view for a specific habit showing completed days.
    Usage: !myhabityear <habit_number>"""
    user_id = ctx.author.id
    try:
        # Get the mapping to translate display number to database ID
        rows, mapping = get_user_habits_mapping(user_id)
        
        if habit_number not in mapping:
            await ctx.send(f"❌ Habit number {habit_number} not found. Use **!myhabits** to see your habits.")
            return
        
        # Get the actual database ID from the mapping
        db_id = mapping[habit_number]
        
        # Get habit description
        habit_description = None
        for row in rows:
            if row['id'] == db_id:
                habit_description = row['description'].strip('"')
                break
        
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                # Get all completions for this habit in the current year
                cursor.execute(
                    "SELECT date FROM habit_completions WHERE user_id = %s AND habit_id = %s AND date >= %s AND date <= %s ORDER BY date",
                    (user_id, db_id, start_date, end_date)
                )
                rows = cursor.fetchall()
        connection.close()

        if not rows:
            await ctx.send(f"You haven't completed **{habit_description}** yet this year. Start tracking your progress! ☑️")
            return

        # Map completion dates
        completed_dates = set()
        for row in rows:
            completion_date = row['date']
            if isinstance(completion_date, str):
                completion_date = datetime.strptime(completion_date, '%Y-%m-%d').date()
            completed_dates.add(completion_date)
        
        msg = f"**{habit_description}** - Your year so far:\n"
        current_date = start_date

        for week in range(27):  # 26 rows for weeks + 1 day for 365 days total
            row = ""
            # first 7 days
            for i in range(7):
                if current_date > end_date:
                    break
                if current_date in completed_dates:
                    row += "🟢"  # Completed
                else:
                    row += "⚪"  # Not completed
                current_date += timedelta(days=1)
            row += "\t"
            # next 7 days
            for i in range(7):
                if current_date > end_date:
                    break
                if current_date in completed_dates:
                    row += "🟢"  # Completed
                else:
                    row += "⚪"  # Not completed
                current_date += timedelta(days=1)               
            msg += row + "\n"
            if current_date > end_date:
                break    
        await ctx.send(msg)
    except Exception as e:
        await ctx.send("❌ Failed to retrieve habit year view. Please contact the bot admin.")
        print(f"Error retrieving habit year view: {e}")

async def get_streak(user_id):
    """Calculate current and longest check-in streak for a user."""
    today = date.today()
    try:
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT DISTINCT date FROM checkins WHERE user_id = %s ORDER BY date ASC",
                    (user_id,)
                )
                rows = cursor.fetchall()
        connection.close()

        if not rows:
            return 0, 0

        # Convert dates to a sorted list of date objects
        dates = []
        for row in rows:
            checkin_date = row['date']
            if isinstance(checkin_date, str):
                checkin_date = datetime.strptime(checkin_date, '%Y-%m-%d').date()
            dates.append(checkin_date)

        # Calculate longest streak
        longest_streak = 1
        streak = 1
        for i in range(1, len(dates)):
            if (dates[i] - dates[i-1]).days == 1:
                streak += 1
                if streak > longest_streak:
                    longest_streak = streak
            else:
                streak = 1

        # Calculate current streak (how many days up to today)
        current_streak = 0
        current_date = today
        i = len(dates) - 1
        while i >= 0 and dates[i] == current_date:
            current_streak += 1
            current_date -= timedelta(days=1)
            i -= 1

        return current_streak, longest_streak
    except Exception as e:
        print(f"Error retrieving check-in streak: {e}")
        return 0, 0


@bot.command()
async def checkin(ctx, *, rating: int):
    """User rates their day on a scale from 1 to 5. Usage: !checkin <rating>
    1 = terrible, 5 = amazing"""
    if rating < 1 or rating > 5:
        await ctx.send("❌This is an invalid rating. Between 1 and 5, fam.")
        return
    
    user_id = ctx.author.id
    try:
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                # Check if user already checked in today
                cursor.execute(
                    "SELECT user_id FROM checkins WHERE user_id = %s AND date = %s",
                    (user_id, today)
                )
                existing = cursor.fetchone()

                if existing:
                    await ctx.send("⏳ You've already checked in today! If you need to update your rating, use **!updatecheckin <rating>**.")
                    return

                cursor.execute(
                    "INSERT INTO checkins (user_id, date, rating) VALUES (%s, %s, %s)",
                    (user_id, today, rating)
                )
        connection.close()

        current_streak, longest_streak = await get_streak(user_id)
        if current_streak == 0:
            await ctx.send("Check-in recorded, but no streak yet! Start checking in daily to build your streak! 🔥")
        else:
            await ctx.send(
                f"✅ Check-in recorded! You rated your day as {mood_colors[rating]}\n"
                f"🔥 Your current check-in streak is {current_streak} day(s)!\n"
                f"🏆 Your longest streak is {longest_streak} day(s)!"
                )
    except Exception as e:
        await ctx.send("❌ Failed to record check-in. Please contact the bot admin.")
        print(f"Error recording check-in: {e}")

@bot.command()
async def updatecheckin(ctx, *, rating: int):
    """Update today's check-in rating. Usage: !updatecheckin <rating>
    1 = terrible, 5 = amazing"""
    if rating < 1 or rating > 5:
        await ctx.send("❌This is an invalid rating. Between 1 and 5, fam.")
        return
    
    today = date.today()
    user_id = ctx.author.id
    try:
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                # Check if user has checked in today
                cursor.execute(
                    "SELECT user_id FROM checkins WHERE user_id = %s AND date = %s",
                    (user_id, today)
                )
                existing = cursor.fetchone()

                if not existing:
                    await ctx.send("❌ You haven't checked in today yet! Use **!checkin <rating>** to record your rating.")
                    return

                cursor.execute(
                    "UPDATE checkins SET rating = %s WHERE user_id = %s AND date = %s",
                    (rating, user_id, today)
                )
        connection.close()
        await ctx.send(f"✅ Check-in updated! You rated your day as {mood_colors[rating]}\n")
    except Exception as e:
        await ctx.send("❌ Failed to update check-in. Please contact the bot admin.")
        print(f"Error updating check-in: {e}")

@bot.command()
async def streak(ctx):
    """Display user's current and longest check-in streak."""
    user_id = ctx.author.id
    today = date.today()
    try:
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT DISTINCT date FROM checkins WHERE user_id = %s ORDER BY date ASC",
                    (user_id,)
                )
                rows = cursor.fetchall()
        connection.close()

        if not rows:
            await ctx.send("You haven't made any check-ins yet. Use **!checkin <rating>** to start tracking your days! ☑️")
            return

        # Convert dates to a sorted list of date objects
        dates = []
        for row in rows:
            checkin_date = row['date']
            if isinstance(checkin_date, str):
                checkin_date = datetime.strptime(checkin_date, '%Y-%m-%d').date()
            dates.append(checkin_date)

        # Calculate longest streak
        longest_streak = 1
        streak = 1
        for i in range(1, len(dates)):
            if (dates[i] - dates[i-1]).days == 1:
                streak += 1
                if streak > longest_streak:
                    longest_streak = streak
            else:
                streak = 1

        # Calculate current streak (how many days up to today)
        current_streak = 0
        current_date = today
        i = len(dates) - 1
        while i >= 0 and dates[i] == current_date:
            current_streak += 1
            current_date -= timedelta(days=1)
            i -= 1

        await ctx.send(
            f"🔥 Your current check-in streak is {current_streak} day(s)!\n"
            f"🏆 Your longest streak is {longest_streak} day(s)!"
        )
    except Exception as e:
        await ctx.send("❌ Failed to retrieve check-in streak. Please contact the bot admin.")
        print(f"Error retrieving check-in streak: {e}")


# Display days ratings
@bot.command()
async def myyear(ctx):
    """Display user's daily check-in ratings for the year."""
    user_id = ctx.author.id
    try:
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT date, rating FROM checkins WHERE user_id = %s ORDER BY date",
                    (user_id,)
                )
                rows = cursor.fetchall()
        connection.close()

        if not rows:
            await ctx.send("You haven't made any check-ins yet. Use **!checkin <rating>** to start tracking your days! ☑️")
            return

        # Map checkins dates to ratings
        day_to_rating = {}
        for row in rows:
            checkin_date = row['date']
            rating = row['rating']
            day_to_rating[checkin_date] = rating
        
        msg = " **Your year so far:** \n"
        current_date = start_date

        for week in range (27): # 26 rows for weeks + 1 day for 365 days total
            row = ""
            # first 7 days
            for i in range(7):
                if current_date > end_date:
                    break
                rating = day_to_rating.get(current_date, None)
                row += mood_colors[rating]
                current_date += timedelta(days=1)
            row += "\t"
            # next 7 days
            for i in range(7):
                if current_date > end_date:
                    break
                rating = day_to_rating.get(current_date, None)
                row += mood_colors[rating]
                current_date += timedelta(days=1)               
            msg += row + "\n"
            if current_date > end_date:
                break    
        await ctx.send(msg)
    except Exception as e:
        await ctx.send("❌ Failed to retrieve check-ins. Please contact the bot admin.")
        print(f"Error retrieving check-ins: {e}")
bot.run(DISCORD_TOKEN)