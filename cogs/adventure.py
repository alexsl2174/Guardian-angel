import discord
from discord.ext import commands
import asyncio
import random
import json
import os
import datetime
from collections import deque
from . import utils
from discord import app_commands
import discord.ui
from typing import Any, List, Dict, Optional
import io
import sys
import traceback

# Define the AdventureGameOverView outside the cog, so it can be registered with the bot
class AdventureGameOverView(discord.ui.View):
    def __init__(self, cog_instance, channel_id: int, player_id: int, game_theme: str = None):
        super().__init__(timeout=None)
        self.cog_instance = cog_instance
        self.channel_id = channel_id
        self.player_id = player_id
        self.game_theme = game_theme
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("This isn't your adventure game!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Retry Adventure", style=discord.ButtonStyle.green, emoji="🔄")
    async def retry_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        if self.message:
            await self.message.edit(view=None)

        await interaction.followup.send("Adventure restarting! Please wait for the new scenario.", ephemeral=False)

        await self.cog_instance._reset_game_in_channel(self.channel_id, self.player_id, self.game_theme)

    @discord.ui.button(label="End Game", style=discord.ButtonStyle.red, emoji="🛑")
    async def stop_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        if self.message:
            await self.message.edit(content="The game has been ended, but this channel will be deleted soon.", view=None)

        await self.cog_instance._end_game(self.channel_id, self.player_id, delete_channel=True, interaction=interaction)


class AdventureChoicesView(discord.ui.View):
    def __init__(self, cog_instance, player_id: int, choices: List[str]):
        super().__init__(timeout=180)
        self.cog_instance = cog_instance
        self.player_id = player_id
        self.choices = choices
        self.message = None
        self.add_buttons()

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(content="This adventure has timed out. Please use `/end_adventure` to finish or start a new game.", view=None)
            except discord.NotFound:
                pass
            except Exception as e:
                print(f"ERROR: Failed to edit message on timeout: {e}")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("This isn't your adventure game!", ephemeral=True)
            return False
        return True

    def add_buttons(self):
        if not self.choices or not isinstance(self.choices, list):
            print("WARNING: Choices provided to AdventureChoicesView are not a list or are empty. No buttons will be added.")
            return

        for i, choice_data in enumerate(self.choices):
            # Check if the choice is a dictionary and get the 'text' key
            if isinstance(choice_data, dict) and 'text' in choice_data:
                choice_text = choice_data['text']
            # Assume it's a string if not a dictionary
            elif isinstance(choice_data, str):
                choice_text = choice_data
            else:
                print(f"WARNING: Choice at index {i} is not a dictionary or a string, skipping. Value: {choice_data}")
                continue

            button_label = choice_text[:80]
            button = discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label=f"Choice {i + 1}",
                custom_id=f"choice_button_{i}"
            )
            button.full_choice_text = choice_text
            button.callback = self.create_button_callback(button)
            self.add_item(button)

    def create_button_callback(self, button: discord.ui.Button):
        async def callback(interaction: discord.Interaction):
            print(f"DEBUG: Player {interaction.user.name} pressed button for choice: '{button.full_choice_text}'")
            try:
                await interaction.response.defer()

                if self.message:
                    await self.message.edit(view=None)

                game = self.cog_instance.active_games.get(interaction.channel.id)
                if game:
                    await self.cog_instance._process_player_action(game, button.full_choice_text, from_button=True)
            except Exception as e:
                print(f"ERROR: Exception in button callback: {e}")
                traceback.print_exc(file=sys.stdout)
        return callback


class AdventureGame:
    def __init__(self, channel_id: int, player_id: int, player_name: str, game_theme: str = None, allowed_traps: list = None):
        self.channel_id = channel_id
        self.player_id = player_id
        self.player_name = player_name
        self.chat_history = deque(maxlen=20)
        self.current_scenario_message = None
        self.current_choices = []
        self.is_incapacitated = False
        self.active_traps: dict[str, int] = {}
        self.game_won = False
        self.game_theme = game_theme
        self.original_roles = []
        self.allowed_traps = allowed_traps if allowed_traps is not None else []
        self.waiting_for_consent = False

    def add_to_history(self, role: str, text: str):
        self.chat_history.append({"role": role, "parts": [{"text": text}]})

    def get_formatted_history(self):
        return list(self.chat_history)

    def is_trap_active(self, trap_name: str) -> bool:
        """Checks if a trap is currently active (level > 0)."""
        return trap_name in self.active_traps and self.active_traps[trap_name] > 0

    def update_traps(self):
        pass

    def check_incapacitation(self):
        self.is_incapacitated = False
        if self.active_traps.get("rope", 0) >= utils.MAX_ROPE_TIGHTNESS:
            self.is_incapacitated = True
        if self.active_traps.get("blindfold", 0) >= utils.MAX_BLINDFOLD_LEVEL:
            self.is_incapacitated = True
        if self.active_traps.get("ball_gag", 0) >= utils.MAX_GAG_LEVEL:
            self.is_incapacitated = True
        if self.active_traps.get("layers_of_tape", 0) >= utils.MAX_TAPE_LAYERS:
            self.is_incapacitated = True


class Adventure(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games: dict[int, AdventureGame] = {}
        self.ai_restrictions = []
        self.bot.loop.create_task(self.load_ai_restrictions())
        self.bot.loop.create_task(self.load_active_games_on_startup())
        self._temp_role_names = {
            "Adventure Player": "Adventure Player",
            "Verified": "Verified",
            "Visitor": "Visitor",
            "CrossVerify": "CrossVerify",
        }

    async def load_ai_restrictions(self):
        print("DEBUG: Loading AI restrictions for adventure game...")
        self.ai_restrictions = utils.get_ai_restrictions() or []
        print(f"DEBUG: AI Restrictions loaded: {self.ai_restrictions}")

    async def load_active_games_on_startup(self):
        await self.bot.wait_until_ready()
        print("DEBUG: Loading active adventure games on startup...")
        saved_games_data = utils.load_active_adventure_games_from_file()
        for channel_id_str, game_data in saved_games_data.items():
            try:
                channel_id = int(channel_id_str)
                game = AdventureGame(
                    channel_id=channel_id,
                    player_id=game_data['player_id'],
                    player_name=game_data['player_name'],
                    game_theme=game_data.get('game_theme'),
                    allowed_traps=game_data.get('allowed_traps', [])
                )
                game.chat_history = deque(game_data.get('chat_history', []), maxlen=20)
                game.active_traps = {k: int(v) for k, v in game_data.get('active_traps', {}).items()}
                game.is_incapacitated = game_data.get('is_incapacitated', False)
                game.game_won = game_data.get('game_won', False)
                game.original_roles = game_data.get('original_roles', [])
                game.waiting_for_consent = game_data.get('waiting_for_consent', False)
                game.current_choices = game_data.get('current_choices', [])

                self.active_games[channel_id] = game
                print(f"DEBUG: Loaded active game in channel {channel_id} for player {game.player_name}")
            except Exception as e:
                print(f"ERROR: Error loading game for channel {channel_id_str}: {e}")
                traceback.print_exc(file=sys.stdout)
        print("DEBUG: Finished loading active adventure games.")

    def _save_game_state(self, game: AdventureGame):
        game_data = {
            'player_id': game.player_id,
            'player_name': game.player_name,
            'chat_history': list(game.chat_history),
            'active_traps': game.active_traps,
            'is_incapacitated': game.is_incapacitated,
            'game_won': game.game_won,
            'game_theme': game.game_theme,
            'original_roles': getattr(game, 'original_roles', []),
            'allowed_traps': game.allowed_traps,
            'waiting_for_consent': game.waiting_for_consent,
            'current_choices': game.current_choices
        }
        all_games = utils.load_active_adventure_games_from_file()
        all_games[str(game.channel_id)] = game_data
        utils.save_active_adventure_games_to_file(all_games)
        print(f"DEBUG: Game state for channel {game.channel_id} saved.")

    def _remove_game_state(self, channel_id: int):
        all_games = utils.load_active_adventure_games_from_file()
        if str(channel_id) in all_games:
            del all_games[str(channel_id)]
            utils.save_active_adventure_games_to_file(all_games)
            print(f"DEBUG: Game state for channel {channel_id} removed.")

    async def _cleanup_channel(self, channel: discord.TextChannel):
        try:
            await channel.delete()
            print(f"DEBUG: Deleted adventure channel: {channel.name} ({channel.id})")
        except discord.NotFound:
            print(f"DEBUG: Adventure channel {channel.id} not found, already deleted.")
        except discord.Forbidden:
            print(f"ERROR: Missing permissions to delete channel {channel.name} ({channel.id}).")
        except Exception as e:
            print(f"ERROR: Error deleting channel {channel.name} ({channel.id}): {e}")

    async def _end_game(self, channel_id: int, player_id: int, delete_channel: bool = True, interaction: discord.Interaction = None):
        print(f"DEBUG: Ending game for channel {channel_id} and player {player_id}")

        game = self.active_games.get(channel_id)
        if game:
            self.active_games.pop(channel_id, None)
            utils.remove_active_adventure_channel(channel_id)
            self._remove_game_state(channel_id)

            guild = self.bot.get_guild(utils.MAIN_GUILD_ID)
            if guild:
                member = guild.get_member(player_id)
                adventure_player_role = discord.utils.get(guild.roles, name=self._temp_role_names["Adventure Player"])

                staff_role_ids = utils.MOD_ROLE_ID if isinstance(utils.MOD_ROLE_ID, list) else [utils.MOD_ROLE_ID]
                is_staff = False
                if member:
                    is_staff = any(str(role.id) in staff_role_ids for role in member.roles)

                if member and not is_staff:
                    bot_member = guild.me
                    if not bot_member.guild_permissions.manage_roles:
                        print(f"ERROR: Bot lacks 'Manage Roles' permission in guild {guild.name}. Cannot manage roles for {member.name}.")
                    else:
                        if adventure_player_role and adventure_player_role in member.roles:
                            if bot_member.top_role > adventure_player_role:
                                try:
                                    await member.remove_roles(adventure_player_role, reason="Adventure game ended.")
                                    print(f"DEBUG: Removed 'Adventure Player' role from {member.name}")
                                except discord.Forbidden:
                                    print(f"ERROR: Bot does not have permission to remove 'Adventure Player' role from {member.name}. Check role hierarchy.")
                                except Exception as e:
                                    print(f"ERROR: Unexpected error removing 'Adventure Player' role from {member.name}: {e}")
                            else:
                                print(f"WARNING: Bot's top role is not higher than 'Adventure Player' role for {member.name}. Cannot remove role.")
                        else:
                            print(f"DEBUG: 'Adventure Player' role not found or not assigned to {member.name}. No need to remove.")

                        if game.original_roles:
                            original_roles_objects = []
                            for role_id in game.original_roles:
                                role = guild.get_role(role_id)
                                if role and bot_member.top_role > role:
                                    original_roles_objects.append(role)
                                elif role:
                                    print(f"WARNING: Bot's top role is not higher than original role '{role.name}' ({role.id}) for {member.name}. Cannot restore this role.")
                                else:
                                    print(f"WARNING: Original role with ID {role_id} not found in guild {guild.name}. Skipping restoration.")

                            if original_roles_objects:
                                try:
                                    await member.add_roles(*original_roles_objects, reason="Adventure game ended - restoring original roles.")
                                    print(f"DEBUG: Restored roles to {member.name}: {[role.name for role in original_roles_objects]}")
                                except discord.Forbidden:
                                    print(f"ERROR: Bot does not have permission to add original roles to {member.name}. Check role hierarchy.")
                                except Exception as e:
                                    print(f"ERROR: Unexpected error adding original roles to {member.name}: {e}")
                            else:
                                print(f"DEBUG: No valid original roles to restore for {member.name} after filtering by bot permissions.")
                        else:
                            print(f"DEBUG: No original roles stored for {member.name} to restore.")
                elif not member:
                    print(f"INFO: Member {player_id} not found in guild {guild.name}. Cannot manage roles.")
                else:
                    print("DEBUG: User is staff. Skipping role management.")

        if delete_channel:
            channel = self.bot.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                if interaction and interaction.response.is_done():
                    await interaction.followup.send("This adventure thread will be deleted shortly. Farewell!", ephemeral=True)
                elif channel:
                    await channel.send("This adventure thread will be deleted shortly. Farewell!")

                await self._cleanup_channel(channel)

        print(f"DEBUG: End game routine complete.")

    async def _reset_game_in_channel(self, channel_id: int, player_id: int, game_theme: str):
        game = AdventureGame(
            channel_id=channel_id,
            player_id=player_id,
            player_name=self.bot.get_user(player_id).display_name,
            game_theme=game_theme,
            allowed_traps=[]
        )
        game.waiting_for_consent = True
        self.active_games[channel_id] = game
        self._save_game_state(game)

        channel = self.bot.get_channel(channel_id)
        if channel:
            consent_traps_list = [
                utils.TRAP_DISPLAY_NAMES.get(t, t.replace('_', ' ').title()) for t in utils.ALL_TRAP_OPTIONS
                if t.lower() not in self.ai_restrictions
            ]

            consent_message_text = (
                f"**Your adventure has been restarted.**\n\n"
                "Please review the following optional elements. "
                f"They can make your adventure more challenging. "
                f"Reply with a comma-separated list to consent, 'all' for everything, or 'none' to opt out.\n\n"
            )
            if consent_traps_list:
                consent_message_text += f"Optional elements: {', '.join(consent_traps_list)}."
            else:
                consent_message_text += "Due to content restrictions, no optional elements are available for consent. Your adventure will begin immediately."
                game.waiting_for_consent = False

            await channel.send(consent_message_text)

    async def _process_player_action(self, game: AdventureGame, action: str, from_button: bool = False):
        print(f"DEBUG: Processing player action: '{action}' from button: {from_button}")
        channel = self.bot.get_channel(game.channel_id)

        if not channel:
            print(f"WARNING: Channel {game.channel_id} not found. Cannot process action.")
            self._end_game(game.channel_id, game.player_id, delete_channel=False)
            return

        game.add_to_history("user", action)
        game.update_traps()
        print(f"DEBUG: Player action added to history. Current traps: {game.active_traps}")

        current_traps_for_ai = {trap: level for trap, level in game.active_traps.items() if level > 0 or level == -1}

        try:
            scenario_data = await utils.generate_scenario_adventure(
                chat_history=game.get_formatted_history(),
                player_name=game.player_name,
                current_traps=current_traps_for_ai,
                ai_restrictions=self.ai_restrictions,
                game_theme=game.game_theme,
                allowed_traps=game.allowed_traps,
                is_incapacitated=game.is_incapacitated
            )
            print(f"DEBUG: AI generated scenario data.")

            if not scenario_data:
                await channel.send("An error occurred with the AI. The scenario could not be generated. Please try again or use `/end_adventure`.")
                print("DEBUG: AI scenario data was None. Aborting turn.")
                return

            game.add_to_history("model", scenario_data["scenario_text"])
            print(f"DEBUG: AI response added to history.")

            if not game.game_theme and scenario_data.get("game_theme"):
                game.game_theme = scenario_data["game_theme"]

            if scenario_data.get("trap_effects"):
                display_to_raw_trap_names = {v.lower(): k for k, v in utils.TRAP_DISPLAY_NAMES.items()}
                for effect in scenario_data["trap_effects"]:
                    ai_trap_display_name = effect.get("name")
                    action_type = effect.get("action")
                    amount = int(effect.get("amount", 1))
                    trap_name = display_to_raw_trap_names.get(ai_trap_display_name.lower())

                    if not trap_name or not action_type or trap_name not in game.allowed_traps:
                        print(f"DEBUG: Invalid or disallowed trap effect from AI: {effect} (Reason: Trap name '{ai_trap_display_name}' not recognized or not in allowed_traps: {game.allowed_traps})")
                        continue

                    current_level = game.active_traps.get(trap_name, 0)
                    prev_incapacitated = game.is_incapacitated

                    if action_type == "apply":
                        target_level = int(effect.get("level", utils.TRAP_DURATIONS.get(trap_name, 1)))
                        game.active_traps[trap_name] = target_level
                        print(f"DEBUG: AI applied trap '{trap_name}' to level {target_level}. Active traps: {game.active_traps}")
                    elif action_type == "tighten":
                        if trap_name in ["rope", "blindfold", "ball_gag", "layers_of_tape"]:
                            max_level = getattr(utils, f"MAX_{trap_name.upper()}_LEVEL", 1)
                            if trap_name == "rope":
                                max_level = utils.MAX_ROPE_TIGHTNESS

                            game.active_traps[trap_name] = min(current_level + amount, max_level)
                        else:
                            game.active_traps[trap_name] = current_level + amount

                    game.check_incapacitation()

                    if game.is_incapacitated and not prev_incapacitated:
                        await channel.send(f"**You are now extremely restrained!** Your situation has escalated. You can still struggle, but movement and action are severely limited.")
                    elif not game.is_incapacitated and prev_incapacitated:
                        await channel.send(f"You managed to loosen some restraints! You are no longer critically incapacitated, but still bound.")
            else:
                print("DEBUG: AI response did not contain 'trap_effects'. No traps were applied in this turn.")

            if scenario_data.get("game_outcome") == "escape":
                await channel.send(f"**🎉 Congratulations, {game.player_name}!** {scenario_data['scenario_text']}")
                game.game_won = True
                await self._end_game(channel.id, game.player_id, delete_channel=True)
                return
            elif scenario_data.get("game_outcome") == "surrender":
                await channel.send(f"**Game Over!** {scenario_data['scenario_text']}")
                game.game_won = True
                await self._end_game(channel.id, game.player_id, delete_channel=True)
                return

            await self._send_adventure_message(channel, game, scenario_data)
            print(f"DEBUG: Sent new message with scenario and choices.")

        except Exception as e:
            print(f"ERROR: Error processing player action or generating scenario: {e}")
            await channel.send("An error occurred during your adventure. Please try again or use `/end_adventure`.")
            traceback.print_exc(file=sys.stdout)
            game.add_to_history("model", "An error occurred during your adventure.")
            self._save_game_state(game)
            return

    async def _send_adventure_message(self, channel, game, scenario_data):
        view = None
        choices = scenario_data.get("choices", [])

        if not isinstance(choices, list):
            print(f"ERROR: Expected 'choices' to be a list, but received type: {type(choices)}. Value: {choices}")
            await channel.send("An internal error occurred while processing your adventure. The choices could not be displayed. The game will now end.")
            await self._end_game(game.channel_id, game.player_id, delete_channel=True)
            return

        message_content = scenario_data["scenario_text"]

        if choices:
            message_content += "\n\n**Choices:**\n"
            for i, choice in enumerate(choices):
                # Check if the choice is a dictionary and get the 'text' key
                if isinstance(choice, dict) and 'text' in choice:
                    choice_text = choice['text']
                # Assume it's a string if not a dictionary
                elif isinstance(choice, str):
                    choice_text = choice
                else:
                    choice_text = "Invalid choice format" # Handle unexpected format gracefully

                message_content += f"{i + 1}. {choice_text}\n"
            view = AdventureChoicesView(self, game.player_id, choices)

        if scenario_data.get("game_outcome") not in ["escape", "surrender"]:
            sent_message = await channel.send(message_content, view=view)
            if view:
                view.message = sent_message
                game.current_choices = choices
                self._save_game_state(game)
        else:
            game_over_view = AdventureGameOverView(self, channel.id, game.player_id, game.game_theme)
            sent_message = await channel.send(message_content, view=game_over_view)
            game_over_view.message = sent_message


    @app_commands.command(name="choose_adventure", description="Starts a new text adventure game.")
    @app_commands.describe(theme="An optional theme for your adventure (e.g., 'haunted mansion', 'space exploration').")
    async def choose_adventure(self, interaction: discord.Interaction, theme: str = None):
        await interaction.response.defer(ephemeral=True)
        print(f"DEBUG: /choose_adventure command received from {interaction.user.name}")

        player_id = interaction.user.id

        for game_channel_id, game_instance in list(self.active_games.items()):
            if game_instance.player_id == player_id:
                existing_channel = self.bot.get_channel(game_channel_id)
                if isinstance(existing_channel, discord.TextChannel):
                    await interaction.followup.send(f"You already have an active adventure in {existing_channel.mention}. Please finish or stop that one first using `/end_adventure`.", ephemeral=True)
                    return
                else:
                    print(f"DEBUG: Found orphaned game for {player_id} in non-existent channel {game_channel_id}. Cleaning up.")
                    await self._end_game(game_channel_id, player_id, delete_channel=False)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return

        adventure_main_channel_id = utils.ADVENTURE_MAIN_CHANNEL_ID
        if not adventure_main_channel_id:
            await interaction.followup.send("The main adventure channel is not configured. Please contact an admin.", ephemeral=True)
            return

        main_channel = self.bot.get_channel(adventure_main_channel_id)
        if not isinstance(main_channel, discord.TextChannel):
            await interaction.followup.send("The main adventure channel is not a valid text channel. Please contact an admin.", ephemeral=True)
            return

        staff_role_ids = utils.MOD_ROLE_ID if isinstance(utils.MOD_ROLE_ID, list) else [utils.MOD_ROLE_ID]
        is_staff = any(str(r.id) in staff_role_ids for r in interaction.user.roles)

        if not guild.me.guild_permissions.manage_roles or not guild.me.guild_permissions.manage_channels:
            if is_staff:
                print(f"WARNING (Staff): Bot lacks 'Manage Roles' or 'Manage Channels' permissions, but the command was executed by a staff member. Proceeding, but role/channel management may fail.")
            else:
                await interaction.followup.send("I don't have enough permissions to manage roles or channels. Please grant me 'Manage Roles' and 'Manage Channels' permissions.", ephemeral=True)
                return

        new_thread = None

        try:
            thread_name = f"adventure-{interaction.user.name.lower().replace(' ', '-')}"

            new_thread = await main_channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.public_thread
            )
            print(f"DEBUG: New thread created: {new_thread.id}")

            game = AdventureGame(new_thread.id, interaction.user.id, interaction.user.display_name, game_theme=theme, allowed_traps=[])
            game.waiting_for_consent = True

            self.active_games[new_thread.id] = game
            utils.set_active_adventure_channel(new_thread.id, game)
            print(f"DEBUG: Game state initialized and added to active games.")

            user_roles_to_restore = []

            if not is_staff:
                for role in interaction.user.roles:
                    if role != guild.default_role and guild.me.top_role > role:
                        user_roles_to_restore.append(role)
                game.original_roles = [role.id for role in user_roles_to_restore]

            adventure_player_role = discord.utils.get(guild.roles, name=self._temp_role_names["Adventure Player"])
            if adventure_player_role and not is_staff:
                if guild.me.top_role > adventure_player_role:
                    try:
                        if user_roles_to_restore:
                            await interaction.user.remove_roles(*user_roles_to_restore, reason="Started adventure game - removing old roles.")
                            print(f"DEBUG: Removed roles from {interaction.user.name}: {[role.name for role in user_roles_to_restore]}")

                        await interaction.user.add_roles(adventure_player_role, reason="Started adventure game.")
                        print(f"DEBUG: Assigned 'Adventure Player' role to {interaction.user.name}")
                    except discord.Forbidden:
                        print("WARNING: Could not manage roles. Missing permissions. Please ensure my role is above other roles I need to manage.")
                    except Exception as e:
                        print(f"WARNING: Error managing roles: {e}")
                else:
                    await interaction.followup.send(f"Warning: I cannot assign the '{adventure_player_role.name}' role because my role is too low. Please adjust role hierarchy.", ephemeral=True)
            elif is_staff:
                print("DEBUG: Staff member started an adventure. Skipping role management.")
            else:
                await interaction.followup.send("Warning: 'Adventure Player' role not found. Please create it or configure `utils.ROLE_NAMES`.", ephemeral=True)

            await interaction.followup.send(f"Your adventure has begun in {new_thread.mention}! Please go to that thread to proceed.", ephemeral=False)

            consent_traps_list = [
                utils.TRAP_DISPLAY_NAMES.get(t, t.replace('_', ' ').title()) for t in utils.ALL_TRAP_OPTIONS
                if t.lower() not in self.ai_restrictions
            ]

            consent_message_text = (
                f"**Welcome, {interaction.user.mention}!**\n\n"
                "Before we begin, please review the following optional elements. "
                "These elements can make your adventure more challenging and immersive. "
                "**To consent to multiple elements, reply with a comma-separated list (e.g., 'Ropes, Blindfold'). "
                "You can also reply with 'all' to consent to everything, or 'none' to opt out of all optional elements.**\n\n"
                "**Game Goal:** Your primary objective is to escape the scenario you find yourself in. "
                "**How to Play:** You'll be presented with choices, which you can select by typing the corresponding number (e.g., `1`). "
                "Alternatively, you can always type out any custom action you wish to attempt; the Game Master will interpret your intent. "
                "**Need to Stop?** If at any point you feel uncomfortable or wish to end the game, simply use the `/end_adventure` command. "
                "Don't worry about choosing an ending, as you will always have the option to retry the scenario after a game over.\n\n"
            )
            if consent_traps_list:
                consent_message_text += f"Now, please let me know which of the following optional elements you consent to potentially encounter: {', '.join(consent_traps_list)}."
            else:
                consent_message_text += "Due to content restrictions, no optional elements are available for consent. Your adventure will begin immediately."
                game.waiting_for_consent = False

            await new_thread.send(consent_message_text)
            self._save_game_state(game)

            if not game.waiting_for_consent:
                await self._start_initial_scenario(new_thread, game)

        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to create threads in that channel or assign roles. Please check my permissions.", ephemeral=True)
            print(f"ERROR: Forbidden error starting adventure for {interaction.user.name}.")
        except Exception as e:
            await interaction.followup.send(f"An unexpected error occurred while starting your adventure: {e}", ephemeral=True)
            print(f"ERROR: Unexpected error starting adventure: {e}")
            traceback.print_exc(file=sys.stdout)

    async def _start_initial_scenario(self, channel, game):
        try:
            scenario_data = await utils.generate_scenario_adventure(
                chat_history=game.get_formatted_history(),
                player_name=game.player_name,
                current_traps={},
                ai_restrictions=self.ai_restrictions,
                game_theme=game.game_theme,
                allowed_traps=game.allowed_traps,
                is_incapacitated=game.is_incapacitated
            )

            if not scenario_data or not isinstance(scenario_data, dict) or 'scenario_text' not in scenario_data:
                await channel.send("An error occurred while generating the scenario. Please try again or use `/end_adventure` to restart.")
                print(f"ERROR: Invalid or empty scenario_data received from AI after consent. Data: {scenario_data}")
                game.add_to_history("model", "An internal error occurred.")
                self._save_game_state(game)
                return

            game.add_to_history("model", scenario_data["scenario_text"])

            if not scenario_data.get("trap_effects"):
                print("DEBUG: AI response missing 'trap_effects' key for initial scenario. Inferring from scenario_text.")
                lower_scenario = scenario_data.get('scenario_text', '').lower()
                for trap_name, display_name in utils.TRAP_DISPLAY_NAMES.items():
                    if display_name.lower() in lower_scenario and trap_name in game.allowed_traps:
                        if trap_name not in game.active_traps:
                            game.active_traps[trap_name] = utils.TRAP_DURATIONS.get(trap_name, 1)
                            print(f"DEBUG: Inferred and applied trap '{trap_name}' from scenario text. Active traps: {game.active_traps}")
                game.check_incapacitation()

            await self._send_adventure_message(channel, game, scenario_data)
        except Exception as e:
            print(f"ERROR: Error starting initial scenario: {e}")
            traceback.print_exc(file=sys.stdout)
            await channel.send("An error occurred while starting your adventure. Please use `/end_adventure` to try again.")


    @app_commands.command(name="end_adventure", description="Ends your current text adventure game.")
    @app_commands.describe(user="The user whose adventure game to end (for staff only).")
    async def end_adventure(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        await interaction.response.defer(ephemeral=True)
        print(f"DEBUG: /end_adventure command received from {interaction.user.name}")

        target_id = interaction.user.id
        target_name = interaction.user.display_name
        is_mod_action = False

        staff_role_ids = utils.MOD_ROLE_ID if isinstance(utils.MOD_ROLE_ID, list) else [utils.MOD_ROLE_ID]
        is_mod = any(str(r.id) in staff_role_ids for r in interaction.user.roles)

        if user:
            if not is_mod:
                await interaction.followup.send("You do not have permission to end another user's game.", ephemeral=True)
                return
            target_id = user.id
            target_name = user.display_name
            is_mod_action = True
            print(f"DEBUG: Mod action detected. Target user: {target_name}")

        game_channel_id = None
        for channel_id, game in self.active_games.items():
            if game.player_id == target_id:
                game_channel_id = channel_id
                break

        if game_channel_id is None:
            if is_mod_action:
                await interaction.followup.send(f"I couldn't find an active adventure game for {target_name}.", ephemeral=True)
            else:
                await interaction.followup.send("You don't have an active adventure game running.", ephemeral=True)
            print(f"DEBUG: No active game found for target {target_name}.")
            return

        channel = self.bot.get_channel(game_channel_id)

        if channel:
            if is_mod_action:
                await channel.send(f"The adventure has been ended for {user.mention} by {interaction.user.mention}. This thread will be deleted shortly.")
            else:
                await channel.send(f"{interaction.user.mention} has ended their adventure. This thread will be deleted shortly.")

        await self._end_game(game_channel_id, target_id, delete_channel=True, interaction=interaction)

        if is_mod_action:
            await interaction.followup.send(f"Successfully ended the adventure game for {user.mention}.", ephemeral=True)
        print("DEBUG: End adventure routine finished.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        print(f"DEBUG: Message received from {message.author.name} in channel {message.channel.id}.")
        if message.author.id == self.bot.user.id:
            print("DEBUG: Message is from this bot, ignoring.")
            return

        try:
            game = self.active_games.get(message.channel.id)
            if not game:
                print("DEBUG: No active game found for this channel.")
                return

            if game.player_id == message.author.id and not game.game_won:
                print("DEBUG: Message is from the correct player in an active game.")
                player_input = message.content

                is_choice_number = False
                choice_text = None
                if player_input.isdigit():
                    choice_index = int(player_input) - 1
                    if 0 <= choice_index < len(game.current_choices):
                        choice_data = game.current_choices[choice_index]
                        if isinstance(choice_data, dict) and 'text' in choice_data:
                            choice_text = choice_data['text']
                        elif isinstance(choice_data, str):
                            choice_text = choice_data
                        else:
                            choice_text = None # or some other default
                        is_choice_number = True
                    else:
                        await message.channel.send("That is not a valid choice number. Please choose from the list or type a custom action.")
                        return

                if game.waiting_for_consent:
                    print("DEBUG: Game is waiting for consent, processing text input.")
                    consented_traps = utils.parse_consent_from_text(player_input, self.ai_restrictions)
                    game.allowed_traps = consented_traps
                    game.waiting_for_consent = False
                    self._save_game_state(game)
                    print("DEBUG: Consent processed, starting new scenario generation.")
                    await self._start_initial_scenario(message.channel, game)
                    return
                else:
                    action_to_process = choice_text if is_choice_number else player_input
                    print(f"DEBUG: Player submitted custom text action or choice: '{action_to_process}'")
                    await self._process_player_action(game, action_to_process)
                    return
        except Exception as e:
            print(f"ERROR: An unexpected error occurred in the on_message listener for adventure game: {e}")
            traceback.print_exc(file=sys.stdout)

        await self.bot.process_commands(message)


async def setup(bot):
    await bot.add_cog(Adventure(bot))