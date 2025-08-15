import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
from discord import app_commands
import os
import json
import math
from typing import List, Dict, Any, Union, Optional
import datetime
import random
import asyncio

# Assume cogs.utils is available
import cogs.utils as utils
from cogs.BugData import INSECT_LIST, SHINY_INSECT_LIST, load_bug_collection, save_bug_collection
from cogs.bug_catching import load_inventory, save_inventory
from cogs.BugbookViews import BugbookListView, TradeConfirmationView

# --- Game Configuration ---
# All IDs are now read from the centralized config in utils.py
COOLDOWN_SECONDS = 7200  # 2 hours
REGULAR_CATCH_CHANCE = 0.85
FAILED_CATCH_CHANCE = 0.10
SHINY_FOUND_CHANCE = 0.05
SHINY_CATCH_SUCCESS_CHANCE = 0.07 # 7% success rate per attempt

def now():
    return datetime.datetime.now(datetime.timezone.utc)

def is_staff():
    """A custom decorator check to see if the user has a Staff role ID."""
    def predicate(interaction: discord.Interaction) -> bool:
        staff_role_ids = utils.ROLE_IDS.get("Staff", [])
        if not isinstance(staff_role_ids, list):
            staff_role_ids = [staff_role_ids]
        
        user_role_ids = [role.id for role in interaction.user.roles]
        return any(role_id in user_role_ids for role_id in staff_role_ids)
    return app_commands.check(predicate)

class TreeGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        try:
            game_data = utils.load_tree_game_data()
            self.TREES = game_data.get("trees", {})
            self.COOLDOWNS = game_data.get("cooldowns", {"water": {}, "bug_catch": {}})
        except AttributeError:
            self.TREES = utils.load_tree_of_life_state()
            self.COOLDOWNS = utils.load_user_cooldowns()

        self.COOLDOWN_SECONDS = COOLDOWN_SECONDS
        self.REGULAR_CATCH_CHANCE = REGULAR_CATCH_CHANCE
        self.FAILED_CATCH_CHANCE = FAILED_CATCH_CHANCE
        self.SHINY_FOUND_CHANCE = SHINY_FOUND_CHANCE
        self.SHINY_CATCH_SUCCESS_CHANCE = SHINY_CATCH_SUCCESS_CHANCE
        self.notification_task = None
        
        # The periodic task is now re-enabled
        self.bot.loop.create_task(self.schedule_initial_notification())

    def cog_unload(self):
        if self.notification_task:
            self.notification_task.cancel()

    async def schedule_initial_notification(self):
        await self.bot.wait_until_ready()
        
        server_id = utils.MAIN_GUILD_ID
        
        if str(server_id) in self.TREES:
            tree_state = self.get_tree_state(server_id)
            last_watered_time = datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])
            
            time_until_next = self.COOLDOWN_SECONDS - (now() - last_watered_time).total_seconds()
            
            if time_until_next <= 0:
                time_until_next = self.COOLDOWN_SECONDS
            
            self.schedule_next_notification(time_until_next)

    def schedule_next_notification(self, delay_seconds: float):
        if self.notification_task:
            self.notification_task.cancel()
        self.notification_task = self.bot.loop.create_task(self._send_status_message_after_delay(delay_seconds))

    async def _send_status_message_after_delay(self, delay_seconds: float):
        try:
            await asyncio.sleep(delay_seconds)
            
            channel = self.bot.get_channel(utils.TREE_CHANNEL_ID)
            if not channel:
                print(f"Error: Status channel with ID {utils.TREE_CHANNEL_ID} not found.")
                return

            tree_state = self.get_tree_state(channel.guild.id)
            tree_size = tree_state['height']
            
            last_watered_time = datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])
            time_since_watered = (now() - last_watered_time).total_seconds()
            ready_to_water = time_since_watered > self.COOLDOWN_SECONDS
            
            description_text = f"Our tree is now size **{tree_size}**!\n\n"
            mention_message = ""
            if ready_to_water:
                description_text += "The tree feels a bit parched! 💧 It's time for a refreshing drink and it's buzzing with new life! 🪲"
                mention_message = f"<@&{utils.ROLE_IDS.get('tree_role_id')}>"
            else:
                description_text += "The tree is still hydrated and growing peacefully. 🌳"

            if tree_size < 10:
                image_file = "tree_size_1.png"
            elif 10 <= tree_size <= 20:
                image_file = "tree_size_2.png"
            else:
                image_file = "tree_size_3.png"
            
            embed = discord.Embed(
                title=f"The Server's Tree of Life",
                description=description_text,
                color=discord.Color.green()
            )
            embed.set_image(url=f"attachment://{image_file}")
            
            await channel.send(content=mention_message, file=discord.File(os.path.join(utils.ASSETS_DIR, image_file)), embed=embed)
            
            self.schedule_next_notification(self.COOLDOWN_SECONDS)
        except asyncio.CancelledError:
            pass
            
    def get_tree_state(self, server_id):
        return self.TREES.get(str(server_id), {"height": 0, "last_watered_by": None, "last_watered_timestamp": now().isoformat(), "rank": 0})

    def save_tree_state(self, server_id, state):
        self.TREES[str(server_id)] = state
        game_data = {"trees": self.TREES, "cooldowns": self.COOLDOWNS}
        utils.save_tree_game_data(game_data)

    def is_cooldown_expired(self, user_id, action_type: str):
        last_used_str = self.COOLDOWNS.get(action_type, {}).get(str(user_id))
        if not last_used_str:
            return True
        
        last_used_time = datetime.datetime.fromisoformat(last_used_str)
        time_diff = now() - last_used_time
        
        return time_diff.total_seconds() >= self.COOLDOWN_SECONDS
    
    def update_last_used_time(self, user_id, action_type: str):
        if action_type not in self.COOLDOWNS:
            self.COOLDOWNS[action_type] = {}
        self.COOLDOWNS[action_type][str(user_id)] = now().isoformat()
        game_data = {"trees": self.TREES, "cooldowns": self.COOLDOWNS}
        utils.save_tree_game_data(game_data)
    
    def _format_time_difference(self, seconds: float) -> str:
        if seconds <= 60:
            return "less than a minute"
        
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        
        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
            
        return " ".join(parts)

    class ShinyCatchView(View):
        def __init__(self, cog, interaction: discord.Interaction, bug_info: dict):
            super().__init__(timeout=180)
            self.cog = cog
            self.interaction = interaction
            self.bug_info = bug_info
            self.catch_attempts = 3
            self.message = None
            self.last_attempt_time = now()
            
            catch_button = Button(label="Try to Catch", style=discord.ButtonStyle.secondary)
            catch_button.callback = self.catch_callback
            self.add_item(catch_button)
        
        async def on_timeout(self) -> None:
            if self.message:
                for item in self.children:
                    item.disabled = True
                await self.message.edit(content="The shiny bug has flown away because you ran out of time!", view=self)

        async def catch_callback(self, interaction: discord.Interaction):
            if interaction.user != self.interaction.user:
                return await interaction.response.send_message("Only the person who found this shiny bug can try to catch it!", ephemeral=True)

            await interaction.response.defer()
            
            # Check for per-try timeout
            if (now() - self.last_attempt_time).total_seconds() < 10:
                remaining_time = 10 - (now() - self.last_attempt_time).total_seconds()
                return await interaction.followup.send(f"You must wait {remaining_time:.1f} seconds before your next attempt.", ephemeral=True)

            self.catch_attempts -= 1
            self.last_attempt_time = now()
            user_id = str(interaction.user.id)
            
            bug_collection = load_bug_collection()
            user_data = bug_collection.get(user_id, {"caught": [], "xp": 0, "shinies_caught": []})
            
            if random.random() < self.cog.SHINY_CATCH_SUCCESS_CHANCE:
                caught_bug_name = f"Shiny {self.bug_info['name']}"
                caught_bug_xp = self.bug_info['xp'] * 2
                caught_bug_emoji = self.bug_info['emoji']
                
                user_data['shinies_caught'].append(caught_bug_name)
                user_data['caught'].append(caught_bug_name)
                user_data['xp'] = user_data.get('xp', 0) + caught_bug_xp
                bug_collection[user_id] = user_data
                save_bug_collection(bug_collection)

                embed = discord.Embed(
                    title="🎉 Shiny Catch Successful!",
                    description=f"You successfully caught the **{caught_bug_name}** {caught_bug_emoji} and earned **{caught_bug_xp}** XP!",
                    color=discord.Color.gold()
                )
                embed.set_thumbnail(url=self.bug_info['image_url'])
                
                for item in self.children:
                    item.disabled = True
                
                await interaction.edit_original_response(embed=embed, view=self)
                self.stop()
                return
            
            embed = discord.Embed(
                title=f"The shiny bug dodged your net!",
                description=f"You have **{self.catch_attempts}** attempt(s) left!",
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=self.bug_info['image_url'])
            
            if self.catch_attempts <= 0:
                embed.title = "A shiny bug escaped!"
                embed.description = f"The shiny bug was too quick and flew away! 💨"
                for item in self.children:
                    item.disabled = True
                self.stop()
            
            await interaction.edit_original_response(embed=embed, view=self)

    class TreeGameView(View):
        def __init__(self, cog, interaction: discord.Interaction, tree_state: dict):
            super().__init__(timeout=180)
            self.cog = cog
            self.interaction = interaction
            self.tree_state = tree_state
            
            water_button = Button(label="Water", style=discord.ButtonStyle.primary, emoji="💧")
            water_button.callback = self.water_callback
            self.add_item(water_button)

            bug_catch_button = Button(label="Catch a Bug", style=discord.ButtonStyle.secondary, emoji="🪲")
            bug_catch_button.callback = self.bug_catch_callback
            self.add_item(bug_catch_button)
        
        async def water_callback(self, interaction: discord.Interaction):
            server_id = interaction.guild.id
            tree_state = self.cog.get_tree_state(server_id)
            
            user_cooldown_expired = self.cog.is_cooldown_expired(interaction.user.id, "water")
            tree_cooldown_expired = (now() - datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])).total_seconds() > self.cog.COOLDOWN_SECONDS

            # Defer the response to prevent "Interaction failed" message.
            await interaction.response.defer(ephemeral=True)

            # Check for cooldowns and return a single ephemeral message if not expired.
            if not user_cooldown_expired or not tree_cooldown_expired:
                last_used_time = self.cog.COOLDOWNS.get("water", {}).get(str(interaction.user.id))
                message = ""

                if not user_cooldown_expired:
                    time_diff = now() - datetime.datetime.fromisoformat(last_used_time)
                    remaining_time = self.cog.COOLDOWN_SECONDS - time_diff.total_seconds()
                    formatted_time = self.cog._format_time_difference(remaining_time)
                    message = f"You have already watered the tree recently. You can try again in **{formatted_time}**."
                elif not tree_cooldown_expired:
                    time_diff = now() - datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])
                    remaining_time = self.cog.COOLDOWN_SECONDS - time_diff.total_seconds()
                    formatted_time = self.cog._format_time_difference(remaining_time)
                    message = f"The tree is already wet! You can water it again in **{formatted_time}**."
                
                return await interaction.followup.send(message, ephemeral=True)
            
            # If both cooldowns are expired, proceed with watering the tree.
            # Check if this is the user's first time watering and give them a net
            user_inventory = load_inventory(interaction.user.id)
            if not user_inventory.get('nets'):
                user_inventory['nets'] = [{"name": "Regular Net", "durability": 10}]
                user_inventory['equipped_net'] = "Regular Net"
                save_inventory(interaction.user.id, user_inventory)
                await interaction.channel.send(f"{interaction.user.mention} has received a free **Regular Net** for watering the tree for the first time! 🎣")

            tree_state['height'] += 1
            tree_state['last_watered_by'] = str(interaction.user.id)
            tree_state['last_watered_timestamp'] = now().isoformat()
            self.cog.save_tree_state(server_id, tree_state)
            self.cog.update_last_used_time(interaction.user.id, "water")
            
            # Send a new, separate message to thank the user.
            await interaction.channel.send(f"Thank you for watering the tree, {interaction.user.mention}! The tree is now size {tree_state['height']}. 🌳")

            # Update the original tree embed, but without the buttons.
            tree_image = self.cog._get_tree_image(tree_state['height'])
            
            embed = discord.Embed(
                title=f"The Server's Tree of Life",
                description=f"The tree is currently size **{tree_state['height']}**.\n\n"
                            f"The tree is now hydrated. 🌳",
                color=discord.Color.green()
            )
            embed.set_image(url=f"attachment://{tree_image.filename}")
            
            await interaction.edit_original_response(attachments=[tree_image], embed=embed, view=None)

        async def bug_catch_callback(self, interaction: discord.Interaction):
            server_id = interaction.guild.id
            tree_state = self.cog.get_tree_state(server_id)
            
            # Check for user cooldown for bug catching first
            if not self.cog.is_cooldown_expired(interaction.user.id, "bug_catch"):
                time_diff = now() - datetime.datetime.fromisoformat(self.cog.COOLDOWNS.get("bug_catch", {}).get(str(interaction.user.id)))
                remaining_time = self.cog.COOLDOWN_SECONDS - time_diff.total_seconds()
                formatted_time = self.cog._format_time_difference(remaining_time)
                return await interaction.response.send_message(f"You have already performed an action recently. You can try again in **{formatted_time}**.", ephemeral=True)

            # Defer the response publicly
            await interaction.response.defer()

            # Check tree height before bug catching
            if tree_state['height'] < 10:
                return await interaction.followup.send("The tree is too small to have bugs! Grow it to size 10 first.", ephemeral=False)
            
            # Get a reference to the Bugbook cog
            bugbook_cog = self.cog.bot.get_cog('Bugbook')
            if not bugbook_cog:
                return await interaction.followup.send("❌ An error occurred: Bugbook cog is not loaded.", ephemeral=True)

            # Call the new catch_bug method in the Bugbook cog
            await bugbook_cog.catch_bug(interaction, self.cog, tree_state)
            
            # The cooldown is now updated by the Bugbook cog's catch_bug method

    @app_commands.command(name="tree", description="Interact with the server's Tree of Life.")
    async def tree(self, interaction: discord.Interaction):
        await interaction.response.defer()

        server_id = interaction.guild.id
        tree_state = self.get_tree_state(server_id)
        tree_size = tree_state['height']
        
        water_status = "The tree is currently hydrated. 🌳"
        
        image_file = self._get_tree_image(tree_size)
        
        embed = discord.Embed(
            title=f"The Server's Tree of Life",
            description=f"The tree is currently size **{tree_size}**.\n\n{water_status}",
            color=discord.Color.green()
        )
        embed.set_image(url=f"attachment://{image_file.filename}")
        
        view = self.TreeGameView(self, interaction, tree_state)
        
        await interaction.followup.send(file=image_file, embed=embed, view=view)

    @app_commands.command(name="resettreecooldowns", description="Reset cooldowns for the Tree of Life (Staff only).")
    @is_staff()
    async def resettreecooldowns(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        server_id = interaction.guild.id
        
        # Reset the server-wide cooldown by updating the timestamp
        tree_state = self.get_tree_state(server_id)
        tree_state['last_watered_timestamp'] = (now() - datetime.timedelta(seconds=self.COOLDOWN_SECONDS + 1)).isoformat()
        self.save_tree_state(server_id, tree_state)
        
        # Clear all user cooldowns associated with the tree game
        self.COOLDOWNS = {"water": {}, "bug_catch": {}}
        game_data = {"trees": self.TREES, "cooldowns": self.COOLDOWNS}
        utils.save_tree_game_data(game_data)
        
        await interaction.followup.send("The Tree of Life's cooldowns have been reset. You can now water the tree again.", ephemeral=True)
    
    @resettreecooldowns.error
    async def resettreecooldowns_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("You do not have the required permissions to use this command.", ephemeral=True)


    async def schedule_initial_notification(self):
        await self.bot.wait_until_ready()
        
        server_id = utils.MAIN_GUILD_ID
        
        if str(server_id) in self.TREES:
            tree_state = self.get_tree_state(server_id)
            last_watered_time = datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])
            
            time_until_next = self.COOLDOWN_SECONDS - (now() - last_watered_time).total_seconds()
            
            if time_until_next <= 0:
                time_until_next = self.COOLDOWN_SECONDS
            
            self.schedule_next_notification(time_until_next)

    def schedule_next_notification(self, delay_seconds: float):
        if self.notification_task:
            self.notification_task.cancel()
        self.notification_task = self.bot.loop.create_task(self._send_status_message_after_delay(delay_seconds))

    async def _send_status_message_after_delay(self, delay_seconds: float):
        try:
            await asyncio.sleep(delay_seconds)
            
            channel = self.bot.get_channel(utils.TREE_CHANNEL_ID)
            if not channel:
                print(f"Error: Status channel with ID {utils.TREE_CHANNEL_ID} not found.")
                return

            tree_state = self.get_tree_state(channel.guild.id)
            tree_size = tree_state['height']
            
            last_watered_time = datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])
            time_since_watered = (now() - last_watered_time).total_seconds()
            ready_to_water = time_since_watered > self.COOLDOWN_SECONDS
            
            description_text = f"Our tree is now size **{tree_size}**!\n\n"
            mention_message = ""
            if ready_to_water:
                description_text += "The tree feels a bit parched! 💧 It's time for a refreshing drink and it's buzzing with new life! 🪲"
                mention_message = f"<@&{utils.ROLE_IDS.get('tree_role_id')}>"
            else:
                description_text += "The tree is still hydrated and growing peacefully. 🌳"

            if tree_size < 10:
                image_file = "tree_size_1.png"
            elif 10 <= tree_size <= 20:
                image_file = "tree_size_2.png"
            else:
                image_file = "tree_size_3.png"
            
            embed = discord.Embed(
                title=f"The Server's Tree of Life",
                description=description_text,
                color=discord.Color.green()
            )
            embed.set_image(url=f"attachment://{image_file}")
            
            await channel.send(content=mention_message, file=discord.File(os.path.join(utils.ASSETS_DIR, image_file)), embed=embed)
            
            self.schedule_next_notification(self.COOLDOWN_SECONDS)
        except asyncio.CancelledError:
            pass
            
    def _get_tree_image(self, height: int) -> discord.File:
        """Returns the correct image file for the tree's height."""
        if height < 10:
            image_path = os.path.join(utils.ASSETS_DIR, "tree_size_1.png")
        elif 10 <= height <= 20:
            image_path = os.path.join(utils.ASSETS_DIR, "tree_size_2.png")
        else:
            image_path = os.path.join(utils.ASSETS_DIR, "tree_size_3.png")
        
        if not os.path.exists(image_path):
            print(f"Error: Missing image file at {image_path}")
            return discord.File(os.path.join(utils.ASSETS_DIR, "placeholder.png"))
        
        return discord.File(image_path, filename=os.path.basename(image_path))


async def setup(bot):
    await bot.add_cog(TreeGame(bot))