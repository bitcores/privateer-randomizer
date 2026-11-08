import os
import sys
import shutil
import mmap
import random
from copy import deepcopy


systems = {0:("17_AR",2), 1:("41-GS",1), 2:("44-P-IM",2), 3:("Aldebran",2), 4:("Auriga",1), 
            5:("Blockade Point Alpha",2), 6:("Blockade Point Charlie",2), 7:("Blockade Point Tango",3),
            8:("Capella",4), 9:("Castor",1), 10:("CM-N1054",1), 11:("CMF-A",2), 12:("Crab-12",2), 13:("Death",2),
            14:("DN-N1912",1), 15:("Famine",3), 16:("Freyja",2), 17:("Hind's Variable N.",2), 18:("Hyades",2),
            19:("119CE",4), 20:("J900",2), 21:("Junction",6), 22:("Tr'Pakh",2), 23:("Sumn-Kp'ta",2),
            24:("Mah'Rahn",1), 25:("KM_252",1), 26:("Lisacc",1), 27:("Manchester",1), 28:("Metsor",2),
            29:("Midgard",2), 30:("ND-57",1), 31:("New Caledonia",4), 32:("Newcastle",4),
            33:("New Constantinople",7), 34:("New Detroit",8), 35:("Nexus",4), 36:("Nitir",3),
            37:("Oxford",3), 38:("Padre",1), 39:("Palan",2), 40:("Pender's Star",2), 41:("Pentonville",1),
            42:("Perry",7), 43:("Pestilence",2), 44:("Pollux",1), 45:("Prasepe",1), 46:("Pyrenees",3),
            47:("Ragnarok",2), 48:("Raxis",1), 49:("Regallis",3), 50:("Rikel",3), 51:("Rygannon",2),
            52:("Saxtogue",2), 53:("Shangri La",1), 54:("Sherwood",5), 55:("Surtur",3), 56:("Telar",3),
            57:("Tingerhoff",4), 58:("Troy",4), 59:("Delta",2), 60:("Gamma",2), 61:("Beta",2),
            62:("Delta Prime",2), 64:("Varnus",1), 65:("War",2), 66:("Xytani",2), 67:("XXN_1927",5),
            68:("Test Bed",0)}


ships = ['GLXYTYPEMERCHANT', 'GLADTYPEGLADIUS\x00', 'ORIOTYPETUG\x00\x00\x00\x00\x00', 'DRAYTYPEDRAYMAN\x00',
         'TALNTYPETALMIL\x00\x00', 'STILTYPESTILETTO', 'TALNWIMPTALPIR\x00\x00', 'TALNWIMPTALMIL\x00\x00',
         'TALNTYPETALRELIG', 'DEMNTYPEDEMON\x00\x00\x00', 'KAMKTYPEKAMEKH\x00\x00', 'GOTHTYPEGOTHRI\x00\x00',
         'DRALTYPEDRALTHI\x00', 'PIRATYPETALPIR\x00\x00', 'PARATYPEFRIGATE\x00', 'BRODTYPEBRDSWORD',
         'CENTTYPEFIGHTER\x00', 'TARSTYPECLUNKER\x00', 'TALNWIMPTALRELIG']

shipscr = {'PIRATYPETALPIR\x00\x00': ['PIR_SF', 'PIR_DA', 'PIR_SA', 'PIR_AA', 'PIR_AF'], 
           'TALNTYPETALRELIG': ['COM_SF', 'COM_DF', 'COM_AF'], 'GLADTYPEGLADIUS\x00': ['MIL_SA', 'MIL_DA', 'MIL_AA'], 
           'DRAYTYPEDRAYMAN\x00': ['MER_AA', 'MER_DP'], 
           'DEMNTYPEDEMON\x00\x00\x00': ['BOU_AA', 'BOU_AF', 'BOU_DF', 'BOU_SF'], 
           'GLXYTYPEMERCHANT': ['MER_SP', 'MER_AA', 'MER_DP'], 'STILTYPESTILETTO': ['CON_SA', 'CON_AA'], 
           'PARATYPEFRIGATE\x00': ['CON_DP', 'CON_AA'], 'BRODTYPEBRDSWORD': ['CON_AA', 'CON_AA'], 
           'TARSTYPECLUNKER\x00': ['MER_AA', 'MER_AP'], 'ORIOTYPETUG\x00\x00\x00\x00\x00': ['MER_AA', 'BOU_DF'], 
           'TALNTYPETALMIL\x00\x00': ['MIL_SA', 'MIL_DA', 'MIL_AA'], 'GOTHTYPEGOTHRI\x00\x00': ['KIL_AA', 'KIL_SF'], 
           'KAMKTYPEKAMEKH\x00\x00': ['KIL_DA', 'KIL_DA'], 'DRALTYPEDRALTHI\x00': ['KIL_DF', 'KIL_AA', 'KIL_DA'], 
           'CENTTYPEFIGHTER\x00': ['BOU_AA', 'BOU_SA'], 'TALNWIMPTALMIL\x00\x00': ['MIL_DA', 'MIL_AA'], 
           'TALNWIMPTALPIR\x00\x00': ['PIR_DA', 'PIR_AA', 'PIR_SF', 'PIR_AF'], 
           'TALNWIMPTALRELIG': ['COM_SF', 'COM_DF', 'COM_AF']}

def makeseed():
    random.seed()
    seed = ""
    for _ in range(12):
        i = random.randint(0,35)
        if i < 10:
            i += 48
        else:
            i += 55
        seed += chr(i)
    return seed

def randomizejumps(gseed):
    seed = gseed

    while True:
        sectors = dict()
        jumps = dict()
        jumpcnt = dict()

        for s in systems:
            if not systems[s][1] == 0:
                jumpcnt[s] = [i for i in range(systems[s][1])]
                jumps[s] = [-1]*systems[s][1]
                sectors[s] = systems[s][1]

        #### jump randomizer

        while len(sectors) > 0:

            if len(sectors) <= 1:
                a = 0
            else:
                a = random.randint(0, len(sectors)-1)

            d = deepcopy(sectors)
            d.pop(list(sectors.keys())[a])
            for x in jumps[list(sectors.keys())[a]]:
                if x >= 0 and x in d:
                    d.pop(x)
            
            # this system cannot jump to any other system, break
            if len(d) == 0:
                break

            if len(d) == 1:
                b = 0
            else:
                b = random.randint(0, len(d)-1)

            if len(jumpcnt[list(sectors.keys())[a]]) == 1:
                i = 0
            else:
                i = random.randint(0, len(jumpcnt[list(sectors.keys())[a]])-1)
            if len(jumpcnt[list(d.keys())[b]]) == 1:
                j = 0
            else:
                j = random.randint(0, len(jumpcnt[list(d.keys())[b]])-1)

            jumps[list(sectors.keys())[a]][jumpcnt[list(sectors.keys())[a]][i]] = list(d.keys())[b]
            jumps[list(d.keys())[b]][jumpcnt[list(d.keys())[b]][j]] = list(sectors.keys())[a]

            jumpcnt[list(sectors.keys())[a]].pop(i)
            jumpcnt[list(d.keys())[b]].pop(j)
            sectors[list(sectors.keys())[a]] -= 1
            sectors[list(d.keys())[b]] -= 1
            if sectors[list(sectors.keys())[a]] == 0:
                sectors.pop(list(sectors.keys())[a])
            if sectors[list(d.keys())[b]] == 0:
                sectors.pop(list(d.keys())[b])

            # sometimes a sector is left with more than one jump unoccupied (chance)
            if len(sectors) == 1:
                break

        ####

        if len(sectors) == 0:
            return jumps, seed
        elif userseed:
            print("Invalid seed")
            sys.exit()
        
        seed = makeseed()
        random.seed(seed)

# starting messages
print("Wing Commander Privateer Randomizer Tool\n")
print("Before starting it is recommended to make a backup of the PRIV.TRE file, just in case.")
print("This tool will make it's own copy of the PRIV.TRE file called PRIV.ori if it does not exist.")
input("Press Enter to continue")

if not os.path.exists("PRIV.TRE"):
    print("PRIV.TRE file not found")
    sys.exit()
if not os.path.exists("PRIV.ori"):
    shutil.copy("PRIV.TRE", "PRIV.ori")
    print("PRIV.TRE backup made")
else:
    # restore the original to rando stuff again
    shutil.copy("PRIV.ori", "PRIV.TRE")

# seed input chance
rseed = ""
print("Game seed (case insensitive, empty for random seed)")
rseed = input("> ").strip().upper()
userseed = False
if rseed == "":
    rseed = makeseed()
else:
    random.seed(rseed)
    userseed = True

randomjumps = "NO"
randomspawns = "NO"
print("Randomize Jumps? (default NO, type Y or YES)")
inp = input("> ").strip().upper()
if inp == "Y" or inp == "YES":
    randomjumps = "YES"

print("Randomize Spawns? (default NO, type Y or YES)")
inp = input("> ").strip().upper()
if inp == "Y" or inp == "YES":
    randomspawns = "YES"

rando = list()
if randomjumps == "YES":
    rando, rseed = randomizejumps(rseed)

#print(rando)
#input()
rev = dict()
for s in systems:
    rev[systems[s][0]] = s

with open("spoiler.txt", "w") as spfile:
    line = "Game Seed: " + rseed + "\n\n"
    spfile.write(line)
    line = "Randomize Jumps? " + randomjumps + "\n"
    spfile.write(line)
    line = "Randomize Spawns? " + randomspawns + "\n\n"
    spfile.write(line)
    line = "Jump List ====================\n\n"
    spfile.write(line)

    for j in rando:
        line = ""
        line += systems[j][0] + ": "
        for r in rando[j]:
            line += systems[r][0] + ", "
        spfile.write(line[:-2]+"\n")

search = "SCTRLABL".encode("utf-8")

#out = ""

with open("PRIV.TRE", "rb+") as file:
    with mmap.mmap(file.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
        pos = mm.find(search)

        while pos != -1:
            next = mm.find(search, pos+1)

            file.seek(pos+8, 0)
            tlen = int.from_bytes(file.read(4))
            label = str(file.read(tlen-1), 'utf-8')
            
            sysid = rev[label]

            if randomspawns == "Y" or randomspawns == "YES":
                scr = mm.find("SCRPCAST".encode("utf-8"), pos)+12
                w = mm.find("WAND".encode("utf-8"), pos)
                w += 8
                we = mm.find("JUMP".encode("utf-8"), pos)
                while  w < we:
                    file.seek(w+3, 0)
                    rs = random.randint(0, len(ships)-1)
                    file.write(ships[rs].encode("utf-8"))
                    a = int.from_bytes(file.read(1))
                    rs_s = random.randint(0, len(shipscr[ships[rs]])-1)
                    file.seek(scr+(8*a), 0)
                    file.write(shipscr[ships[rs]][rs_s].encode("utf-8"))
                    w += 46

            if randomjumps == "Y" or randomjumps == "YES":
                j = 0
                jf = mm.find("JUMPTYPEJUMP".encode("utf-8"), pos)
                while jf > 0 and jf < next:
                    file.seek(jf+43, 0)
                    file.write(int.to_bytes(rando[sysid][j]))

                    j += 1
                    jf = mm.find("JUMPTYPEJUMP".encode("utf-8"), jf+1)

            #out += "\""+str(sysid)+"\":(\""+label+"\","+str(j)+"), "
            #print("System found:", label, "id", sysid, "no. of jumps", j)

            pos = next
            
print(rseed)
print("Randomize Jumps?", randomjumps)
print("Randomize Spawns?", randomspawns)
