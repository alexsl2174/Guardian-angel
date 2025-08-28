# item.py
import discord
from discord import app_commands
from discord.ext import commands
import os
import json
from typing import List, Dict, Any, Union, Optional
import re
import textwrap
from collections import Counter
import random
import cogs.utils as utils
from cogs.BugData import INSECT_LIST, SHINY_INSECT_LIST, load_bug_collection, save_bug_collection

# --- Define the local assets directory ---
ASSETS_DIR = "assets"
# Define the shop items file for administrative commands
SHOP_ITEMS_FILE = os.path.join("data", "shop_items.json")
# Define bug data
BUG_COLLECTION_FILE = os.path.join("data", "bug_collection.json")

# --- Autocomplete function for item names ---
async def item_autocomplete(interaction: discord.Interaction, current: str):
    items_data = utils.load_data(SHOP_ITEMS_FILE, [])
    choices = [
        app_commands.Choice(name=item['name'], value=item['name'])
        for item in items_data
        if current.lower() in item['name'].lower()
    ]
    return choices[:25] # Discord has a limit of 25 choices

# --- UI Views for Item Commands (Now only used for item group commands) ---

class InventorySelect(discord.ui.Select):
    def __init__(self, items: List[Dict[str, Any]], action: str):
        options = [
            discord.SelectOption(label=item['name'], value=item['name'])
            for item in items
        ]
        super().__init__(placeholder=f"Select an item to {action}...", options=options, custom_id=f"inventory_select_{action}")
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        item_name = self.values[0]
        if self.action == "use":
            item_data = utils.get_item_data(item_name)

            # Check for "Fish" item usage
            if item_name.lower() == "fish":
                user_inventory = utils.load_user_inventory(interaction.user.id)
                if user_inventory.get('items', {}).get("fish", 0) > 0:
                    utils.remove_item_from_inventory(interaction.user.id, "fish")

                    if random.random() < 0.2: # 20% chance to catch a cat
                        cat_bug_info = next((bug for bug in INSECT_LIST if bug['name'] == "Purrfect Cat"), None)
                        if cat_bug_info:
                            bug_collection = utils.load_data(BUG_COLLECTION_FILE, {})
                            user_id_str = str(interaction.user.id)
                            user_data = bug_collection.get(user_id_str, {"caught": [], "xp": 0, "shinies_caught": []})

                            user_data['caught'].append(cat_bug_info['name'])
                            user_data['xp'] = user_data.get('xp', 0) + cat_bug_info['xp']
                            bug_collection[user_id_str] = user_data
                            utils.save_data(bug_collection, BUG_COLLECTION_FILE)

                            return await interaction.response.send_message(f"🐟 You used a fish and caught a **Purrfect Cat**! It has been added to your bug book.", ephemeral=True)

                    return await interaction.response.send_message("You used a fish, but nothing happened. 😢", ephemeral=True)

            # Existing use logic for other items
            if not item_data or not item_data.get('role_to_give'):
                return await interaction.response.send_message(f"You cannot use '{item_name}'.", ephemeral=True)

            user_inventory = utils.load_user_inventory(interaction.user.id)
            if item_name not in user_inventory.get('items', {}):
                return await interaction.response.send_message(f"You don't have '{item_name}' to use.", ephemeral=True)

            role = discord.utils.get(interaction.guild.roles, name=item_data['role_to_give'])
            if role and interaction.guild.me.top_role > role:
                try:
                    await interaction.user.add_roles(role, reason=f"Used item '{item_name}'")

                    user_items = user_inventory['items']
                    if user_items.get(item_name.lower(), 0) > 1:
                        user_items[item_name.lower()] -= 1
                    else:
                        del user_items[item_name.lower()]
                    utils.save_user_inventory(interaction.user.id, user_inventory)

                    await interaction.response.send_message(f"You used '{item_name}' and were granted the '{role.name}' role!", ephemeral=True)
                except discord.Forbidden:
                    await interaction.response.send_message("I don't have permissions to grant that role.", ephemeral=True)
            else:
                await interaction.response.send_message("I couldn't grant that role. The role might not exist or my permissions are too low.", ephemeral=True)

        elif self.action == "sell":
            item_data = utils.get_item_data(item_name)
            if not item_data:
                return await interaction.response.send_message("Item not found.", ephemeral=True)

            sell_price = int(item_data['price'] * 0.5)
            utils.update_user_money(interaction.user.id, sell_price)
            utils.remove_item_from_inventory(interaction.user.id, item_name)
            await interaction.response.send_message(f"You sold '{item_name}' for 🪙 {sell_price}!", ephemeral=True)

class InventoryView(discord.ui.View):
    def __init__(self, items: List[Dict[str, Any]], action: str, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)
        self.add_item(InventorySelect(items, action))

class ItemGroup(app_commands.Group):
    def __init__(self, cog):
        super().__init__(name="item", description="View and manage your items.")
        self.cog = cog
        self.main_guild_id = utils.MAIN_GUILD_ID

    @app_commands.command(name="info", description="Get more information about a specific item.")
    @app_commands.autocomplete(item_name=item_autocomplete)
    @app_commands.describe(item_name="The name of the item to get info for.")
    async def item_info_command(self, interaction: discord.Interaction, item_name: str):
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        item_data = utils.get_item_data(item_name)
        if not item_data:
            return await interaction.response.send_message(f"Item '{item_name}' not found.", ephemeral=True)

        embed = discord.Embed(
            title=f"{item_data['name']}",
            description=item_data['description'],
            color=discord.Color.gold()
        )

        file = None
        if item_data.get('image_filename'):
            image_path = os.path.join(ASSETS_DIR, item_data['image_filename'])
            if os.path.exists(image_path):
                file = discord.File(image_path, filename=item_data['image_filename'])
                embed.set_thumbnail(url=f"attachment://{item_data['image_filename']}")

        embed.add_field(name="Price", value=f"🪙 {item_data['price']}", inline=True)

        if item_data.get('type') == 'cosmetic' and item_data.get('role_to_give'):
            embed.add_field(name="Actions", value=f"Gives role: @{item_data['role_to_give']}", inline=False)
        elif item_data.get('type') == 'net' and item_data.get('durability'):
            embed.add_field(name="Durability", value=f"{item_data['durability']} catches", inline=False)

        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    @app_commands.command(name="use", description="Use an item from your inventory.")
    @app_commands.autocomplete(item_name=item_autocomplete)
    @app_commands.describe(item_name="The name of the item you want to use.", quantity="The number of items to use.")
    async def item_use(self, interaction: discord.Interaction, item_name: str, quantity: Optional[int] = 1):
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        user_id = str(interaction.user.id)
        inventory_data = utils.load_user_inventory(user_id)

        if quantity <= 0:
            return await interaction.response.send_message("Quantity must be a positive number.", ephemeral=True)

        current_item_count = inventory_data.get('items', {}).get(item_name.lower(), 0)
        if current_item_count < quantity:
            return await interaction.response.send_message(f"You only have {current_item_count} of '{item_name}' to use.", ephemeral=True)

        item_data = utils.get_item_data(item_name)

        # New logic for "Fish" item
        if item_name.lower() == "fish":
            total_cats_caught = 0
            for _ in range(quantity):
                if random.random() < 0.2: # 20% chance to catch a cat
                    cat_bug_info = next((bug for bug in INSECT_LIST if bug['name'] == "Purrfect Cat"), None)
                    if cat_bug_info:
                        bug_collection = utils.load_data(BUG_COLLECTION_FILE, {})
                        user_data = bug_collection.get(user_id, {"caught": [], "xp": 0, "shinies_caught": []})
                        user_data['caught'].append(cat_bug_info['name'])
                        user_data['xp'] = user_data.get('xp', 0) + cat_bug_info['xp']
                        bug_collection[user_id] = user_data
                        utils.save_data(bug_collection, BUG_COLLECTION_FILE)
                        total_cats_caught += 1

            # Remove items
            utils.remove_item_from_inventory(interaction.user.id, "fish", quantity)

            message = f"You used {quantity} fish. 😢"
            if total_cats_caught > 0:
                message = f"🐟 You used {quantity} fish and caught {total_cats_caught} **Purrfect Cat(s)**! They have been added to your bug book."
            return await interaction.response.send_message(message, ephemeral=True)

        if not item_data or not item_data.get('role_to_give'):
            return await interaction.response.send_message(f"You cannot use '{item_name}'.", ephemeral=True)

        # Handle other item usage
        role_name = item_data['role_to_give']
        role = discord.utils.get(interaction.guild.roles, name=role_name)

        if role and interaction.guild.me.top_role > role:
            try:
                # Assuming you can only use one of these items at a time
                if quantity > 1:
                    await interaction.response.send_message("You can only use one of this type of item at a time.", ephemeral=True)
                    quantity = 1 # Revert to one for items that give roles

                await interaction.user.add_roles(role, reason=f"Used item '{item_name}'")
                utils.remove_item_from_inventory(user_id, item_name, quantity)
                await interaction.response.send_message(f"You used '{item_name}' and were granted the '{role.name}' role!", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("I don't have permissions to grant that role.", ephemeral=True)
        else:
            await interaction.response.send_message("I couldn't grant that role. The role might not exist or my permissions are too low.", ephemeral=True)

    @app_commands.command(name="sell", description="Sell an item from your inventory for half its price.")
    @app_commands.autocomplete(item_name=item_autocomplete)
    @app_commands.describe(item_name="The name of the item you want to sell.", quantity="The number of items to sell.")
    async def item_sell(self, interaction: discord.Interaction, item_name: str, quantity: Optional[int] = 1):
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        user_id = str(interaction.user.id)
        inventory_data = utils.load_user_inventory(user_id)

        if quantity <= 0:
            return await interaction.response.send_message("Quantity must be a positive number.", ephemeral=True)

        current_item_count = inventory_data.get('items', {}).get(item_name.lower(), 0)
        if current_item_count < quantity:
            return await interaction.response.send_message(f"You only have {current_item_count} of that item in your inventory.", ephemeral=True)

        item_data = utils.get_item_data(item_name)
        if not item_data:
            return await interaction.response.send_message(f"Item '{item_name}' not found.", ephemeral=True)

        sell_price_per_item = item_data['price']
        total_sell_price = sell_price_per_item * quantity

        utils.remove_item_from_inventory(user_id, item_name, quantity)
        utils.update_user_money(interaction.user.id, total_sell_price)

        await interaction.response.send_message(f"You sold {quantity} '{item_name}' for 🪙 {total_sell_price}!", ephemeral=True)

    @app_commands.command(name="sellall", description="Sells all items of a specific type from your inventory.")
    @app_commands.autocomplete(item_name=item_autocomplete)
    @app_commands.describe(item_name="The name of the item you want to sell all of.")
    async def item_sell_all(self, interaction: discord.Interaction, item_name: str):
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        user_id = str(interaction.user.id)
        inventory_data = utils.load_user_inventory(user_id)

        current_item_count = inventory_data.get('items', {}).get(item_name.lower(), 0)
        if current_item_count == 0:
            return await interaction.response.send_message(f"You don't have any '{item_name}' to sell.", ephemeral=True)

        item_data = utils.get_item_data(item_name)
        if not item_data:
            return await interaction.response.send_message(f"Item '{item_name}' not found.", ephemeral=True)

        sell_price_per_item = item_data['price']
        total_sell_price = sell_price_per_item * current_item_count

        utils.remove_item_from_inventory(user_id, item_name, current_item_count)
        utils.update_user_money(interaction.user.id, total_sell_price)

        await interaction.response.send_message(f"You sold all {current_item_count} of your '{item_name}' for a total of 🪙 {total_sell_price}!", ephemeral=True)

    @app_commands.command(name="inventory", description="View the items you currently own.")
    async def inventory_command(self, interaction: discord.Interaction):
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        user_inventory_data = utils.load_user_inventory(interaction.user.id)

        # Filter out items with a count of 0
        items_with_count = {item_name: count for item_name, count in user_inventory_data.get('items', {}).items() if count > 0}

        # Check if the filtered inventory is empty
        if not items_with_count and not user_inventory_data.get('nets'):
            return await interaction.response.send_message("Your inventory is empty.", ephemeral=True)

        embed = discord.Embed(
            title=f"🎒 {interaction.user.display_name}'s Inventory",
            description="Your current inventory, page 1/1.",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        # Handle equipped net
        equipped_net = user_inventory_data.get('equipped_net')
        if equipped_net:
            nets = user_inventory_data.get('nets', [])
            equipped_net_data = next((net for net in nets if net['name'] == equipped_net), None)
            if equipped_net_data:
                embed.add_field(name="Equipped Net", value=f"🎣 {equipped_net_data['name']} (Durability: {equipped_net_data['durability']})", inline=False)

        # Handle other items
        if items_with_count:
            item_list = []
            for item_name, count in items_with_count.items():
                item_data = utils.get_item_data(item_name)
                item_emoji = utils.get_item_emoji(item_name, item_data.get("emoji")) if item_data else "🛒"
                item_list.append(f"{item_emoji} {item_name.capitalize()} x{count}")
            embed.add_field(name="Other Items", value="\n".join(item_list), inline=False)

        # Handle unequipped nets, grouping them by name
        unequipped_nets = [net for net in user_inventory_data.get('nets', []) if net['name'] != equipped_net]
        if unequipped_nets:
            net_counts = Counter(net['name'] for net in unequipped_nets)
            net_list = []
            for net_name, count in net_counts.items():
                net_emoji = "🎣"
                durability = next((n['durability'] for n in unequipped_nets if n['name'] == net_name), 'N/A')
                net_list.append(f"{net_emoji} {net_name} (Durability: {durability}) x{count}")

            embed.add_field(name="Unequipped Nets", value="\n".join(net_list), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

class Items(commands.Cog):
    """
    A cog for managing in-bot item store and user inventories.
    This cog now focuses on item management and non-shop related commands.
    """
    def __init__(self, bot):
        self.bot = bot
        self.main_guild_id = utils.MAIN_GUILD_ID
        self.bot.tree.add_command(ItemGroup(self))

    # All admin commands are kept here as they are directly related to managing items
    @app_commands.command(name="additem", description="Adds a new item to the store (Admin only).")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        name="The name of the new item.",
        price="The cost of the item.",
        description="A brief description of the item.",
        item_type="The type of item (e.g., net, cosmetic).",
        emoji="The emoji for the item.",
        image_filename="The filename of the image in the 'assets' folder.",
        requirement="The name of the item required to purchase this item.",
        durability="The durability for nets (optional).",
        role_to_give="The role to be granted when the item is used (name, optional)."
    )
    async def add_item(self, interaction: discord.Interaction, name: str, price: int, description: str, item_type: str, emoji: str, image_filename: Optional[str] = None, requirement: Optional[str] = None, durability: Optional[int] = None, role_to_give: Optional[str] = None):
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        items_data = utils.load_data(SHOP_ITEMS_FILE, [])
        if any(item['name'].lower() == name.lower() for item in items_data):
            return await interaction.response.send_message(f"An item with the name '{name}' already exists.", ephemeral=True)

        new_item = {
            "id": len(items_data) + 1,
            "name": name,
            "price": price,
            "description": description,
            "type": item_type,
            "emoji": emoji,
            "image_filename": image_filename,
            "requirement": requirement,
            "durability": durability,
            "role_to_give": role_to_give
        }

        items_data.append(new_item)
        utils.save_data(items_data, SHOP_ITEMS_FILE)

        await interaction.response.send_message(f"✅ Item `{name}` has been added to the store.", ephemeral=True)

    @app_commands.command(name="edititem", description="Edits an existing item in the store (Admin only).")
    @app_commands.autocomplete(item_name=item_autocomplete)
    @app_commands.describe(
        item_name="The name of the item to edit.",
        new_name="The new name for the item (optional).",
        new_price="The new price (optional).",
        new_description="The new description (optional).",
        new_item_type="The new type of item (optional).",
        new_emoji="The new emoji (optional).",
        new_image_filename="The new filename (optional).",
        new_requirement="The new item required to purchase this item (optional).",
        new_durability="The new durability (optional).",
        new_role_to_give="The new role to be granted (optional)."
    )
    async def edit_item(self, interaction: discord.Interaction, item_name: str, new_name: Optional[str] = None, new_price: Optional[int] = None, new_description: Optional[str] = None, new_item_type: Optional[str] = None, new_emoji: Optional[str] = None, new_image_filename: Optional[str] = None, new_requirement: Optional[str] = None, new_durability: Optional[int] = None, new_role_to_give: Optional[str] = None):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        items_data = utils.load_data(SHOP_ITEMS_FILE, [])
        item_found = next((item for item in items_data if item['name'].lower() == item_name.lower()), None)
        if not item_found:
            return await interaction.followup.send(f"❌ Item `{item_name}` not found in the store.", ephemeral=True)

        if new_name: item_found['name'] = new_name
        if new_price: item_found['price'] = new_price
        if new_description: item_found['description'] = new_description
        if new_item_type: item_found['type'] = new_item_type
        if new_emoji: item_found['emoji'] = new_emoji
        if new_image_filename: item_found['image_filename'] = new_image_filename
        if new_requirement: item_found['requirement'] = new_requirement
        if new_durability: item_found['durability'] = new_durability
        if new_role_to_give: item_found['role_to_give'] = new_role_to_give

        utils.save_data(items_data, SHOP_ITEMS_FILE)
        await interaction.followup.send(f"✅ Item `{item_name}` has been updated.", ephemeral=True)

    @app_commands.command(name="removeitem", description="Removes an item from the store (Admin only).")
    @app_commands.autocomplete(item_name=item_autocomplete)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(item_name="The name of the item to remove.")
    async def remove_item(self, interaction: discord.Interaction, item_name: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        items_data = utils.load_data(SHOP_ITEMS_FILE, [])
        item_to_remove = next((item for item in items_data if item['name'].lower() == item_name.lower()), None)
        if item_to_remove:
            items_data.remove(item_to_remove)
            utils.save_data(items_data, SHOP_ITEMS_FILE)
            await interaction.followup.send(f"✅ Item `{item_name}` has been removed from the store.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Item `{item_name}` not found in the store.", ephemeral=True)

async def setup(bot):
    """The setup function to add this cog to the bot."""
    await bot.add_cog(Items(bot))
    print("Items Cog Loaded!")