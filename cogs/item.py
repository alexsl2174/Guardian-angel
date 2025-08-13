import discord
from discord import app_commands
from discord.ext import commands
import os
import json
from typing import List, Dict, Any, Union, Optional
import re
import textwrap

# Import shared utility functions and global configurations
import cogs.utils as utils 

# --- Define the local assets directory ---
ASSETS_DIR = "assets"
# Define the shop items file for administrative commands
SHOP_ITEMS_FILE = os.path.join("data", "shop_items.json")

# --- UI Views for Item Commands (Now only used for item group commands) ---

# Dropdown for selecting an item from the user's inventory for actions like use/sell
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
            if not item_data or not item_data.get('role_to_give'):
                return await interaction.response.send_message(f"You cannot use '{item_name}'.", ephemeral=True)
            
            user_inventory = utils.load_inventory(interaction.user.id)
            if item_name not in user_inventory['items']:
                return await interaction.response.send_message(f"You don't have '{item_name}' to use.", ephemeral=True)
            
            role = discord.utils.get(interaction.guild.roles, name=item_data['role_to_give'])
            if role and interaction.guild.me.top_role > role:
                try:
                    await interaction.user.add_roles(role, reason=f"Used item '{item_name}'")
                    utils.remove_item_from_inventory(interaction.user.id, item_name)
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
    @app_commands.describe(item_name="The name of the item you want to use.")
    async def item_use(self, interaction: discord.Interaction, item_name: str):
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)
        
        user_id = str(interaction.user.id)
        inventory_data = utils.load_inventory(user_id)

        if not inventory_data.get('items', {}).get(item_name.lower()):
            return await interaction.response.send_message(f"You don't have '{item_name}' to use.", ephemeral=True)

        item_data = utils.get_item_data(item_name)
        if not item_data or not item_data.get('role_to_give'):
            return await interaction.response.send_message(f"You cannot use '{item_name}'.", ephemeral=True)

        role_name = item_data['role_to_give']
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        
        if role and interaction.guild.me.top_role > role:
            try:
                await interaction.user.add_roles(role, reason=f"Used item '{item_name}'")
                
                user_items = inventory_data['items']
                if user_items.get(item_name.lower(), 0) > 1:
                    user_items[item_name.lower()] -= 1
                else:
                    del user_items[item_name.lower()]
                utils.save_inventory(user_id, inventory_data)

                await interaction.response.send_message(f"You used '{item_name}' and were granted the '{role.name}' role!", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("I don't have permissions to grant that role.", ephemeral=True)
        else:
            await interaction.response.send_message("I couldn't grant that role. The role might not exist or my permissions are too low.", ephemeral=True)

    @app_commands.command(name="sell", description="Sell an item from your inventory for half its price.")
    @app_commands.describe(item_name="The name of the item you want to sell.")
    async def item_sell(self, interaction: discord.Interaction, item_name: str):
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)

        user_id = str(interaction.user.id)
        inventory_data = utils.load_inventory(user_id)
        
        if not inventory_data.get('items', {}).get(item_name.lower()):
            return await interaction.response.send_message("You don't have that item in your inventory.", ephemeral=True)

        item_data = utils.get_item_data(item_name)
        if not item_data:
            return await interaction.response.send_message(f"Item '{item_name}' not found.", ephemeral=True)
        
        sell_price = int(item_data['price'] * 0.5)

        user_items = inventory_data['items']
        if user_items.get(item_name.lower(), 0) > 1:
            user_items[item_name.lower()] -= 1
        else:
            del user_items[item_name.lower()]
        
        utils.save_inventory(user_id, inventory_data)
        utils.update_user_money(interaction.user.id, sell_price)
        
        await interaction.response.send_message(f"You sold '{item_name}' for 🪙 {sell_price}!", ephemeral=True)

    @app_commands.command(name="inventory", description="View the items you currently own.")
    async def inventory_command(self, interaction: discord.Interaction):
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)
        
        user_inventory_data = utils.load_inventory(interaction.user.id)
        
        if not user_inventory_data or (not user_inventory_data.get('items') and not user_inventory_data.get('nets')):
            return await interaction.response.send_message("Your inventory is empty.", ephemeral=True)

        embed = discord.Embed(
            title=f"🎒 {interaction.user.display_name}'s Inventory",
            color=discord.Color.blue()
        )
        
        equipped_net = user_inventory_data.get('equipped_net')
        if equipped_net:
            nets = user_inventory_data.get('nets', [])
            equipped_net_data = next((net for net in nets if net['name'] == equipped_net), None)
            if equipped_net_data:
                embed.add_field(name="Equipped Net", value=f"🎣 {equipped_net_data['name']} (Durability: {equipped_net_data['durability']})", inline=False)
        
        items = user_inventory_data.get('items', {})
        if items:
            item_list = []
            for item_name, count in items.items():
                item_list.append(f"**{item_name.capitalize()}** x{count}")
            embed.add_field(name="Other Items", value="\n".join(item_list), inline=False)
        else:
            embed.add_field(name="Other Items", value="You have no other items in your inventory.", inline=False)

        unequipped_nets = [net for net in user_inventory_data.get('nets', []) if net['name'] != equipped_net]
        if unequipped_nets:
            net_list = []
            for net in unequipped_nets:
                net_list.append(f"🎣 {net['name']} (Durability: {net['durability']})")
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
    @app_commands.checks.has_permissions(manage_guild=True)
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