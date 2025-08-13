import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import cogs.utils as utils
from typing import List, Dict, Any, Union, Optional
import asyncio
import datetime
from collections import deque
import discord.ui
import io

class AdventureGame:
    def __init__(self, channel_id: int, player_id: int, player_name: str, game_theme: str = None):
        self.channel_id = channel_id
        self.player_id = player_id
        self.player_name = player_name
        self.game_theme = game_theme
        self.chat_history = deque(maxlen=20)
        self.original_roles: list[int] = []

    def add_to_history(self, role: str, text: str):
        self.chat_history.append({"role": role, "parts": [{"text": text}]})

    def get_formatted_history(self) -> List[Dict[str, Any]]:
        return list(self.chat_history)

class Adventure(commands.Cog):
    """
    A cog for a persistent, AI-powered text adventure game.
    """
    def __init__(self, bot):
        self.bot = bot
        self.active_games: Dict[int, AdventureGame] = {}
        self.ai_restrictions = utils.get_ai_restrictions()

    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the bot is ready. Used to restart the game."""
        print("Adventure cog ready. Attempting to reload active games.")
        saved_games_data = utils.load_active_adventure_games_from_file()
        if saved_games_data:
            for channel_id_str, game_data in saved_games_data.items():
                try:
                    channel_id = int(channel_id_str)
                    game = AdventureGame(
                        channel_id=channel_id,
                        player_id=int(game_data['player_id']),
                        player_name=game_data['player_name'],
                        game_theme=game_data.get('game_theme')
                    )
                    game.chat_history = deque(game_data.get('game_history', []), maxlen=20)
                    game.original_roles = game_data.get('original_roles', [])
                    self.active_games[channel_id] = game
                    print(f"Loaded active game in channel {channel_id} for player {game.player_name}")
                except Exception as e:
                    print(f"Error loading game for channel {channel_id_str}: {e}")
            print(f"Successfully reloaded {len(self.active_games)} active games.")
        else:
            print("No active games to reload.")

    def _save_game_state(self, game: AdventureGame):
        game_data = {
            'player_id': game.player_id,
            'player_name': game.player_name,
            'game_history': list(game.chat_history),
            'game_theme': game.game_theme,
            'original_roles': game.original_roles
        }
        all_games = utils.load_active_adventure_games_from_file()
        all_games[str(game.channel_id)] = game_data
        utils.save_active_adventure_games_to_file(all_games)

    def _remove_game_state(self, channel_id: int):
        all_games = utils.load_active_adventure_games_from_file()
        if str(channel_id) in all_games:
            del all_games[str(channel_id)]
            utils.save_active_adventure_games_to_file(all_games)

    async def _cleanup_adventure(self, member: discord.Member, guild: discord.Guild, game_thread_id: int):
        """Helper function to clean up roles and game state after an adventure ends."""
        if not member:
            return

        # Restore the user's previous roles
        saved_role_ids = utils.load_user_roles(member.id)
        if saved_role_ids:
            try:
                # Use discord.Object to restore roles by ID
                await member.add_roles(*[discord.Object(id) for id in saved_role_ids], reason="Restoring roles after adventure game.")
            except discord.Forbidden:
                print(f"Error: Bot lacks permissions to restore roles for {member.display_name}.")
            finally:
                # Clear the saved roles from the file so they are not restored multiple times
                utils.save_user_roles(member.id, [])
        
        # Remove the 'Player' role
        player_role = guild.get_role(utils.PLAYER_ROLE_ID)
        if player_role:
            try:
                await member.remove_roles(player_role, reason="Adventure game ended.")
            except discord.Forbidden:
                print(f"Error: Bot lacks permissions to remove the Player role from {member.display_name}.")
        
        # Clean up the game state from memory and file
        if game_thread_id in self.active_games:
            del self.active_games[game_thread_id]
            self._remove_game_state(game_thread_id)
        
        # Delete the thread
        channel = guild.get_channel(game_thread_id)
        if isinstance(channel, discord.Thread):
            try:
                await channel.delete()
                print(f"Deleted adventure thread: {channel.name} ({channel.id})")
            except discord.Forbidden:
                print(f"Missing permissions to delete thread {channel.name} ({channel.id}).")
            except discord.NotFound:
                print(f"Thread {channel.id} not found, already deleted.")
            except Exception as e:
                print(f"Error deleting thread {channel.name} ({channel.id}): {e}")

    @app_commands.command(name="setadventurechannel", description="Sets the main channel where adventure threads will be created.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_adventure_channel(self, interaction: discord.Interaction):
        utils.save_adventure_channel_id(interaction.channel.id)
        await interaction.response.send_message(f"This channel has been set as the main adventure channel. Players can now use /startadventure here.", ephemeral=True)
        print(f"Adventure channel set to: {interaction.channel.id}")

    @app_commands.command(name="startadventure", description="Starts a new text adventure game in its own thread.")
    @app_commands.describe(theme="An optional theme for your adventure (e.g., 'haunted mansion', 'space exploration').")
    async def start_adventure(self, interaction: discord.Interaction, theme: Optional[str] = None):
        adventure_channel_id = utils.load_adventure_channel_id()
        if not adventure_channel_id or interaction.channel.id != adventure_channel_id:
            return await interaction.response.send_message(f"Adventure games must be started in the designated adventure channel.", ephemeral=True)

        player_id = str(interaction.user.id)
        
        for game_state in self.active_games.values():
            if game_state.player_id == int(player_id):
                return await interaction.response.send_message("You already have an active adventure. Please use `/endadventure` to finish it first.", ephemeral=True)

        await interaction.response.defer()

        member = interaction.user
        guild = interaction.guild

        # Role Management
        current_roles = [role.id for role in member.roles if role.id != guild.id]
        if current_roles:
            utils.save_user_roles(member.id, current_roles)
            try:
                await member.remove_roles(*[discord.Object(id) for id in current_roles], reason="Started a new adventure game.")
            except discord.Forbidden:
                print("Error: Bot lacks permissions to remove roles.")
                await interaction.followup.send("I couldn't remove your roles. Please check my permissions and role hierarchy.", ephemeral=True)
                return

        player_role = guild.get_role(utils.PLAYER_ROLE_ID)
        if not player_role:
            await interaction.followup.send("The 'Player' role is not configured correctly. Please contact an admin.", ephemeral=True)
            return

        try:
            await member.add_roles(player_role, reason="Started a new adventure game.")
        except discord.Forbidden:
            print("Error: Bot lacks permissions to add the 'Player' role.")
            await interaction.followup.send("I couldn't give you the 'Player' role. Please check my permissions and role hierarchy.", ephemeral=True)
            return

        # Thread Creation
        thread_name = f"{member.display_name}'s Adventure"
        try:
            thread = await interaction.channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread,
                reason="Starting a new adventure."
            )
        except discord.Forbidden:
            print("Error: Bot lacks permissions to create threads.")
            await interaction.followup.send("I couldn't create a thread for your adventure. Please check my permissions.", ephemeral=True)
            return

        game = AdventureGame(thread.id, member.id, member.display_name, game_theme=theme)
        game.original_roles = current_roles
        self.active_games[thread.id] = game
        self._save_game_state(game)
        
        embed = discord.Embed(
            title="A New Adventure Begins!",
            description=f"Welcome to your personal quest, {member.mention}! Your adventure's theme is: **{theme if theme else 'A Dark Forest'}**\n\nThe mysterious voice whispers, 'What do you do?'",
            color=discord.Color.dark_teal()
        )
        
        await thread.send(embed=embed)
        await interaction.followup.send(f"Your adventure has started! Go to {thread.mention} to begin your quest.", ephemeral=True)

    @app_commands.command(name="endadventure", description="Ends the current adventure game.")
    @app_commands.describe(user="The player whose adventure to stop (Admins only).")
    async def end_adventure(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        thread_id = interaction.channel.id

        if thread_id not in self.active_games:
            return await interaction.response.send_message("There is no active adventure game in this channel.", ephemeral=True)

        game_state = self.active_games[thread_id]
        game_player_id = str(game_state.player_id)
        
        # Scenario A: No user is specified. The user running the command must be the player.
        if user is None:
            if str(interaction.user.id) != game_player_id:
                return await interaction.response.send_message("You can only end your own adventure game.", ephemeral=True)
            
            player_member = interaction.user
            await interaction.response.send_message("Your adventure has ended. Thank you for playing!", ephemeral=True)
            await self._cleanup_adventure(player_member, interaction.guild, thread_id)
        
        # Scenario B: A user is specified. The user running the command must be a moderator.
        else:
            if not interaction.user.guild_permissions.manage_channels:
                return await interaction.response.send_message("You do not have permission to stop another player's adventure.", ephemeral=True)
            
            if str(user.id) != game_player_id:
                return await interaction.response.send_message(f"The adventure game in this channel is not being played by {user.display_name}.", ephemeral=True)
            
            player_member = user
            await interaction.response.send_message(f"The adventure of {user.display_name} has been ended by an admin. Thank you for playing!", ephemeral=True)
            await self._cleanup_adventure(player_member, interaction.guild, thread_id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not isinstance(message.channel, discord.Thread):
            return

        game = self.active_games.get(message.channel.id)

        if game and game.player_id == message.author.id:
            player_input = message.content

            # Add the user's message to the game history
            game.add_to_history("user", player_input)
            self._save_game_state(game)

            # Defer the response to allow the AI time to generate
            async with message.channel.typing():
                try:
                    # Generate the AI's response based on the updated history
                    ai_response = await utils.generate_text_with_gemini_with_history(
                        chat_history=game.get_formatted_history(),
                        model_name="gemini-1.5-flash"
                    )

                    if ai_response:
                        game.add_to_history("model", ai_response)
                        self._save_game_state(game)
                        await message.channel.send(ai_response)
                    else:
                        await message.channel.send("The mysterious voice has gone silent...")

                except Exception as e:
                    print(f"Error during adventure game message processing: {e}")
                    await message.channel.send("An error occurred while continuing the adventure.")
            
        await self.bot.process_commands(message)

async def setup(bot):
    await bot.add_cog(Adventure(bot))