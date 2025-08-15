import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re # Import regex for parsing message links

# Import utils for shared constants or helper functions if needed
import cogs.utils as utils

# Define the path to your data directory, typically one level up from cogs
# Adjust this path if your 'data' folder is structured differently
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
PINS_FILE = os.path.join(DATA_DIR, 'user_pins.json')

# Ensure the data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Helper functions for pin storage
def _load_all_pins():
    """Loads all user pins from the JSON file."""
    if not os.path.exists(PINS_FILE):
        return {}
    try:
        with open(PINS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"ERROR: Could not decode JSON from {PINS_FILE}. File might be corrupted. Returning empty data.")
        return {}
    except Exception as e:
        print(f"ERROR: An unexpected error occurred while loading {PINS_FILE}: {e}")
        return {}

def _save_all_pins(all_pins_data):
    """Saves all user pins to the JSON file."""
    try:
        with open(PINS_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_pins_data, f, indent=4)
    except Exception as e:
        print(f"ERROR: An unexpected error occurred while saving {PINS_FILE}: {e}")

def load_user_pins(user_id: int) -> list[str]:
    """Loads pins for a specific user."""
    all_pins = _load_all_pins()
    return all_pins.get(str(user_id), [])

def save_user_pins(user_id: int, pins: list[str]):
    """Saves pins for a specific user."""
    all_pins = _load_all_pins()
    all_pins[str(user_id)] = pins
    _save_all_pins(all_pins)

class Pins(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Updated to use the custom emoji
        self.PIN_EMOJI_NAME = "<:sspins:1405590701030244412>" 
        self.MAX_PINS = 50 # Maximum pins per user
        self.main_guild_id = utils.MAIN_GUILD_ID

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Fix: Added a check to ensure the event is from the main guild.
        if payload.guild_id and payload.guild_id != self.main_guild_id:
            return
            
        # Ignore bot's own reactions
        if payload.user_id == self.bot.user.id:
            return
        
        # Check if the emoji is the pin emoji
        if str(payload.emoji) != self.PIN_EMOJI_NAME:
            return

        # Fetch the guild (server)
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            print(f"Pin Reaction: Guild {payload.guild_id} not found for reaction from user {payload.user_id}.")
            return

        # Fetch the channel
        channel = guild.get_channel(payload.channel_id)
        if not channel:
            print(f"Pin Reaction: Channel {payload.channel_id} not found in guild {payload.guild_id} for reaction from user {payload.user_id}.")
            return
        
        # Fetch the message
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            print(f"Pin Reaction: Message {payload.message_id} not found in channel {payload.channel_id} for user {payload.user_id}.")
            return
        except discord.Forbidden:
            print(f"Pin Reaction: Bot does not have permissions to read message {payload.message_id} in channel {payload.channel_id} for user {payload.user_id}.")
            return
        except discord.HTTPException as e:
            print(f"Pin Reaction: HTTP Exception fetching message {payload.message_id} for user {payload.user_id}: {e}")
            return

        # Get the user who reacted
        user = guild.get_member(payload.user_id)
        if not user:
            print(f"Pin Reaction: User {payload.user_id} not found in guild {payload.guild_id}.")
            return # User left or unknown

        user_pins = load_user_pins(user.id)
        
        pin_id = f"{message.channel.id}:{message.id}"

        # Check for duplicates
        if pin_id in user_pins:
            try:
                await message.remove_reaction(payload.emoji, user)
                print(f"User {user.display_name} ({user.id}) tried to pin duplicate message {pin_id}. Reaction removed.")
            except discord.HTTPException as e:
                print(f"Error removing duplicate pin reaction for user {user.id}: {e}")
            return # Stop if already pinned

        # Check pin limit
        if len(user_pins) >= self.MAX_PINS:
            try:
                await message.remove_reaction(payload.emoji, user)
                print(f"User {user.display_name} ({user.id})'s pinboard is full. Pin {pin_id} not added. Reaction removed.")
            except discord.Forbidden:
                print(f"Could not remove reaction for {user.display_name} on full pinboard.")
            return

        # Add the pin
        user_pins.append(pin_id)
        save_user_pins(user.id, user_pins)

        # Remove the reaction after successful pin, and log to console instead of DMing
        try:
            await message.remove_reaction(payload.emoji, user) 
            print(f"User {user.display_name} ({user.id}) successfully pinned message {pin_id}. Reaction removed.")
        except discord.Forbidden:
            print(f"Could not remove reaction for {user.display_name} after successful pin.")
        except Exception as e:
            print(f"Error during post-pin reaction removal for {user.display_name}: {e}")

    @app_commands.command(name="pins", description="Show or manage your personal pinned messages.")
    @app_commands.describe(
        remove="Optional: Comma-separated list of pin numbers to remove (e.g., '1,3,5')."
    )
    async def pins(self, interaction: discord.Interaction, remove: str = None):
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)

        user_pins = load_user_pins(interaction.user.id)

        # Handle removing pins
        if remove:
            if not user_pins:
                await interaction.followup.send("You have no pins to remove!", ephemeral=True)
                return
            
            remove_indices_str = [idx.strip() for idx in remove.split(',')]
            remove_indices = []
            
            # Validate and convert indices
            for idx_str in remove_indices_str:
                try:
                    idx = int(idx_str) - 1 # Convert to 0-based index
                    if 0 <= idx < len(user_pins):
                        remove_indices.append(idx)
                    else:
                        await interaction.followup.send(f"Invalid pin number: `{idx_str}`. Please provide valid pin numbers from your list.", ephemeral=True)
                        return
                except ValueError:
                    await interaction.followup.send(f"Invalid input: `{idx_str}` is not a number. Please provide a comma-separated list of pin numbers (e.g., '1,3,5').", ephemeral=True)
                    return
            
            # Sort in reverse order to avoid index shifting issues during removal
            remove_indices.sort(reverse=True)
            
            deleted_pins_info = []
            for idx in remove_indices:
                if 0 <= idx < len(user_pins): # Double-check in case of duplicate indices or race conditions
                    deleted_pin = user_pins.pop(idx)
                    deleted_pins_info.append(f"Pin #{idx + 1} (`{deleted_pin}`)") # Store info for feedback
            
            save_user_pins(interaction.user.id, user_pins)

            if deleted_pins_info:
                await interaction.followup.send(f"Successfully deleted: {', '.join(deleted_pins_info)}", ephemeral=True)
            else:
                await interaction.followup.send("No pins were deleted. Please check the numbers you provided.", ephemeral=True)
            return

        # Display pins if no remove argument
        if not user_pins:
            await interaction.followup.send(
                embed=discord.Embed(
                    # Updated to use the custom emoji
                    title="You have no pins! <:sspins:1405590701030244412>",
                    description="React with the Pin (<:sspins:1405590701030244412>) emoji to pin associated messages.\n"
                                "(You can immediately unreact, it will stay pinned!)",
                    color=discord.Color.blue()
                ),
                ephemeral=True
            )
            return

        pin_list_str = []
        for i, pin_id_str in enumerate(user_pins):
            try:
                channel_id_str, message_id_str = pin_id_str.split(':')
                channel_id = int(channel_id_str)
                message_id = int(message_id_str)

                channel = self.bot.get_channel(channel_id)
                if not channel:
                    pin_list_str.append(f"{i+1}. Message ID: `{message_id_str}` (Channel not found)")
                    continue

                try:
                    message = await channel.fetch_message(message_id)
                    # Limit content preview to 50 characters, as in Custom Command
                    content_preview = message.content[:50].replace('\n', ' ') if message.content else "*No Content*"
                    if len(message.content) > 50:
                        content_preview += "..."
                    
                    pin_list_str.append(
                        f"{i+1}. by {message.author.display_name}:\n"
                        f"> [{content_preview}]({message.jump_url})"
                    )
                except discord.NotFound:
                    pin_list_str.append(f"{i+1}. Message ID: `{message_id_str}` (Message not found or deleted)")
                except discord.Forbidden:
                    pin_list_str.append(f"{i+1}. Message ID: `{message_id_str}` (No permissions to view message)")
                except discord.HTTPException as e:
                    pin_list_str.append(f"{i+1}. Message ID: `{message_id_str}` (Error fetching message: {e}")

            except ValueError:
                pin_list_str.append(f"{i+1}. Malformed pin data: `{pin_id_str}`")
            except Exception as e:
                pin_list_str.append(f"{i+1}. An unexpected error occurred with pin `{pin_id_str}`: {e}")

        # Split into multiple messages if the content is too long
        embeds = []
        current_description = ""
        max_desc_length = 4000 

        for line in pin_list_str:
            if len(current_description) + len(line) + 1 > max_desc_length:
                embeds.append(discord.Embed(
                    # Updated to use the custom emoji
                    title="<:sspins:1405590701030244412> Personal Pins (Cont.)",
                    description=current_description,
                    color=discord.Color.blue()
                ))
                current_description = line
            else:
                current_description += "\n" + line
        
        if current_description:
            # First embed has the main title (will be sent as a followup message)
            first_embed = discord.Embed(
                # Updated to use the custom emoji
                title="<:sspins:1405590701030244412> Personal Pins:",
                description=current_description.strip(), 
                color=discord.Color.blue()
            )
            embeds.insert(0, first_embed) 

        # Send all embeds using followup.send()
        for embed in embeds:
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="add_pin_for_user", description="Adds a message to another user's personal pin list (Admin only).")
    @app_commands.describe(
        target_user="The user whose pin list to add to.",
        message_link="The link to the message to pin (right-click message -> Copy Message Link)."
    )
    @app_commands.checks.has_permissions(manage_messages=True) # Requires manage_messages permission
    async def add_pin_for_user(self, interaction: discord.Interaction, target_user: discord.Member, message_link: str):
        if interaction.guild and interaction.guild.id != self.main_guild_id:
            return await interaction.response.send_message("This command is only available on the main server.", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)

        # Regex to extract channel ID and message ID from a Discord message link
        # Example link: https://discord.com/channels/123456789012345678/987654321098765432/112233445566778899
        match = re.search(r'discord\.com/channels/\d+/(\d+)/(\d+)', message_link)
        
        if not match:
            await interaction.followup.send("Invalid message link provided. Please ensure it's a valid Discord message link.", ephemeral=True)
            return

        channel_id = int(match.group(1))
        message_id = int(match.group(2))

        # Fetch the channel and message to ensure they exist and are accessible
        channel = self.bot.get_channel(channel_id)
        if not channel:
            await interaction.followup.send(f"Could not find the channel with ID `{channel_id}`. Please ensure the bot has access to it.", ephemeral=True)
            return
        
        try:
            message_to_pin = await channel.fetch_message(message_id)
        except discord.NotFound:
            await interaction.followup.send("The message specified by the link was not found or has been deleted.", ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.followup.send("I do not have permissions to view that message.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"An error occurred while fetching the message: {e}", ephemeral=True)
            return

        # Prepare the pin ID string
        pin_id = f"{message_to_pin.channel.id}:{message_to_pin.id}"

        # Load the target user's pins
        target_user_pins = load_user_pins(target_user.id)

        # Check for duplicates
        if pin_id in target_user_pins:
            await interaction.followup.send(f"This message is already pinned for {target_user.display_name}.", ephemeral=True)
            return

        # Check pin limit for the target user
        if len(target_user_pins) >= self.MAX_PINS:
            await interaction.followup.send(f"{target_user.display_name}'s pin list is full ({self.MAX_PINS} pins). Cannot add more.", ephemeral=True)
            return

        # Add the pin to the target user's list
        target_user_pins.append(pin_id)
        save_user_pins(target_user.id, target_user_pins)

        # Notify the invoker
        await interaction.followup.send(
            f"Successfully pinned message by {message_to_pin.author.display_name} to {target_user.display_name}'s personal pin list. "
            f"Link: <{message_to_pin.jump_url}>",
            ephemeral=True
        )
        print(f"Admin {interaction.user.display_name} ({interaction.user.id}) pinned message {pin_id} for user {target_user.display_name} ({target_user.id}).")


async def setup(bot):
    await bot.add_cog(Pins(bot))