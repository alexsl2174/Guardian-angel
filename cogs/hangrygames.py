import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import asyncio
import random
import json
import textwrap
import datetime
from typing import List, Dict, Any, Union, Optional
from cogs.utils import load_data, save_data, update_user_money, generate_hangry_event, load_hangrygames_state, save_hangrygames_state, generate_duel_image, generate_solo_death_image, generate_win_image

# --- Configuration and Helper Functions ---

HANGRY_GAMES_STATE_FILE = os.path.join("data", "hangrygames_state.json")
HANGRY_GAMES_WIN_AMOUNT = 250
HANGRY_GAMES_TEAM_WIN_POINTS = 100
ANNOUNCEMENTS_CHANNEL_ID = 825930140478603314

# Define team roles based on user input
DOM_TEAM_ROLES = [829539869889658910, 829540044959645716]
SUB_TEAM_ROLES = [829539964613558272, 1003828021041573958]

def load_config():
    """Loads the bot configuration from a JSON file."""
    try:
        with open('bot_config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("bot_config.json not found!")
        return {"role_ids": {"Staff": []}}

def load_server_wins():
    return load_data(os.path.join("data", "server_wins.json"), {})

def save_server_wins(data):
    save_data(data, os.path.join("data", "server_wins.json"))

def load_global_wins():
    return load_data(os.path.join("data", "global_wins.json"), {})

def save_global_wins(data):
    save_data(data, os.path.join("data", "global_wins.json"))

def load_hangry_games_teams_state():
    """Loads the hangry games team state from a JSON file."""
    if os.path.exists(HANGRY_GAMES_STATE_FILE):
        with open(HANGRY_GAMES_STATE_FILE, 'r') as f:
            state = json.load(f)
            # Ensure the reward_points and team keys exist
            if 'reward_points' not in state:
                state['reward_points'] = 1
            if 'dom' not in state:
                state['dom'] = {"points": 0}
            if 'sub' not in state:
                state['sub'] = {"points": 0}
            return state
    return {"dom": {"points": 0}, "sub": {"points": 0}, "reward_points": 1}

def save_hangry_games_teams_state(state):
    """Saves the hangry games team state to a JSON file."""
    with open(HANGRY_GAMES_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

# --- HangryGamesCog Class ---

class HangryGamesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = load_config()
        self.state = load_hangrygames_state()
        self.team_state = load_hangry_games_teams_state()
        self.game_channel_id = None
        self.active_message_id = None
        self.last_event_time = None
        self.tributes = []

    class GameStartView(discord.ui.View):
        def __init__(self, cog, embed):
            super().__init__(timeout=180)
            self.cog = cog
            self.embed = embed

        @discord.ui.button(label="Join", style=discord.ButtonStyle.green, custom_id="join_hangry_games")
        async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not self.cog.state.get("is_active") or interaction.channel_id != self.cog.state.get("channel_id"):
                return await interaction.response.send_message("The game is not active or this is not the game channel.", ephemeral=True)

            user_id_str = str(interaction.user.id)
            if user_id_str in self.cog.state["tributes"]:
                return await interaction.response.send_message("You have already joined!", ephemeral=True)
                
            self.cog.state["tributes"][user_id_str] = {"kills": 0}
            save_hangrygames_state(self.cog.state)
            
            tribute_mentions = [self.cog.bot.get_user(int(uid)).mention for uid in self.cog.state["tributes"].keys() if self.cog.bot.get_user(int(uid))]
            if tribute_mentions:
                self.embed.set_field_at(0, name=f"Volunteers ({len(tribute_mentions)})", value="\n".join(tribute_mentions), inline=False)
            else:
                self.embed.set_field_at(0, name="Volunteers", value="No one has joined yet.", inline=False)

            # Use interaction.response.edit_message to update the original message
            await interaction.response.edit_message(embed=self.embed, view=self)
            # Sending a follow-up message to the user that joined
            await interaction.followup.send(f"{interaction.user.mention} has joined the game!", ephemeral=True)

        @discord.ui.button(label="Start", style=discord.ButtonStyle.red, custom_id="start_hangry_games")
        async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not self.cog.state.get("is_active") or interaction.channel_id != self.cog.state.get("channel_id"):
                return await interaction.response.send_message("The game is not active or this is not the game channel.", ephemeral=True)

            if len(self.cog.state['tributes']) < 2:
                return await interaction.response.send_message("You need at least 2 tributes to start the game!", ephemeral=True)
                
            for item in self.children:
                item.disabled = True
            # Use interaction.response.edit_message to update the original message
            await interaction.response.edit_message(view=self)
            
            self.cog.state["start_time"] = datetime.datetime.now().isoformat()
            save_hangrygames_state(self.cog.state)
            
            if not self.cog.run_game_events.is_running():
                self.cog.run_game_events.start()
        
    @tasks.loop(minutes=2)
    async def run_game_events(self):
        if not self.state.get("is_active"):
            return

        channel = self.bot.get_channel(self.state["channel_id"])
        if not channel:
            print("Hangry Games channel not found.")
            return

        tribute_ids = list(self.state["tributes"].keys())
        random.shuffle(tribute_ids)
        
        if len(tribute_ids) > 4:
            events_to_run = min(3, len(tribute_ids) // 2)
            for _ in range(events_to_run):
                if len(self.state["tributes"]) < 2:
                    break
                tributes_in_event_ids = random.sample(list(self.state["tributes"].keys()), 2)
                tribute1 = self.bot.get_user(int(tributes_in_event_ids[0]))
                tribute2 = self.bot.get_user(int(tributes_in_event_ids[1]))

                if not tribute1 or not tribute2:
                    if not tribute1: del self.state['tributes'][tributes_in_event_ids[0]]
                    if not tribute2: del self.state['tributes'][tributes_in_event_ids[1]]
                    continue

                event = await generate_hangry_event([tribute1, tribute2], "duel")
                
                # New and improved validation
                if event:
                    try:
                        # Find the correct keys regardless of case
                        winner_key = next(key for key in event.keys() if key.lower() == 'winner')
                        loser_key = next(key for key in event.keys() if key.lower() == 'loser')

                        winner_name = event[winner_key]
                        loser_name = event[loser_key]

                        winner_id = None
                        loser_id = None

                        if winner_name == tribute1.display_name:
                            winner_id = tribute1.id
                            loser_id = tribute2.id
                        elif winner_name == tribute2.display_name:
                            winner_id = tribute2.id
                            loser_id = tribute1.id
                        else:
                            winner_obj, loser_obj = random.sample([tribute1, tribute2], 2)
                            winner_id = winner_obj.id
                            loser_id = loser_obj.id

                        image_file = await generate_duel_image(tribute1.display_avatar.url, tribute2.display_avatar.url)

                        if str(winner_id) in self.state['tributes']:
                            self.state['tributes'][str(winner_id)]['kills'] = self.state['tributes'][str(winner_id)].get('kills', 0) + 1
                        if str(loser_id) in self.state['tributes']:
                            del self.state['tributes'][str(loser_id)]
                        
                        await channel.send(f"⚔️ **{event['title']}**\n{event['description'].format(winner=self.bot.get_user(winner_id).mention, loser=self.bot.get_user(loser_id).mention)}", file=image_file)
                    except (KeyError, StopIteration):
                        # Fallback for unexpected AI response
                        await channel.send(f"An unexpected outcome occurred. The game continues...")
                else:
                    await channel.send(f"An unexpected outcome occurred. The game continues...")
        
        elif len(tribute_ids) > 1:
            event_type = random.choice(["duel", "solo_death"])

            if event_type == "duel" and len(tribute_ids) >= 2:
                tributes_in_event_ids = random.sample(tribute_ids, 2)
                tribute1 = self.bot.get_user(int(tributes_in_event_ids[0]))
                tribute2 = self.bot.get_user(int(tributes_in_event_ids[1]))

                if not tribute1 or not tribute2:
                    if not tribute1: del self.state['tributes'][tributes_in_event_ids[0]]
                    if not tribute2: del self.state['tributes'][tributes_in_event_ids[1]]
                    save_hangrygames_state(self.state)
                    await channel.send("A tribute was not found and has been removed from the game.")
                    return

                event = await generate_hangry_event([tribute1, tribute2], "duel")
                
                if event:
                    try:
                        # Find the correct keys regardless of case
                        winner_key = next(key for key in event.keys() if key.lower() == 'winner')
                        loser_key = next(key for key in event.keys() if key.lower() == 'loser')
                        
                        winner_name = event[winner_key]
                        loser_name = event[loser_key]

                        winner_id = None; loser_id = None
                        if winner_name == tribute1.display_name:
                            winner_id, loser_id = tribute1.id, tribute2.id
                        elif winner_name == tribute2.display_name:
                            winner_id, loser_id = tribute2.id, tribute1.id
                        else:
                            winner_obj, loser_obj = random.sample([tribute1, tribute2], 2)
                            winner_id, loser_id = winner_obj.id, loser_obj.id
                        
                        image_file = await generate_duel_image(tribute1.display_avatar.url, tribute2.display_avatar.url)

                        if str(winner_id) in self.state['tributes']: self.state['tributes'][str(winner_id)]['kills'] = self.state['tributes'][str(winner_id)].get('kills', 0) + 1
                        if str(loser_id) in self.state['tributes']: del self.state['tributes'][str(loser_id)]
                        
                        await channel.send(f"⚔️ **{event['title']}**\n{event['description'].format(winner=self.bot.get_user(winner_id).mention, loser=self.bot.get_user(loser_id).mention)}", file=image_file)
                    except (KeyError, StopIteration):
                        # Fallback for unexpected AI response
                        await channel.send(f"An unexpected outcome occurred. The game continues...")
                else:
                    await channel.send("An unexpected outcome occurred. The game continues...")

            elif event_type == "solo_death" and len(tribute_ids) >= 1:
                victim_id = random.choice(tribute_ids)
                victim = self.bot.get_user(int(victim_id))
                if not victim:
                    del self.state['tributes'][victim_id]
                    save_hangrygames_state(self.state)
                    await channel.send("A tribute was not found and has been removed from the game.")
                    return
                
                event = await generate_hangry_event([victim], "solo_death")
                
                if event:
                    try:
                        tribute_name_key = next(key for key in event.keys() if key.lower() == 'tribute')
                        
                        if event[tribute_name_key] == victim.display_name and str(victim.id) in self.state['tributes']:
                            image_file = await generate_solo_death_image(victim.display_avatar.url)
                            await channel.send(f"🔪 **{event['title']}**\n{event['description'].format(tribute=victim.mention)}", file=image_file)
                            del self.state['tributes'][str(victim.id)]
                        else:
                            await channel.send(f"An unexpected outcome occurred for {victim.mention}. The game continues...")
                            if str(victim.id) in self.state['tributes']:
                                del self.state['tributes'][str(victim.id)]
                    except (KeyError, StopIteration):
                        await channel.send(f"An unexpected outcome occurred for {victim.mention}. The game continues...")
                        if str(victim.id) in self.state['tributes']:
                            del self.state['tributes'][str(victim.id)]
                elif victim:
                    await channel.send(f"An unexpected outcome occurred for {victim.mention}. The game continues...")
                    if str(victim.id) in self.state['tributes']:
                        del self.state['tributes'][str(victim.id)]
        
        tribute_ids = list(self.state["tributes"].keys())
        if len(tribute_ids) == 1:
            winner_id = tribute_ids[0]
            winner = self.bot.get_user(int(winner_id))
            if winner:
                await asyncio.sleep(5)
                await self.declare_winner(winner)
            self.state = {"is_active": False}
            self.run_game_events.cancel()
        elif len(tribute_ids) == 0:
            await channel.send("The game has ended with no winner. How anticlimactic.")
            self.state = {"is_active": False}
            self.run_game_events.cancel()

        save_hangrygames_state(self.state)

    async def declare_winner(self, winner: discord.User):
        channel = self.bot.get_channel(self.state["channel_id"])
        
        start_time_str = self.state.get("start_time")
        time_survived = "unknown"
        if start_time_str:
            start_time = datetime.datetime.fromisoformat(start_time_str)
            duration = datetime.datetime.now() - start_time
            minutes, seconds = divmod(duration.seconds, 60)
            time_survived = f"{minutes:02d}m {seconds:02d}s"

        server_wins = load_server_wins()
        
        guild_id_str = str(self.state.get("guild_id"))
        user_id_str = str(winner.id)

        server_wins[guild_id_str] = server_wins.get(guild_id_str, {})
        server_wins[guild_id_str][user_id_str] = server_wins[guild_id_str].get(user_id_str, 0) + 1
        save_server_wins(server_wins)
        
        total_kills = self.state['tributes'][user_id_str].get('kills', 0)
        total_server_wins = server_wins[guild_id_str][user_id_str]
        
        update_user_money(winner.id, HANGRY_GAMES_WIN_AMOUNT)
        
        guild = self.bot.get_guild(self.state.get("guild_id"))
        member = guild.get_member(winner.id)
        
        team_winner = None
        if member:
            user_role_ids = [role.id for role in member.roles]
            if any(role_id in user_role_ids for role_id in DOM_TEAM_ROLES):
                team_winner = "dom"
            elif any(role_id in user_role_ids for role_id in SUB_TEAM_ROLES):
                team_winner = "sub"
            else:
                team_winner = random.choice(["dom", "sub"])
        else:
            team_winner = random.choice(["dom", "sub"])

        points_gained = self.team_state.get('reward_points', 1)
        self.team_state[team_winner]['points'] += points_gained
        save_hangry_games_teams_state(self.team_state)

        win_image_file = await generate_win_image(winner.display_avatar.url)

        embed = discord.Embed(
            title=f"Congratulations {winner.display_name}!",
            description=f"They have been awarded <a:starcoin:1280590254935380038>{HANGRY_GAMES_WIN_AMOUNT} for their culinary prowess!\n\nThey gained **{points_gained}** points for their team.",
            color=discord.Color.green()
        )
        embed.add_field(name="Statistics", value=f"**Total kills:** {total_kills}\n**Time survived:** {time_survived}\n**Total wins in server:** {total_server_wins}")
        embed.set_image(url="attachment://winner_card.png")
        embed.set_footer(text=f"Insufferable Doms: {self.team_state['dom']['points']} | Fantastic Brats: {self.team_state['sub']['points']}")
        
        await channel.send(file=win_image_file, embed=embed)
        
        if self.team_state[team_winner]['points'] >= HANGRY_GAMES_TEAM_WIN_POINTS:
            announcements_channel = self.bot.get_channel(ANNOUNCEMENTS_CHANNEL_ID)
            
            # --- New Embed Logic for the 100-Point Team Win ---
            winner_name = "Fantastic Brats" if team_winner == "sub" else "Insufferable Doms"
            team_color = discord.Color.blue() if team_winner == "sub" else discord.Color.red()
            
            # Gather all tribute data to build a leaderboard
            all_tributes_data = self.state['tributes']
            leaderboard_entries = []
            for user_id_str, user_data in all_tributes_data.items():
                member = guild.get_member(int(user_id_str))
                if member:
                    leaderboard_entries.append((member.display_name, user_data.get('kills', 0)))
            
            # Sort by kills in descending order
            leaderboard_entries.sort(key=lambda x: x[1], reverse=True)
            
            leaderboard_string = "\n".join([f"{i+1}. **{name}** - {kills} Kills" for i, (name, kills) in enumerate(leaderboard_entries[:10])])
            
            team_win_embed = discord.Embed(
                title=f"{winner_name} Win!",
                description=f"Safe to say the **{winner_name}** won the Hangry Games with {self.team_state[team_winner]['points']} points!",
                color=team_color
            )
            team_win_embed.add_field(name="Top Contributors", value=leaderboard_string if leaderboard_string else "No one contributed to this round.", inline=False)
            
            if announcements_channel:
                await announcements_channel.send(embed=team_win_embed)
                await announcements_channel.send(f"The Hangry Games have been reset.")
            # --- End of New Embed Logic ---
                
            self.team_state['sub']['points'] = 0
            self.team_state['dom']['points'] = 0
            save_hangry_games_teams_state(self.team_state)

    @app_commands.command(name="add_hangry_points", description="[Staff Only] Manually adds points to a team's score.")
    @app_commands.describe(
        points="The number of points to add.",
        team="The team to add points to ('dom' or 'sub')."
    )
    @commands.has_any_role(*[role_id for role_id in load_config()["role_ids"]["Staff"]])
    async def add_hangry_points(self, interaction: discord.Interaction, points: int, team: str):
        await interaction.response.defer(ephemeral=True)

        team = team.lower()
        if team not in ["dom", "sub"]:
            return await interaction.followup.send("Invalid team name. Please use 'dom' or 'sub'.")

        if points < 0:
            return await interaction.followup.send("You cannot add a negative point value.")
            
        try:
            current_points = self.team_state[team]['points']
            self.team_state[team]['points'] = current_points + points
            save_hangry_games_teams_state(self.team_state)
            
            await interaction.followup.send(
                f"Successfully added **{points}** points to the **{team}** team. "
                f"They now have **{self.team_state[team]['points']}** points."
            )
        except KeyError:
            await interaction.followup.send("An error occurred. The team data might be missing from the state file.")

    @app_commands.command(name="hangrygames", description="Start a new Hangry Games!")
    async def hangry_new(self, interaction: discord.Interaction):
        if self.state.get("is_active"):
            return await interaction.response.send_message("A game is already in progress!", ephemeral=True)

        self.state = {
            "is_active": True,
            "channel_id": interaction.channel_id,
            "guild_id": interaction.guild_id,
            "tributes": {},
            "start_time": datetime.datetime.now().isoformat()
        }
        save_hangrygames_state(self.state)

        embed = discord.Embed(
            title="The Hangry Games",
            description=textwrap.dedent("""
            Part 1 - Setting The Table
            🍽️ to join the fight!
            🔪 to let the battle begin!
            """),
            color=discord.Color.orange()
        )
        embed.add_field(name="Volunteers", value="No one has joined yet.")
        
        view = self.GameStartView(self, embed)

        await interaction.response.send_message(embed=embed, view=view)
        
    @app_commands.command(name="end_hangrygames", description="Forcefully ends the current Hangry Games (Admin only).")
    @commands.has_permissions(administrator=True)
    async def end_hangrygames(self, interaction: discord.Interaction):
        if not self.state.get("is_active"):
            return await interaction.response.send_message("There is no active Hangry Games to end.", ephemeral=True)
        
        self.state = {"is_active": False}
        save_hangrygames_state(self.state)
        if self.run_game_events.is_running():
            self.run_game_events.cancel()
        
        await interaction.response.send_message("The current Hangry Games has been forcefully ended.")
        
    @app_commands.command(name="set_hangry_reward", description="[Staff Only] Sets the point total awarded for a Hangry Games win.")
    @app_commands.describe(
        points="The number of points to be awarded to the winning team."
    )
    @commands.has_any_role(*[role_id for role_id in load_config()["role_ids"]["Staff"]])
    async def set_hangry_reward(self, interaction: discord.Interaction, points: int):
        await interaction.response.defer(ephemeral=True)

        if points < 0:
            return await interaction.followup.send("You cannot set a negative point value.")
        
        self.team_state['reward_points'] = points
        save_hangry_games_teams_state(self.team_state)

        await interaction.followup.send(
            f"Successfully set the reward for a Hangry Games win to **{points}** points."
        )

async def setup(bot):
    await bot.add_cog(HangryGamesCog(bot))
    print("Hangry Games Cog Loaded!")
