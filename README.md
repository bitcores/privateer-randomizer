# privateer-randomizer
A randomizer tool for Wing Commander Privateer

**Features**
- Randomized jumps (jumps remain bi-directional)
- Randomized spawns (ship numbers remain the same)
- Seed value
- Spoiler document

**Requirements**

Python 3 is required to run the tool. Having the PATH set will make usage easier.\
Place the priv-rando.py file in the same directory as the PRIV.TRE file.\
**Making a backup of the PRIV.TRE is highly recommended**

**Usage**

```
In Windows Explorer, open the directory with the PRIV.TRE and priv-rando.py in it.
Click in the address bar in Explorer, type in cmd and press Enter
The in Command Prompt type
> python priv-rando.py
```
Game seed can be left empty.\
Entering anything other than Y or YES for randomizer settings will be interpreted as a NO.

**Roadmap**

There are some features in particular I want to add
- Option to generate jumps that can complete the game
- Randomize starting system
- Randomize spawns to a greater degree
- Rewrite in a more friendly format
