import discord
from discord.ext import commands, tasks
import aiohttp
import os
from datetime import datetime, timedelta  

# =======================
# BEÁLLÍTÁSOK
# =======================

TOKEN = os.getenv("TOKEN")

API_BASE = "https://pan-kruger-brooks-trigger.trycloudflare.com"

STOP_API = f"{API_BASE}/stop?stopId={{stop_id}}"
VEHICLE_API = f"{API_BASE}/vehicle?route={{route}}&id={{dep_id}}"
trip_cache = {}  # dep_id -> {"line":..., "vehicle":..., "dest":..., "first_seen":...}

LOG_DIR = os.getenv("LOG_DIR", "/data/logs")
CACHE_FILE = os.path.join(LOG_DIR, "cache.txt")
FLUSH_INTERVAL = 600  # 10 perc
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = "vehhist.txt"
REFRESH_INTERVAL = 180  # 3 perc


WATCH_STOPS = {
    "166","289","346","391","725","792","1008","1112","1247","1333",
    "1346","1800","1935","1994","2185","2225","2228","2360","2391",
    "2432","2502","2503","2544","2549","2587","2588","2900","2901",
    "2902","1989"
}

TRAM_LINES = {"1", "1A", "1-2", "2","3", "X3", "3F","4", "X4"}

# =======================
# DISCORD INIT
# =======================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

# =======================
# SEGÉDFÜGGVÉNYEK
# =======================
from typing import Dict

trip_cache: Dict[str, Dict[str, str]] = {}

async def fetch_json(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status != 200:
                return None
            return await r.json()
    except:
        return None

def save_cache_txt():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        for dep_id, d in trip_cache.items():
            f.write(f"{dep_id}|{d['line']}|{d['vehicle']}|{d['dest']}|{d['first_seen']}\n")

def load_cache_txt():
    if not os.path.exists(LOG_FILE):
        return
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                dep_id, line_no, vehicle, dest, ts = line.strip().split("|")
                trip_cache[dep_id] = {
                    "line": line_no,
                    "vehicle": vehicle,
                    "dest": dest,
                    "first_seen": ts
                }
            except:
                continue

async def update_cache():
    async with aiohttp.ClientSession() as session:
        for stop_id in WATCH_STOPS:
            stop_data = await fetch_json(session, STOP_API.format(stop_id=stop_id))
            if not isinstance(stop_data, list):
                continue
            for dep in stop_data:
                dep_id = str(dep.get("id"))
                line = str(dep.get("line"))
                dest = dep.get("dest", "Ismeretlen")
                if line not in TRAM_LINES or not dep_id:
                    continue

                veh = await fetch_json(session, VEHICLE_API.format(route=line, dep_id=dep_id))
                if not veh or not isinstance(veh, list) or not veh:
                    continue
                vehicle = veh[-1].get("VehicleRegistrationNumber")
                if not vehicle:
                    continue

                if dep_id not in trip_cache:
                    trip_cache[dep_id] = {
                        "line": line,
                        "vehicle": vehicle,
                        "dest": dest,
                        "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
    save_cache_txt()

# --- AUTOMATIKUS FRISSÍTŐ LOOP ---
@tasks.loop(seconds=REFRESH_INTERVAL)
async def refresh_loop():
    await update_cache()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Cache frissítve.")

# --- PARANCSOK TXT-HELYRŐL ---
@bot.command(name="trip")
async def vehhist(ctx, dep_id: str):
    d = trip_cache.get(dep_id)
    if not d:
        return await ctx.send("❌ Nincs ilyen járat a cache-ben.")
    await ctx.send(
        f"📄 **{dep_id}**\n"
        f"Vonal: {d['line']}\n"
        f"Jármű: {d['vehicle']}\n"
        f"Cél: {d['dest']}\n"
        f"Első észlelés: {d['first_seen']}"
    )

def load_cache():
    if not os.path.exists(CACHE_FILE):
        return

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                dep_id, line_no, vehicle, dest, ts = line.strip().split("|")
                trip_cache[dep_id] = {
                    "line": line_no,
                    "vehicle": vehicle,
                    "dest": dest,
                    "first_seen": ts
                }
            except:
                continue

def cache_trip(dep_id, line, vehicle, dest):
    if dep_id not in trip_cache:
        trip_cache[dep_id] = {
            "line": line,
            "vehicle": vehicle,
            "dest": dest,
            "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }


@tasks.loop(seconds=FLUSH_INTERVAL)
async def flush_cache():
    tmp = CACHE_FILE + ".tmp"

    with open(tmp, "w", encoding="utf-8") as f:
        for dep_id, d in trip_cache.items():
            f.write(
                f"{dep_id}|{d['line']}|{d['vehicle']}|{d['dest']}|{d['first_seen']}\n"
            )

    os.replace(tmp, CACHE_FILE)


@bot.command()
async def cacheinfo(ctx, trip_id: str):
    d = trip_cache.get(trip_id)
    if not d:
        return await ctx.send("❌ Nincs ilyen járat a cache-ben.")

    await ctx.send(
        f"📄 **{trip_id}**\n"
        f"Vonal: {d['line']}\n"
        f"Jármű: {d['vehicle']}\n"
        f"Cél: {d['dest']}\n"
        f"Első észlelés: {d['first_seen']}"
    )



def ensure_dirs():
    os.makedirs("logs", exist_ok=True)
    os.makedirs("logs/veh", exist_ok=True)

def is_t6(reg):
    if not isinstance(reg, str):
        return False
    if not reg.startswith("V"):
        return False
    if not reg[1:].isdigit():
        return False
    return 900 <= int(reg[1:]) <= 953 

def is_kt4(reg):
    if not isinstance(reg, str):
        return False
    if not reg.startswith("V"):
        return False
    if not reg[1:].isdigit():
        return False
    return 200 <= int(reg[1:]) <= 217 

def is_tatra(reg):
    if not isinstance(reg, str):
        return False
    if not reg.startswith("V"):
        return False
    if reg[1:].isdigit():
        n = int(reg[1:])
        if 200 <= n <= 953:
            return True

def is_pesa(reg):
    if not isinstance(reg, str):
        return False
    if not reg.startswith("V"):
        return False
    if not reg[1:].isdigit():
        return False
    n = int(reg[1:])
    return 100 <= n <= 107

async def fetch_json(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status != 200:
                return None
            return await r.json()
    except:
        return None

def get_last_vehicle_reg(veh):
    if not isinstance(veh, list) or not veh:
        return None
    last = veh[-1]
    if not isinstance(last, dict):
        return None
    return last.get("VehicleRegistrationNumber")

def save_trip(dep_id, line, vehicle, dest):
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
                f"Cél: {dest}\n"
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
            f.write(f"{ts} - ID {dep_id} - Vonal {line} - {dest}\n")

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
        for stop_id in WATCH_STOPS:
            stop_data = await fetch_json(session, STOP_API.format(stop_id=stop_id))
            if not isinstance(stop_data, list):
                continue

            for dep in stop_data:
                line = str(dep.get("line"))
                if line not in TRAM_LINES:
                    continue

                dep_id = dep.get("id")
                if not dep_id:
                    continue

                dest = dep.get("dest", "Ismeretlen")

                veh = await fetch_json(
                    session,
                    VEHICLE_API.format(route=line, dep_id=dep_id)
                )

                reg = get_last_vehicle_reg(veh)
                if not reg:
                    continue

                save_trip(dep_id, line, reg, dest)

# =======================
# PARANCSOK – MIND
# =======================

@bot.command()
async def allvillamos(ctx):
    active = {}
    async with aiohttp.ClientSession() as session:
        for stop_id in WATCH_STOPS:
            stop_data = await fetch_json(session, STOP_API.format(stop_id=stop_id))
            if not isinstance(stop_data, list):
                continue

            for dep in stop_data:
                line = str(dep.get("line"))
                if line not in TRAM_LINES:
                    continue

                dep_id = dep.get("id")
                dep_time = dep.get("departure", 0)
                dest = dep.get("dest", "Ismeretlen")

                veh = await fetch_json(session, VEHICLE_API.format(route=line, dep_id=dep_id))
                reg = get_last_vehicle_reg(veh)
                if not reg:
                    continue

                if reg not in active or dep_time < active[reg]["dep"]:
                    active[reg] = {"line": line, "dest": dest, "stop": stop_id, "dep": dep_time}

    if not active:
        return await ctx.send("🚫 Jelenleg nincs aktív villamos.")

    embed = discord.Embed(title="🚊 Aktív villamosok", color=0xffff00)
    for reg, i in active.items():
        embed.add_field(name=reg, value=f"Vonal: {i['line']}\nCél: {i['dest']}\nMegálló: {i['stop']}", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def alltatra(ctx):
    active = {}
    async with aiohttp.ClientSession() as session:
        for stop_id in WATCH_STOPS:
            stop_data = await fetch_json(session, STOP_API.format(stop_id=stop_id))
            if not isinstance(stop_data, list):
                continue

            for dep in stop_data:
                line = str(dep.get("line"))
                if line not in TRAM_LINES:
                    continue

                dep_id = dep.get("id")
                dep_time = dep.get("departure", 0)
                dest = dep.get("dest", "Ismeretlen")

                veh = await fetch_json(session, VEHICLE_API.format(route=line, dep_id=dep_id))
                reg = get_last_vehicle_reg(veh)
                if not reg or not is_tatra(reg):
                    continue

                if reg not in active or dep_time < active[reg]["dep"]:
                    active[reg] = {"line": line, "dest": dest, "stop": stop_id, "dep": dep_time}

    if not active:
        return await ctx.send("🚫 Nincs aktív Tatra villamos.")

    embed = discord.Embed(title="🚎 Aktív Tatra villamosok", color=0xffff00)
    for reg, i in active.items():
        embed.add_field(name=reg, value=f"Vonal: {i['line']}\nCél: {i['dest']}\nMegálló: {i['stop']}", inline=False)
    await ctx.send(embed=embed)
    
@bot.command()
async def allpesa(ctx):
    active = {}
    async with aiohttp.ClientSession() as session:
        for stop_id in WATCH_STOPS:
            stop_data = await fetch_json(session, STOP_API.format(stop_id=stop_id))
            if not isinstance(stop_data, list):
                continue

            for dep in stop_data:
                line = str(dep.get("line"))
                if line not in TRAM_LINES:
                    continue

                dep_id = dep.get("id")
                dep_time = dep.get("departure", 0)
                dest = dep.get("dest", "Ismeretlen")

                veh = await fetch_json(session, VEHICLE_API.format(route=line, dep_id=dep_id))
                reg = get_last_vehicle_reg(veh)
                if not reg or not is_pesa(reg):
                    continue

                if reg not in active or dep_time < active[reg]["dep"]:
                    active[reg] = {"line": line, "dest": dest, "stop": stop_id, "dep": dep_time}

    if not active:
        return await ctx.send("🚫 Nincs aktív PESA villamos.")

    embed = discord.Embed(title="🚋 Aktív PESA villamosok", color=0xffff00)
    for reg, i in active.items():
        embed.add_field(name=reg, value=f"Vonal: {i['line']}\nCél: {i['dest']}\nMegálló: {i['stop']}", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def vehhist(ctx, vehicle: str, date: str = None):
    day = resolve_date(date)
    veh_file = f"logs/veh/{vehicle}.txt"

    if not os.path.exists(veh_file):
        return await ctx.send("❌ Nincs ilyen jármű a naplóban.")

    # --- beolvasás ---
    entries = []
    with open(veh_file, "r", encoding="utf-8") as f:
        for l in f:
            if not l.startswith(day):
                continue
            try:
                ts, rest = l.strip().split(" - ", 1)
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                trip_id = rest.split("ID ")[1].split(" ")[0]
                line = rest.split("Vonal ")[1].split(" ")[0]
                dest = rest.split(" - ")[-1]
                entries.append((dt, line, trip_id, dest))
            except:
                continue

    if not entries:
        return await ctx.send(f"❌ {vehicle} nem közlekedett ezen a napon ({day}).")

    # --- időrend ---
    entries.sort(key=lambda x: x[0])

    # --- menetek összevonása ---
    runs = []
    current = None

    for dt, line, trip_id, dest in entries:
        if (
            not current
            or trip_id != current["trip_id"]
            or line != current["line"]
        ):
            if current:
                runs.append(current)
            current = {
                "line": line,
                "trip_id": trip_id,
                "start": dt,
                "end": dt,
                "dest": dest
            }
        else:
            current["end"] = dt

    if current:
        runs.append(current)

    # --- KIÍRÁS (FÉLKÖVÉR!) ---
    lines = [f"🚎 *{vehicle} – vehhist ({day})*"]

    for r in runs:
        lines.append(
            f"*{r['start'].strftime('%H:%M')}* – "
            f"*{r['line']} / {r['trip_id']}* – "
            f"{r['dest']}"
        )

    msg = "\n".join(lines)

    # Discord limit
    for i in range(0, len(msg), 1900):
        await ctx.send(msg[i:i+1900])

@bot.command()
async def jaratinfo(ctx, trip_id: str, date: str = None):
    day = resolve_date(date)
    trip_path = f"logs/{day}/{trip_id}.txt"

    if os.path.exists(trip_path):
        with open(trip_path, "r", encoding="utf-8") as f:
            txt = f.read()
        return await ctx.send(f"📄 **Járat {trip_id} – {day}**\n```{txt[:1800]}```")

    found = []
    veh_dir = "logs/veh"
    for fname in os.listdir(veh_dir):
        path = os.path.join(veh_dir, fname)
        if not path.endswith(".txt"):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(day) and f"ID {trip_id} " in line:
                    found.append((fname.replace(".txt",""), line.strip()))

    if not found:
        return await ctx.send(f"❌ Nincs adat erre a járatra ezen a napon ({day}).")

    out = [f"📄 *Járat {trip_id} – {day}*"]
    for veh, l in found:
        out.append(f"{veh}: {l}")

    msg = "\n".join(out)
    for i in range(0, len(msg), 1900):
        await ctx.send(msg[i:i+1900])

@bot.command()
async def allt6today(ctx, date: str = None):
    day = resolve_date(date)
    veh_dir = "logs/veh"
    skodas = {}

    for fname in os.listdir(veh_dir):
        if not fname.endswith(".txt"):
            continue
        reg = fname.replace(".txt","")
        if not is_t6(reg):
            continue

        with open(os.path.join(veh_dir, fname), "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(day):
                    ts = line.split(" - ")[0]
                    trip_id = line.split("ID ")[1].split(" ")[0]
                    line_no = line.split("Vonal ")[1].split(" ")[0]
                    skodas.setdefault(reg, []).append((ts, line_no, trip_id))

    if not skodas:
        return await ctx.send(f"🚫 {day} napon nem közlekedett Tatra T6.")

    out = [f"🚊 *Tatra T6 – forgalomban ({day})*"]
    for reg in sorted(skodas):
        first = min(skodas[reg], key=lambda x: x[0])
        last = max(skodas[reg], key=lambda x: x[0])
        out.append(f"*{reg}* — {first[0][11:16]} → {last[0][11:16]} (vonal {first[1]})")

    msg = "\n".join(out)
    for i in range(0, len(msg), 1900):
        await ctx.send(msg[i:i+1900])

@bot.command()
async def allkt4today(ctx, date: str = None):
    day = resolve_date(date)
    veh_dir = "logs/veh"
    skodas = {}

    for fname in os.listdir(veh_dir):
        if not fname.endswith(".txt"):
            continue
        reg = fname.replace(".txt","")
        if not is_kt4(reg):
            continue

        with open(os.path.join(veh_dir, fname), "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(day):
                    ts = line.split(" - ")[0]
                    trip_id = line.split("ID ")[1].split(" ")[0]
                    line_no = line.split("Vonal ")[1].split(" ")[0]
                    skodas.setdefault(reg, []).append((ts, line_no, trip_id))

    if not skodas:
        return await ctx.send(f"🚫 {day} napon nem közlekedett Tatra KT4.")

    out = [f"🚊 *Tatra KT4 – forgalomban ({day})*"]
    for reg in sorted(skodas):
        first = min(skodas[reg], key=lambda x: x[0])
        last = max(skodas[reg], key=lambda x: x[0])
        out.append(f"*{reg}* — {first[0][11:16]} → {last[0][11:16]} (vonal {first[1]})")

    msg = "\n".join(out)
    for i in range(0, len(msg), 1900):
        await ctx.send(msg[i:i+1900])

@bot.command()
async def allpesatoday(ctx, date: str = None):
    day = resolve_date(date)
    veh_dir = "logs/veh"
    skodas = {}

    for fname in os.listdir(veh_dir):
        if not fname.endswith(".txt"):
            continue
        reg = fname.replace(".txt","")
        if not is_pesa(reg):
            continue

        with open(os.path.join(veh_dir, fname), "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(day):
                    ts = line.split(" - ")[0]
                    trip_id = line.split("ID ")[1].split(" ")[0]
                    line_no = line.split("Vonal ")[1].split(" ")[0]
                    skodas.setdefault(reg, []).append((ts, line_no, trip_id))

    if not skodas:
        return await ctx.send(f"🚫 {day} napon nem közlekedett Pesa.")

    out = [f"🚊 *Pesa – forgalomban ({day})*"]
    for reg in sorted(skodas):
        first = min(skodas[reg], key=lambda x: x[0])
        last = max(skodas[reg], key=lambda x: x[0])
        out.append(f"*{reg}* — {first[0][11:16]} → {last[0][11:16]} (vonal {first[1]})")

    msg = "\n".join(out)
    for i in range(0, len(msg), 1900):
        await ctx.send(msg[i:i+1900])        

@bot.command()
async def alltatratoday(ctx, date: str = None):
    day = resolve_date(date)
    veh_dir = "logs/veh"
    skodas = {}

    for fname in os.listdir(veh_dir):
        if not fname.endswith(".txt"):
            continue
        reg = fname.replace(".txt","")
        if not is_t6(reg)  and not is_kt4(reg):
            continue

        with open(os.path.join(veh_dir, fname), "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(day):
                    ts = line.split(" - ")[0]
                    trip_id = line.split("ID ")[1].split(" ")[0]
                    line_no = line.split("Vonal ")[1].split(" ")[0]
                    skodas.setdefault(reg, []).append((ts, line_no, trip_id))

    if not skodas:
        return await ctx.send(f"🚫 {day} napon nem közlekedett Tatra.")

    out = [f"🚊 *Tatra – forgalomban ({day})*"]
    for reg in sorted(skodas):
        first = min(skodas[reg], key=lambda x: x[0])
        last = max(skodas[reg], key=lambda x: x[0])
        out.append(f"*{reg}* — {first[0][11:16]} → {last[0][11:16]} (vonal {first[1]})")

    msg = "\n".join(out)
    for i in range(0, len(msg), 1900):
        await ctx.send(msg[i:i+1900])        

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
        return  # már lefutott
    bot.ready_done = True

    print(f"Bejelentkezve mint {bot.user}")
    load_cache_txt()       # meglévő logok betöltése
    await update_cache()   # egyszeri frissítés induláskor
    refresh_loop.start()   # 3 percenkénti frissítés


bot.run(TOKEN)








