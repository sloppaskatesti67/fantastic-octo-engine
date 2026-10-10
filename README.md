# 🐙 fantastic-octo-engine

A desktop pet powered by a game character. Load a character from game save and asset files, and watch it wander around your desktop.

> **Note:** Items marked _(check)_ were inferred from file names. Adjust them to match what the code actually does.

## ✨ Features

- 🖥️ **Desktop companion**: a pet that lives on top of your desktop (`pet.py`, `desktop.py`)
- 🧍 **Character loading**: build the pet's appearance from character data (`character.py`)
- 📦 **Player file dumping**: inspect and export `.plr` player files (`plr_dump.py`)
- 🎨 **XNB asset support**: read XNB game asset files (`xnb.py`)
- 🔀 **Icon toggling**: show or hide desktop icons (`toggle_icons.py`)
- 🚀 **One-click launch** on Windows (`run_pet.bat`)

## 📁 Project Structure

| File | Purpose |
| --- | --- |
| `pet.py` | Main desktop pet logic _(check)_ |
| `desktop.py` | Desktop and window interaction _(check)_ |
| `character.py` | Character data and rendering _(check)_ |
| `plr_dump.py` | Dumps the contents of `.plr` player files |
| `xnb.py` | XNB asset reader |
| `toggle_icons.py` | Toggles desktop icon visibility |
| `run_pet.bat` | Windows launcher |
| `MODLOG.md` | Log of modifications and changes |

## 🔧 Requirements

- Windows _(the `.bat` launcher and desktop-icon toggling suggest this)_
- Python 3.9+
- Any dependencies imported by the scripts. If you add a `requirements.txt`, install them with:

```bash
pip install -r requirements.txt
```

## 🚀 Getting Started

```bash
# Clone the repository
git clone https://github.com/sloppaskatesti67/fantastic-octo-engine.git
cd fantastic-octo-engine
```

### Run the pet

Double-click `run_pet.bat`, or from a terminal:

```bash
python pet.py
```

### Dump a player file

```bash
python plr_dump.py path/to/player.plr
```

### Toggle desktop icons

```bash
python toggle_icons.py
```

## 📝 Changelog

Changes are tracked in [`MODLOG.md`](MODLOG.md).

## 🤝 Contributing

Issues and pull requests are welcome. For larger changes, please open an issue first to discuss what you'd like to do.

## 📄 License

No license has been specified yet. Consider adding one, such as [MIT](https://choosealicense.com/licenses/mit/).
