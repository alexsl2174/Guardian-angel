import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import asyncio
import random
import json
import textwrap
import traceback
import datetime
from typing import List, Dict, Any, Union, Optional
from cogs.utils import load_data, save_data, update_user_money, generate_hangry_event, load_hangrygames_state, save_hangrygames_state, generate_duel_image, generate_solo_death_image, generate_win_image

HANGRY_GAMES_STATE_FILE = os.path.join("data", "hangrygames_state.json")
HANGRY_GAMES_WIN_AMOUNT = 250

def load_server_wins():
    return load_data(os.path.join("data", "server_wins.json"), {})

def save_server_wins(data):
    save_data(data, os.path.join("data", "server_wins.json"))

def load_global_wins():
    return load_data(os.path.join("data", "global_wins.json"), {})

def save_global_wins(data):
    save_data(data, os.path.join("data", "global_wins.json"))

class HangryGamesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state = load_hangrygames_state()
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

            await interaction.response.edit_message(embed=self.embed, view=self)
            await interaction.followup.send(f"{interaction.user.mention} has joined the game!", ephemeral=True)

        @discord.ui.button(label="Start", style=discord.ButtonStyle.red, custom_id="start_hangry_games")
        async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not self.cog.state.get("is_active") or interaction.channel_id != self.cog.state.get("channel_id"):
                return await interaction.response.send_message("The game is not active or this is not the game channel.", ephemeral=True)

            if len(self.cog.state['tributes']) < 2:
                return await interaction.response.send_message("You need at least 2 tributes to start the game!", ephemeral=True)
                
            for item in self.children:
                item.disabled = True
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
        
        # Handle a free-for-all if there are many tributes left
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
                if event and 'title' in event and 'description' in event and 'winner' in event and 'loser' in event:
                    winner_name = event['winner']
                    loser_name = event['loser']

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

        # Handle a single event if there are 2-4 tributes left
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
                if event and 'title' in event and 'description' in event and 'winner' in event and 'loser' in event:
                    winner_name = event['winner']
                    loser_name = event['loser']
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

            elif event_type == "solo_death" and len(tribute_ids) >= 1:
                victim_id = random.choice(tribute_ids)
                victim = self.bot.get_user(int(victim_id))
                if not victim:
                    del self.state['tributes'][victim_id]
                    save_hangrygames_state(self.state)
                    await channel.send("A tribute was not found and has been removed from the game.")
                    return
                
                event = await generate_hangry_event([victim], "solo_death")
                
                # More robust check for all required keys in the event dictionary
                if event and all(key in event for key in ['title', 'description', 'tribute']):
                    # Check that the victim name from the AI event still exists in the game state
                    if event['tribute'] == victim.display_name and str(victim.id) in self.state['tributes']:
                        image_file = await generate_solo_death_image(victim.display_avatar.url)
                        await channel.send(f"🔪 **{event['title']}**\n{event['description'].format(tribute=victim.mention)}", file=image_file)
                        del self.state['tributes'][str(victim.id)]
                    else:
                        # Fallback for an invalid AI response or name mismatch
                        await channel.send(f"An unexpected outcome occurred for {victim.mention}. The game continues...")
                        if str(victim.id) in self.state['tributes']:
                            del self.state['tributes'][str(victim.id)]
                elif victim:
                    # Fallback if the AI response was completely invalid (e.g., missing keys)
                    await channel.send(f"An unexpected outcome occurred for {victim.mention}. The game continues...")
                    if str(victim.id) in self.state['tributes']:
                        del self.state['tributes'][str(victim.id)]
        
        # Check for winner or no tributes left
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
        
        # Calculate time survived
        start_time_str = self.state.get("start_time")
        time_survived = "unknown"
        if start_time_str:
            start_time = datetime.datetime.fromisoformat(start_time_str)
            duration = datetime.datetime.now() - start_time
            minutes, seconds = divmod(duration.seconds, 60)
            time_survived = f"{minutes:02d}m {seconds:02d}s"

        # Update win counts
        server_wins = load_server_wins()
        
        guild_id_str = str(self.state.get("guild_id"))
        user_id_str = str(winner.id)

        server_wins[guild_id_str] = server_wins.get(guild_id_str, {})
        server_wins[guild_id_str][user_id_str] = server_wins[guild_id_str].get(user_id_str, 0) + 1
        save_server_wins(server_wins)
        
        total_kills = self.state['tributes'][user_id_str].get('kills', 0)
        total_server_wins = server_wins[guild_id_str][user_id_str]
        
        update_user_money(winner.id, HANGRY_GAMES_WIN_AMOUNT)
        
        # Generate the winner image
        win_image_file = await generate_win_image(winner.display_avatar.url)

        embed = discord.Embed(
            title=f"Congratulations {winner.display_name}!",
            description=f"They have been awarded <a:starcoin:1280590254935380038>{HANGRY_GAMES_WIN_AMOUNT} for their culinary prowess!",
            color=discord.Color.green()
        )
        embed.add_field(name="Statistics", value=f"**Total kills:** {total_kills}\n**Time survived:** {time_survived}\n**Total wins in server:** {total_server_wins}")
        embed.set_image(url="attachment://winner_card.png")
        
        await channel.send(file=win_image_file, embed=embed)
        
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

async def setup(bot):
    await bot.add_cog(HangryGamesCog(bot))
    print("Hangry Games Cog Loaded!")