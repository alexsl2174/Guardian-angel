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
from cogs.BugbookViews import BugbookListView, TradeConfirmationView

# --- Game Configuration ---
# All IDs are now read from the centralized config in utils.py
COOLDOWN_SECONDS = 7200  # 2 hours
REGULAR_CATCH_CHANCE = 0.85
FAILED_CATCH_CHANCE = 0.10
SHINY_FOUND_CHANCE = 0.05
SHINY_CATCH_SUCCESS_CHANCE = 0.50

def now():
    return datetime.datetime.now(datetime.timezone.utc)

class TreeGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        try:
            game_data = utils.load_tree_game_data()
            self.TREES = game_data.get("trees", {})
            self.LAST_USED_TIMES = game_data.get("user_cooldowns", {})
        except AttributeError:
            self.TREES = utils.load_tree_of_life_state()
            self.LAST_USED_TIMES = utils.load_last_used_times()

        self.COOLDOWN_SECONDS = COOLDOWN_SECONDS
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
            
            channel = self.bot.get_channel(utils.STATUS_CHANNEL_ID)
            if not channel:
                print(f"Error: Status channel with ID {utils.STATUS_CHANNEL_ID} not found.")
                return

            tree_state = self.get_tree_state(channel.guild.id)
            tree_size = tree_state['height']
            
            last_watered_time = datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])
            time_since_watered = (now() - last_watered_time).total_seconds()
            ready_to_water = time_since_watered > self.COOLDOWN_SECONDS
            
            description_text = f"Our tree is now size **{tree_size}**!\n\n"
            if ready_to_water:
                description_text += "The tree feels a bit parched! 💧 It's time for a refreshing drink and it's buzzing with new life! 🪲"
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
            
            await channel.send(file=discord.File(os.path.join(utils.ASSETS_DIR, image_file)), embed=embed)
            
            self.schedule_next_notification(self.COOLDOWN_SECONDS)
        except asyncio.CancelledError:
            pass
            
    def get_tree_state(self, server_id):
        return self.TREES.get(str(server_id), {"height": 0, "last_watered_by": None, "last_watered_timestamp": now().isoformat(), "rank": 0})

    def save_tree_state(self, server_id, state):
        self.TREES[str(server_id)] = state
        game_data = {"trees": self.TREES, "user_cooldowns": self.LAST_USED_TIMES}
        try:
            utils.save_tree_game_data(game_data)
        except AttributeError:
            utils.save_tree_of_life_state(server_id, state)

    def is_cooldown_expired(self, user_id):
        last_used_str = self.LAST_USED_TIMES.get(str(user_id))
        if not last_used_str:
            return True
        
        last_used_time = datetime.datetime.fromisoformat(last_used_str)
        time_diff = now() - last_used_time
        
        return time_diff.total_seconds() >= self.COOLDOWN_SECONDS
    
    def update_last_used_time(self, user_id):
        self.LAST_USED_TIMES[str(user_id)] = now().isoformat()
        game_data = {"trees": self.TREES, "user_cooldowns": self.LAST_USED_TIMES}
        try:
            utils.save_tree_game_data(game_data)
        except AttributeError:
            utils.save_last_used_times(self.LAST_USED_TIMES)
    
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
            
            catch_button = Button(label="Try to Catch", style=discord.ButtonStyle.secondary)
            catch_button.callback = self.catch_callback
            self.add_item(catch_button)

        async def catch_callback(self, interaction: discord.Interaction):
            await interaction.response.defer()
            user_id = str(interaction.user.id)
            
            bug_collection = load_bug_collection()
            user_data = bug_collection.get(user_id, {"caught": [], "xp": 0, "shinies_caught": []})
            
            if random.random() < SHINY_CATCH_SUCCESS_CHANCE:
                caught_bug_name = f"✨ Shiny {self.bug_info['name']}"
                caught_bug_xp = self.bug_info['xp'] * 2
                caught_bug_emoji = self.bug_info['emoji']
                
                user_data['shinies_caught'].append(caught_bug_name)
                user_data['caught'].append(caught_bug_name)
                user_data['xp'] = user_data.get('xp', 0) + caught_bug_xp
                save_bug_collection(bug_collection)

                embed = discord.Embed(
                    title="🎉 Shiny Catch Successful!",
                    description=f"You successfully caught the **{caught_bug_name}** {caught_bug_emoji} and earned **{caught_bug_xp}** XP!",
                    color=discord.Color.gold()
                )
                embed.set_thumbnail(url=self.bug_info['image_url'])
            else:
                caught_bug_name = f"Shiny {self.bug_info['name']}"
                embed = discord.Embed(
                    title=f"A shiny bug escaped!",
                    description=f"The shiny **{caught_bug_name}** was too quick and flew away! 💨",
                    color=discord.Color.red()
                )
                embed.set_thumbnail(url=self.bug_info['image_url'])
            
            for item in self.children:
                item.disabled = True
            
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
        
        async def update_buttons(self):
            user_cooldown_expired = self.cog.is_cooldown_expired(self.interaction.user.id)
            tree_cooldown_expired = (now() - datetime.datetime.fromisoformat(self.tree_state['last_watered_timestamp'])).total_seconds() > self.cog.COOLDOWN_SECONDS
            
            for item in self.children:
                if isinstance(item, Button):
                    if item.label == "Water":
                        item.disabled = not (user_cooldown_expired and tree_cooldown_expired)
                    elif item.label == "Catch a Bug":
                        item.disabled = not user_cooldown_expired or self.tree_state['height'] < 10
            
            await self.interaction.edit_original_response(view=self)

        async def water_callback(self, interaction: discord.Interaction):
            server_id = interaction.guild.id
            tree_state = self.cog.get_tree_state(server_id)
            
            user_cooldown_expired = self.cog.is_cooldown_expired(interaction.user.id)
            tree_cooldown_expired = (now() - datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])).total_seconds() > self.cog.COOLDOWN_SECONDS

            if not user_cooldown_expired:
                time_diff = now() - datetime.datetime.fromisoformat(self.cog.LAST_USED_TIMES.get(str(interaction.user.id)))
                remaining_time = self.cog.COOLDOWN_SECONDS - time_diff.total_seconds()
                formatted_time = self.cog._format_time_difference(remaining_time)
                return await interaction.response.send_message(f"You have already performed an action recently. You can try again in **{formatted_time}**.", ephemeral=False)
            
            if not tree_cooldown_expired:
                time_diff = now() - datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])
                remaining_time = self.cog.COOLDOWN_SECONDS - time_diff.total_seconds()
                formatted_time = self.cog._format_time_difference(remaining_time)
                return await interaction.response.send_message(f"The tree is already wet! You can water it again in **{formatted_time}**.", ephemeral=False)
            
            tree_state['height'] += 1
            tree_state['last_watered_by'] = str(interaction.user.id)
            tree_state['last_watered_timestamp'] = now().isoformat()
            self.cog.save_tree_state(server_id, tree_state)
            self.cog.update_last_used_time(interaction.user.id)
            
            await interaction.response.send_message(f"You watered the server's tree! It's now size {tree_state['height']}.", ephemeral=False)
            await self._update_message_content(interaction)
            
            original_message = await interaction.original_response()
            new_view = self.cog.TreeGameView(self.cog, interaction, tree_state)
            await original_message.edit(view=new_view)


        async def bug_catch_callback(self, interaction: discord.Interaction):
            await interaction.response.defer()
            user_id = str(interaction.user.id)
            
            bug_collection = load_bug_collection()
            user_data = bug_collection.get(user_id, {"caught": [], "xp": 0, "shinies_caught": []})

            roll = random.random()
            
            if self.tree_state['height'] < 10:
                await interaction.followup.send("The tree is too small to have bugs! Grow it to size 10 first.", ephemeral=False)
                return
            
            if roll < SHINY_FOUND_CHANCE:
                caught_bug_info = random.choice(INSECT_LIST)
                
                embed = discord.Embed(
                    title=f"A shiny bug appeared!",
                    description=f"A shiny **{caught_bug_info['name']}** {caught_bug_info['emoji']} has appeared! It looks very rare! You must try to catch it!",
                    color=discord.Color.gold()
                )
                embed.set_thumbnail(url=caught_bug_info['image_url'])

                view = self.cog.ShinyCatchView(self.cog, interaction, caught_bug_info)
                await interaction.followup.send(embed=embed, view=view)
            
            elif roll < SHINY_FOUND_CHANCE + REGULAR_CATCH_CHANCE:
                caught_bug_info = random.choice(INSECT_LIST)
                caught_bug_name = caught_bug_info['name']
                caught_bug_xp = caught_bug_info['xp']
                caught_bug_emoji = caught_bug_info['emoji']
                
                user_data['caught'].append(caught_bug_name)
                user_data['xp'] = user_data.get('xp', 0) + caught_bug_xp
                bug_collection[user_id] = user_data
                save_bug_collection(bug_collection)
                
                embed = discord.Embed(
                    title=f"You caught a bug!",
                    description=f"You found a **{caught_bug_name}** {caught_bug_emoji} and earned **{caught_bug_xp}** XP!",
                    color=discord.Color.blue()
                )
                embed.set_thumbnail(url=caught_bug_info['image_url'])
                await interaction.followup.send(embed=embed)
            
            else:
                await interaction.followup.send("You tried to catch a bug, but it got away!")
    
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
        
        await view.update_buttons()

        await interaction.followup.send(file=image_file, embed=embed, view=view)


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
            
            channel = self.bot.get_channel(utils.STATUS_CHANNEL_ID)
            if not channel:
                print(f"Error: Status channel with ID {utils.STATUS_CHANNEL_ID} not found.")
                return

            tree_state = self.get_tree_state(channel.guild.id)
            tree_size = tree_state['height']
            
            last_watered_time = datetime.datetime.fromisoformat(tree_state['last_watered_timestamp'])
            time_since_watered = (now() - last_watered_time).total_seconds()
            ready_to_water = time_since_watered > self.COOLDOWN_SECONDS
            
            description_text = f"Our tree is now size **{tree_size}**!\n\n"
            if ready_to_water:
                description_text += "The tree feels a bit parched! 💧 It's time for a refreshing drink and it's buzzing with new life! 🪲"
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
            
            await channel.send(file=discord.File(os.path.join(utils.ASSETS_DIR, image_file)), embed=embed)
            
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