# BoardPet

A Tamagotchi-style pet dragon that lives on a bare ESP32: no extra parts. The board keeps the pet alive, saves it to flash, and serves its "LCD screen" as a web page on your home Wi-Fi.

Open **http://boardpet.local** on any device on the same network.

## How it works
- **Starts by itself.** MicroPython runs `main.py` on every power-up, so plug it into any USB power and the pet comes back.
- **Time keeps passing while it's unplugged.** On boot it gets the real time from the internet (NTP) and ages the pet for the time it was off, up to 7 days. If NTP fails, the page sends your laptop's clock instead.
- **Stats** (0–100): Full, Happy, Energy and Clean. Hunger empties in about 8 h and happiness in about 10 h, and it poops every 3 h or so. Asleep, everything drains 4× slower and energy refills.
- **Sick, never dead.** It gets sick if a stat sits at 0 for an hour or 3 poops pile up. Medicine fixes it.
- **Grows up:** egg (5 min) → hatchling (1 day) → young dragon (3 days) → adult with wings.
- **Play** is a 5-round "which way will it look?" game. More right answers means more happiness.
- **On the board:** the blue LED (GPIO2, on most dev boards) blinks slowly when it needs care and fast when it's sick. Pressing **BOOT** pats it (every 30 s at most).

## Files
| File | What |
|---|---|
| `pet.py` | Pet rules. Pure Python, runs on the board and on the desktop |
| `main.py` | Board app: Wi-Fi, NTP, web server, saving, LED, button |
| `index.html` | The page (gzipped onto the board by `deploy.sh`) |
| `config.json` | Name, hostname, Wi-Fi details (gitignored; see `config.example.json`) |
| `tests/test_pet.py` | `python3 tests/test_pet.py` |
| `tools/mock_server.py` | Run the page on the desktop with a fake board: `python3 tools/mock_server.py 8765 --hatched [--speed 600]` |

## Deploy
```
./deploy.sh            # tests, gzips the page, copies to /dev/ttyUSB0, restarts
```
The board needs MicroPython (v1.29 used). The ESP32 only supports **2.4 GHz** Wi-Fi.

Serial log (IP address, unplugged time): `mpremote connect /dev/ttyUSB0 repl`, then Ctrl+D to restart and watch.

## Undo: back to the original firmware
```
python3 -m esptool --port /dev/ttyUSB0 write-flash 0 ../esp32-backup/at-firmware-2.4.0-backup.bin
```
