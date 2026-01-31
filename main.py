import discord
from discord.ext import commands, tasks
import aiohttp
import os
import sys
from datetime import datetime, timedelta

# =======================
# BEÁLLÍTÁSOK
# =======================

TOKEN = os.getenv("TOKEN")

API_BASE = "https://szkt-trolleybus-realtime.hu/api/vehicles"
VEHICLE_API = API_BASE

TRAM_LINES = {"1", "1A", "1-2", "2", "X2", "3", "X3", "3F", "4", "X4"}

LOCK_FILE = "/tmp/discord_bot.lock"

if os.path.exists(LOCK_FILE):
    print("A bot már fut, kilépés.")
    sys.exit(0)

with open(LOCK_FILE, "w") as f:
    f.write(str(os.getpid()))

# =======================
# DISCORD INIT
# =======================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

# =======================
# SEGÉDFÜGGVÉNYEK
# =======================

def ensure_dirs():
    os.makedirs("logs", exist_ok=True)
    os.makedirs("logs/veh", exist_ok=True)

NOSZTALGIA = {"V313", "V314", "V313-V314", "V813"}

def is_nos(reg):
    return reg in NOSZTALGIA

def is_t6(reg):
    return reg.startswith("V") and reg[1:].isdigit() and 900 <= int(reg[1:]) <= 953

def is_kt4(reg):
    return reg.startswith("V") and reg[1:].isdigit() and 200 <= int(reg[1:]) <= 217

def is_tatra(reg):
    return is_t6(reg) or is_kt4(reg)

def is_pesa(reg):
    return reg.startswith("V") and reg[1:].isdigit() and 100 <= int(reg[1:]) <= 107

async def fetch_json(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status != 200:
                return None
            return await r.json()
    except:
        return None

def save_trip(dep_id, line, vehicle, stop):
    ensure_dirs()
    today = datetime.now().strftime("%Y-%m-%d")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    trip_dir = f"logs/{today}"
    os.makedirs(trip_dir, exist_ok=True)

    trip_file = f"{trip_dir}/{dep_id}.txt"
    if not os.path.exists(trip_file):
        with open(trip_file, "w", encoding="utf-8") as f:
            f.write(
                f"Dátum: {today}\n"
                f"ID: {dep_id}\n"
                f"Vonal: {line}\n"
                f"Utolsó megálló: {stop}\n"
                f"Jármű: {vehicle}\n"
                f"Első észlelés: {ts}\n"
            )

    veh_file = f"logs/veh/{vehicle}.txt"
    last_id = None

    if os.path.exists(veh_file):
        with open(veh_file, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
            if lines and "ID " in lines[-1]:
                last_id = lines[-1].split("ID ")[1].split(" ")[0]

    if last_id != dep_id:
        with open(veh_file, "a", encoding="utf-8") as f:
            f.write(f"{ts} - ID {dep_id} - Vonal {line} - {stop}\n")

def resolve_date(date_arg):
    today = datetime.now().date()
    if date_arg is None:
        return today.strftime("%Y-%m-%d")
    if date_arg.endswith("d"):
        d = int(date_arg[:-1])
        return (today - timedelta(days=d)).strftime("%Y-%m-%d")
    return date_arg

# =======================
# LOGGER LOOP
# =======================

@tasks.loop(seconds=30)
async def logger_loop():
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, VEHICLE_API)
        if not isinstance(data, list):
            return

        for v in data:
            line = str(v.get("lineCode"))
            if line not in TRAM_LINES:
                continue

            reg = v.get("VehicleRegistrationNumber")
            if not reg:
                continue

            dep_id = v.get("id")
            stop = v.get("StopAreaName", "Ismeretlen")

            save_trip(dep_id, line, reg, stop)

# =======================
# PARANCSOK
# =======================

@bot.command()
async def szktvillamos(ctx):
    active = {}

    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, VEHICLE_API)
        if not isinstance(data, list):
            return await ctx.send("❌ Nincs adat.")

        for v in data:
            line = str(v.get("lineCode"))
            if line not in TRAM_LINES:
                continue

            reg = v.get("VehicleRegistrationNumber")
            if not reg:
                continue

            active[reg] = {
                "line": line,
                "stop": v.get("StopAreaName", "Ismeretlen"),
                "delay": v.get("Delay", 0)
            }

    if not active:
        return await ctx.send("🚫 Jelenleg nincs aktív villamos.")

    embed = discord.Embed(title="🚊 Aktív villamosok", color=0xffff00)
    for reg, i in active.items():
        embed.add_field(
            name=reg,
            value=f"Vonal: {i['line']}\nMegálló: {i['stop']}\nKésés: {i['delay']} mp",
            inline=False
        )

    await ctx.send(embed=embed)

@bot.command()
async def szkttatra(ctx):
    await vehicle_filter_cmd(ctx, is_tatra, "🚎 Aktív Tatra villamosok")

@bot.command()
async def szktpesa(ctx):
    await vehicle_filter_cmd(ctx, is_pesa, "🚋 Aktív PESA villamosok")

@bot.command()
async def szktnosztalgia(ctx):
    await vehicle_filter_cmd(ctx, is_nos, "🚋 Aktív nosztalgia villamosok")

async def vehicle_filter_cmd(ctx, check_fn, title):
    active = {}

    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, VEHICLE_API)
        if not isinstance(data, list):
            return await ctx.send("❌ Nincs adat.")

        for v in data:
            reg = v.get("VehicleRegistrationNumber")
            if not reg or not check_fn(reg):
                continue

            line = str(v.get("lineCode"))
            if line not in TRAM_LINES:
                continue

            active[reg] = {
                "line": line,
                "stop": v.get("StopAreaName", "Ismeretlen"),
                "delay": v.get("Delay", 0)
            }

    if not active:
        return await ctx.send("🚫 Nincs ilyen aktív jármű.")

    embed = discord.Embed(title=title, color=0xffff00)
    for reg, i in active.items():
        embed.add_field(
            name=reg,
            value=f"Vonal: {i['line']}\nMegálló: {i['stop']}\nKésés: {i['delay']} mp",
            inline=False
        )

    await ctx.send(embed=embed)

@bot.command()
async def vehicleinfo(ctx, vehicle: str):
    path = f"logs/veh/{vehicle}.txt"
    if not os.path.exists(path):
        return await ctx.send(f"❌ Nincs adat a(z) {vehicle} járműről.")

    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    last = lines[-1]
    await ctx.send(f"🚊 **{vehicle} utolsó menete**\n```{last}```")

# =======================
# START
# =======================

@bot.event
async def on_ready():
    if getattr(bot, "ready_done", False):
        return
    bot.ready_done = True

    ensure_dirs()
    print(f"Bejelentkezve mint {bot.user}")
    logger_loop.start()

bot.run(TOKEN)
