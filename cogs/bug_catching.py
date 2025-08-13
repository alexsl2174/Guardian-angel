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

async def setup(bot):
    await bot.add_cog(Bugbook(bot))