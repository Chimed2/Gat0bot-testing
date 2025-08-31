import os, sys, json, random, asyncio, traceback, subprocess, importlib.metadata, aiohttp, discord, yt_dlp
from datetime import datetime, timedelta; from urllib.parse import urlparse; from discord.ext import commands; from discord import app_commands; from discord.ui import View, Button; from dotenv import load_dotenv; from spotipy import Spotify; from spotipy.oauth2 import SpotifyClientCredentials; from googletrans import Translator, LANGUAGES

translator = Translator()
languages = list(LANGUAGES.keys())

UPLOAD_FOLDER = "damns"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# === VENV HANDLER ===
VENV_DIR = "venv"
venv_python = os.path.join(VENV_DIR, "bin", "python") if os.name != "nt" else os.path.join(VENV_DIR, "Scripts", "python.exe")

if not os.path.isdir(VENV_DIR):
    print("[*] Creating virtual environment...")
    subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])

if os.path.realpath(sys.executable) != os.path.realpath(venv_python):
    print(f"[*] Switching to virtual environment: {venv_python}")
    os.execv(venv_python, [venv_python] + sys.argv)

# === REQUIREMENTS INSTALL ===
def check_requirements(req_file="requirements.txt"):
    if not os.path.exists(req_file):
        print(f"[!] {req_file} not found.")
        return
    with open(req_file) as f:
        required = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    installed = {d.metadata['Name'].lower() for d in importlib.metadata.distributions()}
    missing = [pkg for pkg in required if pkg.lower().split('==')[0] not in installed]
    if missing:
        print(f"[*] Installing: {', '.join(missing)}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])

check_requirements()
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

warns = {}
modlogs = []
mutes = {}

spotify = Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

os.makedirs("modlogs", exist_ok=True)
os.makedirs("auto stuff", exist_ok=True)

ytdlp_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
    'default_search': 'auto',
    'noplaylist': True,
    'outtmpl': 'downloads/%(title)s.%(ext)s',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

os.makedirs("downloads", exist_ok=True)

def get_youtube_query_from_spotify(spotify_url):
    try:
        track = spotify.track(spotify_url)
        artist = track['artists'][0]['name']
        title = track['name']
        return f"{artist} - {title}"
    except Exception:
        return None

async def play_audio(interaction, url: str):
    voice = interaction.guild.voice_client

    # Handle Spotify
    if "spotify.com/track/" in url:
        query = get_youtube_query_from_spotify(url)
        if not query:
            return await interaction.followup.send("❌ Couldn't fetch Spotify track.")
    else:
        query = url

    # Download and stream audio
    try:
        with yt_dlp.YoutubeDL(ytdlp_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            audio_url = info["url"]
            title = info.get("title", "Unknown title")

        source = await discord.FFmpegOpusAudio.from_probe(audio_url, method='fallback')
        voice.play(source)
        await interaction.followup.send(f"🎶 Now playing: **{title}**")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to play music: {str(e)}")

def save_word_to_file(guild, folder_type, word, duration=None):
    server_folder = os.path.join("auto stuff", guild.name.replace("/", "_"))
    target_folder = os.path.join(server_folder, folder_type)
    os.makedirs(target_folder, exist_ok=True)
    word_file = os.path.join(target_folder, f"{word}.json")
    data = {"word": word}
    if duration:
        data["duration"] = duration
    with open(word_file, "w") as f:
        json.dump(data, f, indent=4)

def get_words_from_folder(guild, folder_type):
    server_folder = os.path.join("auto stuff", guild.name.replace("/", "_"), folder_type)
    if not os.path.isdir(server_folder):
        return []
    return [f[:-5] for f in os.listdir(server_folder) if f.endswith(".json")]

def get_automute_words_with_duration(guild):
    server_folder = os.path.join("auto stuff", guild.name.replace("/", "_"), "automute")
    if not os.path.isdir(server_folder):
        return {}
    word_map = {}
    for file in os.listdir(server_folder):
        if file.endswith(".json"):
            with open(os.path.join(server_folder, file)) as f:
                data = json.load(f)
                word_map[data["word"]] = data.get("duration", 60)
    return word_map

def save_mod_action(guild, user, moderator, action, reason=""):
    timestamp = datetime.utcnow().isoformat().replace(":", "-")
    server_folder = os.path.join("modlogs", guild.name.replace("/", "_"))
    user_folder = os.path.join(server_folder, f"{user.name}#{user.discriminator}")
    os.makedirs(user_folder, exist_ok=True)
    action_files = [f for f in os.listdir(user_folder) if f.startswith(action)]
    index = len(action_files) + 1
    data = {
        "user": f"{user.name}#{user.discriminator}",
        "moderator": f"{moderator.name}#{moderator.discriminator}" if moderator else "System",
        "action": action,
        "reason": reason,
        "timestamp": timestamp
    }
    filename = os.path.join(user_folder, f"{action}{index}.json")
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

@bot.event
async def on_ready():
    await tree.sync()
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="GATOHELL")
    )
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

@tree.command(name="rps", description="Play Rock Paper Scissors against the bot!")
@app_commands.describe(choice="Your choice: rock, paper, or scissors")
async def rps(interaction: discord.Interaction, choice: str):
    options = ['rock', 'paper', 'scissors']
    bot_choice = random.choice(options)
    user = choice.lower()

    if user not in options:
        await interaction.response.send_message("Invalid choice. Use rock, paper, or scissors.")
        return

    result = "It's a draw!"
    if (user == 'rock' and bot_choice == 'scissors') or \
       (user == 'paper' and bot_choice == 'rock') or \
       (user == 'scissors' and bot_choice == 'paper'):
        result = "You win!"
    elif user != bot_choice:
        result = "You lose!"

    await interaction.response.send_message(f"You chose **{user}**. I chose **{bot_choice}**. {result}")

@tree.command(name="roast", description="Roast a user (SFW only).")
@app_commands.describe(user="User to roast")
async def roast(interaction: discord.Interaction, user: discord.User):
    roasts = [
        "You're as useless as the 'ueue' in 'queue'.",
        "You have something on your chin... no, the third one down.",
        "You're not stupid; you just have bad luck thinking.",
        "You're the reason the gene pool needs a lifeguard.",
        "If I had a dollar for every smart thing you said, I'd be broke."
    ]
    await interaction.response.send_message(f"{user.mention}, {random.choice(roasts)}")

@tree.command(name="say", description="Make the bot say something.")
@app_commands.describe(message="The message for the bot to say")
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message)

@tree.command(name="airhorn", description="Play airhorn in your VC.")
async def airhorn(interaction: discord.Interaction):
    if interaction.user.voice and interaction.user.voice.channel:
        vc = await interaction.user.voice.channel.connect()
        vc.play(discord.FFmpegPCMAudio("airhorn.mp3"))
        while vc.is_playing():
            await discord.utils.sleep_until(vc.loop.time() + 1)
        await vc.disconnect()
        await interaction.response.send_message("AIRHORN BLASTED 🔊")
    else:
        await interaction.response.send_message("You're not in a voice channel.")

@tree.command(name="vineboom", description="Play vine boom in your VC.")
async def vineboom(interaction: discord.Interaction):
    if interaction.user.voice and interaction.user.voice.channel:
        vc = await interaction.user.voice.channel.connect()
        vc.play(discord.FFmpegPCMAudio("vineboom.mp3"))
        while vc.is_playing():
            await discord.utils.sleep_until(vc.loop.time() + 1)
        await vc.disconnect()
        await interaction.response.send_message("💥 VINE BOOM 💥")
    else:
        await interaction.response.send_message("You're not in a voice channel.")

@tree.command(name="dadjoke", description="Get a random dad joke.")
async def dadjoke(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)  # Defer immediately!

    joke = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://icanhazdadjoke.com/",
                headers={"Accept": "application/json"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    joke = data.get("joke")
                else:
                    joke = "❌ Failed to fetch a dad joke. Try again later."
    except Exception as e:
        joke = f"⚠️ Error while fetching joke: `{e}`"

    # Always send a followup to avoid "Unknown interaction"
    await interaction.followup.send(joke)

@tree.command(name="badtranslate", description="Translate a word multiple times through random languages.")
@app_commands.describe(word="The word or phrase to translate", iterations="Number of translations (10–10000)")
async def badtranslate(interaction: discord.Interaction, word: str, iterations: int):
    if iterations < 10 or iterations > 10000:
        await interaction.response.send_message("Please choose between 10 and 10,000 translations.", ephemeral=True)
        return

    try:
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True)
    except discord.NotFound:
        print("❌ Interaction expired before defer.")
        return

    languages = list(LANGUAGES.keys())

    try:
        progress_msg = await interaction.followup.send("🔄 Starting bad translation...")
    except discord.HTTPException as e:
        print(f"❌ Couldn't send progress message: {e}")
        return

    current = word
    total = iterations

    for i in range(total):
        lang = random.choice(languages)
        try:
            translation = await translator.translate(current, dest=lang)  # ✅ await
            current = translation.text
        except Exception as e:
          tb = traceback.format_exc()
          print(f"❌ Exception at iteration {i+1}:\n{tb}")
          await progress_msg.edit(content=f"❌ Error at iteration {i+1}: `{type(e).__name__}`")
          return

        if (i + 1) % max(1, total // 50) == 0 or (i + 1) == total:
            percent = int(((i + 1) / total) * 100)
            bar_len = 20
            filled_len = int(bar_len * percent / 100)
            bar = "█" * filled_len + "-" * (bar_len - filled_len)
            try:
                await progress_msg.edit(content=f"`[{bar}] {percent}%`\nTranslating...")
            except discord.HTTPException:
                pass

        await asyncio.sleep(0.01)

    await progress_msg.edit(content=f"✅ **Bad Translation Result ({iterations}x):**\n{current}")

@tree.command(name="playmusic", description="Play music from YouTube, SoundCloud, Spotify, or Newgrounds.")
@app_commands.describe(url="The music URL")
async def playmusic(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    user = interaction.user

    if not user.voice or not user.voice.channel:
        return await interaction.followup.send("❌ You must be in a voice channel.", ephemeral=True)

    channel = user.voice.channel
    voice = interaction.guild.voice_client

    if not voice or not voice.is_connected():
        await channel.connect()

    await play_audio(interaction, url)

@tree.command(name="stopmusic", description="Stop the music and disconnect from the voice channel.")
async def stopmusic(interaction: discord.Interaction):
    voice = interaction.guild.voice_client
    if voice and voice.is_connected():
        voice.stop()
        await voice.disconnect()
        await interaction.response.send_message("🛑 Music stopped and disconnected.")
    else:
        await interaction.response.send_message("❌ I'm not connected to a voice channel.")

@tree.command(name="swarn", description="Warn a member silently (via DM)")
@app_commands.describe(user="User to warn", reason="Reason for warning")
@app_commands.checks.has_permissions(manage_messages=True)
async def swarn(interaction: discord.Interaction, user: discord.Member, reason: str):
    try:
        await user.send(f"⚠️ You were warned in **{interaction.guild.name}** for: {reason}")
    except:
        pass
    save_mod_action(interaction.guild, user, interaction.user, "warn", reason)
    await interaction.response.send_message("✅ User has been warned (DM sent).", ephemeral=True)

@tree.command(name="skick", description="Silently kick a member")
@app_commands.describe(user="User to kick", reason="Reason for kick")
@app_commands.checks.has_permissions(kick_members=True)
async def skick(interaction: discord.Interaction, user: discord.Member, reason: str):
    await user.kick(reason=reason)
    save_mod_action(interaction.guild, user, interaction.user, "kick", reason)
    await interaction.response.send_message("✅ User has been kicked.", ephemeral=True)

@tree.command(name="sban", description="Silently ban a member")
@app_commands.describe(user="User to ban", reason="Reason for ban")
@app_commands.checks.has_permissions(ban_members=True)
async def sban(interaction: discord.Interaction, user: discord.Member, reason: str):
    await user.ban(reason=reason)
    save_mod_action(interaction.guild, user, interaction.user, "ban", reason)
    await interaction.response.send_message("✅ User has been banned.", ephemeral=True)

@tree.command(name="dice", description="Roll a single dice")
async def dice(interaction: discord.Interaction):
    result = random.randint(1, 6)
    embed = discord.Embed(title="🎲 Dice Roll", description=f"You rolled a **{result}**!", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

@tree.command(name="roll", description="Roll 3 random numbers (1-7)")
async def roll(interaction: discord.Interaction):
    rolls = [str(random.randint(1, 7)) for _ in range(3)]
    embed = discord.Embed(title="🎰 Roll", description=f"Results: {' | '.join(rolls)}", color=discord.Color.purple())
    await interaction.response.send_message(embed=embed)

@tree.command(name="membercount", description="Get the number of server members")
async def membercount(interaction: discord.Interaction):
    count = interaction.guild.member_count
    embed = discord.Embed(title="👥 Member Count", description=f"This server has **{count}** members.", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="uploaddamn", description="Upload one or more damns (comma-separated links)")
@app_commands.describe(url="One or more direct media links, separated by commas")
async def uploaddamn(interaction: discord.Interaction, url: str):
    await interaction.response.defer()

    urls = [u.strip() for u in url.split(",")]
    successful = []
    failed = []

    for link in urls:
        parsed = urlparse(link)
        filename = os.path.basename(parsed.path)

        if not filename:
            failed.append((link, "Invalid or missing filename"))
            continue

        filepath = os.path.join(UPLOAD_FOLDER, filename)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(link) as resp:
                    if resp.status != 200:
                        failed.append((link, f"HTTP {resp.status}"))
                        continue
                    data = await resp.read()
                    with open(filepath, "wb") as f:
                        f.write(data)
            successful.append(filename)
        except Exception as e:
            failed.append((link, str(e)))

    # Build the response message
    msg = ""
    if successful:
        msg += f"✅ Uploaded: {', '.join(successful)}\n"
    if failed:
        msg += "❌ Failed:\n" + "\n".join([f"• {l} — {err}" for l, err in failed])

    await interaction.followup.send(msg or "Something went wrong.")
@bot.tree.command(name="damnhelp", description="DMs you help on how to use the damn commands")
async def damnhelp(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)  # avoid timeout and hide response

    user = interaction.user

    # Embed 1
    embed1 = discord.Embed(
        title="💡 Help for Damn",
        description="This command helps you with damn, and how to use it.",
        color=discord.Color.blurple()
    )

    # Embed 2
    embed2 = discord.Embed(
        title="🖼️ Upload Damn Bird",
        description=(
            "To upload a damn bird, you first need to get an image to upload.\n\n"
            "Go and search in any website (Google, Pinterest, Reddit, etc...), "
            "then right-click on the image and select **'Copy image link'**. "
            "Use `/uploaddamn` with that link to upload it."
        ),
        color=discord.Color.green()
    )

    # Embed 3
    embed3 = discord.Embed(
        title="🎲 How to Get a Random Damn Bird Meme",
        description="To get a random damn bird meme, just run `/randomdamn` in any channel you want.",
        color=discord.Color.orange()
    )

    try:
        await user.send(embeds=[embed1, embed2, embed3])
        await interaction.followup.send("📬 Sent you a DM with help!", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ I can't DM you! Please enable DMs from server members.", ephemeral=True)

@bot.tree.command(name="randomdamn", description="Send a random file from the damns folder")
async def randomdamn(interaction: discord.Interaction):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer()
    except discord.NotFound:
        print("❌ Interaction expired before defer.")
        return

    files = os.listdir(UPLOAD_FOLDER)
    if not files:
        await interaction.followup.send("❌ No damns uploaded yet.")
        return

    random.shuffle(files)
    chosen = files[0]
    filepath = os.path.join(UPLOAD_FOLDER, chosen)

    print(f"📸 Chosen file: {chosen}")

    try:
        await interaction.followup.send(file=discord.File(filepath))
    except Exception as e:
        await interaction.followup.send(f"❌ Couldn't send the file: {e}")

@tree.command(name="enableleveling", description="Enable leveling system for this server")
async def enableleveling(interaction: discord.Interaction):
    guild = interaction.guild
    server_path = os.path.join("srvlevels", guild.name.replace("/", "_"))
    settings_path = os.path.join(server_path, "setting.json")
    usr_path = os.path.join(server_path, "usrlevels")
    os.makedirs(usr_path, exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump({"server_leveling_enabled": True}, f, indent=4)
    await interaction.response.send_message(f"✅ Leveling system enabled for **{guild.name}**!", ephemeral=True)

@tree.command(name="rank", description="Check your current level and XP")
async def rank(interaction: discord.Interaction):
    guild = interaction.guild
    member = interaction.user
    level_file = os.path.join("srvlevels", guild.name.replace("/", "_"), "usrlevels", str(member.id), "lvl.json")
    if not os.path.exists(level_file):
        await interaction.response.send_message("❌ You haven't earned any XP yet!", ephemeral=True)
        return
    with open(level_file, "r") as f:
        data = json.load(f)
    xp = data.get("xp", 0)
    level = data.get("level", 1)
    next_xp = (level + 1) ** 2 * 10
    embed = discord.Embed(
        title=f"📊 {member.name}'s Rank",
        description=f"**Level:** {level}\n**XP:** {xp} / {next_xp}",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_message(msg):
    if msg.author.bot or not msg.guild:
        return

    content = msg.content.lower()
    delete_words = get_words_from_folder(msg.guild, "autodelete")
    mute_words = get_automute_words_with_duration(msg.guild)

    for word in delete_words:
        if word in content:
            await msg.delete()
            await msg.channel.send(f"{msg.author.mention}, that word is not allowed.")
            return

    for word, dur in mute_words.items():
        if word in content:
            role = discord.utils.get(msg.guild.roles, name="Muted")
            if not role:
                role = await msg.guild.create_role(name="Muted")
                for channel in msg.guild.channels:
                    await channel.set_permissions(role, send_messages=False)
            await msg.author.add_roles(role)
            mutes[msg.author.id] = datetime.utcnow() + timedelta(seconds=dur)
            save_mod_action(msg.guild, msg.author, None, "automute", f"Used: {word}")
            await msg.delete()
            await msg.channel.send(f"{msg.author.mention}, you have been muted for using a forbidden word.")
            return

    guild = msg.guild
    user = msg.author
    setting_path = os.path.join("srvlevels", guild.name.replace("/", "_"), "setting.json")
    if os.path.exists(setting_path):
        with open(setting_path, "r") as f:
            settings = json.load(f)
        if settings.get("server_leveling_enabled", False):
            user_path = os.path.join("srvlevels", guild.name.replace("/", "_"), "usrlevels", str(user.id))
            os.makedirs(user_path, exist_ok=True)
            level_file = os.path.join(user_path, "lvl.json")
            if os.path.exists(level_file):
                with open(level_file, "r") as f:
                    data = json.load(f)
            else:
                data = {"xp": 0, "level": 1}
            data["xp"] += 15
            new_level = int((data["xp"] / 10) ** 0.5)
            if new_level > data["level"]:
                data["level"] = new_level
                try:
                    await user.send(f"🎉 You leveled up to **Level {new_level}** in **{guild.name}**!")
                except discord.Forbidden:
                    pass
            with open(level_file, "w") as f:
                json.dump(data, f, indent=4)

    await bot.process_commands(msg)

# (previous code remains unchanged)

cooldowns = {}
lvl_cooldowns = {}

@tree.command(name="lvlcooldown", description="Set XP gain cooldown in seconds for this server")
@app_commands.describe(seconds="Cooldown duration in seconds")
@app_commands.checks.has_permissions(administrator=True)
async def lvlcooldown(interaction: discord.Interaction, seconds: int):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
        return

    setting_path = os.path.join("srvlevels", guild.name.replace("/", "_"), "setting.json")
    if not os.path.exists(setting_path):
        await interaction.response.send_message("❌ Server leveling must be enabled first.", ephemeral=True)
        return

    with open(setting_path, "r") as f:
        settings = json.load(f)

    settings["cooldown"] = max(10, min(86400, seconds))  # restrict between 10 sec and 24 hrs

    with open(setting_path, "w") as f:
        json.dump(settings, f, indent=4)

    await interaction.response.send_message(f"⏱️ XP cooldown set to {settings['cooldown']} seconds.", ephemeral=True)

@tree.command(name="dailyxp", description="Claim daily XP based on your current level (requires level 5)")
async def dailyxp(interaction: discord.Interaction):
    guild = interaction.guild
    user = interaction.user
    level_file = os.path.join("srvlevels", guild.name.replace("/", "_"), "usrlevels", str(user.id), "lvl.json")

    if not os.path.exists(level_file):
        await interaction.response.send_message("❌ You haven't earned any XP yet!", ephemeral=True)
        return

    with open(level_file, "r") as f:
        data = json.load(f)

    if data.get("level", 1) < 5:
        await interaction.response.send_message("🔒 You are not yet level 5. Come back when you meet the requirement.", ephemeral=True)
        return

    claim_path = os.path.join("srvlevels", guild.name.replace("/", "_"), "usrlevels", str(user.id), "daily.json")
    now = datetime.utcnow()
    if os.path.exists(claim_path):
        with open(claim_path, "r") as f:
            last_claim = datetime.fromisoformat(json.load(f).get("last", "1970-01-01T00:00:00"))
        if (now - last_claim).total_seconds() < 86400:
            await interaction.response.send_message("🕒 You have already claimed your daily XP today.", ephemeral=True)
            return

    daily_xp = data["level"] * 25
    data["xp"] += daily_xp
    new_level = int((data["xp"] / 10) ** 0.5)
    if new_level > data["level"]:
        data["level"] = new_level
        try:
            await user.send(f"🎉 You leveled up to **Level {new_level}** in **{guild.name}**!")
        except discord.Forbidden:
            pass

    with open(level_file, "w") as f:
        json.dump(data, f, indent=4)
    with open(claim_path, "w") as f:
        json.dump({"last": now.isoformat()}, f)

    await interaction.response.send_message(f"✅ You gained **{daily_xp} XP**!", ephemeral=True)

@tree.command(name="leaderboard", description="Show top 10 users by XP (only on enabled servers)")
async def leaderboard(interaction: discord.Interaction):
    guild = interaction.guild
    settings_path = os.path.join("srvlevels", guild.name.replace("/", "_"), "setting.json")
    if not os.path.exists(settings_path):
        await interaction.response.send_message("❌ This server does not have server leveling enabled.", ephemeral=True)
        return

    with open(settings_path, "r") as f:
        settings = json.load(f)
    if not settings.get("server_leveling_enabled", False):
        await interaction.response.send_message("❌ This server does not have server leveling enabled.", ephemeral=True)
        return

    usr_folder = os.path.join("srvlevels", guild.name.replace("/", "_"), "usrlevels")
    leaderboard = []
    for user_id in os.listdir(usr_folder):
        lvl_path = os.path.join(usr_folder, user_id, "lvl.json")
        if os.path.exists(lvl_path):
            with open(lvl_path, "r") as f:
                data = json.load(f)
            leaderboard.append((int(user_id), data.get("xp", 0)))

    leaderboard.sort(key=lambda x: x[1], reverse=True)
    embed = discord.Embed(title="🏆 Leaderboard (Top 10)", color=discord.Color.blue())
    for rank, (uid, xp) in enumerate(leaderboard[:10], 1):
        member = guild.get_member(uid)
        name = member.name if member else f"User {uid}"
        embed.add_field(name=f"#{rank} {name}", value=f"XP: {xp}", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.event
async def on_message(msg):
    if msg.author.bot or not msg.guild:
        return

    content = msg.content.lower()
    delete_words = get_words_from_folder(msg.guild, "autodelete")
    mute_words = get_automute_words_with_duration(msg.guild)

    for word in delete_words:
        if word in content:
            await msg.delete()
            await msg.channel.send(f"{msg.author.mention}, that word is not allowed.")
            return

    for word, dur in mute_words.items():
        if word in content:
            role = discord.utils.get(msg.guild.roles, name="Muted")
            if not role:
                role = await msg.guild.create_role(name="Muted")
                for channel in msg.guild.channels:
                    await channel.set_permissions(role, send_messages=False)
            await msg.author.add_roles(role)
            mutes[msg.author.id] = datetime.utcnow() + timedelta(seconds=dur)
            save_mod_action(msg.guild, msg.author, None, "automute", f"Used: {word}")
            await msg.delete()
            await msg.channel.send(f"{msg.author.mention}, you have been muted for using a forbidden word.")
            return

    guild = msg.guild
    user = msg.author
    setting_path = os.path.join("srvlevels", guild.name.replace("/", "_"), "setting.json")
    if os.path.exists(setting_path):
        with open(setting_path, "r") as f:
            settings = json.load(f)
        if settings.get("server_leveling_enabled", False):
            now = datetime.utcnow()
            last_time = cooldowns.get(user.id, datetime.min)
            cooldown_seconds = settings.get("cooldown", 60)
            if (now - last_time).total_seconds() < cooldown_seconds:
                return
            cooldowns[user.id] = now

            user_path = os.path.join("srvlevels", guild.name.replace("/", "_"), "usrlevels", str(user.id))
            os.makedirs(user_path, exist_ok=True)
            level_file = os.path.join(user_path, "lvl.json")
            if os.path.exists(level_file):
                with open(level_file, "r") as f:
                    data = json.load(f)
            else:
                data = {"xp": 0, "level": 1}

            data["xp"] += 10
            new_level = int((data["xp"] / 10) ** 0.5)
            if new_level > data["level"]:
                data["level"] = new_level
                try:
                    await user.send(f"🎉 You leveled up to **Level {new_level}** in **{guild.name}**!")
                except discord.Forbidden:
                    pass

            with open(level_file, "w") as f:
                json.dump(data, f, indent=4)

    await bot.process_commands(msg)

bot.run(TOKEN)

