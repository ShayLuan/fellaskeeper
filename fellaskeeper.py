from datetime import date, timedelta
import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

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
    "!goal <goal> <number> - Set a new goal\n" +
    "!mygoals - List all your goals\n" +
    "\n!updategoal <goal_number> <progress_increment> - Update progress on a goal\n" +
    "\tMake sure to check out your goal number with !mygoals first before updating\n" +
    "\n!delete <goal_number> - Delete a goal by its number\n" + 
    "!checkin <rating> - Rate your day from 1 (terrible) 🤢 to 5 (amazing) 🤩\n" +
    "!updatecheckin <rating> - Update today's check-in rating\n" +
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
        await ctx.send(f"✅ Check-in recorded! You rated your day as {mood_colors[rating]}")
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
        await ctx.send(f"✅ Check-in updated! You rated your day as {mood_colors[rating]}")
    except Exception as e:
        await ctx.send("❌ Failed to update check-in. Please contact the bot admin.")
        print(f"Error updating check-in: {e}")

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