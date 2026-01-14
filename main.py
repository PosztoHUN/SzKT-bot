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

WATCH_STOPS = {
    "166","289","346","391","725","792","1008","1112","1247","1333",
    "1346","1800","1935","1994","2185","2225","2228","2360","2391",
    "2432","2502","2503","2544","2549","2587","2588","2900","2901",
    "2902","1989"
}

TRAM_LINES = {"1", "1A", "1-2", "2","3", "X3", "3F","4", "X4"}

LOG_FILE = os.path.join(os.path.dirname(__file__), "bot_log.txt")

# =======================
# DISCORD INIT
# =======================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

# =======================
# SEGÉDFÜGGVÉNYEK
# =======================

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
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts} - ID {dep_id} - Vonal {line} - Jarmu {vehicle} - {dest}\n")

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
    if not os.path.exists(LOG_FILE):
        return await ctx.send("❌ Nincs log fájl.")

    entries = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for l in f:
            if not l.startswith(day) or f"Jarmu {vehicle} " not in l:
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

    entries.sort(key=lambda x: x[0])

    runs = []
    current = None
    for dt, line, trip_id, dest in entries:
        if not current or trip_id != current["trip_id"] or line != current["line"]:
            if current:
                runs.append(current)
            current = {"line": line, "trip_id": trip_id, "start": dt, "end": dt, "dest": dest}
        else:
            current["end"] = dt
    if current:
        runs.append(current)

    lines = [f"🚎 *{vehicle} – vehhist ({day})*"]
    for r in runs:
        lines.append(f"*{r['start'].strftime('%H:%M')}* – *{r['line']} / {r['trip_id']}* – {r['dest']}")
    msg = "\n".join(lines)
    for i in range(0, len(msg), 1900):
        await ctx.send(msg[i:i+1900])

@bot.command()
async def jaratinfo(ctx, trip_id: str, date: str = None):
    day = resolve_date(date)
    if not os.path.exists(LOG_FILE):
        return await ctx.send("❌ Nincs log fájl.")

    found = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for l in f:
            if l.startswith(day) and f"ID {trip_id} " in l:
                parts = l.strip().split(" - ")
                vehicle = parts[3].split(" ")[1] if len(parts) > 3 else "Ismeretlen"
                found.append((vehicle, l.strip()))

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
    if not os.path.exists(LOG_FILE):
        return await ctx.send("❌ Nincs log fájl.")

    skodas = {}
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for l in f:
            if not l.startswith(day):
                continue
            try:
                parts = l.strip().split(" - ")
                vehicle = parts[3].split(" ")[1]
                if not is_t6(vehicle):
                    continue
                ts = parts[0]
                trip_id = parts[1].split(" ")[1]
                line_no = parts[2].split(" ")[1]
                skodas.setdefault(vehicle, []).append((ts, line_no, trip_id))
            except:
                continue

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
    if not os.path.exists(LOG_FILE):
        return await ctx.send("❌ Nincs log fájl.")

    skodas = {}
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for l in f:
            if not l.startswith(day):
                continue
            try:
                parts = l.strip().split(" - ")
                vehicle = parts[3].split(" ")[1]
                if not is_kt4(vehicle):
                    continue
                ts = parts[0]
                trip_id = parts[1].split(" ")[1]
                line_no = parts[2].split(" ")[1]
                skodas.setdefault(vehicle, []).append((ts, line_no, trip_id))
            except:
                continue

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
    if not os.path.exists(LOG_FILE):
        return await ctx.send("❌ Nincs log fájl.")

    skodas = {}
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for l in f:
            if not l.startswith(day):
                continue
            try:
                parts = l.strip().split(" - ")
                vehicle = parts[3].split(" ")[1]
                if not is_pesa(vehicle):
                    continue
                ts = parts[0]
                trip_id = parts[1].split(" ")[1]
                line_no = parts[2].split(" ")[1]
                skodas.setdefault(vehicle, []).append((ts, line_no, trip_id))
            except:
                continue

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
    if not os.path.exists(LOG_FILE):
        return await ctx.send("❌ Nincs log fájl.")

    skodas = {}
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for l in f:
            if not l.startswith(day):
                continue
            try:
                parts = l.strip().split(" - ")
                vehicle = parts[3].split(" ")[1]
                if not is_t6(vehicle) and not is_kt4(vehicle):
                    continue
                ts = parts[0]
                trip_id = parts[1].split(" ")[1]
                line_no = parts[2].split(" ")[1]
                skodas.setdefault(vehicle, []).append((ts, line_no, trip_id))
            except:
                continue

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
    if not os.path.exists(LOG_FILE):
        return await ctx.send("❌ Nincs log fájl.")

    last = None
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for l in f:
            if f"Jarmu {vehicle} " in l:
                last = l.strip()
    if not last:
        return await ctx.send(f"❌ Nincs adat a(z) {vehicle} járműről.")
    await ctx.send(f"🚊 **{vehicle} utolsó menete**\n```{last}```")
    

# =======================
# START
# =======================

@bot.event
async def on_ready():
    print(f"Bejelentkezve mint {bot.user}")
    logger_loop.start()

bot.run(TOKEN)


