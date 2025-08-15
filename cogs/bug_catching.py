import discord
from discord.ext import commands
from discord.ui import Button, View, Select
from discord import app_commands
import os
import json
import math
from typing import List, Dict, Any, Union, Optional
import datetime
import random
import cogs.utils as utils
from cogs.BugData import INSECT_LIST, SHINY_INSECT_LIST, load_bug_collection, save_bug_collection
from cogs.BugbookViews import BugbookListView, TradeConfirmationView

# The file to store user inventory data
INVENTORY_FILE = os.path.join("data", "user_inventory.json")
SHOP_ITEMS_FILE = os.path.join("data", "shop_items.json")

def load_inventory(user_id: int) -> Dict[str, Any]:
    inventory_data = utils.load_data(INVENTORY_FILE, {})
    user_inventory = inventory_data.get(str(user_id), {"nets": [{"name": "Basic Net", "durability": 10}], "equipped_net": "Basic Net"})
    return user_inventory

def save_inventory(user_id: int, inventory: Dict[str, Any]):
    inventory_data = utils.load_data(INVENTORY_FILE, {})
    inventory_data[str(user_id)] = inventory
    utils.save_data(inventory_data, INVENTORY_FILE)

def load_shop_items():
    return utils.load_data(SHOP_ITEMS_FILE, [])

class Bugbook(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.INSECT_LIST = INSECT_LIST
        self.SHINY_INSECT_LIST = SHINY_INSECT_LIST
        self.bugs_per_page = 10
        self.SHINY_FOUND_CHANCE = 0.05
        self.REGULAR_CATCH_CHANCE = 0.85
        self.SHINY_CATCH_SUCCESS_CHANCE = 0.07

    class ShinyCatchView(View):
        def __init__(self, cog, interaction: discord.Interaction, bug_info: dict):
            super().__init__(timeout=180)
            self.cog = cog
            self.interaction = interaction
            self.bug_info = bug_info
            self.catch_attempts = 3
            self.message = None
            self.last_attempt_time = datetime.datetime.now(datetime.timezone.utc)
            
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
            if (datetime.datetime.now(datetime.timezone.utc) - self.last_attempt_time).total_seconds() < 10:
                remaining_time = 10 - (datetime.datetime.now(datetime.timezone.utc) - self.last_attempt_time).total_seconds()
                return await interaction.followup.send(f"You must wait {remaining_time:.1f} seconds before your next attempt.", ephemeral=True)

            self.catch_attempts -= 1
            self.last_attempt_time = datetime.datetime.now(datetime.timezone.utc)
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

    bugbook_group = app_commands.Group(name="bugbook", description="Commands for your bug collection.")

    async def _autocomplete_my_bugs(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        user_id = str(interaction.user.id)
        bug_collection = load_bug_collection()
        user_data = bug_collection.get(user_id, {"caught": []})
        caught_bugs = user_data.get('caught', [])
        unique_bugs = sorted(list(set(caught_bugs)))
        
        return [
            app_commands.Choice(name=bug, value=bug)
            for bug in unique_bugs if current.lower() in bug.lower()
        ][:25]

    async def _autocomplete_their_bugs(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        target_user = interaction.namespace.target_user
        if not target_user:
            return []

        bug_collection = load_bug_collection()
        target_user_data = bug_collection.get(str(target_user.id), {"caught": []})
        caught_bugs = target_user_data.get('caught', [])
        unique_bugs = sorted(list(set(caught_bugs)))

        return [
            app_commands.Choice(name=bug, value=bug)
            for bug in unique_bugs if current.lower() in bug.lower()
        ][:25]

    async def _autocomplete_nets(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        user_id = int(interaction.user.id)
        inventory = load_inventory(user_id)
        nets_list = inventory.get("nets", [])
        
        # We need to get the net names from the list of dictionaries and ensure they are unique
        net_names = sorted(list(set([
            net['name'] for net in nets_list 
            if isinstance(net, dict) and 'name' in net
        ])))

        # Filter the nets based on the current user input
        matching_nets = [net for net in net_names if current.lower() in net.lower()]
        
        # Create a list of app_commands.Choice objects
        choices = [app_commands.Choice(name=net, value=net) for net in matching_nets]
        
        return choices[:25]

    @app_commands.command(name="equip_net", description="Equip a bug net from your inventory.")
    @app_commands.describe(net="The name of the net to equip.")
    @app_commands.autocomplete(net=_autocomplete_nets)
    async def equip_net(self, interaction: discord.Interaction, net: str):
        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)
        inventory = load_inventory(int(user_id))
        
        # We need to check if the net name exists in the inventory list of dictionaries
        nets_list = inventory.get("nets", [])
        if not any(net_item['name'] == net for net_item in nets_list):
            await interaction.followup.send(f"❌ You don't own a net named **{net}**!", ephemeral=True)
            return

        inventory["equipped_net"] = net
        save_inventory(int(user_id), inventory)

        await interaction.followup.send(f"✅ You have equipped the **{net}**!", ephemeral=True)

    @bugbook_group.command(name="profile", description="View your or another user's bugbook profile.")
    @app_commands.describe(user="The user whose bug book to view.")
    async def bugbook_profile(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        await interaction.response.defer()
        target_user = user or interaction.user
        user_id = str(target_user.id)
        bug_collection = load_bug_collection()
        user_data = bug_collection.get(user_id, {"caught": [], "xp": 0, "shinies_caught": []})
        caught_bugs = user_data.get('caught', [])
        if not caught_bugs:
            embed = discord.Embed(
                title=f"Bug Book for {target_user.display_name}",
                description="This bug book is empty! Go catch some insects at the Tree of Life! 🪲",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed)
        total_xp = user_data.get('xp', 0)
        total_bugs = len(caught_bugs)
        unique_bugs_count = len(set(caught_bugs))
        last_caught_name = caught_bugs[-1] if caught_bugs else "None"
        
        # Check for shiny bug and retrieve the correct emoji
        is_shiny = "Shiny " in last_caught_name
        bug_list_to_check = self.SHINY_INSECT_LIST if is_shiny else self.INSECT_LIST
        last_caught_info = next((i for i in bug_list_to_check if i['name'] == last_caught_name), None)
        
        last_caught_emoji = last_caught_info['emoji'] if last_caught_info else "⭐"
        
        embed = discord.Embed(
            title=f"Bug Book for {target_user.display_name}",
            description=f"They have caught **{unique_bugs_count} unique** insects!",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.add_field(name="Last Insect Caught", value=f"{last_caught_emoji} {last_caught_name}", inline=False)
        embed.add_field(name="Total 🪲", value=f"{total_bugs}", inline=True)
        embed.add_field(name="Total XP from Bugs", value=f"✨ {total_xp}", inline=True)
        await interaction.followup.send(embed=embed)
    
    @bugbook_group.command(name="list", description="List your or another user's caught bugs.")
    @app_commands.describe(user="The user whose bug book to view.", page="The page number to view.")
    async def bugbook_list(self, interaction: discord.Interaction, user: Optional[discord.Member] = None, page: int = 1):
        await interaction.response.defer()
        target_user = user or interaction.user
        user_id = str(target_user.id)
        bug_collection = load_bug_collection()
        user_data = bug_collection.get(user_id, {"caught": [], "xp": 0, "shinies_caught": []})
        caught_bugs = user_data.get('caught', [])
        if not caught_bugs:
            embed = discord.Embed(
                title=f"Bug Book for {target_user.display_name}",
                description="This bug book is empty! Go catch some insects at the Tree of Life! 🪲",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed)
        unique_bugs = list(dict.fromkeys(caught_bugs))
        bugs_per_page = 10
        total_unique_bugs = len(unique_bugs)
        total_pages = math.ceil(total_unique_bugs / bugs_per_page)
        if not 1 <= page <= total_pages:
            return await interaction.followup.send(f"Invalid page number. Please enter a number between 1 and {total_pages}.", ephemeral=True)
        
        view = BugbookListView(
            target_user=target_user,
            unique_bugs=unique_bugs,
            total_unique_bugs=total_unique_bugs,
            bugs_per_page=bugs_per_page,
            total_pages=total_pages,
            cog=self
        )
        view.current_page = page
        
        initial_embed = await view.get_page_embed()
        
        await interaction.followup.send(embed=initial_embed, view=view)

    @bugbook_group.command(name="trade", description="Trade a bug with another user.")
    @app_commands.describe(
        target_user="The user you want to trade with.",
        your_bug="The bug you are offering (for trade).",
        their_bug="The bug you want in return (for trade)."
    )
    @app_commands.autocomplete(
        your_bug=_autocomplete_my_bugs,
        their_bug=_autocomplete_their_bugs
    )
    async def bugbook_trade(self, interaction: discord.Interaction, target_user: discord.Member, your_bug: str, their_bug: str):
        await interaction.response.defer()
        if interaction.user.id == target_user.id:
            return await interaction.followup.send("You cannot trade with yourself!", ephemeral=True)
        bug_collection = load_bug_collection()
        user_id = str(interaction.user.id)
        target_id = str(target_user.id)
        user_data = bug_collection.get(user_id, {"caught": []})
        target_data = bug_collection.get(target_id, {"caught": []})
        user_bugs = user_data.get('caught', [])
        target_bugs = target_data.get('caught', [])
        if your_bug not in user_bugs:
            return await interaction.followup.send(f"You don't own a **{your_bug}** to trade!", ephemeral=True)
        if their_bug not in target_bugs:
            return await interaction.followup.send(f"**{target_user.display_name}** does not own a **{their_bug}**!", ephemeral=True)
        
        # Check for shiny bug and retrieve the correct emoji
        is_your_bug_shiny = "Shiny " in your_bug
        is_their_bug_shiny = "Shiny " in their_bug
        your_bug_list_to_check = self.SHINY_INSECT_LIST if is_your_bug_shiny else self.INSECT_LIST
        their_bug_list_to_check = self.SHINY_INSECT_LIST if is_their_bug_shiny else self.INSECT_LIST
        
        your_bug_info = next((i for i in your_bug_list_to_check if i['name'] == your_bug), None)
        their_bug_info = next((i for i in their_bug_list_to_check if i['name'] == their_bug), None)
        
        your_bug_emoji = your_bug_info['emoji'] if your_bug_info else "⭐"
        their_bug_emoji = their_bug_info['emoji'] if their_bug_info else "⭐"
        
        embed = discord.Embed(
            title="🤝 Bug Trade Proposal",
            description=f"**{interaction.user.display_name}** wants to trade with **{target_user.display_name}**!",
            color=discord.Color.gold()
        )
        embed.add_field(name=f"{interaction.user.display_name}'s Offer", value=f"{your_bug_emoji} {your_bug}", inline=True)
        embed.add_field(name=f"{target_user.display_name}'s Offer", value=f"{their_bug_emoji} {their_bug}", inline=True)
        embed.set_footer(text=f"This trade expires in 3 minutes.")
        view = TradeConfirmationView(bot=self.bot, proposer=interaction.user, target=target_user, proposer_bug=your_bug, target_bug=their_bug)
        message = await interaction.followup.send(content=f"{target_user.mention}, you have a trade offer!", embed=embed, view=view)
        view.message = message

    async def catch_bug(self, interaction: discord.Interaction, tree_cog, tree_state: dict):
        user_id = str(interaction.user.id)
        bug_collection = load_bug_collection()
        user_data = bug_collection.get(user_id, {"caught": [], "xp": 0, "shinies_caught": []})
        
        roll = random.random()

        if roll < tree_cog.SHINY_FOUND_CHANCE:
            caught_bug_info = random.choice(self.INSECT_LIST)
            
            embed = discord.Embed(
                title=f"A shiny bug appeared!",
                description=f"A shiny **{caught_bug_info['name']}** {caught_bug_info['emoji']} has appeared! It looks very rare! You must try to catch it!",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=caught_bug_info['image_url'])

            view = Bugbook.ShinyCatchView(tree_cog, interaction, caught_bug_info)
            message = await interaction.followup.send(embed=embed, view=view)
            view.message = message
        
        elif roll < tree_cog.SHINY_FOUND_CHANCE + tree_cog.REGULAR_CATCH_CHANCE:
            caught_bug_info = random.choice(self.INSECT_LIST)
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
        
        # Update user cooldown after a bug catching attempt
        tree_cog.update_last_used_time(interaction.user.id, "bug_catch")

async def setup(bot):
    await bot.add_cog(Bugbook(bot))