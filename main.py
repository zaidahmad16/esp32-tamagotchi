# BoardPet: runs on the ESP32 at every power-up (MicroPython runs main.py).
# Joins home Wi-Fi, serves the pet page at http://<hostname>.local, keeps the
# pet alive, saves it to flash, and catches up on time spent unplugged.
import asyncio
import json
import os
import time

import machine
import network

import pet

EPOCH_OFFSET = 946684800 if time.gmtime(0)[0] == 2000 else 0  # board epoch -> unix
SAVE_EVERY = 300
STATE = "state.json"

cfg = {"name": "Ember", "hostname": "boardpet", "ssid": "", "password": ""}
try:
    with open("config.json") as f:
        cfg.update(json.load(f))
except Exception as e:
    print("config.json:", e)

led = machine.Pin(2, machine.Pin.OUT, value=0)
button = machine.Pin(0, machine.Pin.IN, machine.Pin.PULL_UP)
wlan = network.WLAN(network.STA_IF)

boot_ms = time.ticks_ms()
clock_ok = False
last_save = 0
last_pat_ms = -60000
message = ""


def now():
    return time.time()


def clock_valid():
    return time.gmtime()[0] >= 2025


def load():
    try:
        with open(STATE) as f:
            return pet.upgrade(json.load(f), cfg["name"])
    except Exception as e:
        print("new pet (", e, ")")
        return pet.new_state(cfg["name"])


s = load()
# Seconds the previous run simulated without a real clock: already inside the
# saved state, so they must not be counted again in the unplugged gap.
prev_unsynced = s["unsynced_s"]
s["unsynced_s"] = 0.0


def save():
    global last_save
    if clock_ok:
        s["last_epoch"] = now()
    try:
        with open(STATE + ".tmp", "w") as f:
            json.dump(s, f)
        os.rename(STATE + ".tmp", STATE)
    except Exception as e:
        print("save failed:", e)
    last_save = time.ticks_ms()


def on_clock():
    """First time the real time is known this boot: age the pet for the time it was unplugged."""
    global clock_ok
    if clock_ok or not clock_valid():
        return
    clock_ok = True
    boot_epoch = now() - time.ticks_diff(time.ticks_ms(), boot_ms) // 1000
    if s["last_epoch"]:
        gap = boot_epoch - s["last_epoch"] - prev_unsynced
        print("unplugged for", gap, "s")
        if gap > 0:
            pet.apply_elapsed(s, gap)
    s["unsynced_s"] = 0.0
    save()


def set_clock_unix(t):
    """Set the RTC from a unix timestamp (seconds)."""
    tm = time.gmtime(int(t) - EPOCH_OFFSET)
    machine.RTC().datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))


# ---------- background tasks ----------

async def wifi_task():
    network.hostname(cfg["hostname"])
    wlan.active(True)
    while True:
        if not wlan.isconnected() and cfg["ssid"]:
            try:
                wlan.connect(cfg["ssid"], cfg["password"])
            except OSError:
                pass
            for _ in range(40):
                if wlan.isconnected():
                    print("wifi up: http://%s.local  (%s)" % (cfg["hostname"], wlan.ifconfig()[0]))
                    break
                await asyncio.sleep_ms(250)
        await asyncio.sleep(10)


async def ntp_task():
    import ntptime
    while True:
        if wlan.isconnected():
            try:
                ntptime.settime()
                print("clock set", time.gmtime())
                on_clock()
                await asyncio.sleep(6 * 3600)
                continue
            except Exception as e:
                print("ntp:", e)
        await asyncio.sleep(30)


async def tick_task():
    last = time.ticks_ms()
    while True:
        await asyncio.sleep(1)
        t = time.ticks_ms()
        dt = time.ticks_diff(t, last) / 1000
        last = t
        pet.apply_elapsed(s, dt)
        if not clock_ok:
            s["unsynced_s"] += dt
        if time.ticks_diff(t, last_save) > SAVE_EVERY * 1000:
            save()


async def led_task():
    while True:
        m = pet.mood(s)
        if m == "sick":
            on, off = 120, 120
        elif pet.needs(s) and m != "sleep":
            on, off = 150, 1850
        else:
            led.value(0)
            await asyncio.sleep_ms(500)
            continue
        led.value(1)
        await asyncio.sleep_ms(on)
        led.value(0)
        await asyncio.sleep_ms(off)


async def button_task():
    global last_pat_ms, message
    prev = 1
    while True:
        v = button.value()
        if prev == 1 and v == 0:
            if time.ticks_diff(time.ticks_ms(), last_pat_ms) > 30000:
                last_pat_ms = time.ticks_ms()
                ok, message = pet.act(s, "pat")
            for _ in range(3):
                led.value(1)
                await asyncio.sleep_ms(60)
                led.value(0)
                await asyncio.sleep_ms(60)
        prev = v
        await asyncio.sleep_ms(40)


# ---------- web server ----------

def parse_query(q):
    out = {}
    for part in q.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v.replace("+", " ")
    return out


def unquote(v):
    b = bytearray()
    i = 0
    while i < len(v):
        c = v[i]
        if c == "%" and i + 3 <= len(v):
            b.append(int(v[i + 1:i + 3], 16))
            i += 3
        else:
            b.extend(c.encode())
            i += 1
    return b.decode()


def state_json():
    d = pet.public(s)
    d["message"] = message
    d["clock_ok"] = clock_ok
    return json.dumps(d)


async def send(w, status, ctype, body, extra=""):
    if isinstance(body, str):
        body = body.encode()
    w.write(("HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
             "Cache-Control: no-store\r\nConnection: close\r\n%s\r\n")
            % (status, ctype, len(body), extra))
    w.write(body)
    await w.drain()


async def send_page(w):
    try:
        size = os.stat("index.html.gz")[6]
    except OSError:
        await send(w, "404 Not Found", "text/plain", "index.html.gz missing")
        return
    w.write("HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
            "Content-Encoding: gzip\r\nContent-Length: %d\r\n"
            "Cache-Control: no-cache\r\nConnection: close\r\n\r\n" % size)
    buf = bytearray(1024)
    with open("index.html.gz", "rb") as f:
        while True:
            n = f.readinto(buf)
            if not n:
                break
            w.write(buf[:n])
            await w.drain()


async def handle(r, w):
    global message
    try:
        line = await asyncio.wait_for(r.readline(), 5)
        while True:
            h = await asyncio.wait_for(r.readline(), 5)
            if not h or h == b"\r\n":
                break
        parts = line.decode().split()
        if len(parts) < 2:
            return
        path, _, q = parts[1].partition("?")
        q = parse_query(q)
        if path == "/":
            await send_page(w)
        elif path == "/api/state":
            await send(w, "200 OK", "application/json", state_json())
        elif path == "/api/act":
            ok, message = pet.act(s, q.get("a", ""), q.get("won", 0))
            if ok:
                save()
            await send(w, "200 OK", "application/json", state_json())
        elif path == "/api/sync":
            # Fallback clock: the page's time, only used if NTP hasn't worked.
            if not clock_ok:
                try:
                    set_clock_unix(int(q.get("t", "0")) // 1000)
                    on_clock()
                except Exception as e:
                    print("sync:", e)
            await send(w, "200 OK", "application/json", state_json())
        elif path == "/api/rename":
            name = unquote(q.get("name", "")).strip()[:16]
            if name:
                s["name"] = name
                message = "Renamed to " + name + "."
                save()
            await send(w, "200 OK", "application/json", state_json())
        elif path == "/api/new_egg":
            if q.get("confirm") == "yes":
                name = s["name"]
                s.clear()
                s.update(pet.new_state(name))
                message = "A new egg appeared."
                save()
            await send(w, "200 OK", "application/json", state_json())
        else:
            await send(w, "404 Not Found", "text/plain", "not found")
    except Exception as e:
        print("http:", e)
    finally:
        try:
            w.close()
            await w.wait_closed()
        except Exception:
            pass


async def main():
    print("BoardPet starting:", s["name"], pet.stage(s))
    if clock_valid():  # RTC survives soft resets
        on_clock()
    await asyncio.start_server(handle, "0.0.0.0", 80, backlog=4)
    for t in (wifi_task, ntp_task, tick_task, led_task, button_task):
        asyncio.create_task(t())
    while True:
        await asyncio.sleep(3600)


try:
    asyncio.run(main())
except KeyboardInterrupt:
    save()
    print("stopped (KeyboardInterrupt)")
except Exception as e:
    # Anything unexpected: save the pet and reboot back into it.
    print("crash:", e)
    save()
    time.sleep(2)
    machine.reset()
