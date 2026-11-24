"""Wing Commander Privateer randomizer.

Shuffles the jump connections between star systems and, if asked, the ships
that random encounters spawn. Works on PRIV.TRE (Privateer) and RF.TRE
(Righteous Fire). Run it from the folder that holds the archive:

    python priv-rando.py

or name the archive on the command line:

    python priv-rando.py D:\\Games\\Privateer\\RF.TRE

How the data is laid out (DATA\\SECTORS\\SECTORS.IFF inside the archive):

    FORM "SSSS"
      TABL                  one u32 offset per star system
      per system: u32 length, then FORM "SCTR"
        LABL                system name (Valhalla has a NAME chunk first)
        SPHR                19-byte nav point records
        FORM "SCRP"
          CAST              8-byte pilot names
          FORM "PART"
            WAND            46-byte random encounter records
            JUMP            46-byte jump point records
            OJMP            46-byte story-gated jump points (a few systems)
        FORM "LOAD"
          OBJT              8-byte ship type names the system preloads

The fields this script reads or writes:

    JUMP / OJMP record   +20  nav slot (the low SPHR type of the jump's nav point)
                         +21  this system's index
                         +45  destination system index
    SPHR record          +0   type: 0-8 low group, 10-18 the nav point entry
                              of slot (type - 10), 20-22 hidden spheres
                         +16  kind (nav point entry): 0 empty, 1 base, 2 jump
                         +17  base code (kind 1) or destination system (kind 2)
                         +18  the "Nav N" number shown on the map
    WAND record          +3   16 bytes: ship type file and ship class
                         +19  u16 index of the pilot in CAST

A jump exists twice: the JUMP record (used by the jump drive and the
arrival) and the kind-2 nav point entry of the same slot (used by the
navigation map, its "Jump to" text and the mission generator). Both are
always written together.

Righteous Fire reads only RF.TRE (its RF.CFG names rf.tre and nothing else)
and RF.TRE has its own complete SECTORS.IFF, so a Righteous Fire game needs
only RF.TRE randomized; PRIV.TRE is for Privateer.
"""

import hashlib
import os
import random
import struct
import sys

if sys.version_info < (3, 8):
    print("This script needs Python 3.8 or newer. You have %d.%d." % sys.version_info[:2])
    sys.exit(1)

VERSION = "2.0"

# The data fingerprints (see data_fingerprint) of the unmodified archives,
# taken from the CD / GOG release (PRIV.TRE 89,486,108 bytes and RF.TRE
# 72,960,246 bytes, both dated 1995-02-02). Only the star map chunks this
# script changes go into the fingerprint, so it does not depend on the rest of
# the file. For each: the game, the base code of the base a new game starts at
# (INITCFG.PAK / INITRF.PAK name it; the start system is the one whose nav
# point list holds that base) and the base's name.
KNOWN_ARCHIVES = {
    "5651d1c42b9811fe234d3122b9ebaf481fd3daca00b453e69890d24f97631d03": ("Privateer", 0, "Achilles"),
    "91b1996a83849be240628bb596321a4c4ea2a7f218f9a2519baa0f6e479e25ab": ("Righteous Fire", 18, "Jolson"),
}

# Hulls that count as capital ships. A capital ship is only ever replaced by
# another capital ship, and a fighter by a fighter, so the number of capital
# ships in the game stays exactly as it was.
CAPITAL_HULLS = {"PARATYPE", "BRODTYPE", "KAMKTYPE"}  # Paradigm, Broadsword, Kamekh

SECTORS_NAME = "\\DATA\\SECTORS\\SECTORS.IFF"
JUMP_RECORD_SIZE = 46
SPHR_RECORD_SIZE = 19
WAND_RECORD_SIZE = 46


class ArchiveError(Exception):
    """The archive is not what this script expects."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def u16le(data, pos):
    return struct.unpack_from("<H", data, pos)[0]


def u32le(data, pos):
    return struct.unpack_from("<I", data, pos)[0]


def u32be(data, pos):
    return struct.unpack_from(">I", data, pos)[0]


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def text(raw):
    """A null-padded name from the data as a string."""
    return bytes(raw).split(b"\0")[0].decode("latin-1")


# ---------------------------------------------------------------------------
# Reading the archive
# ---------------------------------------------------------------------------

def read_tre_directory(data):
    """The file list of a .TRE archive: (name, offset, size) per entry.

    Header: u32 entry count, u32 end of the table. Each entry is 74 bytes:
    a flag byte, a 65-byte null-terminated name, u32 offset, u32 size.
    """
    if len(data) < 8:
        raise ArchiveError("the file is too small to be a .TRE archive")
    count = u32le(data, 0)
    if count == 0 or 8 + count * 74 > len(data):
        raise ArchiveError("the file does not start with a .TRE file table")
    entries = []
    for i in range(count):
        pos = 8 + i * 74
        name = text(data[pos + 1:pos + 66])
        offset = u32le(data, pos + 66)
        size = u32le(data, pos + 70)
        if offset + size > len(data):
            raise ArchiveError("the file table points past the end of the file")
        entries.append((name, offset, size))
    return entries


def iff_chunks(data, start, end):
    """The chunks of one IFF level between start and end.

    Yields (tag, payload_start, payload_size, form_type). A FORM's payload
    starts after its 4-byte form type. Chunks are padded to even sizes.
    """
    pos = start
    while pos < end:
        if pos + 8 > end:
            raise ArchiveError("an IFF chunk header is cut off at offset %d" % pos)
        tag = bytes(data[pos:pos + 4])
        size = u32be(data, pos + 4)
        payload = pos + 8
        if payload + size > end:
            raise ArchiveError("an IFF chunk runs past its parent at offset %d" % pos)
        if tag == b"FORM":
            yield tag, payload + 4, size - 4, bytes(data[payload:payload + 4])
        else:
            yield tag, payload, size, None
        pos = payload + size + (size & 1)


def all_chunks(data, start, end, path=""):
    """Every non-FORM chunk below start..end as (path, tag, start, size)."""
    found = []
    for tag, pos, size, form_type in iff_chunks(data, start, end):
        if tag == b"FORM":
            found.extend(all_chunks(data, pos, pos + size, path + "/" + form_type.decode("latin-1")))
        else:
            found.append((path, tag.decode("latin-1"), pos, size))
    return found


class NavPoint:
    """One SPHR record. Offsets are absolute positions in the archive."""

    def __init__(self, offset, raw):
        self.offset = offset
        self.type = raw[0]
        self.kind = raw[16]
        self.target = raw[17]  # base code (kind 1) or destination system (kind 2)
        self.number = raw[18]  # the "Nav N" shown on the map


class Jump:
    """One JUMP or OJMP record and the nav point entry that shows it."""

    def __init__(self, system, chunk, offset, raw, nav_points):
        self.system = system
        self.chunk = chunk  # "JUMP" or "OJMP"
        self.offset = offset
        self.slot = raw[20]
        self.dest = raw[45]
        # The nav point entry of the same slot. A jump whose slot has no
        # kind-2 entry is not shown on the map (Righteous Fire's Rikel and
        # Eden have one each); it has no nav copy to keep in step.
        self.nav = None
        for nav in nav_points:
            if 10 <= nav.type <= 18 and nav.type - 10 == self.slot and nav.kind == 2:
                self.nav = nav

    def key(self):
        return (self.system, self.chunk, self.offset)

    def nav_text(self):
        return "Nav %d" % self.nav.number if self.nav else "no nav point"


class WandRecord:
    def __init__(self, offset, raw):
        self.offset = offset
        self.hull = bytes(raw[3:19])  # ship type file + ship class, 8 bytes each
        self.cast_slot = u16le(raw, 19)
        self.nav_type = raw[21]
        self.squad = raw[35]

    def hull_type(self):
        return text(self.hull[:8]).upper()


class StarSystem:
    def __init__(self, index):
        self.index = index
        self.name = ""
        self.nav_points = []
        self.jumps = []     # JUMP records
        self.ojumps = []    # OJMP records (story-gated)
        self.wand = []
        self.cast_offset = None
        self.cast = []
        self.objt = []

    def all_jumps(self):
        return self.jumps + self.ojumps


class Sectors:
    """Everything this script needs from SECTORS.IFF, with archive offsets."""

    def __init__(self, data):
        self.data = data
        self.entries = read_tre_directory(data)
        matches = [e for e in self.entries if e[0].upper().endswith(SECTORS_NAME)]
        if len(matches) != 1:
            raise ArchiveError("the archive does not hold exactly one SECTORS.IFF")
        name, self.base, self.size = matches[0]
        self.systems = read_systems(data, self.base, self.size)

    def by_name(self, name):
        for system in self.systems:
            if system.name == name:
                return system
        return None

    def aids_names(self):
        """Base names of the pilot files (DATA\\AIDS\\*.IFF) in the archive."""
        names = set()
        for name, offset, size in self.entries:
            upper = name.upper()
            if "\\DATA\\AIDS\\" in upper and upper.endswith(".IFF"):
                names.add(upper.split("\\")[-1][:-4])
        return names


def read_systems(data, base, size):
    end = base + size
    if bytes(data[base:base + 4]) != b"FORM" or bytes(data[base + 8:base + 12]) != b"SSSS":
        raise ArchiveError("SECTORS.IFF does not start with FORM SSSS")
    if base + 8 + u32be(data, base + 4) != end:
        raise ArchiveError("SECTORS.IFF has an unexpected size")
    if bytes(data[base + 12:base + 16]) != b"TABL":
        raise ArchiveError("SECTORS.IFF has no system table (TABL)")
    count = u32be(data, base + 16) // 4
    systems = []
    for index in range(count):
        block = base + u32le(data, base + 20 + 4 * index)  # TABL offsets count from the start of SECTORS.IFF
        if block + 16 > end or bytes(data[block + 4:block + 8]) != b"FORM" \
                or bytes(data[block + 12:block + 16]) != b"SCTR":
            raise ArchiveError("system %d does not point at a FORM SCTR" % index)
        form_end = block + 12 + u32be(data, block + 8)  # the FORM's size counts from its type
        if form_end > end:
            raise ArchiveError("system %d runs past the end of SECTORS.IFF" % index)
        systems.append(read_one_system(data, index, block + 16, form_end))
    return systems


def read_one_system(data, index, start, end):
    system = StarSystem(index)
    chunks = all_chunks(data, start, end)
    names = {}
    for path, tag, pos, size in chunks:
        if tag in ("LABL", "NAME") and tag not in names:
            names[tag] = text(data[pos:pos + size])
    # The name the game shows is LABL; NAME (only Valhalla has one) is the fallback.
    system.name = names.get("LABL") or names.get("NAME") or "system %d" % index

    for path, tag, pos, size in chunks:
        if tag == "SPHR":
            records(size, SPHR_RECORD_SIZE, "SPHR", system)
            for i in range(size // SPHR_RECORD_SIZE):
                at = pos + i * SPHR_RECORD_SIZE
                system.nav_points.append(NavPoint(at, data[at:at + SPHR_RECORD_SIZE]))
    for path, tag, pos, size in chunks:
        if tag in ("JUMP", "OJMP"):
            records(size, JUMP_RECORD_SIZE, tag, system)
            for i in range(size // JUMP_RECORD_SIZE):
                at = pos + i * JUMP_RECORD_SIZE
                raw = data[at:at + JUMP_RECORD_SIZE]
                if bytes(raw[2:18]) != b"JUMPTYPEJUMP\0\0\0\0" or raw[21] != index:
                    raise ArchiveError("%s has a %s record that does not look like a jump" % (system.name, tag))
                jump = Jump(index, tag, at, raw, system.nav_points)
                (system.jumps if tag == "JUMP" else system.ojumps).append(jump)
        elif tag == "WAND":
            records(size, WAND_RECORD_SIZE, "WAND", system)
            for i in range(size // WAND_RECORD_SIZE):
                at = pos + i * WAND_RECORD_SIZE
                system.wand.append(WandRecord(at, data[at:at + WAND_RECORD_SIZE]))
        elif tag == "CAST":
            records(size, 8, "CAST", system)
            system.cast_offset = pos
            system.cast = [text(data[pos + 8 * i:pos + 8 * i + 8]) for i in range(size // 8)]
        elif tag == "OBJT":
            records(size, 8, "OBJT", system)
            system.objt = [text(data[pos + 8 * i:pos + 8 * i + 8]).upper() for i in range(size // 8)]
    for record in system.wand:
        if record.cast_slot >= len(system.cast):
            raise ArchiveError("%s has an encounter whose pilot is not in its CAST list" % system.name)
    return system


def records(size, record_size, tag, system):
    if size % record_size:
        raise ArchiveError("%s: the %s chunk is not a whole number of records" % (system.name, tag))


def data_fingerprint(sectors):
    """SHA-256 over every chunk this script may change (JUMP, OJMP, SPHR,
    WAND and CAST of every system, in table order).

    It tells an unmodified archive from one that was already randomized or
    modded, without depending on the rest of the file.
    """
    digest = hashlib.sha256()
    data = sectors.data
    for system in sectors.systems:
        for nav in system.nav_points:
            digest.update(data[nav.offset:nav.offset + SPHR_RECORD_SIZE])
        for jump in system.all_jumps():
            digest.update(data[jump.offset:jump.offset + JUMP_RECORD_SIZE])
        for record in system.wand:
            digest.update(data[record.offset:record.offset + WAND_RECORD_SIZE])
        if system.cast_offset is not None:
            digest.update(data[system.cast_offset:system.cast_offset + 8 * len(system.cast)])
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------

def make_seed():
    """A new 12-character seed from the operating system's random source."""
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    pick = random.SystemRandom()
    return "".join(alphabet[pick.randrange(len(alphabet))] for _ in range(12))


def feature_rng(seed, feature):
    """A random number generator of its own for one feature.

    The generator is seeded with the first 16 bytes of
    SHA-256("<seed>/<feature>"), so the jumps and the spawns each depend only
    on the seed: turning spawns on or off never changes the jumps.
    """
    digest = hashlib.sha256(("%s/%s" % (seed, feature)).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:16], byteorder="big"))


def shuffled(items, rng):
    """A shuffled copy of items (Fisher-Yates, written out so the result
    for a seed does not depend on the Python version)."""
    items = list(items)
    for i in range(len(items) - 1, 0, -1):
        j = rng.randrange(i + 1)
        items[i], items[j] = items[j], items[i]
    return items


def weighted_choice(options, weights, rng):
    """One of options, each picked with a chance proportional to its weight."""
    roll = rng.randrange(sum(weights))
    for option, weight in zip(options, weights):
        if roll < weight:
            return option
        roll -= weight
    return options[-1]


# ---------------------------------------------------------------------------
# Jumps
# ---------------------------------------------------------------------------

def pair_up_jumps(sectors):
    """Each jump record with the record that leads back.

    Returns {jump key: return jump}. Refuses an archive whose jumps are not
    two-way (counting JUMP and OJMP records together they always are).
    """
    by_pair = {}
    for system in sectors.systems:
        for jump in system.all_jumps():
            by_pair.setdefault((jump.system, jump.dest), []).append(jump)
    partner = {}
    for (a, b), there in by_pair.items():
        back = by_pair.get((b, a), [])
        if len(back) != len(there) or a == b:
            raise ArchiveError("the jump from %s to %s has no way back" % (
                system_name(sectors, a), system_name(sectors, b)))
        for jump, other in zip(there, back):
            partner[jump.key()] = other
    return partner


def system_name(sectors, index):
    if 0 <= index < len(sectors.systems):
        return sectors.systems[index].name
    return "system %d" % index


def find_pinned_jumps(sectors):
    """The jumps the shuffle must leave alone, with the reason for each.

    Worked out from the data, not from a list of names:
    - every OJMP record: a story-gated jump that the plot opens (Privateer's
      Kilrathi chain Rygannon -> Delta -> Beta -> Gamma -> Delta Prime, and in
      Righteous Fire also Valhalla -> Eden);
    - every jump of a system that an OJMP leads into: such a system is hidden
      from the map until the story opens it, and the original game's map
      fails with an error when an ordinary system's jump into a hidden one is
      not its last nav point, so these systems keep exactly their own links;
    - every jump with no nav point on the map (Righteous Fire's Rikel <-> Eden
      link), which the story uses as it is;
    - and the way back of each of these.
    """
    partner = pair_up_jumps(sectors)
    locked = set()
    for system in sectors.systems:
        for jump in system.ojumps:
            locked.add(jump.dest)
    reasons = {}
    for system in sectors.systems:
        for jump in system.ojumps:
            reasons[jump.key()] = "story jump (OJMP)"
        for jump in system.jumps:
            if jump.system in locked:
                reasons.setdefault(jump.key(), "inside a story-locked system")
            elif jump.nav is None:
                reasons.setdefault(jump.key(), "hidden jump, not on the map")
    for key in list(reasons):
        back = partner[key]
        reasons.setdefault(back.key(), "way back of a pinned jump")
    return reasons, partner


def free_jump_slots(sectors, pinned):
    """{system index: [its jump records the shuffle may change]}."""
    slots = {}
    for system in sectors.systems:
        free = [jump for jump in system.jumps if jump.key() not in pinned]
        if free:
            slots[system.index] = free
    return slots


def is_graphical(degrees):
    """Erdos-Gallai test: can these degrees form a graph with no self or
    double links at all?"""
    d = sorted(degrees, reverse=True)
    if sum(d) % 2:
        return False
    for k in range(1, len(d) + 1):
        left = sum(d[:k])
        right = k * (k - 1) + sum(min(x, k) for x in d[k:])
        if left > right:
            return False
    return True


def random_tree(degrees, rng):
    """A random tree over the systems in degrees, no system getting more
    links than it has slots. Returns a list of (a, b) links.

    First every system gets one link, then the extra links a tree needs
    are spread over the slots that are left, then a random Pruefer sequence
    with those link counts is turned into the tree.
    """
    nodes = sorted(degrees)
    if len(nodes) == 1:
        return []
    tree_degree = dict((node, 1) for node in nodes)
    spare = []
    for node in nodes:
        spare.extend([node] * (degrees[node] - 1))
    for node in shuffled(spare, rng)[:len(nodes) - 2]:
        tree_degree[node] += 1
    sequence = []
    for node in nodes:
        sequence.extend([node] * (tree_degree[node] - 1))
    sequence = shuffled(sequence, rng)
    remaining = dict(tree_degree)
    links = []
    for node in sequence:
        leaf = min(n for n in nodes if remaining[n] == 1)
        links.append((leaf, node))
        remaining[leaf] -= 1
        remaining[node] -= 1
    last = [n for n in nodes if remaining[n] == 1]
    links.append((last[0], last[1]))
    return links


def random_connected_map(degrees, rng, forbidden=frozenset(), tries=2000):
    """Links between systems so that every system uses exactly its number
    of slots, the map is connected, and no link joins a system to itself
    or joins two systems twice (or repeats a pair in forbidden).

    degrees: {system: number of free jump slots}. Returns sorted (a, b)
    links with a < b. A random tree first makes sure every system can be
    reached; the slots left over are paired at random, and a pair that
    would make a self or double link swaps a partner with another random
    pair until none is left. If that gets stuck, a new tree is drawn.
    Raises ValueError when the slot counts cannot make such a map (never
    the case with the game's own data).
    """
    nodes = sorted(n for n in degrees if degrees[n] > 0)
    if not nodes:
        return []
    total = sum(degrees[n] for n in nodes)
    if len(nodes) == 1 or total < 2 * (len(nodes) - 1) or not is_graphical([degrees[n] for n in nodes]):
        raise ValueError("these jump slot counts cannot make one connected map without self or double links")
    for _ in range(tries):
        tree = random_tree(dict((n, degrees[n]) for n in nodes), rng)
        taken = set(frozenset(link) for link in tree)
        if taken & forbidden:
            continue
        left = dict((n, degrees[n]) for n in nodes)
        for a, b in tree:
            left[a] -= 1
            left[b] -= 1
        stubs = []
        for node in nodes:
            stubs.extend([node] * left[node])
        extra = pair_stubs(shuffled(stubs, rng), rng, taken | set(forbidden))
        if extra is not None:
            return sorted(tuple(sorted(link)) for link in tree + extra)
    raise ValueError("could not build a connected map from these jump slots")


def pair_stubs(stubs, rng, taken):
    """Pair the stubs (a list holding each system once per free slot) into
    links. A link is bad when it joins a system to itself or repeats a pair
    in taken or in the new links. Each bad link trades one end with another
    random link when both new links are good. Returns the links, or None
    when it gets stuck."""
    links = [(stubs[i], stubs[i + 1]) for i in range(0, len(stubs), 2)]
    count = {}  # how often each pair occurs among the new links
    for a, b in links:
        pair = frozenset((a, b))
        count[pair] = count.get(pair, 0) + 1

    def bad(link):
        a, b = link
        pair = frozenset(link)
        return a == b or pair in taken or count[pair] > 1

    def swap(i, j, first, second):
        for old in (links[i], links[j]):
            count[frozenset(old)] -= 1
        links[i], links[j] = first, second
        for new in (first, second):
            pair = frozenset(new)
            count[pair] = count.get(pair, 0) + 1

    for _ in range(200 * (len(links) + 1)):
        broken = [i for i in range(len(links)) if bad(links[i])]
        if not broken:
            return links
        if len(links) < 2:
            return None
        i = broken[rng.randrange(len(broken))]
        j = rng.randrange(len(links) - 1)
        if j >= i:
            j += 1
        (a, b), (c, d) = links[i], links[j]
        old = links[i], links[j]
        if rng.randrange(2):
            swap(i, j, (a, c), (b, d))
        else:
            swap(i, j, (a, d), (b, c))
        if bad(links[i]) or bad(links[j]):
            swap(i, j, old[0], old[1])
    return None


def plan_jumps(sectors, rng):
    """New destinations for the free jump records.

    Returns {jump key: new destination}. Each system keeps its number of
    jump slots, every link is two-way, and the free systems form one
    connected map; the pinned story links hang off it as before.
    """
    pinned, partner = find_pinned_jumps(sectors)
    slots = free_jump_slots(sectors, pinned)
    forbidden = set()
    for key in pinned:
        jump = jump_by_key(sectors, key)
        if jump.system in slots and jump.dest in slots:
            forbidden.add(frozenset((jump.system, jump.dest)))
    degrees = dict((system, len(free)) for system, free in slots.items())
    links = random_connected_map(degrees, rng, frozenset(forbidden))
    neighbours = dict((system, []) for system in slots)
    for a, b in links:
        neighbours[a].append(b)
        neighbours[b].append(a)
    new_dest = {}
    for system in sorted(slots):
        for jump, dest in zip(slots[system], shuffled(neighbours[system], rng)):
            new_dest[jump.key()] = dest
    return new_dest


def jump_by_key(sectors, key):
    for jump in sectors.systems[key[0]].all_jumps():
        if jump.key() == key:
            return jump
    raise KeyError(key)


def jump_writes(sectors, new_dest):
    """The bytes to write for the new destinations: the JUMP record's
    destination and its nav point entry's destination, together."""
    writes = {}
    for key, dest in new_dest.items():
        jump = jump_by_key(sectors, key)
        writes[jump.offset + 45] = dest
        if jump.nav is not None:
            writes[jump.nav.offset + 17] = dest
    return writes


def check_jump_map(sectors, start=None):
    """Problems with the jump data, as a list of sentences (empty when fine).

    Checks that every jump record and its nav point entry name the same
    destination, that no system jumps to itself or twice to the same
    system, that every jump has a way back, and, given a start system,
    which systems cannot be reached from it.
    """
    problems = []
    count = len(sectors.systems)
    for system in sectors.systems:
        seen = set()
        for jump in system.all_jumps():
            if jump.dest >= count:
                problems.append("%s jumps to a system that does not exist" % system.name)
                continue
            if jump.dest == system.index:
                problems.append("%s jumps to itself" % system.name)
            if jump.dest in seen:
                problems.append("%s has two jumps to %s" % (system.name, system_name(sectors, jump.dest)))
            seen.add(jump.dest)
            if jump.nav is not None and jump.nav.target != jump.dest:
                problems.append("%s %s: the map says %s, the jump goes to %s" % (
                    system.name, jump.nav_text(), system_name(sectors, jump.nav.target),
                    system_name(sectors, jump.dest)))
    try:
        pair_up_jumps(sectors)
    except ArchiveError as error:
        problems.append(str(error))
    if start is not None:
        reached = reachable(sectors, start)
        for system in sectors.systems:
            if system.all_jumps() and system.index not in reached:
                problems.append("%s cannot be reached from %s" % (system.name, system_name(sectors, start)))
    return problems


def reachable(sectors, start, story_open=True):
    """The systems a pilot can reach from start. With story_open False the
    story-gated OJMP jumps count as closed (a new game)."""
    seen = set([start])
    todo = [start]
    while todo:
        system = sectors.systems[todo.pop()]
        jumps = system.all_jumps() if story_open else system.jumps
        for jump in jumps:
            if jump.dest not in seen and jump.dest < len(sectors.systems):
                seen.add(jump.dest)
                todo.append(jump.dest)
    return seen


def find_start_system(sectors, base_code):
    """The system whose nav point list holds the base the new game starts at."""
    found = [s.index for s in sectors.systems for nav in s.nav_points
             if 10 <= nav.type <= 18 and nav.kind == 1 and nav.target == base_code]
    if len(found) != 1:
        raise ArchiveError("could not find the start base (code %d) in the data" % base_code)
    return found[0]


# ---------------------------------------------------------------------------
# Spawns
# ---------------------------------------------------------------------------

def faction_of(pilot):
    """MIL_DA -> MIL. Pilots of random encounters are named <faction>_<skill><morale>."""
    return pilot.split("_")[0]


def hull_group(hull):
    return "capital" if text(hull[:8]).upper() in CAPITAL_HULLS else "fighter"


def spawn_tables(sectors):
    """What the unmodified game uses, counted over every encounter record:
    {(faction, group): {hull: count}} and {(faction, group): {pilot: count}}."""
    hulls = {}
    pilots = {}
    for system in sectors.systems:
        for record in system.wand:
            pilot = system.cast[record.cast_slot]
            key = (faction_of(pilot), hull_group(record.hull))
            hulls.setdefault(key, {})
            hulls[key][record.hull] = hulls[key].get(record.hull, 0) + 1
            pilots.setdefault(key, {})
            pilots[key][pilot] = pilots[key].get(pilot, 0) + 1
    return hulls, pilots


def plan_spawns(sectors, rng):
    """New hulls and pilots for the random encounters.

    Returns {offset: new bytes}. The rules:
    - a record keeps its faction (the pilot's prefix) and its squad size;
    - its new hull is one that faction flies somewhere in the unmodified
      game, of the same group (capital or fighter), picked with the
      unmodified game's own frequencies, and only a hull the system already
      spawns or preloads (its OBJT list), so the system has the ship's data;
    - the pilot is rerolled per CAST slot, not per record: a few slots are
      shared by two records, and both get the same new pilot; the new pilot
      is one of the same faction and group in the unmodified game, and its
      file must exist in the archive;
    - systems without encounter records are skipped.
    """
    hull_counts, pilot_counts = spawn_tables(sectors)
    aids = sectors.aids_names()
    writes = {}
    for system in sectors.systems:
        if not system.wand:
            continue
        allowed_types = set(system.objt) | set(record.hull_type() for record in system.wand)
        for record in system.wand:
            pilot = system.cast[record.cast_slot]
            counts = hull_counts[(faction_of(pilot), hull_group(record.hull))]
            options = [h for h in sorted(counts) if text(h[:8]).upper() in allowed_types]
            if record.hull not in options:
                options.append(record.hull)
            new_hull = weighted_choice(options, [counts.get(h, 1) for h in options], rng)
            if new_hull != record.hull:
                for i, value in enumerate(new_hull):
                    writes[record.offset + 3 + i] = value
        users = {}
        for record in system.wand:
            users.setdefault(record.cast_slot, set()).add(
                (faction_of(system.cast[record.cast_slot]), hull_group(record.hull)))
        for slot in sorted(users):
            keys = sorted(users[slot])
            names = None
            for key in keys:
                here = set(n for n in pilot_counts[key] if n.upper() in aids)
                names = here if names is None else names & here
            options = sorted(names)
            old = system.cast[slot]
            if not options:
                continue
            weights = [sum(pilot_counts[key].get(n, 0) for key in keys) for n in options]
            new = weighted_choice(options, weights, rng)
            if new != old:
                raw = new.encode("latin-1")[:8].ljust(8, b"\0")
                for i, value in enumerate(raw):
                    writes[system.cast_offset + 8 * slot + i] = value
    return writes


# ---------------------------------------------------------------------------
# Building and checking the result
# ---------------------------------------------------------------------------

def apply_writes(original, writes):
    result = bytearray(original)
    for offset, value in writes.items():
        result[offset] = value
    return result


def changed_offsets(before, after, start, end):
    """Offsets between start and end where the two differ."""
    return [i for i in range(start, end) if before[i] != after[i]]


def check_result(original, result, sectors, writes):
    """Make sure only the intended bytes changed. Returns a list of problems."""
    problems = []
    if len(result) != len(original):
        problems.append("the archive size changed")
        return problems
    start, end = sectors.base, sectors.base + sectors.size
    if result[:start] != original[:start] or result[end:] != original[end:]:
        problems.append("bytes outside SECTORS.IFF changed")
    for offset in changed_offsets(original, result, start, end):
        if offset not in writes:
            problems.append("an unexpected byte changed at offset %d" % offset)
            break
    return problems


# ---------------------------------------------------------------------------
# The spoiler file, read back from the patched archive
# ---------------------------------------------------------------------------

def spoiler_lines(before, after, settings):
    """The spoiler, made by reading the patched archive back, not from the plan."""
    lines = []
    lines.append("Wing Commander Privateer Randomizer %s" % VERSION)
    lines.append("")
    for label, value in settings:
        lines.append("%s: %s" % (label, value))
    lines.append("")
    pinned, partner = find_pinned_jumps(before)
    lines.append("Jump List ====================")
    lines.append("(every system with its jumps; each link shows up at both ends)")
    lines.append("")
    for system in sorted(after.systems, key=lambda s: s.name.upper()):
        if not system.all_jumps():
            continue
        parts = []
        for jump in sorted(system.all_jumps(), key=lambda j: (j.nav.number if j.nav else 99, j.offset)):
            entry = "%s (%s)" % (system_name(after, jump.dest), jump.nav_text())
            if jump.key() in pinned:
                entry += " [story link kept]"
            parts.append(entry)
        lines.append("%s: %s" % (system.name, ", ".join(parts)))
    spawn_part = spawn_changes(before, after)
    if spawn_part:
        lines.append("")
        lines.append("Spawn Changes ================")
        lines.append("")
        lines.extend(spawn_part)
    return lines


def hull_text(hull):
    return "%s/%s" % (text(hull[:8]), text(hull[8:]))


def spawn_changes(before, after):
    lines = []
    for old, new in zip(before.systems, after.systems):
        changes = []
        for number, (a, b) in enumerate(zip(old.wand, new.wand), 1):
            if a.hull != b.hull:
                where = "Nav %d" % (a.nav_type + 1) if a.nav_type <= 8 else "hidden sphere"
                changes.append("  encounter %d (%s, squad of %d): %s -> %s" % (
                    number, where, a.squad, hull_text(a.hull), hull_text(b.hull)))
        for slot, (a, b) in enumerate(zip(old.cast, new.cast)):
            if a != b:
                changes.append("  pilot slot %d: %s -> %s" % (slot, a, b))
        if changes:
            lines.append("%s:" % new.name)
            lines.extend(changes)
    return lines


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def read_file(path):
    with open(path, "rb") as handle:
        return handle.read()


def write_file_safely(path, data):
    """Write data to path through a temporary file in the same folder, check
    it, and only then put it in place, so a failure never leaves a half
    written file behind."""
    temp = path + ".tmp"
    try:
        with open(temp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if sha256_hex(read_file(temp)) != sha256_hex(data):
            raise OSError("the written copy does not read back the same")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def backup_name(path):
    """PRIV.TRE -> PRIV.ori (the name the first version of this script used)."""
    return os.path.splitext(path)[0] + ".ori"


def identify(sectors):
    """(game, start base code, start base name) for an unmodified archive, else None."""
    return KNOWN_ARCHIVES.get(data_fingerprint(sectors))


def load_original(path, say):
    """The unmodified archive bytes to randomize from, making the backup
    the first time. Raises ArchiveError with a readable message when the
    files are not safe to use."""
    name = os.path.basename(path)
    backup = backup_name(path)
    if not os.access(path, os.W_OK):
        raise ArchiveError("%s is read-only. Clear the read-only flag in its file properties and run again." % name)
    current = read_file(path)
    current_known = identify(Sectors(current))
    if os.path.exists(backup):
        original = read_file(backup)
        if identify(Sectors(original)) is None:
            raise ArchiveError("the backup %s is not an unmodified archive. Put an original %s back in place, "
                               "delete %s and run again." % (os.path.basename(backup), name, os.path.basename(backup)))
        if current_known is not None and current != original:
            raise ArchiveError("%s is unmodified but differs from the backup %s. Delete %s if %s is the copy "
                               "you want to keep, and run again." % (name, os.path.basename(backup),
                                                                    os.path.basename(backup), name))
        if len(current) != len(original):
            raise ArchiveError("%s has a different size than its backup %s, so something else changed it. "
                               "Copy %s over %s to undo that, then run again." % (
                                   name, os.path.basename(backup), os.path.basename(backup), name))
        say("Using the backup %s as the original." % os.path.basename(backup))
        return original
    if current_known is None:
        raise ArchiveError("%s does not hold the unmodified jump and encounter data, and there is no backup "
                           "%s. It may already be randomized or modded. Put the original file back and "
                           "run again." % (name, os.path.basename(backup)))
    write_file_safely(backup, current)
    say("Backup made: %s" % os.path.basename(backup))
    return current


# ---------------------------------------------------------------------------
# The whole run
# ---------------------------------------------------------------------------

def randomize(path, seed, do_jumps, do_spawns, say=print):
    """Randomize the archive at path. Returns the spoiler file name."""
    name = os.path.basename(path)
    original = load_original(path, say)
    before = Sectors(original)
    game, start_base, start_base_name = identify(before)
    start = find_start_system(before, start_base)
    say("%s: %s, %d star systems, a new game starts at %s in %s." % (
        name, game, len(before.systems), start_base_name, before.systems[start].name))

    writes = {}
    if do_jumps:
        writes.update(jump_writes(before, plan_jumps(before, feature_rng(seed, "jumps"))))
    if do_spawns:
        writes.update(plan_spawns(before, feature_rng(seed, "spawns")))
    result = apply_writes(original, writes)

    after = Sectors(result)
    problems = check_result(original, result, before, writes)
    problems += check_jump_map(after, start)
    newgame = reachable(after, start, story_open=False)
    for index in sorted(reachable(before, start, story_open=False) - newgame):
        problems.append("%s can no longer be reached in a new game" % after.systems[index].name)
    if problems:
        raise ArchiveError("the result failed its checks, nothing was written:\n  " + "\n  ".join(problems))

    write_file_safely(path, bytes(result))
    say("%s written." % name)

    patched = Sectors(read_file(path))
    settings = [
        ("Game Seed", seed),
        ("Randomize Jumps?", "YES" if do_jumps else "NO"),
        ("Randomize Spawns?", "YES" if do_spawns else "NO"),
        ("Archive", "%s (%s)" % (name, game)),
        ("Original SHA-256", sha256_hex(original)),
        ("Result SHA-256", sha256_hex(patched.data)),
        ("Start", "%s in %s" % (start_base_name, patched.systems[start].name)),
    ]
    spoiler = "spoiler-%s.txt" % os.path.splitext(name)[0]
    spoiler_path = os.path.join(os.path.dirname(path), spoiler)
    with open(spoiler_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(spoiler_lines(before, patched, settings)) + "\n")
    return spoiler_path


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

def ask(question):
    print(question)
    try:
        return input("> ").strip()
    except EOFError:
        print("")
        print("No answer given, stopping.")
        sys.exit(1)


def yes(answer):
    return answer.upper() in ("Y", "YES")


def choose_archive(arguments):
    """The archive to randomize: the one named on the command line, the one
    in this folder, or, when both PRIV.TRE and RF.TRE are here, the one the
    player picks."""
    if arguments:
        return arguments[0]
    found = [name for name in ("PRIV.TRE", "RF.TRE") if os.path.exists(name)]
    if not found:
        print("Neither PRIV.TRE nor RF.TRE is in this folder (%s)." % os.getcwd())
        print("Run the script from the game folder, or name the archive: python priv-rando.py <path to PRIV.TRE>")
        sys.exit(1)
    if len(found) == 1:
        return found[0]
    while True:
        answer = ask("Both PRIV.TRE (Privateer) and RF.TRE (Righteous Fire) are here. Which one? (PRIV or RF)").upper()
        if answer in ("PRIV", "PRIV.TRE", "P"):
            return "PRIV.TRE"
        if answer in ("RF", "RF.TRE", "R"):
            return "RF.TRE"
        print("Please type PRIV or RF.")


def main(arguments):
    print("Wing Commander Privateer Randomizer Tool %s\n" % VERSION)
    print("This tool keeps an untouched copy of the archive (PRIV.ori or RF.ori) and")
    print("always randomizes from that copy. To undo everything, answer NO to both")
    print("questions, or copy the .ori file back over the .TRE file.")
    ask("Press Enter to continue")

    path = choose_archive(arguments)
    if not os.path.exists(path):
        print("%s not found" % path)
        sys.exit(1)

    seed = ask("Game seed (case insensitive, empty for random seed)").upper()
    if seed == "":
        seed = make_seed()
    do_jumps = yes(ask("Randomize Jumps? (default NO, type Y or YES)"))
    do_spawns = yes(ask("Randomize Spawns? (default NO, type Y or YES)"))

    try:
        spoiler = randomize(path, seed, do_jumps, do_spawns)
    except (ArchiveError, OSError) as error:
        print("")
        print("Stopped: %s" % error)
        sys.exit(1)

    if not do_jumps and not do_spawns:
        print("Nothing randomized: %s is the original again." % os.path.basename(path))
    print("Spoiler written to %s" % os.path.basename(spoiler))
    print(seed)
    print("Randomize Jumps?", "YES" if do_jumps else "NO")
    print("Randomize Spawns?", "YES" if do_spawns else "NO")


if __name__ == "__main__":
    main(sys.argv[1:])
