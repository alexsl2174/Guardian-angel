import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import random
import datetime
import os
import asyncio
import sys
import traceback
from typing import List, Dict, Any, Union, Optional
import re
import cogs.utils as utils

# Define the path to the data directory, now local to this cog's file.
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
DAILY_MESSAGE_COOLDOWNS_FILE = os.path.join(DATA_DIR, "daily_message_cooldowns.json")
REWARDS_FILE = os.path.join(DATA_DIR, 'rewards.json')

# Helper functions for data persistence, now located in this file.
def _load_data(file_path: str, default_value: Any = None) -> Any:
    """Loads data from a JSON file, returning a default value if the file is not found or is corrupted."""
    if not os.path.exists(file_path):
        return default_value if default_value is not None else {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error in {file_path}: {e}. Returning default value.")
        return default_value if default_value is not None else {}
    except Exception as e:
        print(f"Error loading data from {file_path}: {e}. Returning default value.")
        return default_value if default_value is not None else {}

def _save_data(data: Any, file_path: str):
    """Saves data to a JSON file."""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving data to {file_path}: {e}")

async def is_moderator(interaction: discord.Interaction) -> bool:
    """Checks if the user has a Staff role."""
    staff_roles = utils.ROLE_IDS.get("Staff")
    if not staff_roles:
        return False
    
    # Ensure staff_roles is a list to handle both single ID and list of IDs
    if not isinstance(staff_roles, list):
        staff_roles = [staff_roles]

    user_role_ids = [role.id for role in interaction.user.roles]
    return any(role_id in user_role_ids for role_id in staff_roles)

class TimeRole(commands.Cog):
    """A cog for handling timed rewards, roles, and related tasks."""

    def __init__(self, bot):
        self.bot = bot
        self.main_guild_id = utils.MAIN_GUILD_ID
        
        # Hard-coded channel and role IDs
        self.daily_message_reward_channel_id = utils.bot_config.get('DAILY_MESSAGE_REWARD_CHANNEL_ID')
        
        # NEW: Constants for the task drop system
        self.TASK_DROP_CHANNEL_ID = 1397729250584432731
        self.TIMED_TASK_ROLE_ID = 1408994431356370964
        self.checkin_cooldown_role_id = 1293639562815475752
        
    @commands.Cog.listener()
    async def on_ready(self):
        # This listener is called when the cog is loaded and the bot is ready.
        self.checkin_cooldown_role_task.start()
        self.daily_post_task.start()
        self.check_timed_roles.start()
        self.periodic_revive.start() # Now starting the revive task here
        print("Checkin Cooldown role task started.")
        print("Daily post task started.")
        print("Timed roles check started.")
        print("Periodic revive task started.")
    
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        # Handle command-specific errors, if any exist in this cog.
        print(f"Ignoring exception in command {interaction.command}:", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

###################################################################
###### CHECK IN CHANNEL TEXTUAL MESSAGE FOR DAILY #################
###################################################################

    @tasks.loop(seconds=30)  # Check every 30 seconds
    async def checkin_cooldown_role_task(self):
        """This task runs to check for and remove the checkin cooldown role."""
        await self.bot.wait_until_ready()
        
        guild = self.bot.get_guild(self.main_guild_id)
        if not guild:
            print("Main guild not found. Skipping checkin cooldown role task.")
            return

        checkin_cooldown_role = guild.get_role(self.checkin_cooldown_role_id)
        if not checkin_cooldown_role:
            print("Checkin Cooldown role not found. Skipping checkin cooldown role task.")
            return

        # Load timestamps to check for checkin cooldown expiration
        cooldown_data = _load_data(DAILY_MESSAGE_COOLDOWNS_FILE, {})
        
        now = datetime.datetime.now(datetime.timezone.utc)
        
        #Checkin Cooldown is 16 hours, converted to seconds
        cooldown_seconds = 16 * 60 * 60

        for user_id_str, timestamp_str in list(cooldown_data.items()):
            try:
                member = await guild.fetch_member(int(user_id_str))
                if member and checkin_cooldown_role in member.roles:
                    last_reward_time = datetime.datetime.fromisoformat(timestamp_str)
                    time_since_last_reward = (now - last_reward_time).total_seconds()

                    if time_since_last_reward >= cooldown_seconds:
                        print(f"DEBUG: Removing cooldown role from user {member.display_name}")
                        await member.remove_roles(checkin_cooldown_role, reason="Daily message reward cooldown expired.")
                        del cooldown_data[user_id_str]
                        _save_data(cooldown_data, DAILY_MESSAGE_COOLDOWNS_FILE)
            except discord.NotFound:
                # User left the server, clean up their data
                if user_id_str in cooldown_data:
                    del cooldown_data[user_id_str]
                    _save_data(cooldown_data, DAILY_MESSAGE_COOLDOWNS_FILE)
                print(f"DEBUG: User {user_id_str} not found, cleaning up cooldown data.")
            except Exception as e:
                print(f"DEBUG: An error occurred while processing user {user_id_str}: {e}")
    
###################################################################################################
################# CHECK IN COMMAND WHO CAN BE DAILY OR WEEKLY ##################################### 
###################################################################################################

    # --- Check-in and Reward Commands ---
    @app_commands.command(name="checkin", description="Check in daily or weekly for role-based rewards.")
    @app_commands.describe(period="The period you want to check in for.")
    @app_commands.choices(period=[
        app_commands.Choice(name="daily", value="daily"),
        app_commands.Choice(name="weekly", value="weekly")
    ])
    async def checkin(self, interaction: discord.Interaction, period: app_commands.Choice[str]):
        """Allows a user to check in for a daily or weekly reward."""
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        user_id = str(interaction.user.id)
        member = interaction.user
        period_type = period.value
        
        # Load the reward and cooldown data
        rewards_data = _load_data(REWARDS_FILE, {})
        
        # Initialize keys if they don't exist
        if 'cooldowns' not in rewards_data:
            rewards_data['cooldowns'] = {}
        if 'rewards' not in rewards_data:
            rewards_data['rewards'] = {}
        
        cooldowns = rewards_data.get('cooldowns', {})
        rewards = rewards_data.get('rewards', {})

        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Check cooldown
        last_checkin_str = cooldowns.get(user_id, {}).get(period_type)
        if last_checkin_str:
            last_checkin = datetime.datetime.fromisoformat(last_checkin_str)
            if period_type == 'daily' and (now - last_checkin).total_seconds() < 24*60*60:
                time_left = (last_checkin + datetime.timedelta(days=1)) - now
                minutes, seconds = divmod(time_left.seconds, 60)
                return await interaction.response.send_message(f"You have already checked in for your daily reward! Try again in {time_left.seconds // 3600}h {minutes}m {seconds}s.", ephemeral=True)
            elif period_type == 'weekly' and (now - last_checkin).total_seconds() < 7*24*60*60:
                time_left = (last_checkin + datetime.timedelta(weeks=1)) - now
                minutes, seconds = divmod(time_left.seconds, 60)
                return await interaction.response.send_message(f"You have already checked in for your weekly reward! Try again in {time_left.seconds // 3600}h {minutes}m {seconds}s.", ephemeral=True)

        # Calculate rewards based on roles
        total_reward = 0
        reward_messages = []
        user_role_ids = [role.id for role in member.roles]

        for role_id, amount in rewards.get(period_type, {}).items():
            if int(role_id) in user_role_ids:
                total_reward += amount
                role_obj = discord.utils.get(member.guild.roles, id=int(role_id))
                if role_obj:
                    reward_messages.append(f"• **{role_obj.name}** - {amount} coins")
                else:
                    reward_messages.append(f"• **Role ID {role_id}** - {amount} coins (Role not found)")


        if total_reward > 0:
            utils.update_user_money(user_id, total_reward)
            
            if user_id not in cooldowns:
                cooldowns[user_id] = {}
            cooldowns[user_id][period_type] = now.isoformat()
            rewards_data['cooldowns'] = cooldowns
            _save_data(rewards_data, REWARDS_FILE)

            embed = discord.Embed(
                title=f"✅ {period_type.capitalize()} Check-in Rewards!",
                description="You've successfully claimed the following rewards:",
                color=discord.Color.green()
            )
            embed.add_field(name="Rewards Received", value="\n".join(reward_messages), inline=False)
            embed.add_field(name="Total", value=f"**{total_reward}** <a:starcoin:1280590254935380038>", inline=False)
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(f"You do not have any roles with {period_type} rewards set. Please contact a staff member to have a reward set.", ephemeral=True)

##############################################################################################################
########## COMMAND TO SET REWARD FOR /SET TIMED ROLE CREATED ROLE ############################################
##############################################################################################################

    @app_commands.command(name="set_reward", description="[Staff Only] Sets a reward for a role.")
    @app_commands.describe(
        period="The period for the reward (daily or weekly).",
        role="The role to set the reward for.",
        amount="The amount of coins to be rewarded."
    )
    @app_commands.choices(period=[
        app_commands.Choice(name="daily", value="daily"),
        app_commands.Choice(name="weekly", value="weekly")
    ])
    @app_commands.check(is_moderator)
    async def set_reward(self, interaction: discord.Interaction, period: app_commands.Choice[str], role: discord.Role, amount: int):
        """Allows staff to set a reward for a specific role."""
        rewards_data = _load_data(REWARDS_FILE, {})
        period_type = period.value
        role_id_str = str(role.id)

        if 'rewards' not in rewards_data:
            rewards_data['rewards'] = {}
        if period_type not in rewards_data['rewards']:
            rewards_data['rewards'][period_type] = {}
        
        rewards_data['rewards'][period_type][role_id_str] = amount
        _save_data(rewards_data, REWARDS_FILE)

        await interaction.response.send_message(f"Successfully set the **{period_type}** reward for the role **{role.name}** to **{amount}** coins.", ephemeral=True)

 #############################################################################################
### COMMAND TO REMOVE THE ROLE TIMED OUT 16 CHECKIN FROM USER WHO HAVE IT 
# (THIS WAS ADDED WHILE I WAS TRYING TO BUGFIX THE COMMAND, WILL NOT BE NEEDED WHEN FIX) ####
#####################################################################################

    @app_commands.command(name="cleardailycheckinrole", description="[Moderator Only] Removes the daily check-in role from all users.")
    @app_commands.check(is_moderator)
    async def cleardailycheckinrole(self, interaction: discord.Interaction):
        """Removes the daily check-in role from all users on the server and resets their cooldowns."""
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        cooldown_role = guild.get_role(self.cooldown_role_id)

        if not cooldown_role:
            return await interaction.followup.send(f"Error: The cooldown role with ID `{self.cooldown_role_id}` was not found on this server.", ephemeral=True)

        members_with_role = [member for member in guild.members if cooldown_role in member.roles]

        if not members_with_role:
            await interaction.followup.send("No users currently have the daily check-in role.", ephemeral=True)
            return

        cleared_count = 0
        for member in members_with_role:
            try:
                await member.remove_roles(cooldown_role, reason="Manual reset via cleardailycheckinrole command.")
                cleared_count += 1
                await asyncio.sleep(0.5) # Add a small delay to avoid rate-limiting
            except discord.Forbidden:
                print(f"Error: Bot does not have permissions to remove role from {member.display_name}")
            except Exception as e:
                print(f"Error removing role from {member.display_name}: {e}")

        # Also clear the cooldown data file to reset cooldowns for all users
        utils.save_daily_message_cooldowns({})

        await interaction.followup.send(f"Successfully removed the daily check-in role from **{cleared_count}** user(s) and reset the cooldown data file.", ephemeral=True)

#####################################################################################################
### COMMAND FOR STAFF TO CREATE TIMED ROLE (WHO MIGHT NOT WORK ACTUALLY) ###########################
######################################################################################################

    @app_commands.command(name="set_timed_role", description="Adds or updates a global timed role.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        role="The role to be added/removed.",
        hours="Duration in hours for a one-time or daily repeatable role.",
        day_of_week="The day of the week to apply the role for one-time or weekly repeatable roles.",
        repeatable="If true, the role will repeat daily or weekly."
    )
    @app_commands.autocomplete(day_of_week=utils.day_of_week_autocomplete)
    async def set_timed_role(self, interaction: discord.Interaction, role: discord.Role, hours: Optional[int] = None, day_of_week: Optional[str] = None, repeatable: Optional[bool] = False):
        await interaction.response.defer(ephemeral=True)

        try:
            guild_id = interaction.guild_id

            if repeatable:
                if hours is not None and hours > 0:
                    # Daily repeatable role based on hours
                    utils.save_timed_role_data(guild_id, role.id, None, True, "daily", hours)
                    await interaction.followup.send(f"Timed role {role.mention} has been set to repeat daily, being removed after {hours} hour(s).", ephemeral=True)
                elif day_of_week:
                    # Weekly repeatable role based on day of week
                    days_of_week_map = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6}
                    if day_of_week not in days_of_week_map:
                        await interaction.followup.send("Invalid `day_of_week` specified. Please use the autocomplete options.", ephemeral=True)
                        return
                    utils.save_timed_role_data(guild_id, role.id, None, True, day_of_week, None)
                    await interaction.followup.send(f"Timed role {role.mention} has been set to repeat weekly on {day_of_week}.", ephemeral=True)
                else:
                    await interaction.followup.send("You must provide either `hours` or a `day_of_week` for a repeatable role.", ephemeral=True)
            else: # Not repeatable
                if hours is not None and hours > 0:
                    # One-time role based on hours
                    expiration_date = datetime.datetime.now() + datetime.timedelta(hours=hours)
                    duration_text = f"{hours} hour(s)"
                    utils.save_timed_role_data(guild_id, role.id, expiration_date.isoformat(), False, None, None)
                    await interaction.followup.send(f"Timed role {role.mention} has been set to expire in {duration_text}.", ephemeral=True)
                elif day_of_week:
                    # One-time role based on day of week
                    days_of_week_map = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6}
                    if day_of_week not in days_of_week_map:
                        await interaction.followup.send("Invalid `day_of_week` specified. Please use the autocomplete options.", ephemeral=True)
                        return

                    today = datetime.datetime.now()
                    target_day_index = days_of_week_map[day_of_week]
                    current_day_index = today.weekday()

                    days_until = target_day_index - current_day_index
                    if days_until <= 0:
                        days_until += 7

                    expiration_date = today + datetime.timedelta(days=days_until)
                    duration_text = f"until next {day_of_week}"
                    utils.save_timed_role_data(guild_id, role.id, expiration_date.isoformat(), False, None, None)
                    await interaction.followup.send(f"Timed role {role.mention} has been set to expire {duration_text}.", ephemeral=True)
                else:
                    await interaction.followup.send("You must provide either a duration in `hours` or a `day_of_week` for a one-time role.", ephemeral=True)

        except ValueError as e:
            await interaction.followup.send(f"Invalid input provided: {e}. Please check your values.", ephemeral=True)
        except Exception as e:
            print(f"Error in set_timed_role: {traceback.format_exc()}")
            await interaction.followup.send(f"An unexpected error occurred: {e}", ephemeral=True)

#################################################################
####### CHAT REVIVE SECTION #####################################
#################################################################

    @app_commands.command(name="revivepref", description="Sets the time interval for periodic chat revival.")
    @app_commands.checks.has_any_role(*utils.ROLE_IDS.get("Staff", []))
    @app_commands.describe(
        hours="How often the chat revive should run in hours (e.g., 8).",
        test_revive="Set to True to run the revive immediately for testing."
    )
    async def revive_pref(self, interaction: discord.Interaction, hours: Optional[int] = None, test_revive: Optional[bool] = False):
        """
        Sets the chat revive interval and allows for immediate testing.
        """
        await interaction.response.defer(ephemeral=True)

        if hours is not None:
            if hours < 1:
                await interaction.followup.send("The number of hours must be at least 1.", ephemeral=True)
                return
            utils.update_dynamic_config("REVIVE_INTERVAL_HOURS", hours)
            await interaction.followup.send(f"Chat revive interval set to {hours} hours. The next revive will be checked at this interval.", ephemeral=True)

        if test_revive:
            await interaction.followup.send("Running chat revive test now...", ephemeral=True)
            await self._run_revive_logic(is_test=True)

        if hours is None and not test_revive:
            await interaction.followup.send(f"Current chat revive interval is {utils.bot_config.get('REVIVE_INTERVAL_HOURS', 6)} hours.", ephemeral=True)

###################
## CHAT REVIVE LOGIC ##
################

    async def _run_revive_logic(self, is_test: bool = False):
        channel_id = utils.CHAT_REVIVE_CHANNEL_ID
        if not channel_id:
            print("Periodic revive failed: No chat revive channel set.")
            return

        try:
            channel = await self.bot.fetch_channel(channel_id)
        except discord.NotFound:
            print(f"Periodic revive failed: Channel with ID {channel_id} not found.")
            return
        except discord.Forbidden:
            print(f"Periodic revive failed: Bot lacks permissions to fetch channel with ID {channel_id}.")
            return

        revive_interval_hours = utils.bot_config.get("REVIVE_INTERVAL_HOURS", 6)

        if not is_test:
            last_message_age = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=revive_interval_hours)
            last_message_found = False

            try:
                async for message in channel.history(limit=1, oldest_first=False):
                    last_message = message
                    last_message_found = True
                    break
            except discord.Forbidden:
                print(f"Periodic revive failed: Bot lacks permissions to read message history in channel {channel.name}.")
                return
            except Exception as e:
                print(f"Error fetching channel history in {channel.name}: {e}")
                return

            if last_message_found and last_message.created_at.replace(tzinfo=datetime.timezone.utc) > last_message_age:
                print(f"Periodic revive skipped: Channel {channel.name} is active. Last message sent at {last_message.created_at}.")
                return

        revive_role_id = utils.CHAT_REVIVE_ROLE_ID
        role = channel.guild.get_role(revive_role_id)
        if not role:
            print(f"Periodic revive failed: Role with ID {revive_role_id} not found in guild {channel.guild.name}.")
            return

        prompt = "Generate a short, engaging, and non-controversial question to revive a chat conversation. The question should be similar to these examples: 'What's the best movie you've seen recently?', 'If you could travel anywhere in the world right now, where would you go?', 'Alright, chat’s been too quiet… so, pineapple on pizza: yes or no? 🍍🍕', 'If you could swap lives with a video game character for a day, who would it be?', 'Imagine you wake up in the last movie/series you watched. What’s your survival plan?', 'What’s a conspiracy theory you don’t believe, but still find super entertaining?', 'Quick vote: Coffee ☕, Tea 🍵, or Energy Drinks ⚡?', 'Favorite season? 🌸 Spring | ☀️ Summer | 🍂 Autumn | ❄️ Winter', 'If you were a potato, how would you want to be cooked?', 'The last emoji you used is your weapon in the apocalypse. How screwed are you?', 'Name something that isn’t illegal but feels like it should be.' or 'Would you rather fight 1 horse-sized duck or 100 duck-sized horses?', 'If you had $1,000 to spend in 1 hour, what would you buy?', 'Let’s settle this once and for all: cats 🐱 or dogs 🐶?' The response should be a single sentence."

        chat_history = [{"role": "user", "parts": [{"text": prompt}]}]
        ai_message = await utils.generate_text_with_gemini_with_history(chat_history=chat_history)

        if ai_message:
            message_content = f"{role.mention}\n\n{ai_message}"
            await channel.send(message_content)

    @tasks.loop(minutes=30)
    async def periodic_revive(self):
        await self._run_revive_logic(is_test=False)

###############

    @tasks.loop(minutes=30)
    async def check_timed_roles(self):
        print("Checking for expired timed roles...")
        all_timed_roles = utils.load_timed_roles()
        now = datetime.datetime.now(datetime.timezone.utc)

        # Define the day of week mapping locally since it might not be in utils
        day_of_week_map = {
            'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3,
            'Friday': 4, 'Saturday': 5, 'Sunday': 6
        }

        guilds_to_update = {}

        for guild_id_str, roles_data in all_timed_roles.items():
            guild = self.bot.get_guild(int(guild_id_str))
            if not guild:
                continue

            guilds_to_update[guild_id_str] = {}

            for role_id_str, role_info in roles_data.items():
                is_repeatable = role_info.get('repeatable', False)
                expiration_date_str = role_info.get('expiration_date')
                day_of_week_name = role_info.get('day_of_week')
                hours = role_info.get('hours')
                last_action_time_str = role_info.get('last_action_time')
                role = guild.get_role(int(role_id_str))

                if not role:
                    continue

                # Handling of non-repeatable roles
                if not is_repeatable and expiration_date_str:
                    expiration_date = datetime.datetime.fromisoformat(expiration_date_str)
                    if now >= expiration_date:
                        for member in role.members:
                            try:
                                await member.remove_roles(role, reason="Timed role expiration.")
                                print(f"Removed expired role {role.name} from {member.display_name}.")
                            except discord.Forbidden:
                                print(f"Could not remove role {role.name} from {member.display_name}. Bot lacks permissions.")

                        continue
                    else:
                        guilds_to_update[guild_id_str][role_id_str] = role_info

                # Handling of weekly repeatable roles
                elif is_repeatable and day_of_week_name and day_of_week_name != "daily":
                    target_day_index = day_of_week_map.get(day_of_week_name)
                    current_day_index = now.weekday()

                    if current_day_index == target_day_index:
                        # Add role to all members who don't have it
                        for member in guild.members:
                            if role not in member.roles:
                                try:
                                    await member.add_roles(role, reason=f"Weekly repeatable role on {day_of_week_name}.")
                                    print(f"Added repeatable role {role.name} to {member.display_name}.")
                                except discord.Forbidden:
                                    print(f"Could not add repeatable role {role.name} to {member.display_name}. Bot lacks permissions.")
                    else:
                        # Remove role from all members who have it
                        for member in role.members:
                            try:
                                await member.remove_roles(role, reason=f"Weekly repeatable role removed as {day_of_week_name} has passed.")
                                print(f"Removed repeatable role {role.name} from {member.display_name}.")
                            except discord.Forbidden:
                                print(f"Could not remove repeatable role {role.name} from {member.display_name}. Bot lacks permissions.")

                    guilds_to_update[guild_id_str][role_id_str] = role_info

                # Handling of daily repeatable roles (UPDATED LOGIC)
                elif is_repeatable and day_of_week_name == "daily" and hours:
                    last_action_time = None
                    if last_action_time_str:
                        last_action_time = datetime.datetime.fromisoformat(last_action_time_str)

                    time_since_last_action = now - last_action_time if last_action_time else datetime.timedelta(hours=hours + 1)

                    if time_since_last_action >= datetime.timedelta(hours=hours):
                        # Time has passed, remove the role from everyone and then re-add it
                        for member in role.members:
                            try:
                                await member.remove_roles(role, reason="Daily timed role expiration.")
                                print(f"Removed daily role {role.name} from {member.display_name}.")
                            except discord.Forbidden:
                                print(f"Could not remove role {role.name} from {member.display_name}. Bot lacks permissions.")

                        for member in guild.members:
                            if role not in member.roles:
                                try:
                                    await member.add_roles(role, reason=f"Daily repeatable role.")
                                    print(f"Added daily role {role.name} to {member.display_name}.")
                                except discord.Forbidden:
                                    print(f"Could not add repeatable role {role.name} to {member.display_name}. Bot lacks permissions.")

                        role_info['last_action_time'] = now.isoformat()

                    guilds_to_update[guild_id_str][role_id_str] = role_info

        utils.save_timed_roles_full_data(guilds_to_update)

    @tasks.loop(hours=24)
    async def daily_post_task(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        weekday_name = now.strftime('%A').lower()

        last_post_data = utils.load_last_daily_post_date()
        last_weekday = last_post_data.get('last_weekday')

        if last_weekday == weekday_name:
            return

        timed_channels = utils.load_timed_channels()
        if weekday_name in timed_channels:
            channel_id, role_id, post_title = timed_channels[weekday_name]
            channel = self.bot.get_channel(channel_id)
            if not channel:
                print(f"Daily post failed: Channel with ID {channel_id} not found for {weekday_name}.")
                return

            role = channel.guild.get_role(role_id)
            if not role:
                print(f"Daily post failed: Role with ID {role_id} not found for {weekday_name}.")
                return

            image_urls = {
                "monday": utils.BUMDAY_MONDAY_IMAGE_URL,
                "tuesday": utils.TITS_OUT_TUESDAY_IMAGE_URL,
                "wednesday": utils.WET_WEDNESDAY_IMAGE_URL,
                "thursday": utils.FURBABY_THURSDAY_IMAGE_URL,
                "friday": utils.FRISKY_FRIDAY_IMAGE_URL,
                "saturday": utils.SELFIE_SATURDAY_IMAGE_URL,
                "sunday": utils.SLUTTY_SUNDAY_IMAGE_URL
            }
            image_url = image_urls.get(weekday_name)

            embed = discord.Embed(
                title=f"{post_title}!",
                description="Post your image here!",
                color=discord.Color.dark_purple()
            )
            if image_url:
                embed.set_image(url=image_url)

            await channel.send(f"{role.mention}", embed=embed)
            utils.save_last_daily_post_date(now, weekday_name)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild or message.channel.id not in utils.load_daily_posts_channels():
            return

        if message.attachments and any(a.content_type.startswith('image/') for a in message.attachments):
            user_id = message.author.id
            last_post_date = utils.load_last_image_post_date(user_id)
            now = datetime.datetime.now()
            seven_days_ago = now - datetime.timedelta(days=7)

            if last_post_date is None or last_post_date < seven_days_ago:
                utils.update_user_money(user_id, 250)
                utils.save_last_image_post_date(user_id, now)

                await message.channel.send(f"{message.author.mention}, you have been credited with 250 coins for your image post! Please post any comments in <#{utils.DAILY_COMMENTS_CHANNEL_ID}>.", delete_after=10)
    
async def setup(bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(TimeRole(bot))
    print("TimeRole Cog Loaded!")
