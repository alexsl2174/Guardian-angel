import json
import os
import random
import datetime
import asyncio
import aiohttp
import discord
from typing import List, Dict, Any, Union, Optional
import re
import base64
import io
import textwrap
import cogs.utils as utils
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from discord import app_commands

# Set up Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("WARNING: GEMINI_API_KEY environment variable not set. Gemini API calls will fail.")

_gemini_model = None
DEFAULT_TRANSLATION_MODEL_NAME = "gemini-1.5-flash"
GEMINI_IMAGE_MODEL_NAME = "gemini-1.5-flash"
AI_GENERATION_TIMEOUT = 180

# --- File Path Definitions ---
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Directory for local assets
ASSETS_DIR = "assets"
if not os.path.exists(ASSETS_DIR):
    os.makedirs(ASSETS_DIR)

# Local file paths for images
HANGRY_GAMES_BACKGROUND_FILE = os.path.join(ASSETS_DIR, "hangry_games_background.png")
CLASH_OVERLAY_FILE = os.path.join(ASSETS_DIR, "clash_overlay.png")
SKULL_OVERLAY_FILE = os.path.join(ASSETS_DIR, "skull_overlay.png")
WINNING_BG_FILE = os.path.join(ASSETS_DIR, "winning_bg.png")
MEDAL_OVERLAY_FILE = os.path.join(ASSETS_DIR, "winner_overlay.png")

BALANCES_FILE = os.path.join(DATA_DIR, "balances.json")
COOLDOWNS_FILE = os.path.join(DATA_DIR, "cooldowns.json")
COUNTING_GAME_STATE_FILE = os.path.join(DATA_DIR, "counting_game_state.json")
PINS_FILE = os.path.join(DATA_DIR, 'user_pins.json')
COUNTED_USERS_FILE = os.path.join(DATA_DIR, 'counted_users.json')
COUNTING_PREFERENCES_FILE = os.path.join(DATA_DIR, 'counting_preferences.json')
HANGRY_GAMES_STATE_FILE = os.path.join(DATA_DIR, 'hangrygames_state.json')
ITEMS_FILE = os.path.join(DATA_DIR, 'items.json')
INVENTORY_FILE = os.path.join(DATA_DIR, 'inventory.json')
SWEAR_JAR_FILE = os.path.join(DATA_DIR, 'swear_jar.json')
CHAT_REVIVE_CHANNEL_FILE = os.path.join(DATA_DIR, 'chat_revive_channel.json')
TIMED_ROLES_FILE = os.path.join(DATA_DIR, 'timed_roles.json')
LAST_IMAGE_POST_FILE = os.path.join(DATA_DIR, 'last_image_post.json')
LAST_DAILY_POST_DATE_FILE = os.path.join(DATA_DIR, 'last_daily_post_date.json')
ANAGRAM_GAME_STATE_FILE = os.path.join(DATA_DIR, 'anagram_game_state.json')
ANAGRAM_WORDS_FILE = os.path.join(DATA_DIR, 'anagram_words.json')
TREE_FILE = os.path.join(DATA_DIR, 'tree.json')
BUMP_BATTLE_STATE_FILE = os.path.join(DATA_DIR, 'bump_battle_state.json')
VOTE_COOLDOWNS_FILE = os.path.join(DATA_DIR, 'vote_cooldowns.json')
VOTE_POINTS_FILE = os.path.join(DATA_DIR, 'vote_points.json')
ADVENTURE_AI_RESTRICTIONS_FILE = os.path.join(DATA_DIR, 'adventure_ai_restrictions.txt')
ACTIVE_ADVENTURE_GAMES_FILE = os.path.join(DATA_DIR, 'active_adventure_games.json')
DAILY_POSTS_FILE = os.path.join(DATA_DIR, 'daily_posts.json')
BUG_COLLECTION_FILE = os.path.join(DATA_DIR, "bug_collection.json")
PENDING_TRADES_FILE = os.path.join(DATA_DIR, "pending_trades.json")
BOT_CONFIG_FILE = os.path.join(DATA_DIR, "bot_config.json")
SHOP_ITEMS_FILE = os.path.join(DATA_DIR, "shop_items.json")
USER_BALANCES_FILE = os.path.join(DATA_DIR, "balances.json")
USER_INVENTORY_FILE = os.path.join(DATA_DIR, "user_inventory.json")
USER_ROLES_FILE = os.path.join(DATA_DIR, 'user_roles.json')

# --- Configuration Loading ---
FIRST_COUNT_REWARD = 25
FIRST_COUNT_ROLE = "First Timer Counter"

def load_data(file_path: str, default_value: Any = None):
    """Loads data from a JSON file, returning a default value if the file is not found or is corrupted."""
    if not os.path.exists(file_path):
        return default_value if default_value is not None else {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error in {file_path}: {e}. Returning default value.")
        return default_value if default_value is not None else {}
    except Exception as e:
        print(f"Error loading data from {file_path}: {e}. Returning default value.")
        return default_value if default_value is not None else {}

def save_data(data: Any, file_path: str):
    """Saves data to a JSON file."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving data to {file_path}: {e}")

# Load the dynamic bot configuration
bot_config = load_data(BOT_CONFIG_FILE, {})

# --- Role and Channel IDs (Now Loaded from Config) ---
MAIN_GUILD_ID = bot_config.get("MAIN_GUILD_ID", int(os.getenv("MAIN_GUILD_ID")) if os.getenv("MAIN_GUILD_ID") else None)
TEST_CHANNEL_ID = bot_config.get("TEST_CHANNEL_ID", 1403900596020580523)

PLAYER_ROLE_ID = bot_config.get("PLAYER_ROLE_ID", int(os.getenv("PLAYER_ROLE_ID")) if os.getenv("PLAYER_ROLE_ID") else None)
ADVENTURE_MAIN_CHANNEL_ID = bot_config.get("ADVENTURE_MAIN_CHANNEL_ID", TEST_CHANNEL_ID)

CHAT_REVIVE_CHANNEL_ID = bot_config.get("CHAT_REVIVE_CHANNEL_ID", TEST_CHANNEL_ID)
DAILY_COMMENTS_CHANNEL_ID = bot_config.get("DAILY_COMMENTS_CHANNEL_ID", TEST_CHANNEL_ID)
SELF_ROLES_CHANNEL_ID = bot_config.get("SELF_ROLES_CHANNEL_ID", TEST_CHANNEL_ID)
SINNER_CHAT_CHANNEL_ID = bot_config.get("SINNER_CHAT_CHANNEL_ID", TEST_CHANNEL_ID)
BUMDAY_MONDAY_CHANNEL_ID = bot_config.get("BUMDAY_MONDAY_CHANNEL_ID", TEST_CHANNEL_ID)
TITS_OUT_TUESDAY_CHANNEL_ID = bot_config.get("TITS_OUT_TUESDAY_CHANNEL_ID", TEST_CHANNEL_ID)
WET_WEDNESDAY_CHANNEL_ID = bot_config.get("WET_WEDNESDAY_CHANNEL_ID", TEST_CHANNEL_ID)
FURBABY_THURSDAY_CHANNEL_ID = bot_config.get("FURBABY_THURSDAY_CHANNEL_ID", TEST_CHANNEL_ID)
FRISKY_FRIDAY_CHANNEL_ID = bot_config.get("FRISKY_FRIDAY_CHANNEL_ID", TEST_CHANNEL_ID)
SELFIE_SATURDAY_CHANNEL_ID = bot_config.get("SELFIE_SATURDAY_CHANNEL_ID", TEST_CHANNEL_ID)
SLUTTY_SUNDAY_CHANNEL_ID = bot_config.get("SLUTTY_SUNDAY_CHANNEL_ID", TEST_CHANNEL_ID)
ANAGRAM_CHANNEL_ID = bot_config.get("ANAGRAM_CHANNEL_ID", TEST_CHANNEL_ID)
BUMP_BATTLE_CHANNEL_ID = bot_config.get("BUMP_BATTLE_CHANNEL_ID", TEST_CHANNEL_ID)
ANNOUNCEMENTS_CHANNEL_ID = bot_config.get("ANNOUNCEMENTS_CHANNEL_ID", TEST_CHANNEL_ID)
VOTE_CHANNEL_ID = bot_config.get("VOTE_CHANNEL_ID", TEST_CHANNEL_ID)
VOTE_COOLDOWN_HOURS = bot_config.get("VOTE_COOLDOWN_HOURS", 24)
STATUS_CHANNEL_ID = bot_config.get("STATUS_CHANNEL_ID", TEST_CHANNEL_ID)
COUNTING_CHANNEL_ID = bot_config.get("COUNTING_CHANNEL_ID", TEST_CHANNEL_ID)
REVIVE_INTERVAL_HOURS = bot_config.get("REVIVE_INTERVAL_HOURS", 6)

ROLE_IDS = bot_config.get("role_ids", {})
CHAT_REVIVE_ROLE_ID = ROLE_IDS.get("chat_revive_role", None)
ANNOUNCEMENTS_ROLE_ID = ROLE_IDS.get("announcements_role", None)
MOD_ROLE_ID = ROLE_IDS.get("Staff", [])

TIMED_CHANNELS = bot_config.get("timed_channels", {})
DAILY_POSTS_CHANNELS = [channel_id for channel_id, _, _ in TIMED_CHANNELS.values()]

REVIVE_IMAGE_URL = "https://images-ext-1.discordapp.net/external/h4lDt1zEboh_iGS9rgvSgSOMiSw9AmHZI6u9aae8BsU/%3Fwidth%3D662%26height%3D662/https/images-ext-1.discordapp.net/external/8FPhOjICXo6SVfWoVS3CgZUDp-Eut9pbVvVQYnUN6sM/https/cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/c742221693daadcf6ed5b3d6885dc5bda3d46d3bae77d62ebe76715446e92375.gif"
BUMDAY_MONDAY_IMAGE_URL = "https://images-ext-1.discordapp.net/extbumernal/8FPhOjICXo6SVfWoVS3CgZUDp-Eut9pbVvVQYnUN6sM/https/cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/c742221693daadcf6ed5b3d6885dc5bda3d46d3bae77d62ebe76715446e92375.gif"
TITS_OUT_TUESDAY_IMAGE_URL = "https://imagetitss-ext-1.discordapp.net/external/h4lDt1zEboh_iGS9rgvSgSOMiSw9AmHZI6u9aae8BsU/%3Fwidth%3D662%26height%3D662/https/images-ext-1.discordapp.net/external/8FPhOjICXo6SVfWoVS3CgZUDp-Eut9pbVvVQYnUN6sM/https/cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/c742221693daadcf6ed5b3d6885dc5bda3d46d3bae77d62ebe76715446e92375.gif"
WET_WEDNESDAY_IMAGE_URL = "https://images-ext-1.discordapp.net/external/g5V64D8WkF5C8l4P9_k1c6hN_uM7wV3J7-fP-Xb3S2o/https/cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/13a9616335193910c0f9a2e8c56e301297e68d1358d348a1352e6978438b8156.gif"
FURBABY_THURSDAY_IMAGE_URL = "https://images-ext-1.discordapp.net/external/L4N64D3S8P6A9v0L8J8Y4F9_d7eU_gQ3-mP-Xb3S2o/https/cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/c346a06e902b4129b0a688463e26b17a02d41b53c1264c78216c522f778d9482.gif"
FRISKY_FRIDAY_IMAGE_URL = "https://images-ext-1.discordapp.net/external/b1sN1c3gT8o6V9rY7W5O6a9m4x4H3e2Q9k2P1s0p2z3r/https/cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/254a6b245c38d21b7964b58e6979a08e67b2d56a73c1d4786431f13b631d87e0.gif"
SELFIE_SATURDAY_IMAGE_URL = "https://images-ext-1.discordapp.net/external/u1O-Wp9K-Q6a6C9x_qQ7p3S9m2hH6f_q1g-sS6m9p9o/https/cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/a7a7d4511d51c36f5647c9451d6c8b9d9f0a2d596e382b6c934372e1858e388f.gif"
SLUTTY_SUNDAY_IMAGE_URL = "https://images-ext-1.discordapp.net/external/yX0j0H7F8_hO_qG7T_g8t5k3z6gY8b9e6m3-p_q0z9o/https/cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/13a9616335193910c0f9a2e8c56e301297e68d1358d348a1352e6978438b8156.gif"
VERIFY_IMAGE_URL = "https://images-ext-1.discordapp.net/external/iHRkyLReRBCS-6ouS4pyLH3lNu36MadIHn-LI8-AvdM/https/cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/d5a266d70a4c63757d8ba496510819680e5e568daebf66e29ec4b4ff9c05a41c.gif"
CROSS_VERIFIED_IMAGE_URL = "https://images-ext-1.discordapp.net/external/iHRkyLReRBCS-6ouS4pyLH3lNu36MadIHn-LI8-AvdM/https/cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/d5a266d70a4c63757d8ba496510819680e5e568daebf66e29ec4b4ff9c05a41c.gif"
SINNER_CHAT_WELCOME_IMAGE_URL = "https://images-ext-1.discordapp.net/external/iHRkyLReRBCS-6ouS4pyLH3lNu36MadIHn-LI8-AvdM/https/cdn-longterm.mee6.xyz/plugins/embeds/images/824204389421023282/d5a266d70a4c63757d8ba496510819680e5e568daebf66e29ec4b4ff9c05a41c.gif"

# BUMP_BATTLE_GIF_FILE = os.path.join(ASSETS_DIR, "bump_battle.gif")

# --- Autocomplete Functions for Commands ---
async def channel_id_name_autocomplete(interaction: discord.Interaction, current: str):
    """Provides a list of channel ID keys from the bot_config for autocomplete."""
    choices = []
    for key in bot_config:
        if isinstance(bot_config[key], int) and ("channel" in key.lower()):
            
            if key.upper().endswith("_CHANNEL_ID"):
                readable_name = key.upper().replace("_CHANNEL_ID", "").replace("_", " ").title()
            else:
                readable_name = key.upper().replace("_", " ").title()
                
            choices.append(app_commands.Choice(name=readable_name, value=key))
            
    return choices

async def role_id_name_autocomplete(interaction: discord.Interaction, current: str):
    """Provides a list of role ID keys from the bot_config for autocomplete."""
    choices = []
    role_ids_dict = bot_config.get("role_ids", {})
    for key in role_ids_dict:
        if isinstance(role_ids_dict[key], int):
            choices.append(app_commands.Choice(name=key, value=key))
    return choices

# --- Utility Functions for Data Persistence and AI ---
def update_dynamic_config(key, value):
    global bot_config
    bot_config[key] = value
    save_data(bot_config, BOT_CONFIG_FILE)
    reload_globals()

def remove_dynamic_config(key):
    global bot_config
    if key in bot_config:
        del bot_config[key]
        save_data(bot_config, BOT_CONFIG_FILE)
        reload_globals()

def update_dynamic_role(role_name, role_id):
    """Updates a specific role ID in the nested 'role_ids' dictionary."""
    global bot_config
    if "role_ids" not in bot_config:
        bot_config["role_ids"] = {}
    bot_config["role_ids"][role_name] = role_id
    save_data(bot_config, BOT_CONFIG_FILE)
    reload_globals()

def reload_globals():
    global MAIN_GUILD_ID, TEST_CHANNEL_ID, CHAT_REVIVE_CHANNEL_ID, DAILY_COMMENTS_CHANNEL_ID, SELF_ROLES_CHANNEL_ID, SINNER_CHAT_CHANNEL_ID, BUMDAY_MONDAY_CHANNEL_ID, TITS_OUT_TUESDAY_CHANNEL_ID, WET_WEDNESDAY_CHANNEL_ID, FURBABY_THURSDAY_CHANNEL_ID, FRISKY_FRIDAY_CHANNEL_ID, SELFIE_SATURDAY_CHANNEL_ID, SLUTTY_SUNDAY_CHANNEL_ID, ANAGRAM_CHANNEL_ID, BUMP_BATTLE_CHANNEL_ID, ANNOUNCEMENTS_CHANNEL_ID, VOTE_CHANNEL_ID, VOTE_COOLDOWN_HOURS, ROLE_IDS, CHAT_REVIVE_ROLE_ID, ANNOUNCEMENTS_ROLE_ID, MOD_ROLE_ID, TIMED_CHANNELS, DAILY_POSTS_CHANNELS, STATUS_CHANNEL_ID, COUNTING_CHANNEL_ID, PLAYER_ROLE_ID, ADVENTURE_MAIN_CHANNEL_ID, REVIVE_INTERVAL_HOURS
    
    bot_config = load_data(BOT_CONFIG_FILE, {})

    MAIN_GUILD_ID = bot_config.get("MAIN_GUILD_ID", int(os.getenv("MAIN_GUILD_ID")) if os.getenv("MAIN_GUILD_ID") else None)
    TEST_CHANNEL_ID = bot_config.get("TEST_CHANNEL_ID", 1403900596020580523)
    CHAT_REVIVE_CHANNEL_ID = bot_config.get("CHAT_REVIVE_CHANNEL_ID", TEST_CHANNEL_ID)
    DAILY_COMMENTS_CHANNEL_ID = bot_config.get("DAILY_COMMENTS_CHANNEL_ID", TEST_CHANNEL_ID)
    SELF_ROLES_CHANNEL_ID = bot_config.get("SELF_ROLES_CHANNEL_ID", TEST_CHANNEL_ID)
    SINNER_CHAT_CHANNEL_ID = bot_config.get("SINNER_CHAT_CHANNEL_ID", TEST_CHANNEL_ID)
    BUMDAY_MONDAY_CHANNEL_ID = bot_config.get("BUMDAY_MONDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    TITS_OUT_TUESDAY_CHANNEL_ID = bot_config.get("TITS_OUT_TUESDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    WET_WEDNESDAY_CHANNEL_ID = bot_config.get("WET_WEDNESDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    FURBABY_THURSDAY_CHANNEL_ID = bot_config.get("FURBABY_THURSDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    FRISKY_FRIDAY_CHANNEL_ID = bot_config.get("FRISKY_FRIDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    SELFIE_SATURDAY_CHANNEL_ID = bot_config.get("SELFIE_SATURDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    SLUTTY_SUNDAY_CHANNEL_ID = bot_config.get("SLUTTY_SUNDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    ANAGRAM_CHANNEL_ID = bot_config.get("ANAGRAM_CHANNEL_ID", TEST_CHANNEL_ID)
    BUMP_BATTLE_CHANNEL_ID = bot_config.get("BUMP_BATTLE_CHANNEL_ID", TEST_CHANNEL_ID)
    ANNOUNCEMENTS_CHANNEL_ID = bot_config.get("ANNOUNCEMENTS_CHANNEL_ID", TEST_CHANNEL_ID)
    VOTE_CHANNEL_ID = bot_config.get("VOTE_CHANNEL_ID", TEST_CHANNEL_ID)
    VOTE_COOLDOWN_HOURS = bot_config.get("VOTE_COOLDOWN_HOURS", 24)
    STATUS_CHANNEL_ID = bot_config.get("STATUS_CHANNEL_ID", TEST_CHANNEL_ID)
    COUNTING_CHANNEL_ID = bot_config.get("COUNTING_CHANNEL_ID", TEST_CHANNEL_ID)
    REVIVE_INTERVAL_HOURS = bot_config.get("REVIVE_INTERVAL_HOURS", 6)
    
    ROLE_IDS = bot_config.get("role_ids", {})
    CHAT_REVIVE_ROLE_ID = ROLE_IDS.get("chat_revive_role", None)
    ANNOUNCEMENTS_ROLE_ID = ROLE_IDS.get("announcements_role", None)
    MOD_ROLE_ID = ROLE_IDS.get("Staff", None)

    PLAYER_ROLE_ID = bot_config.get("PLAYER_ROLE_ID", int(os.getenv("PLAYER_ROLE_ID")) if os.getenv("PLAYER_ROLE_ID") else None)
    ADVENTURE_MAIN_CHANNEL_ID = bot_config.get("ADVENTURE_MAIN_CHANNEL_ID", TEST_CHANNEL_ID)

    TIMED_CHANNELS = bot_config.get("timed_channels", {})
    DAILY_POSTS_CHANNELS = [channel_id for channel_id, _, _ in TIMED_CHANNELS.values()]

def load_timed_channels():
    return TIMED_CHANNELS

def load_daily_posts_channels():
    return DAILY_POSTS_CHANNELS

def get_user_money(user_id: int) -> int:
    balances = load_data(BALANCES_FILE, {})
    return balances.get(str(user_id), 0)

def update_user_money(user_id: int, amount: int):
    balances = load_data(BALANCES_FILE, {})
    user_id_str = str(user_id)
    balances[user_id_str] = balances.get(user_id_str, 0) + amount
    save_data(balances, BALANCES_FILE)

def load_chat_revive_channel() -> Optional[int]:
    return CHAT_REVIVE_CHANNEL_ID

def save_chat_revive_channel(channel_id: int):
    update_dynamic_config("CHAT_REVIVE_CHANNEL_ID", channel_id)

def save_timed_role_data(guild_id: int, role_id: int, expiration_date: datetime.datetime):
    data = load_data(TIMED_ROLES_FILE, {})
    guild_id_str = str(guild_id)
    if guild_id_str not in data:
        data[guild_id_str] = {}
    data[guild_id_str][str(role_id)] = expiration_date.isoformat()
    save_data(data, TIMED_ROLES_FILE)

def load_last_image_post_date(user_id: int) -> Optional[datetime.datetime]:
    data = load_data(LAST_IMAGE_POST_FILE, {})
    post_date_str = data.get(str(user_id))
    if post_date_str:
        return datetime.datetime.fromisoformat(post_date_str)
    return None

def save_last_image_post_date(user_id: int, post_date: datetime.datetime):
    data = load_data(LAST_IMAGE_POST_FILE, {})
    data[str(user_id)] = post_date.isoformat()
    save_data(data, LAST_IMAGE_POST_FILE)

def load_last_daily_post_date():
    return load_data(LAST_DAILY_POST_DATE_FILE, {})

def save_last_daily_post_date(post_date: datetime.datetime, weekday_name: str):
    data = {'last_post_date': post_date.isoformat(), 'last_weekday': weekday_name}
    save_data(data, LAST_DAILY_POST_DATE_FILE)

def rebuild_daily_posts():
    reload_globals()

def load_counting_game_state():
    return load_data(COUNTING_GAME_STATE_FILE, {
        "counting_channel_id": COUNTING_CHANNEL_ID,
        "current_count": 0,
        "last_counter_id": None,
        "guess_game_active": False,
        "guess_game_number": 0,
        "guess_attempts": 0,
        "lucky_number": 0,
        "lucky_number_active": False
    })

def save_counting_game_state(state: Dict[str, Any]):
    save_data(state, COUNTING_GAME_STATE_FILE)

def check_if_user_counted(user_id: int) -> bool:
    counted_users = load_data(COUNTED_USERS_FILE, [])
    return str(user_id) in counted_users

def set_user_counted(user_id: int):
    counted_users = load_data(COUNTED_USERS_FILE, [])
    user_id_str = str(user_id)
    if user_id_str not in counted_users:
        counted_users.append(user_id_str)
        save_data(counted_users, COUNTED_USERS_FILE)
    
def load_user_pins(user_id: int) -> list[str]:
    all_pins = load_data(PINS_FILE, {})
    return all_pins.get(str(user_id), [])

def save_user_pins(user_id: int, pins: list[str]):
    all_pins = load_data(PINS_FILE, {})
    all_pins[str(user_id)] = pins
    save_data(all_pins, PINS_FILE)
    
def load_counting_preferences():
    return load_data(COUNTING_PREFERENCES_FILE, {
        "consecutive_counting": False,
        "delete_incorrect": False,
        "role_on_miscount": True,
        "sudden_death": True,
        "mode": "incremental"
    })

def save_counting_preferences(preferences: Dict[str, Any]):
    save_data(preferences, COUNTING_PREFERENCES_FILE)
    
def load_make_a_sentence_state():
    return load_data(BOT_CONFIG_FILE, {
        "make_a_sentence_channel_id": bot_config.get("MAKE_A_SENTENCE_CHANNEL_ID", TEST_CHANNEL_ID),
        "finished_sentences_channel_id": bot_config.get("FINISHED_SENTENCES_CHANNEL_ID", TEST_CHANNEL_ID),
        "current_sentence": []
    })

def save_make_a_sentence_state(state: Dict[str, Any]):
    save_data(state, BOT_CONFIG_FILE)

def load_hangrygames_state():
    return load_data(HANGRY_GAMES_STATE_FILE, {})

def save_hangrygames_state(state: Dict[str, Any]):
    save_data(state, HANGRY_GAMES_STATE_FILE)

async def generate_hangry_event(tributes: List[discord.Member], event_type: str) -> Optional[Dict[str, Any]]:
    if not GEMINI_API_KEY:
        print("Gemini API key is not set. Skipping AI generation.")
        return None
    
    model = genai.GenerativeModel(DEFAULT_TRANSLATION_MODEL_NAME)
    
    if event_type == "duel" and len(tributes) == 2:
        prompt = (
            f"Generate a very short, high-energy Hangry Games duel event in JSON format. "
            f"Tributes: {tributes[0].display_name} vs. {tributes[1].display_name}. "
            "Focus on a unique, action-packed food-themed attack. "
            "JSON keys: `title`, `description` (one sentence with placeholders), `winner`, `loser`."
        )
    elif event_type == "solo_death" and len(tributes) == 1:
        prompt = (
            f"Generate a very short, humorous, and ironic Hangry Games solo death event in JSON format. "
            f"Tribute: {tributes[0].display_name}. "
            "The death must be a clumsy food-related accident. "
            f"**Crucially, the 'tribute' key must contain the exact name: '{tributes[0].display_name}'**. "
            "JSON keys: `title`, `description` (one sentence with a placeholder), `tribute`."
        )
    else:
        return None
    
    try:
        response = await asyncio.wait_for(
            model.generate_content_async(prompt),
            timeout=AI_GENERATION_TIMEOUT
        )
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[len("```json"):].strip()
        if response_text.endswith("```"):
            response_text = response_text[:-len("```")].strip()
        return json.loads(response_text)
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
        print(f"Error generating hangry event: {e}")
        return None

def load_items() -> List[Dict[str, Any]]:
    return load_data(SHOP_ITEMS_FILE, [])

def save_items(items: List[Dict[str, Any]]):
    save_data(items, SHOP_ITEMS_FILE)

def get_item_data(item_name: str) -> Optional[Dict[str, Any]]:    
    items = load_items()
    return next((item for item in items if item['name'].lower() == item_name.lower()), None)

def load_user_inventory(user_id: int) -> Dict[str, Any]:
    inventory_data = load_data(USER_INVENTORY_FILE, {})
    return inventory_data.get(str(user_id), {})

def save_user_inventory(user_id: int, user_inventory: Dict[str, Any]):
    inventory_data = load_data(USER_INVENTORY_FILE, {})
    inventory_data[str(user_id)] = user_inventory
    save_data(inventory_data, USER_INVENTORY_FILE)

def add_item_to_inventory(user_id: int, item_name: str, item_data: Dict[str, Any]):
    user_inventory_data = load_data(USER_INVENTORY_FILE, {})
    user_data = user_inventory_data.get(str(user_id), {"items": {}, "nets": None, "net_durability": 0, "xp": 0})
    
    if item_data.get("type") == 'net':
        user_data['nets'] = {"name": item_data['name'], "durability": item_data['durability']}
    else:
        item_name_lower = item_name.lower()
        user_data['items'][item_name_lower] = user_data['items'].get(item_name_lower, 0) + 1

    user_inventory_data[str(user_id)] = user_data
    save_data(user_inventory_data, USER_INVENTORY_FILE)

def remove_item_from_inventory(user_id: int, item_name: str):
    inventory_data = load_data(USER_INVENTORY_FILE, {})
    user_id_str = str(user_id)
    user_data = inventory_data.get(user_id_str, {"items": {}})
    
    item_name_lower = item_name.lower()
    if user_data['items'].get(item_name_lower, 0) > 1:
        user_data['items'][item_name_lower] -= 1
    elif item_name_lower in user_data['items']:
        del user_data['items'][item_name_lower]
        
    inventory_data[user_id_str] = user_data
    save_data(inventory_data, USER_INVENTORY_FILE)
    
async def handle_buy_item(interaction: discord.Interaction, item_to_buy: Dict[str, Any], free_purchase: bool):

    user_id = interaction.user.id

    user_id_str = str(user_id)



    inventory_data = load_data(USER_INVENTORY_FILE, {})

    user_data = inventory_data.get(user_id_str, {"items": {}, "nets": [], "net_durability": 0, "xp": 0, "equipped_net": None})



    required_item = item_to_buy.get("requirement")

    if required_item:

        if required_item.lower() not in user_data.get("items", {}):

            return await interaction.followup.send(f"You must have `{required_item}` in your inventory to purchase this item.", ephemeral=True)

    

    item_price = item_to_buy['price']



    if not free_purchase:

        user_balance = get_user_money(user_id)

        if user_balance < item_price:

            return await interaction.followup.send(f"You don't have enough money to buy `{item_to_buy['name']}`. You need <a:starcoin:1280590254935380038> {item_price - user_balance} more.", ephemeral=True)



        update_user_money(user_id, -item_price)

    

    if item_to_buy.get("type") == 'net':

        if 'nets' not in user_data:

            user_data['nets'] = []



        # Fix: Ensure durability is pulled from the item data.

        new_net = {"name": item_to_buy['name'], "durability": item_to_buy['durability']}

        user_data['nets'].append(new_net)



        if not user_data.get('equipped_net'):

            user_data['equipped_net'] = item_to_buy['name']

            message_text = f"✅ You have successfully purchased and equipped the **{item_to_buy['name']}** for <a:starcoin:1280590254935380038> {item_price}!"

        else:

            message_text = f"✅ You have successfully purchased the **{item_to_buy['name']}** for <a:starcoin:1280590254935380038> {item_price}! It has been added to your inventory."



    else:

        item_name = item_to_buy['name']

        item_name_lower = item_name.lower()

        if 'items' not in user_data:

            user_data['items'] = {}

        user_data['items'][item_name_lower] = user_data['items'].get(item_name_lower, 0) + 1



        if item_to_buy.get("type") == "cosmetic":

            role = discord.utils.get(interaction.guild.roles, name=item_to_buy.get("role_to_give"))

            if role:

                member = interaction.guild.get_member(user_id)

                if member:

                    await member.add_roles(role)

        

        message_text = f"✅ You have successfully purchased the **{item_to_buy['name']}** for <a:starcoin:1280590254935380038> {item_price}!"



    if free_purchase:

        message_text = f"✅ (TEST) You have successfully purchased the **{item_to_buy['name']}** for free!"



    inventory_data[user_id_str] = user_data

    save_data(inventory_data, USER_INVENTORY_FILE)

    

    await interaction.followup.send(message_text, ephemeral=True)


def load_swear_jar_data():
    return load_data(SWEAR_JAR_FILE, {'words': [], 'tally': {}})

def get_item_emoji(item_name: str, emoji_str: str) -> str:
    """Helper function to get the correct emoji string."""
    if emoji_str:
        if emoji_str.startswith('<') and emoji_str.endswith('>'):
            return emoji_str
        # If it's a raw name like ':GoldenHalo:', return it as is.
        # This allows Discord's client to render it.
        return emoji_str
    return "🛒"

def save_swear_jar_data(data: Dict[str, Any]):
    save_data(data, SWEAR_JAR_FILE)
    
def save_timed_role_data(guild_id: int, role_id: int, expiration_date: datetime.datetime):
    data = load_data(TIMED_ROLES_FILE, {})
    guild_id_str = str(guild_id)
    if guild_id_str not in data:
        data[guild_id_str] = {}
    data[guild_id_str][str(role_id)] = expiration_date.isoformat()
    save_data(data, TIMED_ROLES_FILE)

def load_timed_roles() -> Dict[str, Dict[str, str]]:
    return load_data(TIMED_ROLES_FILE, {})

def load_anagram_game_state():
    return load_data(ANAGRAM_GAME_STATE_FILE, {"channel_id": ANAGRAM_CHANNEL_ID, "current_word": None, "shuffled_word": None})

def save_anagram_game_state(state: Dict[str, Any]):
    save_data(state, ANAGRAM_GAME_STATE_FILE)

def load_anagram_words():
    if not os.path.exists(ANAGRAM_WORDS_FILE):
        ANAGRAM_WORD_LIST = ["discord", "python", "google", "gemini", "bot", "code", "cog", "server", "channel", "message", "emoji", "command", "task", "event", "user", "role"]
        save_data({"words": ANAGRAM_WORD_LIST}, ANAGRAM_WORDS_FILE)
    return load_data(ANAGRAM_WORDS_FILE, {}).get("words", [])

def load_tree_game_data():
    return load_data(TREE_FILE, {"trees": {}, "user_cooldowns": {}})

def save_tree_game_data(data: Dict[str, Any]):
    save_data(data, TREE_FILE)

def load_tree_of_life_state(guild_id: int):
    game_data = load_tree_game_data()
    return game_data.get("trees", {}).get(str(guild_id), {
        "height": 0,
        "last_watered_by": None,
        "last_watered_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "rank": 0
    })

def save_tree_of_life_state(guild_id: int, state: Dict[str, Any]):
    game_data = load_tree_game_data()
    game_data["trees"][str(guild_id)] = state
    save_tree_game_data(game_data)

def load_user_cooldowns():
    game_data = load_tree_game_data()
    return game_data.get("user_cooldowns", {})

def save_user_cooldowns(cooldowns: Dict[str, str]):
    game_data = load_tree_game_data()
    game_data["user_cooldowns"] = cooldowns
    save_tree_game_data(game_data)


def load_bump_battle_state():
    return load_data(BUMP_BATTLE_STATE_FILE, {
        'sub': {'points': 0, 'users': {}},
        'dom': {'points': 0, 'users': {}}
    })

def save_bump_battle_state(state: Dict[str, Any]):
    save_data(state, BUMP_BATTLE_STATE_FILE)

def load_vote_cooldowns():
    return load_data(VOTE_COOLDOWNS_FILE, {})

def save_vote_cooldowns(data: Dict[str, str]):
    save_data(data, VOTE_COOLDOWNS_FILE)

def load_vote_points():
    return load_data(VOTE_POINTS_FILE, {'subs': {}, 'doms': {}})

def save_vote_points(data: Dict[str, Any]):
    save_data(data, VOTE_POINTS_FILE)
    
def get_ai_restrictions() -> str:
    if os.path.exists(ADVENTURE_AI_RESTRICTIONS_FILE):
        with open(ADVENTURE_AI_RESTRICTIONS_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        default_restrictions = textwrap.dedent("""
            You are a text adventure game master.
            You will create a story based on the user's input.
            The story should be dark, fantasy, and mysterious.
            Do not break character.
            Keep your responses concise and focused on the current scene.
        """).strip()
        with open(ADVENTURE_AI_RESTRICTIONS_FILE, 'w', encoding='utf-8') as f:
            f.write(default_restrictions)
        return default_restrictions

def load_active_adventure_games_from_file() -> Dict[str, Any]:
    return load_data(ACTIVE_ADVENTURE_GAMES_FILE, {})

def save_active_adventure_games_to_file(state: Dict[str, Any]):
    save_data(state, ACTIVE_ADVENTURE_GAMES_FILE)

async def generate_text_with_gemini_with_history(chat_history: List[Dict[str, Any]], model_name: str = DEFAULT_TRANSLATION_MODEL_NAME) -> Optional[str]:
    if not GEMINI_API_KEY:
        print("Gemini API key is not set. Skipping AI generation.")
        return None
    try:
        model = genai.GenerativeModel(model_name)
        chat = model.start_chat(history=chat_history[:-1])
        response = await asyncio.wait_for(chat.send_message_async(chat_history[-1]['parts'][0]['text']), timeout=AI_GENERATION_TIMEOUT)
        return response.text
    except Exception as e:
        print(f"Error during Gemini text generation: {e}")
        return None

async def add_role_to_member(member: discord.Member, role_name: str):
    role = discord.utils.get(member.guild.roles, name=role_name)
    if not role:
        try:
            role = await member.guild.create_role(name=role_name, reason=f"Role for first count in the counting game.")
            print(f"Created new role: {role_name}")
        except discord.Forbidden:
            print(f"Failed to create role '{role_name}'. Bot lacks permissions.")
            return
    if role and member.guild.me.top_role > role:
        try:
            await member.add_roles(role, reason=f"Gave '{role_name}' role.")
        except discord.Forbidden:
            print(f"Failed to add role '{role_name}' to {member}. Bot lacks permissions or role hierarchy is wrong.")

def load_bug_collection():
    return load_data(BUG_COLLECTION_FILE, {})

def save_bug_collection(data):
    save_data(data, BUG_COLLECTION_FILE)

def load_pending_trades():
    return load_data(PENDING_TRADES_FILE, {})

def save_pending_trades(data):
    save_data(data, PENDING_TRADES_FILE)
    
async def generate_image_from_text(prompt: str) -> Optional[str]:
    if not GEMINI_API_KEY:
        print("Gemini API key is not set. Skipping image generation.")
        return None
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        image_generation_prompt = f"Create a detailed, high-quality image that visually represents the following scene: {prompt}. Focus on fantasy and mysterious elements. Do not include any text in the image."
        print(f"Simulating image generation for prompt: '{prompt}'")
        return "https://via.placeholder.com/1024x1024.png?text=Generated+Image+Placeholder"
    except Exception as e:
        print(f"Error during Gemini image generation: {e}")
        return None
    
async def generate_anagram_word_with_gemini() -> Optional[str]:
    """Generates a new word for the anagram game using the Gemini AI."""
    if not GEMINI_API_KEY:
        print("Gemini API key is not set. Skipping AI generation for anagram.")
        return None
    try:
        model = genai.GenerativeModel(DEFAULT_TRANSLATION_MODEL_NAME)
        prompt = "Generate a single, common, English word between 5 and 10 letters long. Do not include any punctuation or extra text."
        response = await asyncio.wait_for(
            model.generate_content_async(prompt),
            timeout=AI_GENERATION_TIMEOUT
        )
        word = response.text.strip().lower()
        if re.match(r'^[a-z]{5,10}$', word):
            return word
        else:
            return None
    except Exception as e:
        print(f"Error during Gemini word generation: {e}")
        return None

async def generate_work_phrase_with_gemini(is_success: bool) -> Optional[str]:
    """Generates a new phrase for the work command using the Gemini AI."""
    if not GEMINI_API_KEY:
        print("Gemini API key is not set. Skipping AI generation.")
        return None
    try:
        model = genai.GenerativeModel(DEFAULT_TRANSLATION_MODEL_NAME)
        if is_success:
            prompt = "Generate a single, short, and funny phrase describing a successful, mundane work task. Start the phrase with a verb. Do not include any extra text or punctuation."
        else:
            prompt = "Generate a single, short, and funny phrase describing a clumsy, negative work outcome. Start the phrase with a verb. Do not include any extra text or punctuation."
        
        response = await asyncio.wait_for(
            model.generate_content_async(prompt),
            timeout=AI_GENERATION_TIMEOUT
        )
        return response.text.strip()
    except Exception as e:
        print(f"Error during Gemini phrase generation: {e}")
        return None

async def generate_crime_phrase_with_gemini(is_success: bool) -> Optional[str]:
    """Generates a new phrase for the crime command using the Gemini AI."""
    if not GEMINI_API_KEY:
        print("Gemini API key is not set. Skipping AI generation.")
        return None
    try:
        model = genai.GenerativeModel(DEFAULT_TRANSLATION_MODEL_NAME)
        if is_success:
            prompt = "Generate a single, short, and creative phrase describing a successful crime. Start the phrase with a verb. Do not include any extra text or punctuation."
        else:
            prompt = "Generate a single, short, and funny phrase describing a failed crime attempt. Start the phrase with a verb. Do not include any extra text or punctuation."
        
        response = await asyncio.wait_for(
            model.generate_content_async(prompt),
            timeout=AI_GENERATION_TIMEOUT
        )
        return response.text.strip()
    except Exception as e:
        print(f"Error during Gemini phrase generation: {e}")
        return None

def get_item_emoji(item_name: str, emoji_str: str) -> str:
    """Helper function to get the correct emoji string."""
    if emoji_str and not emoji_str.startswith('<'):
        return emoji_str
    return emoji_str or "🛒"

async def handle_buy_item(interaction: discord.Interaction, item_to_buy: Dict[str, Any], free_purchase: bool):
    user_id = interaction.user.id
    user_id_str = str(user_id)

    # Load the entire inventory data first
    inventory_data = utils.load_data(USER_INVENTORY_FILE, {})
    
    # Get the user's data, or create a new entry if they don't exist
    if user_id_str not in inventory_data:
        inventory_data[user_id_str] = {"items": {}, "nets": [], "net_durability": 0, "xp": 0, "equipped_net": None}
    
    user_data = inventory_data[user_id_str]

    required_item = item_to_buy.get("requirement")
    if required_item:
        if required_item.lower() not in user_data.get("items", {}):
            return await interaction.followup.send(f"You must have `{required_item}` in your inventory to purchase this item.", ephemeral=True)
    
    item_price = item_to_buy.get('price', 0)

    if not free_purchase:
        user_balance = utils.get_user_money(user_id)
        if user_balance < item_price:
            return await interaction.followup.send(f"You don't have enough money to buy `{item_to_buy['name']}`. You need <a:starcoin:1280590254935380038> {item_price - user_balance} more.", ephemeral=True)
        utils.update_user_money(user_id, -item_price)
    
    if item_to_buy.get("type") == 'net':
        if 'nets' not in user_data:
            user_data['nets'] = []
        
        new_net = {"name": item_to_buy['name'], "durability": item_to_buy.get('durability', 0)}
        user_data['nets'].append(new_net)

        if not user_data.get('equipped_net'):
            user_data['equipped_net'] = item_to_buy['name']
            message_text = f"✅ You have successfully purchased and equipped the **{item_to_buy['name']}** for <a:starcoin:1280590254935380038> {item_price}!"
        else:
            message_text = f"✅ You have successfully purchased the **{item_to_buy['name']}** for <a:starcoin:1280590254935380038> {item_price}! It has been added to your inventory."
    else:
        item_name = item_to_buy['name']
        item_name_lower = item_name.lower()
        if 'items' not in user_data:
            user_data['items'] = {}
        user_data['items'][item_name_lower] = user_data['items'].get(item_name_lower, 0) + 1

        if item_to_buy.get("type") == "cosmetic":
            role = discord.utils.get(interaction.guild.roles, name=item_to_buy.get("role_to_give"))
            if role:
                member = interaction.guild.get_member(user_id)
                if member:
                    await member.add_roles(role)
        
        message_text = f"✅ You have successfully purchased the **{item_to_buy['name']}** for <a:starcoin:1280590254935380038> {item_price}!"

    if free_purchase:
        message_text = f"✅ (TEST) You have successfully purchased the **{item_to_buy['name']}** for free!"

    # Save the entire dictionary, which now contains the updated user data
    utils.save_data(inventory_data, USER_INVENTORY_FILE)
    
    await interaction.followup.send(message_text, ephemeral=True)

async def generate_duel_image(winner_avatar_url: str, loser_avatar_url: str) -> discord.File:
    """Generates a duel image by combining two user avatars with a duel overlay."""
    try:
        bg_img = Image.open(HANGRY_GAMES_BACKGROUND_FILE).convert("RGBA").resize((1000, 500))
        clash_overlay = Image.open(CLASH_OVERLAY_FILE).convert("RGBA").resize((200, 200))
        
        async with aiohttp.ClientSession() as session:
            async def get_image(url: str, session: aiohttp.ClientSession):
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    return await resp.read()

            winner_avatar_data = await get_image(winner_avatar_url, session)
            loser_avatar_data = await get_image(loser_avatar_url, session)

        winner_avatar = Image.open(io.BytesIO(winner_avatar_data)).convert("RGBA").resize((256, 256))
        loser_avatar = Image.open(io.BytesIO(loser_avatar_data)).convert("RGBA").resize((256, 256))
        
        loser_avatar = ImageOps.grayscale(loser_avatar)
        loser_avatar = loser_avatar.convert("RGBA")

        final_image = Image.new("RGBA", (1000, 500))
        final_image.paste(bg_img, (0, 0))

        winner_avatar_rotated = winner_avatar.rotate(5, expand=True)
        loser_avatar_rotated = loser_avatar.rotate(-5, expand=True)

        final_image.paste(winner_avatar_rotated, (175, 122), winner_avatar_rotated)
        final_image.paste(loser_avatar_rotated, (575, 122), loser_avatar_rotated)
        
        final_image.paste(clash_overlay, (400, 150), clash_overlay)
        
        img_buffer = io.BytesIO()
        final_image.save(img_buffer, format="PNG")
        img_buffer.seek(0)
        
        return discord.File(img_buffer, filename="duel_event.png")

    except FileNotFoundError as e:
        print(f"Error: A required local image file was not found: {e}. Please ensure the images are in the '{ASSETS_DIR}' directory.")
        return discord.File(io.BytesIO(b""), filename="error.png")
    except aiohttp.ClientResponseError as e:
        print(f"Error downloading avatar image: {e.status} for URL {e.request_info.url}. Returning a default image.")
        return discord.File(io.BytesIO(b""), filename="error.png")
    except Exception as e:
        print(f"Error generating duel image: {e}")
        return discord.File(io.BytesIO(b""), filename="error.png")

async def generate_solo_death_image(avatar_url: str) -> discord.File:
    """Generates a solo death image with a grayscale avatar and a death overlay."""
    try:
        bg_img = Image.open(HANGRY_GAMES_BACKGROUND_FILE).convert("RGBA").resize((1000, 500))
        skull_overlay = Image.open(SKULL_OVERLAY_FILE).convert("RGBA").resize((200, 200))
        
        async with aiohttp.ClientSession() as session:
            async def get_image(url: str, session: aiohttp.ClientSession):
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    return await resp.read()

            avatar_data = await get_image(avatar_url, session)

        avatar_img = Image.open(io.BytesIO(avatar_data)).convert("RGBA").resize((256, 256))
        
        avatar_img = ImageOps.grayscale(avatar_img)
        avatar_img = avatar_img.convert("RGBA")

        red_tint = Image.new("RGBA", avatar_img.size, (255, 0, 0, 100))
        avatar_img = Image.alpha_composite(avatar_img, red_tint)
        
        final_image = Image.new("RGBA", (1000, 500))
        final_image.paste(bg_img, (0,0))
        
        vignette_overlay = Image.new('RGBA', final_image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(vignette_overlay)
        center_x, center_y = final_image.width // 2, final_image.height // 2
        
        for i in range(100):
            alpha = int(255 * (i / 100))
            draw.ellipse((center_x - i*5, center_y - i*2.5, center_x + i*5, center_y + i*2.5), fill=(0, 0, 0, alpha))
        vignette_overlay = vignette_overlay.filter(ImageFilter.GaussianBlur(radius=50))
        final_image = Image.alpha_composite(final_image, vignette_overlay)

        final_image.paste(avatar_img, (int((1000 - 256)/2), int((500 - 256)/2)), avatar_img)
        final_image.paste(skull_overlay, (int((1000 - 200)/2), int((500 - 200)/2)), skull_overlay)
        
        draw = ImageDraw.Draw(final_image)
        try:
            font = ImageFont.truetype("arialbd.ttf", 60)
        except IOError:
            font = ImageFont.load_default()
        
        game_over_text = "GAME OVER"
        text_bbox = draw.textbbox( (0,0), game_over_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        draw.text((final_image.width/2 - text_width/2, final_image.height - 100), game_over_text, font=font, fill=(255, 0, 0, 255))

        img_buffer = io.BytesIO()
        final_image.save(img_buffer, format="PNG")
        img_buffer.seek(0)
        
        return discord.File(img_buffer, filename="solo_death_event.png")
    
    except FileNotFoundError as e:
        print(f"Error: A required local image file was not found: {e}. Please ensure the images are in the '{ASSETS_DIR}' directory.")
        return discord.File(io.BytesIO(b""), filename="error.png")
    except aiohttp.ClientResponseError as e:
        print(f"Error downloading avatar image: {e.status} for URL {e.request_info.url}. Returning a default image.")
        return discord.File(io.BytesIO(b""), filename="error.png")
    except Exception as e:
        print(f"Error generating solo death image: {e}")
        return discord.File(io.BytesIO(b""), filename="error.png")

async def generate_win_image(winner_avatar_url: str) -> discord.File:
    """Generates a custom winner image by compositing the avatar and medal onto the winning background."""
    try:
        bg_img = Image.open(WINNING_BG_FILE).convert("RGBA").resize((1000, 500))
        medal_overlay = Image.open(MEDAL_OVERLAY_FILE).convert("RGBA")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(winner_avatar_url) as resp:
                resp.raise_for_status()
                avatar_data = await resp.read()
        avatar_img = Image.open(io.BytesIO(avatar_data)).convert("RGBA")
        
        avatar_img = avatar_img.resize((350, 350))
        medal_overlay = medal_overlay.resize((400, 400))
        
        final_image = bg_img.copy()

        avatar_x = (bg_img.width - avatar_img.width) // 2
        avatar_y = (bg_img.height - avatar_img.height) // 2 - 50
        final_image.paste(avatar_img, (avatar_x, avatar_y), avatar_img)
        
        medal_x = (bg_img.width - medal_overlay.width) // 2
        medal_y = avatar_y + avatar_img.height - 100
        final_image.paste(medal_overlay, (medal_x, medal_y), medal_overlay)
        
        img_buffer = io.BytesIO()
        final_image.save(img_buffer, format="PNG")
        img_buffer.seek(0)
        
        return discord.File(img_buffer, filename="winner_card.png")

    except FileNotFoundError as e:
        print(f"Error: A required local image file was not found: {e}. Please ensure the images are in the '{ASSETS_DIR}' directory.")
        return discord.File(io.BytesIO(b""), filename="error.png")
    except aiohttp.ClientResponseError as e:
        print(f"Error downloading avatar image: {e.status} for URL {e.request_info.url}. Returning a default image.")
        return discord.File(io.BytesIO(b""), filename="error.png")
    except Exception as e:
        print(f"Error generating win image: {e}")
        return discord.File(io.BytesIO(b""), filename="error.png")
