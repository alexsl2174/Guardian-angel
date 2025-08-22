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
    # Initialize the 'stars' key if it doesn't exist
    if 'stars' not in user_inventory:
        user_inventory['stars'] = 0
    # Initialize the 'items' dictionary if it doesn't exist
    if 'items' not in user_inventory:
        user_inventory['items'] = {}
    if 'apple' not in user_inventory['items']:
        user_inventory['items']['apple'] = 0
    if 'compost' not in user_inventory['items']:
        user_inventory['items']['compost'] = 0
    if 'beehive' not in user_inventory['items']:
        user_inventory['items']['beehive'] = 0
    if 'bees' not in user_inventory['items']:
        user_inventory['items']['bees'] = 0
    if 'honey' not in user_inventory['items']:
        user_inventory['items']['honey'] = 0
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
        self.FAIRY_GRANT_CHANCE = 0.10
        # Night time is from 8 PM to 6 AM UTC
        self.NIGHT_HOURS_UTC = (20, 6)
        self.MIN_APPLES_PER_CATCH = 1
        self.MAX_APPLES_PER_CATCH = 3
        # New net catch chances
        self.NET_CATCH_CHANCES = {
            "Basic Net": 0.85,
            "Regular Net": 0.90,
            "Strong Net": 0.95,
            "Master Net": 0.99
        }

    class ShinyCatchView(View):
        def __init__(self, cog, interaction: discord.Interaction, bug_info: dict):
            # Set timeout to None to make the view permanent
            super().__init__(timeout=None)
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
        
        # Load user inventory to check for the cat and stars
        user_inventory = load_inventory(target_user.id)
        
        if not caught_bugs:
            # Check for cat and stars even if bug book is empty
            if not user_inventory.get('items', {}).get('caught cat') and user_inventory.get('stars', 0) == 0:
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
        
        # Add a field for the last caught bug, if any
        if caught_bugs:
            embed.add_field(name="Last Insect Caught", value=f"{last_caught_emoji} {last_caught_name}", inline=False)
        
        # Add the dedicated "Caught a Cat" and "Stars" field if the item exists in the inventory
        if user_inventory.get('items', {}).get('caught cat'):
            embed.add_field(name="Caught a Cat", value="🐱 **Yes!**", inline=False)
        
        if user_inventory.get('stars', 0) > 0:
            embed.add_field(name="Stars Collected", value=f"✨ **{user_inventory['stars']}**", inline=False)
        
        # Add a field for apples and compost
        apples_count = user_inventory.get('items', {}).get('apple', 0)
        compost_count = user_inventory.get('items', {}).get('compost', 0)
        honey_count = user_inventory.get('items', {}).get('honey', 0)
        
        resource_text = f"🍎 Apples: **{apples_count}**\n♻️ Compost: **{compost_count}**"
        if honey_count > 0:
            resource_text += f"\n🍯 Honey: **{honey_count}**"
        
        if apples_count > 0 or compost_count > 0 or honey_count > 0:
            embed.add_field(name="Resources", value=resource_text, inline=False)
            
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
            
            # Check for apples and compost even if bug book is empty
            user_inventory = load_inventory(target_user.id)
            apples_count = user_inventory.get('items', {}).get('apple', 0)
            compost_count = user_inventory.get('items', {}).get('compost', 0)
            honey_count = user_inventory.get('items', {}).get('honey', 0)
            
            resource_text = f"🍎 Apples: **{apples_count}**\n♻️ Compost: **{compost_count}**"
            if honey_count > 0:
                resource_text += f"\n🍯 Honey: **{honey_count}**"
            
            if apples_count > 0 or compost_count > 0 or honey_count > 0:
                embed.add_field(name="Resources", value=resource_text, inline=False)

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
        user_inventory = load_inventory(interaction.user.id)
        
        equipped_net_name = user_inventory.get('equipped_net')
        if not equipped_net_name:
            await interaction.followup.send("❌ You don't have a net equipped! Use `/equip_net` to equip one.", ephemeral=True)
            tree_cog.update_last_used_time(interaction.user.id, "bug_catch")
            return
            
        equipped_net = next((net for net in user_inventory.get('nets', []) if net['name'] == equipped_net_name), None)
        
        if not equipped_net:
            user_inventory['equipped_net'] = None
            save_inventory(interaction.user.id, user_inventory)
            await interaction.followup.send("❌ Your equipped net could not be found. It has been unequipped. Please equip a new net.", ephemeral=True)
            tree_cog.update_last_used_time(interaction.user.id, "bug_catch")
            return

        if equipped_net['durability'] <= 0:
            user_inventory['nets'].remove(equipped_net)
            user_inventory['equipped_net'] = None
            save_inventory(interaction.user.id, user_inventory)
            await interaction.followup.send(f"Your **{equipped_net_name}** has broken! You must purchase and equip a new net.", ephemeral=False)
            tree_cog.update_last_used_time(interaction.user.id, "bug_catch")
            return
        
        # Check for night time and fairy event
        current_hour_utc = utils.now().hour
        is_night_time = self.NIGHT_HOURS_UTC[0] <= current_hour_utc or current_hour_utc < self.NIGHT_HOURS_UTC[1]
        
        if is_night_time and random.random() < self.FAIRY_GRANT_CHANCE:
            user_inventory['stars'] = user_inventory.get('stars', 0) + 1
            # Get max durability of the net from the shop items list
            shop_items = load_shop_items()
            equipped_net_shop_data = next((item for item in shop_items if item.get('name') == equipped_net_name), None)
            
            if equipped_net_shop_data:
                equipped_net['durability'] = equipped_net_shop_data.get('durability', equipped_net['durability'])
                
            save_inventory(interaction.user.id, user_inventory)
            
            embed = discord.Embed(
                title="✨ A Fairy's Gift!",
                description="The Tree of Life seems to be glowing faintly in the night. A tiny, luminous fairy flits down from the leaves and grants **{}** a shimmering **star**! Your **{}** has been fully repaired!".format(interaction.user.mention, equipped_net_name),
                color=discord.Color.purple()
            )
            
            fairy_image_path = os.path.join(utils.ASSETS_DIR, "night_fairy.png")
            
            if os.path.exists(fairy_image_path):
                file = discord.File(fairy_image_path, filename="night_fairy.png")
                embed.set_image(url="attachment://night_fairy.png")
                await interaction.followup.send(embed=embed, file=file)
            else:
                await interaction.followup.send(embed=embed)
                print(f"Warning: night_fairy.png not found at {fairy_image_path}. Sending embed without image.")

            tree_cog.update_last_used_time(interaction.user.id, "bug_catch")
            return
            
        # Reduce durability for regular catch attempts
        equipped_net['durability'] -= 1
        save_inventory(interaction.user.id, user_inventory)

        # Get the catch chance from the net's name, with a default of 0.85
        net_catch_chance = self.NET_CATCH_CHANCES.get(equipped_net_name, self.REGULAR_CATCH_CHANCE)
        
        # Apply bonus catch chance from bees
        regular_catch_chance_with_bonus = net_catch_chance
        beehive_state = tree_state.get('beehive', {})
        if beehive_state.get('is_placed') and beehive_state.get('bee_count', 0) > 0:
            bonus = beehive_state['bee_count'] * 0.01
            regular_catch_chance_with_bonus += min(bonus, 0.10) # Cap bonus at 10%
        
        roll = random.random()

        if roll < tree_cog.SHINY_FOUND_CHANCE:
            caught_bug_info = random.choice(self.INSECT_LIST)
            
            embed = discord.Embed(
                title=f"A shiny bug appeared!",
                description=f"A shiny **{caught_bug_info['name']}** {caught_bug_info['emoji']} has appeared! It looks very rare! **{interaction.user.mention}** must try to catch it!",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=caught_bug_info['image_url'])

            view = Bugbook.ShinyCatchView(tree_cog, interaction, caught_bug_info)
            message = await interaction.followup.send(embed=embed, view=view)
            view.message = message
        
        elif roll < tree_cog.SHINY_FOUND_CHANCE + regular_catch_chance_with_bonus:
            caught_bug_info = random.choice(self.INSECT_LIST)
            caught_bug_name = caught_bug_info['name']
            caught_bug_xp = caught_bug_info['xp']
            caught_bug_emoji = caught_bug_info['emoji']
            
            apples_found = random.randint(self.MIN_APPLES_PER_CATCH, self.MAX_APPLES_PER_CATCH)
            user_inventory['items']['apple'] = user_inventory.get('items', {}).get('apple', 0) + apples_found
            save_inventory(interaction.user.id, user_inventory)
            
            user_data['caught'].append(caught_bug_name)
            user_data['xp'] = user_data.get('xp', 0) + caught_bug_xp
            bug_collection[user_id] = user_data
            save_bug_collection(bug_collection)

            # Check for broken net after durability is reduced
            if equipped_net['durability'] <= 0:
                user_inventory['nets'].remove(equipped_net)
                user_inventory['equipped_net'] = None
                save_inventory(interaction.user.id, user_inventory)
                await interaction.followup.send(f"**{interaction.user.mention}** caught a **{caught_bug_name}** {caught_bug_emoji} and earned **{caught_bug_xp}** XP! They also found **{apples_found}** apples 🍎! Their net, a **{equipped_net_name}**, has **broken!** You must purchase and equip a new net.", ephemeral=False)
            else:
                await interaction.followup.send(f"**{interaction.user.mention}** caught a **{caught_bug_name}** {caught_bug_emoji} and earned **{caught_bug_xp}** XP! They also found **{apples_found}** apples 🍎! Their net, a **{equipped_net_name}**, has **{equipped_net['durability']}** durability left.")
        
        else:
            # Check for broken net after durability is reduced
            if equipped_net['durability'] <= 0:
                user_inventory['nets'].remove(equipped_net)
                user_inventory['equipped_net'] = None
                save_inventory(interaction.user.id, user_inventory)
                await interaction.followup.send(f"**{interaction.user.mention}** tried to catch a bug with their **{equipped_net_name}**, but it got away! Their net has **broken!** You must purchase and equip a new net.")
            else:
                await interaction.followup.send(f"**{interaction.user.mention}** tried to catch a bug with their **{equipped_net_name}**, but it got away! Their net has **{equipped_net['durability']}** durability left.")
        
        tree_cog.update_last_used_time(interaction.user.id, "bug_catch")

async def setup(bot):
    await bot.add_cog(Bugbook(bot))
