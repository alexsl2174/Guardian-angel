import discord
print("Script start.")
from discord.ext import commands, tasks
from discord import app_commands
import google.generativeai as genai
import os
print("Current working directory:", os.getcwd())
import textwrap
from dotenv import load_dotenv
import json
import random
import datetime
import re
import traceback
from typing import Optional
import io


# Load environment variables from the .env file
load_dotenv()

# --- Import all utilities and constants from cogs.utils ---
import cogs.utils as utils

# ===============================================
# --- 1. GLOBAL CONFIGURATION & BOT INSTANCE ATTRIBUTES ---
# ===============================================

# --- Gemini AI Configuration ---
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
except Exception as e:
    print(f"FATAL: Could not configure Gemini AI. Is the GEMINI_AI_KEY valid? Error: {e}")
    exit()

# ===============================================
# --- 2. DISCORD BOT INITIALIZATION ---
# ===============================================
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True
intents.guilds = True
intents.presences = True

# We set the command_prefix to a character that won't be used,
# as we are only using slash commands. This prevents the bot from
# trying to process every message.
bot = commands.Bot(command_prefix="!", intents=intents)

# ===============================================
# --- 3. BOT EVENTS (Main Dispatchers & Global Listeners) ---
# ===============================================

@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user} (ID: {bot.user.id})')
    print("Carl AI is ready!")

    bot.owner_id = int(os.getenv("DISCORD_BOT_OWNER_ID")) if os.getenv("DISCORD_BOT_OWNER_ID") else None

    cogs_to_load = [
        "cogs.economy",
        "cogs.counting_game",
        "cogs.fun_commands",
        "cogs.pins",
        "cogs.adventure",
        "cogs.hangrygames",
        "cogs.swear_jar",
        "cogs.item",
        "cogs.shop",
        "cogs.bug_catching",
        "cogs.tree",
        "cogs.ai_features",
        "cogs.admintool"
    ]
    
    for cog_name in cogs_to_load:
        try:
            await bot.load_extension(cog_name)
            print(f"Successfully loaded {cog_name}")
        except Exception as e:
            print(f"Failed to load {cog_name}: {e}")
            traceback.print_exc()
            
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Failed to sync commands on startup: {e}")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        seconds = int(error.retry_after)
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        time_str = []
        if hours > 0: time_str.append(f"{hours}h")
        if minutes > 0: time_str.append(f"{minutes}m")
        if seconds > 0 or not time_str: time_str.append(f"{seconds}s")

        await interaction.response.send_message(f"This command is on cooldown. Please try again in **{' '.join(time_str)}**.", ephemeral=True)
    elif isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You don't have the necessary permissions to use this command.", ephemeral=True)
    elif isinstance(error, app_commands.MissingAnyRole):
        await interaction.response.send_message("You are missing one or more of the required roles to use this command.", ephemeral=True)
    elif isinstance(error, commands.NotOwner):
        await interaction.response.send_message("You must be the bot owner to use this command.", ephemeral=True)
    elif isinstance(error, app_commands.NoPrivateMessage):
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
    # The correct class to check for a missing argument
    elif isinstance(error, commands.MissingRequiredArgument):
        await interaction.response.send_message("Missing arguments. Please check the command usage.", ephemeral=True)
    else:
        # Check if the command object exists before trying to access its name
        command_name = interaction.command.name if interaction.command else "Unknown Command"
        print(f"Unhandled application command error in {command_name}: {error}")
        traceback.print_exc()
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("An unexpected error occurred while executing this command.", ephemeral=True)
            else:
                await interaction.followup.send("An unexpected error occurred while executing this command.", ephemeral=True)
        except discord.errors.InteractionResponded:
            # If the initial response failed, this will catch it
            await interaction.followup.send("An unexpected error occurred while executing this command.", ephemeral=True)

@bot.tree.command(name="sync", description="Syncs all application commands with Discord.")
@commands.is_owner()
async def sync_commands(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await bot.tree.sync()
    await interaction.followup.send("Commands have been synchronized!", ephemeral=True)

# --- Run the Bot ---
bot.run(os.getenv("DISCORD_BOT_TOKEN"))
