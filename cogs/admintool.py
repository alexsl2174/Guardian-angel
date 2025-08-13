import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import aiohttp
import re
import cogs.utils as utils
from dotenv import load_dotenv
import datetime
from typing import Optional
import traceback

load_dotenv()

class EmojiGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="emoji", description="Manage server emojis.")

    @app_commands.command(name="add", description="Adds a custom emoji to the server from a URL.")
    @app_commands.checks.has_permissions(manage_emojis=True)
    async def emoji_add(self, interaction: discord.Interaction, name: str, image_url: str):
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(f"Failed to fetch the image from the URL. Status: {resp.status}", ephemeral=True)
                        return
                    image_bytes = await resp.read()

            await interaction.guild.create_custom_emoji(name=name, image=image_bytes)
            await interaction.followup.send(f"Successfully added emoji `:{name}:`!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I don't have the permissions to manage emojis.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An unexpected error occurred: {e}", ephemeral=True)

    @app_commands.command(name="steal", description="Adds an emoji from another server to this one.")
    @app_commands.checks.has_permissions(manage_emojis=True)
    async def emoji_steal(self, interaction: discord.Interaction, emoji: str):
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        emoji_match = re.match(r'<a?:(\w+):(\d+)>', emoji)
        if not emoji_match:
            await interaction.followup.send("Invalid emoji format. Please provide a custom emoji from another server.", ephemeral=True)
            return
        
        emoji_name = emoji_match.group(1)
        emoji_id = emoji_match.group(2)
        is_animated = emoji.startswith('<a:')

        emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if is_animated else 'png'}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(emoji_url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(f"Failed to fetch the emoji from the URL. Status: {resp.status}", ephemeral=True)
                        return
                    image_bytes = await resp.read()

            await interaction.guild.create_custom_emoji(name=emoji_name, image=image_bytes)
            await interaction.followup.send(f"Successfully stole emoji `:{emoji_name}:`!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I don't have the permissions to manage emojis.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An unexpected error occurred: {e}", ephemeral=True)

    @app_commands.command(name="delete", description="Deletes a custom emoji from the server.")
    @app_commands.checks.has_permissions(manage_emojis=True)
    @app_commands.describe(emoji="The custom emoji to delete (e.g., <:name:id>).")
    async def emoji_delete(self, interaction: discord.Interaction, emoji: str):
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        emoji_match = re.match(r'<a?:(\w+):(\d+)>', emoji)
        if not emoji_match:
            await interaction.followup.send("Invalid emoji format. Please provide a custom emoji from this server.", ephemeral=True)
            return

        emoji_id = int(emoji_match.group(2))

        try:
            full_emoji = await interaction.guild.fetch_emoji(emoji_id)
        except discord.NotFound:
            await interaction.followup.send("That emoji was not found in this server.", ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.followup.send("I do not have permission to fetch that emoji.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"An unexpected error occurred while fetching the emoji: {e}", ephemeral=True)
            return

        if not full_emoji.guild == interaction.guild:
            await interaction.followup.send("That emoji does not belong to this server.", ephemeral=True)
            return

        try:
            await full_emoji.delete()
            await interaction.followup.send(f"Successfully deleted the emoji `{full_emoji.name}`!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I don't have the permissions to manage emojis.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An unexpected error occurred: {e}", ephemeral=True)

class CurrencyGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="currency", description="Add or remove currency from a user.")
        
    @app_commands.command(name="add", description="Adds currency to a user's balance.")
    @app_commands.checks.has_any_role(utils.ROLE_IDS["Staff"])
    async def currency_add(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        if amount <= 0:
            await interaction.followup.send("Amount must be a positive number.", ephemeral=True)
            return
        
        utils.update_user_money(member.id, amount)
        await interaction.followup.send(f"Successfully added {amount} coins to {member.mention}'s balance.", ephemeral=True)

    @app_commands.command(name="remove", description="Removes currency from a user's balance.")
    @app_commands.checks.has_any_role(utils.ROLE_IDS["Staff"])
    async def currency_remove(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        if amount <= 0:
            await interaction.followup.send("Amount must be a positive number.", ephemeral=True)
            return
        
        utils.update_user_money(member.id, -amount)
        await interaction.followup.send(f"Successfully removed {amount} coins from {member.mention}'s balance.", ephemeral=True)

class AdminTools(commands.Cog):
    """A cog for server administration, verification, and automated tasks."""
    def __init__(self, bot):
        self.bot = bot
        self.bot.tree.add_command(EmojiGroup())
        self.bot.tree.add_command(CurrencyGroup())

    @app_commands.command(name="set_channel", description="Sets a specific channel ID dynamically.")
    @app_commands.describe(
        channel_id_name="The name of the channel ID to set (e.g., announcements_channel_id).",
        channel="The channel to set."
    )
    @app_commands.autocomplete(channel_id_name=utils.channel_id_name_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def set_channel(self, interaction: discord.Interaction, channel_id_name: str, channel: discord.TextChannel):
        """
        Sets a specific channel ID dynamically and reloads the configuration.
        This command is for administrators only.
        """
        await interaction.response.defer(ephemeral=True)

        if channel_id_name not in utils.bot_config:
            await interaction.followup.send(f"Error: The key '{channel_id_name}' was not found in the bot configuration.")
            return

        try:
            utils.update_dynamic_config(channel_id_name, channel.id)
            await interaction.followup.send(f"Successfully set `{channel_id_name}` to channel `{channel.name}` (`{channel.id}`).")
        except Exception as e:
            await interaction.followup.send(f"An error occurred while saving the configuration: {e}")

    @app_commands.command(name="unset_channel", description="Removes a specific channel ID from the bot's configuration.")
    @app_commands.describe(
        channel_id_name="The name of the channel ID to remove."
    )
    @app_commands.autocomplete(channel_id_name=utils.channel_id_name_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def unset_channel(self, interaction: discord.Interaction, channel_id_name: str):
        """
        Removes a specific channel ID from the dynamic config.
        This command is for administrators only.
        """
        await interaction.response.defer(ephemeral=True)

        if channel_id_name not in utils.bot_config:
            await interaction.followup.send(f"Error: The key '{channel_id_name}' was not found in the bot configuration.")
            return

        try:
            utils.remove_dynamic_config(channel_id_name)
            await interaction.followup.send(f"Successfully removed `{channel_id_name}` from the bot configuration.")
        except Exception as e:
            await interaction.followup.send(f"An error occurred while removing the configuration: {e}")
            
    @app_commands.command(name="set_role", description="Sets a specific role ID dynamically.")
    @app_commands.describe(
        role_id_name="The name of the role ID to set (e.g., Staff).",
        role="The role to set."
    )
    @app_commands.autocomplete(role_id_name=utils.role_id_name_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def set_role(self, interaction: discord.Interaction, role_id_name: str, role: discord.Role):
        """
        Sets a specific role ID dynamically and reloads the configuration.
        This command is for administrators only.
        """
        await interaction.response.defer(ephemeral=True)

        if role_id_name not in utils.bot_config.get("role_ids", {}):
            await interaction.followup.send(f"Error: The key '{role_id_name}' was not found in the role configuration.")
            return

        try:
            utils.update_dynamic_role(role_id_name, role.id)
            await interaction.followup.send(f"Successfully set `{role_id_name}` to role `{role.name}` (`{role.id}`).")
        except Exception as e:
            await interaction.followup.send(f"An error occurred while saving the configuration: {e}")
            
    @app_commands.command(name="revivepref", description="Sets the time interval for periodic chat revival.")
    @app_commands.default_permissions(administrator=True)
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
            await interaction.followup.send(f"Current chat revive interval is {utils.REVIVE_INTERVAL_HOURS} hours.", ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        self.periodic_revive.start()
        self.daily_post_task.start()
        print("Scheduled tasks started.")

    async def _run_revive_logic(self, is_test: bool = False):
        channel_id = utils.CHAT_REVIVE_CHANNEL_ID
        if not channel_id:
            print("Periodic revive failed: No chat revive channel set.")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            print(f"Periodic revive failed: Channel with ID {channel_id} not found.")
            return
        
        if not is_test:
            # Get the last message in the channel to check for inactivity
            last_message_age = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=utils.REVIVE_INTERVAL_HOURS)
            last_message_found = False
            
            try:
                async for message in channel.history(limit=1, oldest_first=False):
                    last_message = message
                    last_message_found = True
                    break
            except discord.Forbidden:
                print(f"Periodic revive failed: Bot lacks permissions to read message history in channel {channel.name}.")
                return

            if last_message_found and last_message.created_at > last_message_age:
                print(f"Periodic revive skipped: Channel {channel.name} is active.")
                return

        revive_role_id = utils.CHAT_REVIVE_ROLE_ID
        role = channel.guild.get_role(revive_role_id)
        if not role:
            print(f"Periodic revive failed: Role with ID {revive_role_id} not found in guild {channel.guild.name}.")
            return
            
        prompt = "Generate a short, engaging, and non-controversial message to revive a chat conversation. It should be a single sentence."
        chat_history = [{"role": "user", "parts": [{"text": prompt}]}]
        ai_message = await utils.generate_text_with_gemini_with_history(chat_history=chat_history)

        if ai_message:
            message_content = f"{role.mention}\n\n{ai_message}"
            await channel.send(message_content)

    @tasks.loop(minutes=30)
    async def periodic_revive(self):
        # This task runs every 30 minutes and calls the main revive logic
        # which checks the user-configured interval.
        await self._run_revive_logic(is_test=False)
        
    @app_commands.command(name="add_update_global_timed_role", description="Adds or updates a global timed role with an expiration date.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add_update_global_timed_role(self, interaction: discord.Interaction, role: discord.Role, year: int, month: int, day: int, hour: int = 0, minute: int = 0):
        try:
            expiration_date = datetime.datetime(year, month, day, hour, minute)
            if expiration_date < datetime.datetime.now():
                await interaction.response.send_message("The expiration date cannot be in the past.", ephemeral=True)
                return

            guild_id = interaction.guild_id
            utils.save_timed_role_data(guild_id, role.id, expiration_date)
            await interaction.response.send_message(f"Timed role {role.name} has been set to expire on {expiration_date}.", ephemeral=True)

        except ValueError as e:
            await interaction.response.send_message(f"Invalid date/time provided: {e}. Please use valid numbers for year, month, day, hour, and minute.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An unexpected error occurred: {e}", ephemeral=True)

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
                
                # Send a public message in the channel instead of a DM
                await message.channel.send(f"{message.author.mention}, you have been credited with 250 coins for your image post! Please post any comments in <#{utils.DAILY_COMMENTS_CHANNEL_ID}>.", delete_after=10)
                
    @app_commands.command(name="verify", description="[Staff Only] Verify a member and grant them the 'Verified Access' role.")
    @app_commands.checks.has_any_role(utils.ROLE_IDS.get("Staff", 0))
    @app_commands.describe(member="The member to verify.")
    async def verify(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.guild and interaction.guild.id != utils.MAIN_GUILD_ID:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        access_role_obj = interaction.guild.get_role(utils.ROLE_IDS.get("verified_access"))
        id_verified_role_obj = interaction.guild.get_role(utils.ROLE_IDS.get("id_verified"))
        visitor_role_obj = interaction.guild.get_role(utils.ROLE_IDS.get("Visitor"))
        sinner_chat_channel = self.bot.get_channel(utils.SINNER_CHAT_CHANNEL_ID)
        self_roles_channel_id = utils.SELF_ROLES_CHANNEL_ID

        if not access_role_obj or not id_verified_role_obj or not visitor_role_obj or not sinner_chat_channel:
            return await interaction.response.send_message("One or more required roles or channels could not be found. Please check role IDs and channel IDs in settings.", ephemeral=True)

        try:
            await member.add_roles(access_role_obj, id_verified_role_obj, reason="Manually verified by a staff member.")
            await member.remove_roles(visitor_role_obj, reason="Member has been verified.")
            
            if sinner_chat_channel:
                embed_title = f"Welcome To The Sinners Side Of The Server ❧"
                embed_description = f"You are now verified {member.mention}! Go to <#{self_roles_channel_id}> then make yourself at home."
                
                embed = discord.Embed(
                    title=embed_title,
                    description=embed_description,
                    color=discord.Color.green()
                )
                embed.set_image(url=utils.VERIFY_IMAGE_URL)
                await sinner_chat_channel.send(embed=embed)

            await interaction.response.send_message(f"Successfully verified {member.mention} and posted the welcome message.", ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to assign or remove one of the roles. Please check my permissions.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred while trying to assign/remove roles or send the message: {e}", ephemeral=True)

    @app_commands.command(name="crossverify", description="[Staff Only] Verify a member and grant them the 'Cross Verified' role.")
    @app_commands.checks.has_any_role(utils.ROLE_IDS.get("Staff", 0))
    @app_commands.describe(member="The member to cross-verify.")
    async def crossverify(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.guild and interaction.guild.id != utils.MAIN_GUILD_ID:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        access_role_obj = interaction.guild.get_role(utils.ROLE_IDS.get("cross_verified"))
        id_verified_role_obj = interaction.guild.get_role(utils.ROLE_IDS.get("id_verified"))
        visitor_role_obj = interaction.guild.get_role(utils.ROLE_IDS.get("Visitor"))
        sinner_chat_channel = self.bot.get_channel(utils.SINNER_CHAT_CHANNEL_ID)
        self_roles_channel_id = utils.SELF_ROLES_CHANNEL_ID

        if not access_role_obj or not id_verified_role_obj or not visitor_role_obj or not sinner_chat_channel:
            return await interaction.response.send_message("One or more required roles or channels could not be found. Please check role IDs and channel IDs in settings.", ephemeral=True)

        try:
            await member.add_roles(access_role_obj, id_verified_role_obj, reason="Manually cross-verified by a staff member.")
            await member.remove_roles(visitor_role_obj, reason="Member has been cross-verified.")

            if sinner_chat_channel:
                embed_title = f"Welcome To The Sinners Side Of The Server ❧"
                embed_description = f"You are now cross verified, {member.mention}! Go to <#{self_roles_channel_id}> then make yourself at home."
                
                embed = discord.Embed(
                    title=embed_title,
                    description=embed_description,
                    color=discord.Color.green()
                )
                embed.set_image(url=utils.CROSS_VERIFIED_IMAGE_URL)
                await sinner_chat_channel.send(embed=embed)

            await interaction.response.send_message(f"Successfully cross-verified {member.mention} and posted the welcome message.", ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to assign or remove one of the roles. Please check my permissions.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred while trying to assign/remove roles or send the message: {e}", ephemeral=True)

async def setup(bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(AdminTools(bot))
    print("AdminTools Cog Loaded!")