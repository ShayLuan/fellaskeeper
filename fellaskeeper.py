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

# intents
intents = discord.Intents.default() 
intents.message_content = True  # needed to read messages
intents.members = True  # needed to see who joins/leaves

# command prefix
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Dictionary to store user goals
goals = {}

# Event: bot is ready
@bot.event
async def on_ready():
    print(f"Successfully logged in as {bot.user.name} ☑️")
    print("------")
    print("No need to wait for the New Year or tomorrow. Today is ready.")
    await bot.change_presence(activity=discord.Game(name="locked in an Adderall frenzy"))

# simple test command
@bot.command()
async def help(ctx):
    """Show the help menu"""
    await ctx.send("```" + "Commands:\n" + 
    "!help - Show the help menu\n" + 
    "!ping - Check if the bot is responsive\n" +
    "!goal <goal> <number> - Set a new goal\n" +
    "!mygoals - List all your goals\n" +
    "!delete <goal_id> - Delete a goal by its ID\n" + 
    "```")

@bot.command()
async def ping(ctx):
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
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT description, progress, total FROM goals WHERE user_id = %s",
                    (user_id,)
                )
                rows = cursor.fetchall()
        connection.close()

        if not rows:
            await ctx.send("You haven't set any goals yet.\n User !goal <goal> <number> to set one! 🚀")
            return
        
        msg = "**YOUR GOALS:**\n"
        for row in rows:
            msg += f"- {row['id']} - {row['description'].strip('\"')}: {row['progress']}/{row['total']}\n"
        await ctx.send(msg)
    except Exception as e:
        await ctx.send("❌ Failed to retrieve goals. Please contact the bot admin.")
        print(f"Error retrieving goals: {e}")

@bot.command()
async def delete(ctx, *, id: int):
    """Delete a goal by its ID. Usage: !delete <goal_id>
    Make sure user can only delete their own goals."""
    user_id = ctx.author.id
    try:
        connection = get_db_connection()
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM goals WHERE id = %s AND user_id = %s RETURNING id;",
                    (id, user_id)
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

bot.run(DISCORD_TOKEN)