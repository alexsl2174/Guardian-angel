import discord
from discord.ui import Button, View
import os
import json
import math
from typing import List, Dict, Any, Union, Optional
from cogs.BugData import load_bug_collection, save_bug_collection, INSECT_LIST

class BugbookListView(discord.ui.View):
    def __init__(self, target_user: discord.Member, unique_bugs, total_unique_bugs, bugs_per_page, total_pages, cog):
        super().__init__(timeout=None)
        self.target_user = target_user
        self.unique_bugs = unique_bugs
        self.total_unique_bugs = total_unique_bugs
        self.bugs_per_page = bugs_per_page
        self.total_pages = total_pages
        self.current_page = 1
        self.cog = cog
        self.update_buttons()

    async def get_page_embed(self):
        start_index = (self.current_page - 1) * self.bugs_per_page
        end_index = start_index + self.bugs_per_page
        bugs_to_display = self.unique_bugs[start_index:end_index]
        
        bug_list_text = []
        bug_collection = load_bug_collection()
        caught_bugs_all = bug_collection.get(str(self.target_user.id), {}).get('caught', [])
        
        for bug_name in bugs_to_display:
            count = caught_bugs_all.count(bug_name)
            bug_info = next((i for i in INSECT_LIST if i['name'] == bug_name), None)
            emoji = bug_info['emoji'] if bug_info else "⭐"
            bug_list_text.append(f"{emoji} {bug_name} (x{count})")

        user_data = load_bug_collection().get(str(self.target_user.id), {})
        shinies_caught_count = len(user_data.get('shinies_caught', []))
        total_bugs_in_list = len(INSECT_LIST)

        embed = discord.Embed(
            title=f"Bug Book for {self.target_user.display_name}",
            description=f"You have caught **{self.total_unique_bugs} / {len(INSECT_LIST)}** unique insects!",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        embed.add_field(name="Shiny Bugs Caught", value=f"✨ **{shinies_caught_count}** / {total_bugs_in_list}", inline=False)
        embed.add_field(name=f"Insects Caught (Page {self.current_page}/{self.total_pages})", value="\n".join(bug_list_text) or "No bugs on this page.", inline=False)
        
        return embed

    def update_buttons(self):
        self.children[0].disabled = self.current_page == 1
        self.children[1].disabled = self.current_page == 1
        self.children[2].disabled = self.current_page == self.total_pages
        self.children[3].disabled = self.current_page == self.total_pages

    @discord.ui.button(emoji="⏪", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            return await interaction.response.send_message("This is not your bug book.", ephemeral=True)
        self.current_page = 1
        self.update_buttons()
        embed = await self.get_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            return await interaction.response.send_message("This is not your bug book.", ephemeral=True)
        if self.current_page > 1:
            self.current_page -= 1
        self.update_buttons()
        embed = await self.get_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            return await interaction.response.send_message("This is not your bug book.", ephemeral=True)
        if self.current_page < self.total_pages:
            self.current_page += 1
        self.update_buttons()
        embed = await self.get_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="⏩", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            return await interaction.response.send_message("This is not your bug book.", ephemeral=True)
        self.current_page = self.total_pages
        self.update_buttons()
        embed = await self.get_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)

class TradeConfirmationView(discord.ui.View):
    def __init__(self, bot, proposer: discord.Member, target: discord.Member, proposer_bug: str, target_bug: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.proposer = proposer
        self.target = target
        self.proposer_bug = proposer_bug
        self.target_bug = target_bug
        
    async def disable_buttons(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.target:
            return await interaction.response.send_message("You are not the recipient of this trade and cannot accept it.", ephemeral=True)
        
        await interaction.response.defer()

        bug_collection = load_bug_collection()
        proposer_data = bug_collection.get(str(self.proposer.id), {"caught": []})
        target_data = bug_collection.get(str(self.target.id), {"caught": []})

        if self.proposer_bug not in proposer_data['caught'] or self.target_bug not in target_data['caught']:
            await self.disable_buttons()
            return await interaction.followup.send("The trade could not be completed because one of the bugs is no longer available.", ephemeral=False)

        proposer_data['caught'].remove(self.proposer_bug)
        proposer_data['caught'].append(self.target_bug)

        target_data['caught'].remove(self.target_bug)
        target_data['caught'].append(self.proposer_bug)
        
        bug_collection[str(self.proposer.id)] = proposer_data
        bug_collection[str(self.target.id)] = target_data
        save_bug_collection(bug_collection)

        await self.disable_buttons()
        await interaction.followup.send(f"✅ **{self.target.mention}** has accepted the trade! **{self.proposer_bug}** has been traded for **{self.target_bug}**!", ephemeral=False)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.target:
            return await interaction.response.send_message("You are not the recipient of this trade and cannot decline it.", ephemeral=True)
        
        await self.disable_buttons()
        await interaction.response.send_message(f"❌ **{self.target.mention}** has declined the trade.", ephemeral=False)