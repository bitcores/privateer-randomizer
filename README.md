# privateer-randomizer
A randomizer tool for Wing Commander Privateer and Righteous Fire

**Features**
- Randomized jumps (jumps remain bi-directional, and every system can still be reached)
- Randomized spawns (each encounter keeps its faction, squad size and number of capital ships)
- Works on Privateer (PRIV.TRE) and Righteous Fire (RF.TRE)
- Seed value: the same seed always gives the same result
- Spoiler document, read back from the patched archive
- Keeps an untouched backup and always randomizes from it

**Requirements**

Python 3.8 or newer is required to run the tool. Having the PATH set will make usage easier.\
Place the priv-rando.py file in the same directory as the PRIV.TRE or RF.TRE file.\
**Making a backup of the archive is still recommended**

**Usage**

```
In Windows Explorer, open the directory with the PRIV.TRE (or RF.TRE) and priv-rando.py in it.
Click in the address bar in Explorer, type in cmd and press Enter
Then in Command Prompt type
> python priv-rando.py
```
When both PRIV.TRE and RF.TRE are in the folder, the tool asks which one to randomize (type PRIV or RF).
You can also name the archive: `python priv-rando.py D:\Games\Privateer\RF.TRE`\
Game seed can be left empty; a random seed is then made and printed.\
Entering anything other than Y or YES for randomizer settings will be interpreted as a NO.

The spoiler is written next to the archive as spoiler-PRIV.txt or spoiler-RF.txt. It lists the
seed, the options, the archive and a SHA-256 of the original, then every system with its jumps
(each link shows up at both ends, with its nav point number) and, with spawns on, every changed
ship and pilot.

**Restoring the original**

The first run copies the archive to PRIV.ori (or RF.ori) and every later run starts from that copy.
To get the original back, either run the tool and answer NO to both questions, or copy PRIV.ori
over PRIV.TRE (RF.ori over RF.TRE).

**Righteous Fire**

Righteous Fire reads only RF.TRE (its RF.CFG names rf.tre and nothing else), and RF.TRE holds its own
complete copy of the star map. So randomizing RF.TRE is all a Righteous Fire game needs, and
randomizing PRIV.TRE does not change Righteous Fire (or the other way round). Randomize each one on
its own if you play both.

**What the tool keeps as it is**

- The story jumps. The Kilrathi chain Rygannon - Delta - Beta - Gamma - Delta Prime is opened by the
  plot, and Delta, Beta, Gamma and Delta Prime stay hidden on the map until then; these links are
  never changed. In Righteous Fire the same goes for Valhalla - Eden and the Rikel - Eden link.
  The tool finds these links in the data (the OJMP records, the systems they lead into, and jumps
  that have no nav point), not from a list of names.
- The number of jump points of every system.
- With spawns on: each encounter keeps its faction and squad size. A fighter only becomes another
  fighter of the same faction, and a capital ship (Paradigm, Broadsword, Kamekh) another capital ship,
  picked with the frequencies the original game uses, and only from the ships that system already
  spawns or preloads. Pilots get a new skill and morale within their faction.

**What changed in this version, and why**

- The tool now reads the archive's file table and the star map (SECTORS.IFF) chunk by chunk instead
  of searching for byte patterns. The old search missed Valhalla (its data starts differently), so
  Valhalla's jump got written into Delta Prime's place: every result had two one-way jumps and
  Valhalla could not be reached. Righteous Fire (70 systems, with Eden) now works too.
- A jump is stored twice: in the jump point record (used by the jump drive and the arrival) and in
  the nav point list (used by the navigation map, its "Jump to" text and the mission generator).
  The old version changed only the first, so the map showed different destinations than the jumps
  really went to. Both are now always written together.
- The map is always connected: a random tree over all systems is built first, then the remaining
  jump points are paired. No seed is ever "Invalid" any more, and there are no self links or two
  links between the same pair of systems.
- The story jumps and hidden systems are left alone. Before, a jump from an ordinary system into a
  hidden Kilrathi system could make the original game's navigation map stop with an error.
- The seed now reproduces the whole result, also when it was made for you. Jumps and spawns each
  use their own random stream made from the seed, so turning spawns on or off does not change the
  jumps.
- Safety: the tool refuses an archive that was already randomized or modded (it compares the
  star map data with the unmodified game), checks the backup, writes a temporary copy and only
  replaces the archive when every check passed, and stops with a clear message on a read-only file.
- Spawns no longer give every encounter a random ship from all 19 hulls, which changed factions,
  could give one pilot two different ships and nearly doubled the number of capital ships.
- It runs on Python 3.8 and newer (the old version needed 3.11).

**Self-test**

`python selftest.py` checks the tool on a small made-up archive (no game data needed).

**Roadmap**

There are some features in particular I want to add
- Option to generate jumps that can complete the game
- Randomize starting system
- Randomize spawns to a greater degree
- Rewrite in a more friendly format
