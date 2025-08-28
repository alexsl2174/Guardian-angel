import discord
from discord.ext import commands
from discord import app_commands, ui
import os
import math
from typing import Dict, Any, List, Optional
import cogs.utils as utils


# Define file paths for JSON data
SHOP_ITEMS_FILE = os.path.join("data", "shop_items.json")
USER_INVENTORY_FILE = os.path.join("data", "user_inventory.json")
ASSETS_FOLDER = "assets"

def load_user_inventory():
    return utils.load_data(USER_INVENTORY_FILE, {})

def save_user_inventory(data):
    utils.save_data(data, USER_INVENTORY_FILE)

class ShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.shop_items = utils.load_data(SHOP_ITEMS_FILE, [])
        self.items_per_page = 8

    class QuantityModal(ui.Modal, title="Select Quantity"):
        def __init__(self, item_to_buy: Dict[str, Any]):
            super().__init__()
            self.item_to_buy = item_to_buy
            self.quantity_input = ui.TextInput(
                label=f"How many {self.item_to_buy['name']} do you want to buy?",
                placeholder="Enter a number (e.g., 1, 5, 10)...",
                min_length=1,
                max_length=4,
            )
            self.add_item(self.quantity_input)

        async def on_submit(self, interaction: discord.Interaction):
            try:
                quantity = int(self.quantity_input.value)
                if quantity <= 0:
                    return await interaction.response.send_message("Please enter a valid quantity greater than zero.", ephemeral=True)
            except ValueError:
                return await interaction.response.send_message("Please enter a valid number.", ephemeral=True)

            await interaction.response.defer(ephemeral=True)

            await utils.handle_buy_item(interaction, self.item_to_buy, quantity=quantity)

    class ShopView(discord.ui.View):
        def __init__(self, original_author: discord.Member, shop_items: list, items_per_page: int, cog):
            super().__init__(timeout=180)
            self.original_author_id = original_author.id
            self.original_author = original_author
            self.shop_items = shop_items
            self.items_per_page = items_per_page
            self.total_pages = math.ceil(len(self.shop_items) / self.items_per_page) if self.shop_items else 1
            self.current_page = 1
            self.message = None
            self.cog = cog

            self.recreate_components()

        def recreate_components(self):
            self.clear_items()

            start_index = (self.current_page - 1) * self.items_per_page
            end_index = start_index + self.items_per_page
            items_to_display = self.shop_items[start_index:end_index]

            options = []
            for item in items_to_display:
                if 'id' in item:
                    item_name = item.get('name', 'Unknown Item')
                    item_price = item.get('price', 0)
                    item_requirement = item.get('requirement')

                    # Check if the user has the required role.
                    # Items with no requirement are always available.
                    has_requirement = True
                    if item_requirement:
                        required_role = discord.utils.get(self.original_author.roles, name=item_requirement)
                        if not required_role:
                            has_requirement = False

                    # Skip item if the requirement is not met.
                    if not has_requirement:
                        continue

                    item_emoji_string = item.get("emoji")
                    item_emoji = None

                    # Check if the emoji string is a custom Discord emoji.
                    if item_emoji_string and item_emoji_string.startswith('<'):
                        try:
                            item_emoji = discord.PartialEmoji.from_str(item_emoji_string)
                        except:
                            item_emoji = item_emoji_string
                    else:
                        item_emoji = item_emoji_string

                    options.append(
                        discord.SelectOption(
                            label=f"{item_name.capitalize()} - 🪙 {item_price}",
                            value=str(item['id']),
                            emoji=item_emoji
                        )
                    )

            if options:
                item_select = discord.ui.Select(
                    placeholder="Choose an item to buy...",
                    options=options,
                    custom_id="shop_select"
                )
                item_select.callback = self.select_callback
                self.add_item(item_select)

            prev_button = discord.ui.Button(label="⬅️ Previous Page", style=discord.ButtonStyle.secondary, custom_id="prev_page")
            next_button = discord.ui.Button(label="Next Page ➡️", style=discord.ButtonStyle.secondary, custom_id="next_page")

            prev_button.callback = self.previous_page
            next_button.callback = self.next_page

            prev_button.disabled = self.current_page == 1
            next_button.disabled = self.current_page == self.total_pages

            self.add_item(prev_button)
            self.add_item(next_button)

        async def _update_embed_and_view(self, interaction: discord.Interaction):
            embed, file = self.cog._create_shop_embed(self.shop_items, self.current_page)
            self.recreate_components()

            await interaction.edit_original_response(embed=embed, view=self, attachments=[file] if file else [])

        async def previous_page(self, interaction: discord.Interaction):
            if interaction.user.id != self.original_author_id:
                return await interaction.response.send_message("This is not your shop view.", ephemeral=True)

            await interaction.response.defer()

            if self.current_page > 1:
                self.current_page -= 1
            await self._update_embed_and_view(interaction)

        async def next_page(self, interaction: discord.Interaction):
            if interaction.user.id != self.original_author_id:
                return await interaction.response.send_message("This is not your shop view.", ephemeral=True)

            await interaction.response.defer()

            if self.current_page < self.total_pages:
                self.current_page += 1

            await self._update_embed_and_view(interaction)

        async def select_callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.original_author_id:
                return await interaction.response.send_message("You can only interact with your own shop view.", ephemeral=True)

            selected_item_id = int(interaction.data['values'][0])

            item_to_buy = next((item for item in self.shop_items if item['id'] == selected_item_id), None)

            if not item_to_buy:
                return await interaction.response.send_message("This item is no longer available.", ephemeral=True)

            print(f"DEBUG: User is trying to buy '{item_to_buy['name']}'.")

            # Re-check the requirement before processing the purchase.
            item_requirement = item_to_buy.get('requirement')
            if item_requirement:
                print(f"DEBUG: Item has a requirement: '{item_requirement}'.")
                required_role = discord.utils.get(interaction.user.roles, name=item_requirement)
                if not required_role:
                    print(f"DEBUG: User does NOT have the required role '{item_requirement}'.")
                    await interaction.response.send_message(f"You do not meet the requirement to buy this item. You need the '{item_requirement}' role.", ephemeral=True)
                    return
                print(f"DEBUG: User has the required role '{item_requirement}'. Proceeding with purchase.")

            modal = self.cog.QuantityModal(item_to_buy)
            await interaction.response.send_modal(modal)

    @app_commands.command(name="shop", description="Displays the items available for purchase in the store.")
    async def shop_command(self, interaction: discord.Interaction):
        shop_items_data = utils.load_data(SHOP_ITEMS_FILE, [])
        embed, file = self._create_shop_embed(shop_items_data, 1)
        await interaction.response.send_message(
            embed=embed,
            view=self.ShopView(interaction.user, shop_items_data, self.items_per_page, self),
            file=file,
            ephemeral=True
        )

    def _create_shop_embed(self, shop_items: list, page_number: int):
        start_index = (page_number - 1) * self.items_per_page
        end_index = start_index + self.items_per_page
        items_to_display = shop_items[start_index:end_index]
        total_pages = math.ceil(len(shop_items) / self.items_per_page) if shop_items else 1

        embed = discord.Embed(
            title="The Sinners' Shop",
            description="Use the dropdown menu to select an item, then enter a quantity to buy.",
            color=discord.Color.gold()
        )

        file = None
        if items_to_display and items_to_display[0].get("image_filename"):
            image_path = os.path.join(ASSETS_FOLDER, items_to_display[0]["image_filename"])
            if os.path.exists(image_path):
                file = discord.File(image_path, filename=items_to_display[0]["image_filename"])
                embed.set_thumbnail(url=f"attachment://{items_to_display[0]['image_filename']}")

        if not items_to_display:
            embed.description = "The shop is currently empty. Please check back later!"
        else:
            for item in items_to_display:
                item_name = item.get("name", "Unknown Item")
                item_description = item.get("description", "No description provided.")

                item_emoji = utils.get_item_emoji(item_name, item.get("emoji"))

                if item.get("type") == "net":
                    item_durability = item.get("durability", 0)
                    item_description += f"\nDurability: {item_durability} catches"

                if item.get("requirement"):
                    item_description += f"\n**Requirement:** {item['requirement']}"

                embed.add_field(
                    name=f"{item_emoji} {item_name}",
                    value=f"**Price:** <a:starcoin:1280590254935380038> {item.get('price', 0)}\n**Description:** {item_description}",
                    inline=False
                )

        embed.set_footer(text=f"Page {page_number}/{total_pages}")

        return embed, file

async def setup(bot):
    await bot.add_cog(ShopCog(bot))
    print("Shop Cog Loaded!")