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

# The now() function is now in utils.py to avoid a circular import.
import cogs.utils as utils
from cogs.BugData import INSECT_LIST, SHINY_INSECT_LIST, load_bug_collection, save_bug_collection
from cogs.bug_catching import load_inventory, save_inventory
from cogs.BugbookViews import BugbookListView, TradeConfirmationView

# --- Game Configuration ---
# All IDs are now read from the centralized config in utils.py
BASE_COOLDOWN_SECONDS = 7200  # 2 hours
MIN_COOLDOWN_SECONDS = 900 # 15 minutes
COOLDOWN_REDUCTION_PER_HEIGHT = 60 # 1 minute per height
COMPOST_REDUCTION_SECONDS = 1800 # 30 minutes
REGULAR_CATCH_CHANCE = 0.85
FAILED_CATCH_CHANCE = 0.10
SHINY_FOUND_CHANCE = 0.05
SHINY_CATCH_SUCCESS_CHANCE = 0.07 # 7% success rate per attempt

HONEY_PER_BEE_PER_HOUR = 1
BEE_DECAY_CHANCE = 0.05 # 5% chance per bug catch attempt for one bee to fly away
MAX_BEEHIVE_CAPACITY = 100
MIN_HIVE_HEIGHT_REQUIRED = 15

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

        self.BASE_COOLDOWN_SECONDS = BASE_COOLDOWN_SECONDS
        self.MIN_COOLDOWN_SECONDS = MIN_COOLDOWN_SECONDS
        self.COOLDOWN_REDUCTION_PER_HEIGHT = COOLDOWN_REDUCTION_PER_HEIGHT
        self.COMPOST_REDUCTION_SECONDS = COMPOST_REDUCTION_SECONDS
        self.REGULAR_CATCH_CHANCE = REGULAR_CATCH_CHANCE
        self.FAILED_CATCH_CHANCE = FAILED_CATCH_CHANCE
        self.SHINY_FOUND_CHANCE = SHINY_FOUND_CHANCE
        self.SHINY_CATCH_SUCCESS_CHANCE = SHINY_CATCH_SUCCESS_CHANCE
        self.HONEY_PER_BEE_PER_HOUR = HONEY_PER_BEE_PER_HOUR
        self.BEE_DECAY_CHANCE = BEE_DECAY_CHANCE
        self.notification_task = None
        
        # Start the notification system
        self.bot.loop.create_task(self.schedule_initial_notification())

    def cog_unload(self):
        if self.notification_task:
            self.notification_task.cancel()

    async def schedule_initial_notification(self):
        await self.bot.wait_until_ready()
        
        server_id = utils.MAIN_GUILD_ID
        
        if str(server_id) in self.TREES:
            tree_state = self.get_tree_state(server_id)
            tree_cooldown = self.get_tree_cooldown(tree_state['height'])
            last_watered_time = datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])
            
            time_until_next = tree_cooldown - (utils.now() - last_watered_time).total_seconds()
            
            if time_until_next <= 0:
                time_until_next = 10  # A small delay to ensure it sends the message after restart.
            
            self.schedule_next_notification(time_until_next)

    def schedule_next_notification(self, delay_seconds: float):
        if self.notification_task:
            print("Canceling existing notification task.")
            self.notification_task.cancel()
        print(f"Scheduling new notification task with a delay of {delay_seconds} seconds.")
        self.notification_task = self.bot.loop.create_task(self._send_status_message_after_delay(delay_seconds))

    async def _send_status_message_after_delay(self, delay_seconds: float):
        try:
            print(f"Notification task initiated. Waiting for {delay_seconds} seconds...")
            await asyncio.sleep(delay_seconds)
            
            print("Waking up! Attempting to send a tree status message.")
            
            channel = self.bot.get_channel(utils.TREE_CHANNEL_ID)
            if not channel:
                print(f"Error: Status channel with ID {utils.TREE_CHANNEL_ID} not found. Notification aborted.")
                return

            print(f"Found channel: {channel.name}. Fetching tree state.")
            tree_state = self.get_tree_state(channel.guild.id)
            tree_size = tree_state['height']
            tree_cooldown = self.get_tree_cooldown(tree_size)
            
            last_watered_time = datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])
            time_since_watered = (utils.now() - last_watered_time).total_seconds()
            ready_to_water = time_since_watered > tree_cooldown
            
            description_text = f"Our tree is now size **{tree_size}**!\n\n"
            mention_message = ""
            if ready_to_water:
                description_text += "The tree feels a bit parched! 💧 It's time for a refreshing drink and it's buzzing with new life! 🪲"
                
                tree_role_id = utils.ROLE_IDS.get('tree_role_id')
                if tree_role_id:
                    mention_message = f"<@&{tree_role_id}>"
                    print(f"Tree is ready to be watered. Mentioning role with ID: {tree_role_id}")
                else:
                    print("Warning: Tree role ID not found in utils.ROLE_IDS. Cannot mention role.")
            else:
                description_text += "The tree is still hydrated and growing peacefully. 🌳"
                print("Tree is not yet ready to be watered. No mention will be sent.")

            image_file = self._get_tree_image(tree_state)
            print(f"Using tree image: {image_file.filename}")
            
            embed = discord.Embed(
                title=f"The Server's Tree of Life",
                description=description_text,
                color=discord.Color.green()
            )
            embed.set_image(url=f"attachment://{image_file.filename}")
            
            await channel.send(content=mention_message, file=image_file, embed=embed)
            print("Notification message sent successfully.")
            
            # Reschedule the task for the next cooldown period
            self.schedule_next_notification(self.get_tree_cooldown(self.get_tree_state(channel.guild.id)['height']))
        
        except asyncio.CancelledError:
            print("Notification task was cancelled. This is expected on bot shutdown or cog reload.")
            pass
        except Exception as e:
            print(f"An unexpected error occurred in the notification task: {e}")

    def get_tree_cooldown(self, height: int) -> float:
        """Calculates the dynamic tree cooldown based on its height."""
        reduction = height * self.COOLDOWN_REDUCTION_PER_HEIGHT
        return max(self.BASE_COOLDOWN_SECONDS - reduction, self.MIN_COOLDOWN_SECONDS)
            
    def get_user_cooldown(self, height: int) -> float:
        """Calculates the dynamic user cooldown based on tree height."""
        reduction = height * self.COOLDOWN_REDUCTION_PER_HEIGHT
        return max(self.BASE_COOLDOWN_SECONDS - reduction, self.MIN_COOLDOWN_SECONDS)
            
    def get_tree_state(self, server_id):
        # Default state now includes beehive information
        default_state = {
            "height": 0,
            "last_watered_by": None,
            "last_watered_timestamp": utils.now().isoformat(),
            "rank": 0,
            "beehive": {
                "is_placed": False,
                "bee_count": 0,
                "last_honey_collected": utils.now().isoformat()
            }
        }
        state = self.TREES.get(str(server_id), default_state)
        # Ensure new keys are added to old state data
        if "beehive" not in state:
            state["beehive"] = default_state["beehive"]
        return state

    def save_tree_state(self, server_id, state):
        self.TREES[str(server_id)] = state
        game_data = {"trees": self.TREES, "cooldowns": self.COOLDOWNS}
        utils.save_tree_game_data(game_data)

    def is_cooldown_expired(self, user_id, action_type: str, tree_height: int):
        last_used_str = self.COOLDOWNS.get(action_type, {}).get(str(user_id))
        if not last_used_str:
            return True
        
        last_used_time = datetime.datetime.fromisoformat(last_used_str)
        time_diff = utils.now() - last_used_time
        
        cooldown = self.get_user_cooldown(tree_height)
        return time_diff.total_seconds() >= cooldown
    
    def update_last_used_time(self, user_id, action_type: str):
        if action_type not in self.COOLDOWNS:
            self.COOLDOWNS[action_type] = {}
        self.COOLDOWNS[action_type][str(user_id)] = utils.now().isoformat()
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
            super().__init__(timeout=300)  # 5 minute timeout instead of None
            self.cog = cog
            self.interaction = interaction
            self.bug_info = bug_info
            self.catch_attempts = 3
            self.message = None
            self.last_attempt_time = utils.now()
            
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
            if (utils.now() - self.last_attempt_time).total_seconds() < 10:
                remaining_time = 10 - (utils.now() - self.last_attempt_time).total_seconds()
                return await interaction.followup.send(f"You must wait {remaining_time:.1f} seconds before your next attempt.", ephemeral=True)

            self.catch_attempts -= 1
            self.last_attempt_time = utils.now()
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
            # Use a normal timeout instead of None to prevent persistent view issues
            super().__init__(timeout=300)  # 5 minute timeout
            self.cog = cog
            self.interaction = interaction
            self.tree_state = tree_state
            
            # Remove custom_ids to avoid persistent view complications
            water_button = Button(label="Water", style=discord.ButtonStyle.primary, emoji="💧")
            water_button.callback = self.water_callback
            self.add_item(water_button)

            bug_catch_button = Button(label="Catch a Bug", style=discord.ButtonStyle.secondary, emoji="🪲")
            bug_catch_button.callback = self.bug_catch_callback
            self.add_item(bug_catch_button)
            
            recycle_button = Button(label="Recycle", style=discord.ButtonStyle.blurple, emoji="♻️")
            recycle_button.callback = self.recycle_callback
            self.add_item(recycle_button)
            
            collect_honey_button = Button(label="Collect Honey", style=discord.ButtonStyle.success, emoji="🍯")
            collect_honey_button.callback = self.collect_honey_callback
            self.add_item(collect_honey_button)
            
            # Disable honey button if there is no beehive or no bees
            beehive_state = tree_state.get('beehive', {})
            has_beehive = beehive_state.get('is_placed', False)
            has_bees = beehive_state.get('bee_count', 0) > 0
            collect_honey_button.disabled = not has_beehive or not has_bees

        async def water_callback(self, interaction: discord.Interaction):
            # DEFER IMMEDIATELY to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            server_id = interaction.guild.id
            tree_state = self.cog.get_tree_state(server_id)
            
            user_cooldown = self.cog.get_user_cooldown(tree_state['height'])
            tree_cooldown = self.cog.get_tree_cooldown(tree_state['height'])
            
            user_cooldown_expired = self.cog.is_cooldown_expired(interaction.user.id, "water", tree_state['height'])
            tree_cooldown_expired = (utils.now() - datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])).total_seconds() > tree_cooldown

            # Check for cooldowns
            if not user_cooldown_expired or not tree_cooldown_expired:
                last_used_time = self.cog.COOLDOWNS.get("water", {}).get(str(interaction.user.id))
                message = ""

                if not user_cooldown_expired:
                    time_diff = utils.now() - datetime.datetime.fromisoformat(last_used_time)
                    remaining_time = user_cooldown - time_diff.total_seconds()
                    formatted_time = self.cog._format_time_difference(remaining_time)
                    message = f"You have already watered the tree recently. You can try again in **{formatted_time}**."
                elif not tree_cooldown_expired:
                    time_diff = utils.now() - datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])
                    remaining_time = tree_cooldown - time_diff.total_seconds()
                    formatted_time = self.cog._format_time_difference(remaining_time)
                    message = f"The tree is already wet! You can water it again in **{formatted_time}**."
                
                return await interaction.followup.send(message, ephemeral=True)
            
            # Check if this is the user's first time watering and give them a net
            user_inventory = load_inventory(interaction.user.id)
            if not user_inventory.get('nets'):
                user_inventory['nets'] = [{"name": "Regular Net", "durability": 10}]
                user_inventory['equipped_net'] = "Regular Net"
                save_inventory(interaction.user.id, user_inventory)
                await interaction.followup.send(f"{interaction.user.mention} has received a free **Regular Net** for watering the tree for the first time! 🎣\n\nTree watered! Tree is now size {tree_state['height'] + 1}. 🌳", ephemeral=False)
            else:
                await interaction.followup.send(f"Thank you for watering the tree, {interaction.user.mention}! The tree is now size {tree_state['height'] + 1}. 🌳", ephemeral=False)

            tree_state['height'] += 1
            tree_state['last_watered_by'] = str(interaction.user.id)
            tree_state['last_watered_timestamp'] = utils.now().isoformat()
            self.cog.save_tree_state(server_id, tree_state)
            self.cog.update_last_used_time(interaction.user.id, "water")

        async def bug_catch_callback(self, interaction: discord.Interaction):
            # DEFER IMMEDIATELY to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            server_id = interaction.guild.id
            tree_state = self.cog.get_tree_state(server_id)
            
            # Check for user cooldown for bug catching first
            if not self.cog.is_cooldown_expired(interaction.user.id, "bug_catch", tree_state['height']):
                time_diff = utils.now() - datetime.datetime.fromisoformat(self.cog.COOLDOWNS.get("bug_catch", {}).get(str(interaction.user.id)))
                remaining_time = self.cog.get_user_cooldown(tree_state['height']) - time_diff.total_seconds()
                formatted_time = self.cog._format_time_difference(remaining_time)
                return await interaction.followup.send(f"You have already performed an action recently. You can try again in **{formatted_time}**.", ephemeral=True)

            # Check tree height before bug catching
            if tree_state['height'] < 10:
                return await interaction.followup.send("The tree is too small to have bugs! Grow it to size 10 first.", ephemeral=True)
            
            # Get a reference to the Bugbook cog
            bugbook_cog = self.cog.bot.get_cog('Bugbook')
            if not bugbook_cog:
                return await interaction.followup.send("❌ An error occurred: Bugbook cog is not loaded.", ephemeral=True)

            # Call the new catch_bug method in the Bugbook cog
            await bugbook_cog.catch_bug(interaction, self.cog, tree_state)
            
            # After a successful bug catch attempt, check for bee decay
            if tree_state['beehive']['is_placed'] and tree_state['beehive']['bee_count'] > 0:
                if random.random() < self.cog.BEE_DECAY_CHANCE:
                    tree_state['beehive']['bee_count'] -= 1
                    self.cog.save_tree_state(server_id, tree_state)
                    # For a full-featured bot, you might send a small notification about a bee flying away.

        async def recycle_callback(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            user_id = interaction.user.id
            user_inventory = load_inventory(user_id)
            
            apples_needed = 10
            current_apples = user_inventory.get('items', {}).get('apple', 0)
            
            if current_apples >= apples_needed:
                user_inventory['items']['apple'] = current_apples - apples_needed
                user_inventory['items']['compost'] = user_inventory.get('items', {}).get('compost', 0) + 1
                save_inventory(user_id, user_inventory)
                await interaction.followup.send(f"✅ You have recycled 10 apples into 1 compost! You now have **{user_inventory['items']['compost']}** compost.", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ You need 10 apples to create compost. You currently have **{current_apples}**.", ephemeral=True)

        async def collect_honey_callback(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            server_id = interaction.guild.id
            tree_state = self.cog.get_tree_state(server_id)
            beehive_state = tree_state['beehive']
            
            if not beehive_state['is_placed'] or beehive_state['bee_count'] <= 0:
                return await interaction.followup.send("❌ There is no beehive or no bees to collect honey from!", ephemeral=True)
                
            last_collected_time = datetime.datetime.fromisoformat(beehive_state['last_honey_collected'])
            time_since_last_collection = (utils.now() - last_collected_time).total_seconds()
            
            # Calculate honey produced
            honey_produced = math.floor((time_since_last_collection / 3600) * beehive_state['bee_count'] * self.cog.HONEY_PER_BEE_PER_HOUR)
            
            if honey_produced <= 0:
                return await interaction.followup.send("The bees haven't produced any new honey yet. Check back later!", ephemeral=True)
            
            user_inventory = load_inventory(interaction.user.id)
            user_inventory['items']['honey'] = user_inventory.get('items', {}).get('honey', 0) + honey_produced
            save_inventory(interaction.user.id, user_inventory)
            
            # Update the last collection timestamp
            beehive_state['last_honey_collected'] = utils.now().isoformat()
            self.cog.save_tree_state(server_id, tree_state)
            
            await interaction.followup.send(f"🍯 You collected **{honey_produced}** honey! You now have **{user_inventory['items']['honey']}** honey in total.", ephemeral=True)

    @app_commands.command(name="tree", description="Interact with the server's Tree of Life.")
    async def tree(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        server_id = interaction.guild.id
        tree_state = self.get_tree_state(server_id)
        tree_size = tree_state['height']
        
        # Calculate dynamic cooldowns
        tree_cooldown = self.get_tree_cooldown(tree_size)
        
        # Calculate time remaining for the tree cooldown
        time_since_watered = (utils.now() - datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])).total_seconds()
        remaining_tree_cooldown = tree_cooldown - time_since_watered
        
        if remaining_tree_cooldown > 0:
            cooldown_end_time = datetime.datetime.fromisoformat(tree_state['last_watered_timestamp']) + datetime.timedelta(seconds=tree_cooldown)
            cooldown_end_timestamp = int(cooldown_end_time.timestamp())
            water_status = f"The tree is currently hydrated. You can water it again <t:{cooldown_end_timestamp}:R>."
        else:
            water_status = "The tree is ready to be watered! 💧"
        
        # Get tree image
        image_file = self._get_tree_image(tree_state)
        
        # Create embed
        embed = discord.Embed(
            title=f"The Server's Tree of Life",
            description=f"The tree is currently size **{tree_size}**.\n\n{water_status}",
            color=discord.Color.green()
        )
        embed.set_image(url=f"attachment://{image_file.filename}")
        
        beehive_status = "Not Placed"
        beehive_state = tree_state.get('beehive', {})
        if beehive_state.get('is_placed'):
            bee_count = beehive_state.get('bee_count', 0)
            beehive_status = f"Placed! 🍯 There are **{bee_count}** bees!"
        
        embed.add_field(name="Beehive", value=beehive_status, inline=False)
        
        # Create simple view with buttons
        view = self.TreeGameView(self, interaction, tree_state)
        
        await interaction.followup.send(
            file=image_file, 
            embed=embed, 
            view=view
        )
    
    @app_commands.command(name="compost", description="Reduce the Tree of Life's cooldown using compost.")
    async def compost(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        user_inventory = load_inventory(user_id)
        
        current_compost = user_inventory.get('items', {}).get('compost', 0)
        
        if current_compost >= 1:
            user_inventory['items']['compost'] = current_compost - 1
            save_inventory(user_id, user_inventory)
            
            server_id = interaction.guild.id
            tree_state = self.get_tree_state(server_id)
            
            last_watered_time = datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])
            
            # --- FIX: Subtract COMPOST_REDUCTION_SECONDS instead of adding them ---
            new_last_watered_time = last_watered_time - datetime.timedelta(seconds=self.COMPOST_REDUCTION_SECONDS)
            # --- END OF FIX ---
            
            # Ensure the new time does not go past the current time.
            if new_last_watered_time > utils.now():
                tree_state['last_watered_timestamp'] = utils.now().isoformat()
            else:
                tree_state['last_watered_timestamp'] = new_last_watered_time.isoformat()
            
            self.save_tree_state(server_id, tree_state)
            
            await interaction.followup.send(f"✅ You have used 1 compost to reduce the tree's cooldown by 30 minutes. You have **{user_inventory['items']['compost']}** compost remaining.", ephemeral=True)
        else:
            await interaction.followup.send("❌ You don't have any compost to use!", ephemeral=True)
    
    @app_commands.command(name="beehive", description="Set up a beehive or add bees to it.")
    @app_commands.describe(add_bees="The number of bees you want to add. Leave blank to set up a new beehive.")
    async def beehive(self, interaction: discord.Interaction, add_bees: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        user_inventory = load_inventory(interaction.user.id)
        server_id = interaction.guild.id
        tree_state = self.get_tree_state(server_id)

        # Scenario 1: User wants to add bees
        if add_bees is not None:
            if not tree_state['beehive']['is_placed']:
                return await interaction.followup.send("❌ There is no beehive placed on the Tree of Life. You need to set one up first.", ephemeral=True)
            
            if add_bees <= 0:
                return await interaction.followup.send("Please specify a number greater than 0 to add bees.", ephemeral=True)

            if add_bees > user_inventory.get('items', {}).get('bees', 0):
                return await interaction.followup.send(f"❌ You don't have enough bees! You have **{user_inventory.get('items', {}).get('bees', 0)}** bees, but you tried to add **{add_bees}**.", ephemeral=True)

            new_bee_count = tree_state['beehive']['bee_count'] + add_bees
            if new_bee_count > MAX_BEEHIVE_CAPACITY:
                return await interaction.followup.send(f"❌ The beehive can only hold a maximum of **{MAX_BEEHIVE_CAPACITY}** bees! You tried to add too many.", ephemeral=True)
            
            user_inventory['items']['bees'] -= add_bees
            tree_state['beehive']['bee_count'] = new_bee_count
            
            save_inventory(interaction.user.id, user_inventory)
            self.save_tree_state(server_id, tree_state)
            
            await interaction.followup.send(f"✅ You have added **{add_bees}** bees to the beehive. There are now **{new_bee_count}** bees in the hive!", ephemeral=False)
        
        # Scenario 2: User wants to set up a beehive
        else:
            if tree_state['height'] < MIN_HIVE_HEIGHT_REQUIRED:
                return await interaction.followup.send(f"❌ The Tree of Life must be at least size {MIN_HIVE_HEIGHT_REQUIRED} to support a beehive.", ephemeral=True)
                
            if tree_state['beehive']['is_placed']:
                return await interaction.followup.send("❌ There is already a beehive on the Tree of Life.", ephemeral=True)
                
            if user_inventory.get('items', {}).get('beehive', 0) < 1:
                return await interaction.followup.send("❌ You need to purchase a beehive first to add it to the tree.", ephemeral=True)

            user_inventory['items']['beehive'] -= 1
            tree_state['beehive']['is_placed'] = True
            tree_state['beehive']['last_honey_collected'] = utils.now().isoformat()
            
            save_inventory(interaction.user.id, user_inventory)
            self.save_tree_state(server_id, tree_state)
            
            await interaction.followup.send("✅ You have successfully placed a beehive on the Tree of Life! You can now add bees to it with `/beehive add_bees <amount>`.", ephemeral=False)
            
    @app_commands.command(name="resettreecooldowns", description="Reset cooldowns for the Tree of Life (Staff only).")
    @is_staff()
    async def resettreecooldowns(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        server_id = interaction.guild.id
        
        # Reset the server-wide cooldown by updating the timestamp
        tree_state = self.get_tree_state(server_id)
        tree_state['last_watered_timestamp'] = (utils.now() - datetime.timedelta(seconds=self.get_tree_cooldown(tree_state['height']) + 1)).isoformat()
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
            
    def _get_tree_image(self, tree_state: dict) -> discord.File:
        """Returns the correct image file for the tree's height."""
        height = tree_state['height']
        beehive_placed = tree_state['beehive']['is_placed']
        
        if beehive_placed and height > 20:
            image_path = os.path.join(utils.ASSETS_DIR, "tree_size_3_bee.png")
        elif height < 10:
            image_path = os.path.join(utils.ASSETS_DIR, "tree_size_1.png")
        elif 10 <= height <= 20:
            image_path = os.path.join(utils.ASSETS_DIR, "tree_size_2.png")
        else: # height > 20
            image_path = os.path.join(utils.ASSETS_DIR, "tree_size_3.png")
        
        if not os.path.exists(image_path):
            print(f"Error: Missing image file at {image_path}")
            return discord.File(os.path.join(utils.ASSETS_DIR, "placeholder.png"))
        
        return discord.File(image_path, filename=os.path.basename(image_path))


async def setup(bot):
    await bot.add_cog(TreeGame(bot))
