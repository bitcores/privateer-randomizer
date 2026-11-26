# privateer-randomizer
A randomizer tool for Wing Commander Privateer

**Features**
- Randomized jumps (jumps remain bi-directional)
- Randomized spawns (ship numbers remain the same)
- Randomize starting system
- Seed value
- Spoiler document

**Requirements**

Python 3 is required to run the tool. Having the PATH set will make usage easier.\
Place the priv-rando.py file in the same directory as the PRIV.TRE file.\
**Making a backup of the PRIV.TRE and the INITCFG.PAK is highly recommended**

**Usage**

```
In Windows Explorer, open the directory with the PRIV.TRE and priv-rando.py in it.
Click in the address bar in Explorer, type in cmd and press Enter
The in Command Prompt type
> python priv-rando.py
```
Game seed can be left empty.\
Entering anything other than Y or YES for randomizer settings will be interpreted as a NO.

**CD version things**
In my case, I installed Privateer from a CD in DosBox manually, so I had a separate game directory and a CD directory with the PRIV.TRE and INITCFG.PAK in separate places.\
If this is the case, you can combine the two directories into one. Copy the two .TRE files (PRIV.TRE and RF.TRE) into the game directory and edit the two PRIV.CFG and RF.CFG files.\
These files have the paths to the .TRE files. Usually it will have something like
```
=D:\priv.tre
```
where D: points to your CD drive. Just change it to the mounted directory of your game drive DosBox uses, for example
```
=C:\PRIVATR\priv.tre
```

**OpenPrivateer things**
I haven't done much testing in OpenPrivateer yet but from what I have seen there are differences in how OpenPrivateer does the Nav computers so it will display the randomized destination systems in the Nav computer.\
Beta, Gamma, and Delta Prime also do not crash OpenPrivateer when you open the Nav computer, which is a plus.

**Roadmap**

There are some features in particular I want to add
- Option to generate jumps that can complete the game
- Randomize spawns to a greater degree
- Rewrite in a more friendly format
