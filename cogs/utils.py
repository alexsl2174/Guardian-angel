# cogs/utils.py

import json
import os
import random
import datetime
import google.generativeai as genai
import asyncio
import aiohttp
import discord
from typing import List, Dict, Any, Union, Optional
import re
import base64
import io
import textwrap
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
CONFIG_FILE = 'timed_roles.json'
HANGRY_GAMES_BACKGROUND_FILE = os.path.join(ASSETS_DIR, "hangry_games_background.png")
CLASH_OVERLAY_FILE = os.path.join(ASSETS_DIR, "clash_overlay.png")
SKULL_OVERLAY_FILE = os.path.join(ASSETS_DIR, "skull_overlay.png")
WINNING_BG_FILE = os.path.join(ASSETS_DIR, "winning_bg.png")
MEDAL_OVERLAY_FILE = os.path.join(ASSETS_DIR, "winner_overlay.png")
SORRY_JAR_FILE = 'data/sorry_jar.json'

# Other file paths for various bot features
ADVENTURE_AI_RESTRICTIONS_FILE = os.path.join(DATA_DIR, 'adventure_ai_restrictions.txt')
DAILY_MESSAGE_COOLDOWNS_FILE = os.path.join(DATA_DIR, "daily_message_cooldowns.json")
BOOSTER_REWARDS_FILE = os.path.join(DATA_DIR, "booster_rewards.json")
ACTIVE_ADVENTURE_GAMES_FILE = os.path.join(DATA_DIR, 'active_adventure_games.json')
USER_ROLES_FILE = os.path.join(DATA_DIR, 'user_roles.json')
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
DAILY_POSTS_FILE = os.path.join(DATA_DIR, 'daily_posts.json')
BUG_COLLECTION_FILE = os.path.join(DATA_DIR, "bug_collection.json")
PENDING_TRADES_FILE = os.path.join(DATA_DIR, "pending_trades.json")
BOT_CONFIG_FILE = os.path.join(DATA_DIR, "bot_config.json")
REWARDS_FILE = os.path.join(DATA_DIR, 'rewards.json')
SHOP_ITEMS_FILE = os.path.join(DATA_DIR, "shop_items.json")
USER_BALANCES_FILE = os.path.join(DATA_DIR, "balances.json")
USER_INVENTORY_FILE = os.path.join(DATA_DIR, "user_inventory.json")


# --- Configuration Loading ---
FIRST_COUNT_REWARD = 25
FIRST_COUNT_ROLE = "First Timer Counter"

def load_daily_posts_channels():
     return DAILY_POSTS_CHANNELS

def load_daily_message_cooldowns() -> Dict[str, str]:
    return load_data(DAILY_MESSAGE_COOLDOWNS_FILE, {})

def save_daily_message_cooldowns(data: Dict[str, str]):
    save_data(data, DAILY_MESSAGE_COOLDOWNS_FILE)

def load_booster_rewards() -> Dict[str, str]:
    return load_data(BOOSTER_REWARDS_FILE, {})


# Add these functions to your cogs/utils.py file
def load_rewards():
    """Loads rewards data from the JSON file."""
    return load_data(REWARDS_FILE, {'cooldowns': {}, 'rewards': {}})

def save_rewards(data):
    """Saves rewards data to the JSON file."""
    save_data(data, REWARDS_FILE)

def load_sorry_jar_data():
    """Loads the sorry jar data from a JSON file."""
    try:
        if not os.path.exists('data'):
            os.makedirs('data')
        with open(SORRY_JAR_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print(f"Error decoding JSON from {SORRY_JAR_FILE}. Returning an empty dictionary.")
        return {}

def save_sorry_jar_data(data):
    """Saves the sorry jar data to a JSON file."""
    try:
        if not os.path.exists('data'):
            os.makedirs('data')
        with open(SORRY_JAR_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except IOError as e:
        print(f"Error saving sorry jar data: {e}")

def save_booster_rewards(data: Dict[str, str]):
    save_data(data, BOOSTER_REWARDS_FILE)

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

# --- Global Configuration Constants (Reloaded via reload_globals) ---
QOTD_ROLE_ID = None
MAIN_GUILD_ID = None
TEST_CHANNEL_ID = None
PLAYER_ROLE_ID = None
QOTD_CHANNEL_ID = None
ADVENTURE_MAIN_CHANNEL_ID = None
CHAT_REVIVE_CHANNEL_ID = None
DAILY_COMMENTS_CHANNEL_ID = None
SELF_ROLES_CHANNEL_ID = None
SINNER_CHAT_CHANNEL_ID = None
BUMDAY_MONDAY_CHANNEL_ID = None
TITS_OUT_TUESDAY_CHANNEL_ID = None
WET_WEDNESDAY_CHANNEL_ID = None
FURBABY_THURSDAY_CHANNEL_ID = None
FRISKY_FRIDAY_CHANNEL_ID = None
SELFIE_SATURDAY_CHANNEL_ID = None
SLUTTY_SUNDAY_CHANNEL_ID = None
ANAGRAM_CHANNEL_ID = None
BUMP_BATTLE_CHANNEL_ID = None
ANNOUNCEMENTS_CHANNEL_ID = None
VOTE_CHANNEL_ID = None
VOTE_COOLDOWN_HOURS = None
TREE_CHANNEL_ID = None
COUNTING_CHANNEL_ID = None
REVIVE_INTERVAL_HOURS = None
ROLE_IDS = {}
CHAT_REVIVE_ROLE_ID = None
ANNOUNCEMENTS_ROLE_ID = None
MOD_ROLE_ID = None
TIMED_CHANNELS = {}
DAILY_POSTS_CHANNELS = []

# Image URLs for daily posts
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


# --- Autocomplete Functions for Commands ---
async def channel_id_name_autocomplete(interaction: discord.Interaction, current: str):
    """Provides a list of channel ID keys from the bot_config for autocomplete."""
    choices = []
    # Explicitly list all channel ID keys to include in the autocomplete
    channel_keys = [
        "TEST_CHANNEL_ID",
        "CHAT_REVIVE_CHANNEL_ID",
        "ADVENTURE_CHANNEL_ID",
        "DAILY_COMMENTS_CHANNEL_ID",
        "SELF_ROLES_CHANNEL_ID",
        "SINNER_CHAT_CHANNEL_ID",
        "ANAGRAM_CHANNEL_ID",
        "BUMP_BATTLE_CHANNEL_ID",
        "ANNOUNCEMENTS_CHANNEL_ID",
        "VOTE_CHANNEL_ID",
        "COUNTING_CHANNEL_ID",
        "BUMDAY_MONDAY_CHANNEL_ID",
        "TITS_OUT_TUESDAY_CHANNEL_ID",
        "WET_WEDNESDAY_CHANNEL_ID",
        "FURBABY_THURSDAY_CHANNEL_ID",
        "FRISKY_FRIDAY_CHANNEL_ID",
        "SELFIE_SATURDAY_CHANNEL_ID",
        "SLUTTY_SUNDAY_CHANNEL_ID",
        "TREE_CHANNEL_ID",
        "QOTD_CHANNEL_ID"
    ]
    
    for key in channel_keys:
        if key in bot_config and isinstance(bot_config.get(key), int) and current.lower() in key.lower():
            # Create a more readable name for the user
            readable_name = key.replace("_CHANNEL_ID", "").replace("_", " ").title()
            choices.append(app_commands.Choice(name=readable_name, value=key))
            
    return choices

async def role_id_name_autocomplete(interaction: discord.Interaction, current: str):
    """Provides a list of role ID keys from the bot_config for autocomplete."""
    choices = []
    role_ids_dict = bot_config.get("role_ids", {})
    # Added PLAYER_ROLE_ID to the autocomplete choices
    if "PLAYER_ROLE_ID" in bot_config and "player" in current.lower():
        choices.append(app_commands.Choice(name="PLAYER_ROLE_ID", value="PLAYER_ROLE_ID"))
    for key in role_ids_dict:
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
    """Updates a specific role ID in the nested 'role_ids' dictionary or at the top level."""
    global bot_config
    if role_name == "PLAYER_ROLE_ID":
        bot_config[role_name] = role_id
    else:
        if "role_ids" not in bot_config:
            bot_config["role_ids"] = {}
        bot_config["role_ids"][role_name] = role_id
    save_data(bot_config, BOT_CONFIG_FILE)
    reload_globals()

def reload_globals():
    global MAIN_GUILD_ID, TEST_CHANNEL_ID, PLAYER_ROLE_ID, ADVENTURE_MAIN_CHANNEL_ID, CHAT_REVIVE_CHANNEL_ID, DAILY_COMMENTS_CHANNEL_ID, SELF_ROLES_CHANNEL_ID, SINNER_CHAT_CHANNEL_ID, BUMDAY_MONDAY_CHANNEL_ID, TITS_OUT_TUESDAY_CHANNEL_ID, WET_WEDNESDAY_CHANNEL_ID, FURBABY_THURSDAY_CHANNEL_ID, FRISKY_FRIDAY_CHANNEL_ID, SELFIE_SATURDAY_CHANNEL_ID, SLUTTY_SUNDAY_CHANNEL_ID, ANAGRAM_CHANNEL_ID, BUMP_BATTLE_CHANNEL_ID, ANNOUNCEMENTS_CHANNEL_ID, VOTE_CHANNEL_ID, VOTE_COOLDOWN_HOURS, ROLE_IDS, CHAT_REVIVE_ROLE_ID, ANNOUNCEMENTS_ROLE_ID, MOD_ROLE_ID, TIMED_CHANNELS, DAILY_POSTS_CHANNELS, TREE_CHANNEL_ID, COUNTING_CHANNEL_ID, REVIVE_INTERVAL_HOURS, QOTD_CHANNEL_ID, QOTD_ROLE_ID, CHECKIN_CHANNEL_ID, DAILY_MESSAGE_REWARD_CHANNEL_ID, BOOSTER_REWARD_CHANNEL_ID

    bot_config_reloaded = load_data(BOT_CONFIG_FILE, {})
    
    # Reloading all global variables from the config
    QOTD_CHANNEL_ID = bot_config_reloaded.get("QOTD_CHANNEL_ID", TEST_CHANNEL_ID)
    CHECKIN_CHANNEL_ID = bot_config.get("CHECKIN_CHANNEL_ID", None)
    DAILY_MESSAGE_REWARD_CHANNEL_ID = bot_config.get("DAILY_MESSAGE_REWARD_CHANNEL_ID", None)
    BOOSTER_REWARD_CHANNEL_ID = bot_config.get("BOOSTER_REWARD_CHANNEL_ID", None)
    QOTD_ROLE_ID = bot_config_reloaded.get("QOTD_ROLE_ID", None)
    MAIN_GUILD_ID = bot_config_reloaded.get("MAIN_GUILD_ID", None)
    TEST_CHANNEL_ID = bot_config_reloaded.get("TEST_CHANNEL_ID", 1403900596020580523)
    CHAT_REVIVE_CHANNEL_ID = bot_config_reloaded.get("CHAT_REVIVE_CHANNEL_ID", TEST_CHANNEL_ID)
    ADVENTURE_MAIN_CHANNEL_ID = bot_config_reloaded.get("ADVENTURE_CHANNEL_ID", TEST_CHANNEL_ID)
    PLAYER_ROLE_ID = bot_config_reloaded.get("PLAYER_ROLE_ID", None)
    DAILY_COMMENTS_CHANNEL_ID = bot_config_reloaded.get("DAILY_COMMENTS_CHANNEL_ID", TEST_CHANNEL_ID)
    SELF_ROLES_CHANNEL_ID = bot_config_reloaded.get("SELF_ROLES_CHANNEL_ID", TEST_CHANNEL_ID)
    SINNER_CHAT_CHANNEL_ID = bot_config_reloaded.get("SINNER_CHAT_CHANNEL_ID", TEST_CHANNEL_ID)
    BUMDAY_MONDAY_CHANNEL_ID = bot_config_reloaded.get("BUMDAY_MONDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    TITS_OUT_TUESDAY_CHANNEL_ID = bot_config_reloaded.get("TITS_OUT_TUESDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    WET_WEDNESDAY_CHANNEL_ID = bot_config_reloaded.get("WET_WEDNESDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    FURBABY_THURSDAY_CHANNEL_ID = bot_config_reloaded.get("FURBABY_THURSDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    FRISKY_FRIDAY_CHANNEL_ID = bot_config_reloaded.get("FRISKY_FRIDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    SELFIE_SATURDAY_CHANNEL_ID = bot_config_reloaded.get("SELFIE_SATURDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    SLUTTY_SUNDAY_CHANNEL_ID = bot_config_reloaded.get("SLUTTY_SUNDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    ANAGRAM_CHANNEL_ID = bot_config_reloaded.get("ANAGRAM_CHANNEL_ID", TEST_CHANNEL_ID)
    BUMP_BATTLE_CHANNEL_ID = bot_config_reloaded.get("BUMP_BATTLE_CHANNEL_ID", TEST_CHANNEL_ID)
    ANNOUNCEMENTS_CHANNEL_ID = bot_config_reloaded.get("ANNOUNCEMENTS_CHANNEL_ID", TEST_CHANNEL_ID)
    VOTE_CHANNEL_ID = bot_config_reloaded.get("VOTE_CHANNEL_ID", TEST_CHANNEL_ID)
    VOTE_COOLDOWN_HOURS = bot_config_reloaded.get("VOTE_COOLDOWN_HOURS", 24)
    TREE_CHANNEL_ID = bot_config_reloaded.get("TREE_CHANNEL_ID", TEST_CHANNEL_ID)
    COUNTING_CHANNEL_ID = bot_config_reloaded.get("COUNTING_CHANNEL_ID", TEST_CHANNEL_ID)
    REVIVE_INTERVAL_HOURS = bot_config_reloaded.get("REVIVE_INTERVAL_HOURS", 6)
    BUMDAY_MONDAY_CHANNEL_ID = bot_config_reloaded.get("BUMDAY_MONDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    TITS_OUT_TUESDAY_CHANNEL_ID = bot_config_reloaded.get("TITS_OUT_TUESDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    WET_WEDNESDAY_CHANNEL_ID = bot_config_reloaded.get("WET_WEDNESDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    FURBABY_THURSDAY_CHANNEL_ID = bot_config_reloaded.get("FURBABY_THURSDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    FRISKY_FRIDAY_CHANNEL_ID = bot_config_reloaded.get("FRISKY_FRIDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    SELFIE_SATURDAY_CHANNEL_ID = bot_config_reloaded.get("SELFIE_SATURDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    SLUTTY_SUNDAY_CHANNEL_ID = bot_config_reloaded.get("SLUTTY_SUNDAY_CHANNEL_ID", TEST_CHANNEL_ID)
    CHECKIN_CHANNEL_ID = bot_config_reloaded.get("CHECKIN_CHANNEL_ID", None)
    DAILY_MESSAGE_REWARD_CHANNEL_ID = bot_config_reloaded.get("DAILY_MESSAGE_REWARD_CHANNEL_ID", None)
    BOOSTER_REWARD_CHANNEL_ID = bot_config_reloaded.get("BOOSTER_REWARD_CHANNEL_ID", None)


    ROLE_IDS = bot_config_reloaded.get("role_ids", {})
    CHAT_REVIVE_ROLE_ID = ROLE_IDS.get("chat_revive_role", None)
    ANNOUNCEMENTS_ROLE_ID = ROLE_IDS.get("announcements_role", None)
    MOD_ROLE_ID = ROLE_IDS.get("Staff", [])

    TIMED_CHANNELS = bot_config_reloaded.get("timed_channels", {})
    DAILY_POSTS_CHANNELS = [channel_id for channel_id, _, _ in TIMED_CHANNELS.values()]

# Call reload_globals() once at the start to load initial config
reload_globals()

# --- ADVENTURE GAME SPECIFIC CONFIGURATIONS ---
ALL_TRAP_OPTIONS = [
    "rope",
    "blindfold",
    "ball_gag",
    "mummification",
    "straitjacket",
    "leather_strap",
    "leather_mittens",
    "layers_of_tape",
]

TRAP_DISPLAY_NAMES = {
    "ball_gag": "Ball Gag",
    "rope": "Ropes",
    "blindfold": "Blindfold",
    "mummification": "Mummification",
    "straitjacket": "Straitjacket",
    "leather_strap": "Leather Straps",
    "leather_mittens": "Leather Mittens",
    "layers_of_tape": "Layers of Tape",
}

TRAP_DURATIONS = {
    "ball_gag": 3,
    "rope": 2,
    "blindfold": 1,
    "mummification": 1,
    "straitjacket": 1,
    "leather_strap": 1,
    "leather_mittens": 1,
    "layers_of_tape": 1,
}

MAX_ROPE_TIGHTNESS = 5
MAX_BLINDFOLD_LEVEL = 3
MAX_GAG_LEVEL = 4
MAX_TAPE_LAYERS = 5

TRAP_DESCRIPTIONS = {
    "ball_gag": "Your mouth feels strange... your attempts to speak are met with muffled, garbled sounds. Communication will be difficult.",
    "rope": "Suddenly, something tightens around you! You're ensnared by strong bindings that restrict your movement. You'll need to struggle to get free.",
    "blindfold": "Darkness descends as something covers your eyes. Your vision is completely obscured, forcing your other senses to sharpen.",
    "mummification": "You're suddenly enveloped in wraps! They tighten around you from head to toe, leaving you almost completely immobile and just enough room to breathe.",
    "straitjacket": "Your arms are swiftly pinned! A restrictive garment tightens, trapping your limbs securely against your body. Movement is severely limited.",
    "leather_strap": "Heavy, resilient straps lash out, binding you securely to your surroundings! The strong material holds you firmly in place, preventing escape.",
    "leather_mittens": "Your hands are encased in thick leather mittens, restricting their use. You can't grasp small objects or use your fingers with precision.",
    "layers_of_tape": "Layers of strong, wide tape are applied over your mouth, or around your wrists and ankles. It feels sticky and suffocating, making movement or speech difficult."
}

def parse_consent_from_text(text: str, ai_restrictions: List[str]) -> List[str]:
    text_lower = text.lower()
    consented = []

    if "none" in text_lower or "no traps" in text_lower or "no to all" in text_lower:
        return []

    if "all" in text_lower or "all traps" in text_lower:
        return [trap for trap in ALL_TRAP_OPTIONS if trap.lower() not in ai_restrictions]

    for trap in ALL_TRAP_OPTIONS:
        display_name_lower = TRAP_DISPLAY_NAMES.get(trap, trap.replace('_', ' ')).lower()
        if trap.lower() in text_lower or display_name_lower in text_lower:
            if trap.lower() not in ai_restrictions:
                consented.append(trap)
            else:
                print(f"User attempted to consent to restricted trap: {trap}")

    return list(set(consented))

def set_active_adventure_channel(channel_id: int, game_instance: Any):
    """Placeholder function to indicate an adventure game is active."""
    # This function is a placeholder since the game state is managed by the main cog.
    # The error indicates a missing function, so adding this as a stub will resolve it.
    pass

def remove_active_adventure_channel(channel_id: int):
    """Placeholder function to indicate an adventure game is no longer active."""
    # This function is also a placeholder to match the expected calls.
    pass

def load_active_adventure_games_from_file() -> Dict[str, Any]:
    """Loads active adventure games state from a file."""
    return load_data(ACTIVE_ADVENTURE_GAMES_FILE, {})

def save_active_adventure_games_to_file(state: Dict[str, Any]):
    """Saves active adventure games state to a file."""
    save_data(state, ACTIVE_ADVENTURE_GAMES_FILE)

def load_user_roles(user_id: int) -> list[int]:
    """Loads a user's original roles from a JSON file."""
    all_roles = load_data(USER_ROLES_FILE, {})
    return all_roles.get(str(user_id), [])

def save_user_roles(user_id: int, roles: list[int]):
    """Saves a user's roles to a JSON file."""
    all_roles = load_data(USER_ROLES_FILE, {})
    all_roles[str(user_id)] = roles
    save_data(all_roles, USER_ROLES_FILE)
    
def save_adventure_channel_id(channel_id: int):
    """Saves the adventure channel ID to the bot configuration."""
    update_dynamic_config("ADVENTURE_CHANNEL_ID", channel_id)

def load_adventure_channel_id() -> Optional[int]:
    """Loads the adventure channel ID from the bot configuration."""
    return bot_config.get("ADVENTURE_CHANNEL_ID")

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

async def generate_scenario_adventure(
    chat_history: List[Dict[str, Any]],
    player_name: str,
    current_traps: Dict[str, int],
    ai_restrictions: List[str],
    game_theme: str = None,
    allowed_traps: List[str] = None,
    is_incapacitated: bool = False
) -> Dict[str, Any]:
    """
    Generates a new adventure scenario based on the game state.
    """
    global _gemini_model
    if _gemini_model is None:
        try:
            _gemini_model = genai.GenerativeModel(DEFAULT_TRANSLATION_MODEL_NAME)
        except Exception as e:
            print(f"Error initializing Gemini model: {e}")
            return {"scenario_text": "AI model is not ready.", "choices": []}

    system_instruction_parts = [
        "You are the Game Master for a text-based adventure game. You are a neutral, objective narrator.",
        "Your responses must be in JSON format with three keys: `scenario_text`, `choices`, and `trap_effects`.",
        "The `scenario_text` describes the current situation. The `choices` key is a list of 2-4 possible actions for the player. The `trap_effects` key is a list of effects to apply to the player's character.",
        "The story should be focused on escaping from a difficult or restrictive situation. The goal is to escape, not to be bound.",
        f"The player's name is {player_name}.",
    ]
    if game_theme:
        system_instruction_parts.append(f"The theme of this adventure is '{game_theme}'.")
    if current_traps:
        traps_description = ', '.join([f"{TRAP_DISPLAY_NAMES.get(t, t)} (Level: {level})" for t, level in current_traps.items()])
        system_instruction_parts.append(f"The player is currently affected by these conditions: {traps_description}.")
    if is_incapacitated:
        system_instruction_parts.append("The player is currently incapacitated. Their actions should be limited to struggling against their restraints or attempting to call for help.")
    if allowed_traps:
        system_instruction_parts.append(f"The player has consented to the following optional elements, which you can introduce into the game: {', '.join(allowed_traps)}.")
    else:
        system_instruction_parts.append("The player has NOT consented to any optional elements. Do not introduce any restraints or traps.")
    
    system_instruction_parts.append("IMPORTANT: You must adhere to the following strict safety guidelines. Never generate content related to: " + ', '.join(ai_restrictions) + ".")

    full_prompt = "\n".join(system_instruction_parts)
    
    full_chat_history = [{"role": "user", "parts": [{"text": full_prompt}]}]
    full_chat_history.extend(chat_history)
    full_chat_history.append({"role": "user", "parts": [{"text": "Please provide the next game turn in the specified JSON format."}]})

    try:
        response = await asyncio.wait_for(
            _gemini_model.generate_content_async(full_chat_history),
            timeout=AI_GENERATION_TIMEOUT
        )
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[len("```json"):].strip()
        if response_text.endswith("```"):
            response_text = response_text[:-len("```")].strip()
        return json.loads(response_text)
    
    except asyncio.TimeoutError:
        return {"scenario_text": "AI generation timed out. Please try again.", "choices": []}
    except json.JSONDecodeError:
        print(f"AI response was not valid JSON: {response.text}")
        return {"scenario_text": "An error occurred with the AI. The response was not in a valid format.", "choices": []}
    except Exception as e:
        print(f"Error generating adventure scenario: {e}")
        return {"scenario_text": "An error occurred with the AI. Please try again.", "choices": []}

async def generate_image_from_text(scenario_text: str, game_theme: str = None) -> Optional[bytes]:
    """Generates an image from a text description using Gemini's vision model."""
    if not GEMINI_API_KEY:
        print("Gemini API key is not set. Skipping image generation.")
        return None
    
    prompt = f"Create a high-quality fantasy image of a character in a scenario described as: '{scenario_text}'. The setting is a {game_theme if game_theme else 'dark fantasy world'}."
    
    try:
        print("Gemini API does not directly return an image file. Returning a placeholder.")
        img = Image.new('RGB', (1024, 576), color = 'gray')
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 40)
        except IOError:
            font = ImageFont.load_default()
        d.text((20, 20), "Placeholder Image from Gemini", fill=(0,0,0), font=font)
        
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        return img_byte_arr.getvalue()
    
    except Exception as e:
        print(f"Error during Gemini image generation: {e}")
        return None

def get_ai_restrictions() -> List[str]:
    """Loads AI restrictions from a file, creating a default if it doesn't exist."""
    try:
        if os.path.exists(ADVENTURE_AI_RESTRICTIONS_FILE):
            with open(ADVENTURE_AI_RESTRICTIONS_FILE, 'r', encoding='utf-8') as f:
                lines = [line.strip().lower() for line in f if line.strip()]
            return lines
        else:
            default_restrictions = [
                'rape', 'torture', 'non-consensual_acts', 'pedophilia', 'zoophilia',
                'violence', 'death'
            ]
            with open(ADVENTURE_AI_RESTRICTIONS_FILE, 'w', encoding='utf-8') as f:
                f.write('\n'.join(default_restrictions))
            return default_restrictions
    except Exception as e:
        print(f"Error loading AI restrictions: {e}")
        return []

def garble_text(text: str) -> str:
    """Simulates garbled speech."""
    garbled_chars = "mhmphfflblh"
    result = []
    for char in text:
        if char.isalpha():
            if random.random() < 0.3:
                result.append(random.choice(garbled_chars))
            else:
                result.append(char)
        else:
            result.append(char)
    return "".join(result)

def load_timed_channels():
    return TIMED_CHANNELS

def load_daily_posts_channels():
    return DAILY_POSTS_CHANNELS

def get_user_money(user_id: int) -> int:
    """Gets a user's wallet balance."""
    balances = load_data(BALANCES_FILE, {})
    user_id_str = str(user_id)
    user_data = balances.get(user_id_str, {"wallet": 0, "bank": 0})
    
    # Check for the old format (integer) and migrate it
    if isinstance(user_data, int):
        new_data = {"wallet": user_data, "bank": 0}
        balances[user_id_str] = new_data
        save_data(balances, BALANCES_FILE)
        return new_data["wallet"]
        
    return user_data.get("wallet", 0)

def get_user_bank_money(user_id: int) -> int:
    """Gets a user's bank balance."""
    balances = load_data(BALANCES_FILE, {})
    user_id_str = str(user_id)
    user_data = balances.get(user_id_str, {"wallet": 0, "bank": 0})

    # Check for the old format (integer) and migrate it
    if isinstance(user_data, int):
        new_data = {"wallet": user_data, "bank": 0}
        balances[user_id_str] = new_data
        save_data(balances, BALANCES_FILE)
        return new_data["bank"]
        
    return user_data.get("bank", 0)

def update_user_money(user_id: int, amount: int):
    """Updates a user's wallet balance."""
    balances = load_data(BALANCES_FILE, {})
    user_id_str = str(user_id)
    user_data = balances.get(user_id_str, {"wallet": 0, "bank": 0})
    
    # Check for the old format and migrate before updating
    if isinstance(user_data, int):
        user_data = {"wallet": user_data, "bank": 0}
        
    user_data["wallet"] += amount
    balances[user_id_str] = user_data
    save_data(balances, BALANCES_FILE)

def update_user_bank_money(user_id: int, amount: int):
    """Updates a user's bank balance."""
    balances = load_data(BALANCES_FILE, {})
    user_id_str = str(user_id)
    user_data = balances.get(user_id_str, {"wallet": 0, "bank": 0})
    
    # Check for the old format and migrate before updating
    if isinstance(user_data, int):
        user_data = {"wallet": user_data, "bank": 0}

    user_data["bank"] += amount
    balances[user_id_str] = user_data
    save_data(balances, BALANCES_FILE)
    
def transfer_money(user_id: int, amount: int, from_type: str, to_type: str):
    """Transfers money between a user's wallet and bank."""
    balances = load_data(BALANCES_FILE, {})
    user_id_str = str(user_id)
    
    user_data = balances.get(user_id_str, {"wallet": 0, "bank": 0})
    # Check for the old format and migrate before updating
    if isinstance(user_data, int):
        user_data = {"wallet": user_data, "bank": 0}

    user_data[from_type] -= amount
    user_data[to_type] += amount
    balances[user_id_str] = user_data
    save_data(balances, BALANCES_FILE)

def load_chat_revive_channel() -> Optional[int]:
    return CHAT_REVIVE_CHANNEL_ID

def save_chat_revive_channel(channel_id: int):
    update_dynamic_config("CHAT_REVIVE_CHANNEL_ID", channel_id)

def load_timed_roles():
    """Loads all timed roles from the JSON file."""
    if not os.path.exists("data"):
        os.makedirs("data")
    if not os.path.exists(TIMED_ROLES_FILE):
        return {}
    with open(TIMED_ROLES_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_timed_role_data(guild_id, role_id, expiration_date=None, repeatable=False, day_of_week=None, hours=None):
    """
    Saves a timed role's information to a JSON file.
    Args:
        guild_id (int): The ID of the guild.
        role_id (int): The ID of the role.
        expiration_date (str): The ISO formatted expiration date.
        repeatable (bool): Whether the role is repeatable.
        day_of_week (str): The day of the week for repeatable roles (e.g., 'Monday', 'daily').
        hours (int): The duration in hours for daily repeatable roles.
    """
    all_timed_roles = load_timed_roles()
    guild_id_str = str(guild_id)
    role_id_str = str(role_id)

    if guild_id_str not in all_timed_roles:
        all_timed_roles[guild_id_str] = {}

    all_timed_roles[guild_id_str][role_id_str] = {
        "expiration_date": expiration_date,
        "repeatable": repeatable,
        "day_of_week": day_of_week,
        "hours": hours
    }
    
    # Initialize last_action_time for new daily repeatable roles
    if repeatable and day_of_week == "daily":
        all_timed_roles[guild_id_str][role_id_str]["last_action_time"] = datetime.datetime.now(datetime.timezone.utc).isoformat()


    with open(TIMED_ROLES_FILE, "w") as f:
        json.dump(all_timed_roles, f, indent=4)


def save_timed_roles_full_data(data):
    """Saves the entire timed roles dictionary to the JSON file."""
    if not os.path.exists("data"):
        os.makedirs("data")
    with open(TIMED_ROLES_FILE, "w") as f:
        json.dump(data, f, indent=4)

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
    
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(DEFAULT_TRANSLATION_MODEL_NAME)
    
    if event_type == "duel" and len(tributes) == 2:
        prompt = (
            f"Generate a short, high-energy Hangry Games duel event in strict JSON format. "
            f"Tributes: {tributes[0].display_name} vs. {tributes[1].display_name}. "
            "The duel must be ridiculous and food-themed, with wild, imaginative, and funny combat using cooking, eating, or weaponized food. "
            "The event should read like a mini-scene (2–3 sentences) with action and maybe a quick reaction or consequence. "
            "Avoid repeating any previously used foods, weapons, or scenarios—each duel must use new foods or a fresh twist. "
            "Rotate between different food categories (fruits, vegetables, baked goods, drinks, condiments, meats, dairy, desserts, etc.) to keep variety. "
            "JSON keys required: `title` (funny food-fight style headline), "
            "`description` (2–3 sentences using placeholders {winner} and {loser}), "
            "`winner` (tribute name), and `loser` (tribute name). "
            "Keep it energetic, surprising, and playful, but always food-focused."
        )

    elif event_type == "solo_death" and len(tributes) == 1:
        prompt = (
            f"Generate a short, humorous, and ironic Hangry Games solo death event in strict JSON format. "
            f"Tribute: {tributes[0].display_name}. "
            "The death must be a ridiculous, clumsy, food-related accident—something unexpected, cartoonish, and over-the-top. "
            "The event should read like a mini-scene (2–3 sentences) with a bit of setup, the accident, and an ironic aftermath. "
            "Do NOT reuse the same food item, weapon, or scenario as in previous events—make each one unique. "
            "JSON keys required: `title` (funny food-fight style headline), "
            "`description` (2–3 sentences using placeholder {tribute}), "
            "`tribute` (tribute name)."
            "Keep it playful and exaggerated, never dark or gory."
        )

    else:
        return None
    
    # Retry loop for AI generation
    retries = 3
    while retries > 0:
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
            
            event = json.loads(response_text)
            
            # Normalize keys to lowercase for consistent access
            normalized_event = {k.lower(): v for k, v in event.items()}
            
            # Validate the normalized keys based on the event type
            if event_type == "duel":
                required_keys = ['title', 'description', 'winner', 'loser']
            elif event_type == "solo_death":
                required_keys = ['title', 'description', 'tribute']
            else:
                return None
            
            if all(key in normalized_event for key in required_keys):
                return normalized_event
            else:
                print(f"AI response missing required keys. Retrying... {event}")
                retries -= 1
                await asyncio.sleep(1) # Wait a second before retrying
                continue

        except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
            print(f"Error generating hangry event. Retrying...: {e}")
            retries -= 1
            await asyncio.sleep(1)
            continue
            
    print("Failed to generate a valid event after multiple retries.")
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

def add_item_to_inventory(user_id: int, item_name: str, item_data: Optional[Dict[str, Any]] = None, count: int = 1):
    """Adds a generic item to a user's inventory, handling stacks and nets."""
    user_inventory_data = load_data(USER_INVENTORY_FILE, {})
    user_data = user_inventory_data.get(str(user_id), {"items": {}, "nets": [], "net_durability": 0, "xp": 0})

    if item_data and item_data.get('type') == 'net':
        # Add a new net entry
        new_net = {
            "name": item_name,
            "durability": item_data.get("durability", 0)
        }
        user_data["nets"].append(new_net)
    else:
        # Handle regular items with a counter
        user_items = user_data.get("items", {})
        item_name_lower = item_name.lower()
        user_items[item_name_lower] = user_items.get(item_name_lower, 0) + count
        user_data["items"] = user_items

    user_inventory_data[str(user_id)] = user_data
    save_data(user_inventory_data, USER_INVENTORY_FILE)

def remove_item_from_inventory(user_id: int, item_name: str, count: int = 1):
    """Removes a specified number of items from a user's inventory."""
    user_inventory_data = load_data(USER_INVENTORY_FILE, {})
    user_data = user_inventory_data.get(str(user_id), {"items": {}, "nets": [], "net_durability": 0, "xp": 0})
    user_items = user_data.get("items", {})
    item_name_lower = item_name.lower()

    if user_items.get(item_name_lower, 0) > count:
        user_items[item_name_lower] -= count
    else:
        # If the count is greater than or equal to the total, remove the item completely.
        if item_name_lower in user_items:
            del user_items[item_name_lower]

    user_data["items"] = user_items
    user_inventory_data[str(user_id)] = user_data
    save_data(user_inventory_data, USER_INVENTORY_FILE)
    
async def handle_buy_item(interaction: discord.Interaction, item_to_buy: Dict[str, Any], quantity: int = 1, free_purchase: bool = False):
    user_id = str(interaction.user.id)

    # Get user money using the dedicated function
    user_money = get_user_money(interaction.user.id)
    
    # Load user inventory from the correct file (user_inventory.json)
    user_inventory_data = load_data(USER_INVENTORY_FILE, {})
    user_items = user_inventory_data.get(user_id, {}).get('items', {})
    
    total_price = item_to_buy.get('price', 0) * quantity

    # --- Start Debugging Code ---
    print(f"--- Debugging handle_buy_item ---")
    print(f"User ID: {user_id}")
    print(f"User Money: {user_money}")
    print(f"Item Price: {item_to_buy.get('price', 0)}")
    print(f"Quantity: {quantity}")
    print(f"Calculated Total Price: {total_price}")
    print(f"---------------------------------")
    # --- End Debugging Code ---

    if not free_purchase:
        if user_money < total_price:
            return await interaction.followup.send("You don't have enough coins to purchase this item.", ephemeral=True)

        if item_to_buy.get('requirement'):
            required_item = item_to_buy['requirement'].lower()
            if user_items.get(required_item, 0) == 0:
                return await interaction.followup.send(f"You need to own the '{required_item}' item to buy this.", ephemeral=True)
    
    # Update user's money
    if not free_purchase:
        update_user_money(interaction.user.id, -total_price)
    
    # Add item to inventory based on type
    if item_to_buy.get('type') == 'net':
        for _ in range(quantity):
            add_item_to_inventory(interaction.user.id, item_to_buy.get('name'), item_data=item_to_buy)
    else:
        # This function call now uses the corrected argument name
        add_item_to_inventory(interaction.user.id, item_to_buy.get('name'), count=quantity)
        
    await interaction.followup.send(f"Successfully purchased {quantity} '{item_to_buy.get('name')}' for {total_price} coins!", ephemeral=True)

def load_swear_jar_data():
    return load_data(SWEAR_JAR_FILE, {'words': [], 'tally': {}})

def get_item_emoji(item_name: str, emoji_str: str) -> str:
    """Helper function to get the correct emoji string."""
    if emoji_str:
        if emoji_str.startswith('<') and emoji_str.endswith('>'):
            return emoji_str
        return emoji_str
    return "🛒"

def save_swear_jar_data(data: Dict[str, Any]):
    save_data(data, SWEAR_JAR_FILE)

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

def now():
    """Returns the current UTC time."""
    return datetime.datetime.now(datetime.timezone.utc)

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
    """Loads AI restrictions from a file, creating a default if it doesn't exist."""
    try:
        with open(ADVENTURE_AI_RESTRICTIONS_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        default_restrictions = textwrap.dedent("""
            You are a text adventure game master.
            You will create a story based on the user's input.
            The story should be dark, fantasy, and mysterious.
            Do not break character.
            Keep your responses concise and focused on the current scene.
        """).strip()
        with open(ADVENTURE_AI_RESTRICTIONS_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(default_restrictions))
        return default_restrictions
    except Exception as e:
        print(f"Error loading AI restrictions: {e}")
        return ""

def load_active_adventure_games_from_file() -> Dict[str, Any]:
    """Loads active adventure games state from a file."""
    return load_data(ACTIVE_ADVENTURE_GAMES_FILE, {})

def save_active_adventure_games_to_file(state: Dict[str, Any]):
    """Saves active adventure games state to a file."""
    save_data(state, ACTIVE_ADVENTURE_GAMES_FILE)

def load_user_roles(user_id: int) -> list[int]:
    """Loads a user's original roles from a JSON file."""
    all_roles = load_data(USER_ROLES_FILE, {})
    return all_roles.get(str(user_id), [])

def save_user_roles(user_id: int, roles: list[int]):
    """Saves a user's roles to a JSON file."""
    all_roles = load_data(USER_ROLES_FILE, {})
    all_roles[str(user_id)] = roles
    save_data(all_roles, USER_ROLES_FILE)
    
def save_adventure_channel_id(channel_id: int):
    """Saves the adventure channel ID to the bot configuration."""
    update_dynamic_config("ADVENTURE_CHANNEL_ID", channel_id)

def load_adventure_channel_id() -> Optional[int]:
    """Loads the adventure channel ID from the bot configuration."""
    return bot_config.get("ADVENTURE_CHANNEL_ID")

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
async def generate_image_from_text(scenario_text: str, game_theme: str = None) -> Optional[bytes]:
    """Generates an image from a text description using Gemini's vision model."""
    if not GEMINI_API_KEY:
        print("Gemini API key is not set. Skipping image generation.")
        return None
    
    prompt = f"Create a high-quality fantasy image of a character in a scenario described as: '{scenario_text}'. The setting is a {game_theme if game_theme else 'dark fantasy world'}."
    
    try:
        # Note: As of my last update, Gemini's API for image generation from text is not fully public
        # or it returns a placeholder. The following code simulates a placeholder.
        print("Gemini API does not directly return an image file. Returning a placeholder.")
        # Create a simple placeholder image
        img = Image.new('RGB', (1024, 576), color='gray')
        d = ImageDraw.Draw(img)
        try:
            # You can change 'arial.ttf' to another font file if you have one.
            font = ImageFont.truetype("arial.ttf", 40)
        except IOError:
            font = ImageFont.load_default()
        d.text((20, 20), "Placeholder Image from Gemini", fill=(0, 0, 0), font=font)
        
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        return img_byte_arr.getvalue()
    
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
        prompt = "Generate a single, common English word between 5 and 10 letters long. The word should be different from any previously generated word. Choose a word at random so the result varies each time. Do not include punctuation, numbers, or extra text—only output the word."
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
        print("Gemini API not set. Skipping AI generation.")
        return None
    try:
        model = genai.GenerativeModel(DEFAULT_TRANSLATION_MODEL_NAME)
        if is_success:
            prompt = (
                "Generate a single, short, and funny phrase describing a successful work task. "
                "The tone should be slightly absurd and lighthearted, similar to these examples: "
                "'worked as a chef in a bustling restaurant kitchen', "
                "'answered customer calls with a smile as a call center representative'. "
                "Do not include any extra text or punctuation."
            )
        else:
            prompt = (
                "Generate a single, short, and comically disastrous phrase for a failed work task. "
                "The outcome should be ironic and humorous, similar to these examples: "
                "'spilled coffee on the boss's new suit and were fired on the spot', "
                "'lost an important file and had to pay for its replacement'. "
                "Do not include any extra text or punctuation."
            )
        
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
        print("Gemini API not set. Skipping AI generation.")
        return None
    try:
        model = genai.GenerativeModel(DEFAULT_TRANSLATION_MODEL_NAME)
        if is_success:
            prompt = (
                "Generate a single, short, and creative phrase describing an unexpectedly successful crime. "
                "The phrase should be descriptive and slightly absurd. Do not include any extra text or punctuation."
            )
        else:
            prompt = (
                "Generate a single, short, and funny phrase describing a clumsy, failed crime attempt. "
                "The phrasing should be embarrassing and humorous. Do not include any extra text or punctuation."
            )
        
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

async def day_of_week_autocomplete(interaction: discord.Interaction, current: str):
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    return [
        app_commands.Choice(name=day, value=day)
        for day in days if current.lower() in day.lower()
    ]

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
