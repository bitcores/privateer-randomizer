"""Self-test for priv-rando.py. Needs no game data.

Run it from any folder:

    python selftest.py

It builds a small made-up archive with the same layout as the game's
(a .TRE file table, SECTORS.IFF with its system table, LABL / NAME, SPHR,
CAST, WAND, JUMP, OJMP and OBJT chunks) and checks the archive walk, the
jump shuffle, the spawn shuffle, the seeds, the whole run on files and the
spoiler. Every check is a plain assert; the last line says how it went.
"""

import ast
import importlib.util
import os
import random
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "priv-rando.py")
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("priv_rando", SCRIPT)
rando = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rando)


# ---------------------------------------------------------------------------
# Building a made-up archive
# ---------------------------------------------------------------------------

def chunk(tag, payload):
    data = tag + struct.pack(">I", len(payload)) + payload
    return data + (b"\0" if len(payload) % 2 else b"")


def form(form_type, children):
    payload = form_type + b"".join(children)
    return b"FORM" + struct.pack(">I", len(payload)) + payload


def name8(name):
    return name.encode("latin-1").ljust(8, b"\0")


def jump_record(index, local, slot, dest):
    rec = bytearray(46)
    struct.pack_into("<H", rec, 0, local)
    rec[2:18] = b"JUMPTYPEJUMP\0\0\0\0"
    struct.pack_into("<H", rec, 18, local)
    rec[20] = slot
    rec[21] = index
    rec[34:45] = bytes([0xFF, 0xFF, 0x01] + [0xFF] * 8)
    rec[45] = dest
    return bytes(rec)


def sphr_record(index, type_, tail):
    rec = bytearray(19)
    rec[0] = type_
    rec[1] = index
    rec[14:19] = bytes(tail)
    return bytes(rec)


def wand_record(index, number, hull, cast_slot, nav_type, squad):
    rec = bytearray(46)
    rec[0] = 100
    rec[1] = number
    rec[3:19] = hull
    struct.pack_into("<H", rec, 19, cast_slot)
    rec[21] = nav_type
    struct.pack_into("<H", rec, 22, index)
    rec[35] = squad
    return bytes(rec)


HULLS = {
    "MIL": [b"GLADTYPEGLADIUS\0", b"TALNTYPETALMIL\0\0"],
    "PIR": [b"PIRATYPETALPIR\0\0", b"TALNWIMPTALPIR\0\0"],
    "CON": [b"PARATYPEFRIGATE\0", b"BRODTYPEBRDSWORD", b"STILTYPESTILETTO"],
}


def system_block(index, spec):
    """One system. spec: name, opens_with_name, jumps [(chunk, dest, shown)],
    base (base code or None), encounters [(faction, hull, cast slot, squad)]."""
    sphr = []
    jumps = []
    ojumps = []
    slot = 0
    for number, (kind, dest, shown) in enumerate(spec["jumps"], 1):
        if shown:
            rec = jump_record(index, number, slot, dest)
            sphr.append(sphr_record(index, slot + 10, [0xD0, 0x07, 2, dest, slot + 1]))
            sphr.append(sphr_record(index, slot, [0xE0, 0x2E, 0xFF, 0xFF, 0xFF]))
            slot += 1
        else:
            rec = jump_record(index, number, 15, dest)  # a jump with no nav point
            sphr.append(sphr_record(index, 15, [0xE0, 0x2E, 0xFF, 0xFF, 0xFF]))
        (ojumps if kind == "OJMP" else jumps).append(rec)
    if spec.get("base") is not None:
        sphr.append(sphr_record(index, slot + 10, [0xD0, 0x07, 1, spec["base"], slot + 1]))
        sphr.append(sphr_record(index, slot, [0xE0, 0x2E, 0xFF, 0xFF, 0xFF]))
    cast = [name8("PLAYER")] + [name8("JMP%d" % i) for i in range(len(spec["jumps"]))]
    wand = []
    objt = [b"NTRNTYPE"]
    for number, (faction, hull, pilot, squad) in enumerate(spec.get("encounters", []), 1):
        wand.append(wand_record(index, number, hull, pilot, 0, squad))
        if hull[:8] not in objt:
            objt.append(hull[:8])
    pilots = spec.get("pilots", [])
    cast += [name8(p) for p in pilots]
    names = []
    if spec.get("opens_with_name"):
        names.append(chunk(b"NAME", b"?\0"))
    names.append(chunk(b"LABL", spec["name"].encode("latin-1") + b"\0"))
    part = [chunk(b"CNST", b"\0" * 4)]
    if wand:
        part.append(chunk(b"WAND", b"".join(wand)))
    part.append(chunk(b"JUMP", b"".join(jumps)))
    if ojumps:
        part.append(chunk(b"OJMP", b"".join(ojumps)))
    body = names + [
        chunk(b"RACE", b"\x04\xff"),
        chunk(b"SPHR", b"".join(sphr)),
        form(b"SCRP", [chunk(b"CAST", b"".join(cast)), form(b"PART", part)]),
        form(b"LOAD", [chunk(b"OBJT", b"".join(objt))]),
    ]
    sctr = form(b"SCTR", body)
    return struct.pack("<I", len(sctr)) + sctr


def build_sectors(specs):
    blocks = [system_block(i, s) for i, s in enumerate(specs)]
    table_size = 4 * len(blocks)
    first = 12 + 8 + table_size  # FORM header, form type, TABL header, table
    offsets = []
    pos = first
    for block in blocks:
        offsets.append(pos)
        pos += len(block)
    table = chunk(b"TABL", struct.pack("<%dI" % len(offsets), *offsets))
    payload = b"SSSS" + table + b"".join(blocks)
    return b"FORM" + struct.pack(">I", len(payload)) + payload


def build_tre(files):
    """files: [(name, bytes)] -> the bytes of a .TRE archive."""
    table_end = 8 + 74 * len(files)
    data = b""
    table = b""
    pos = table_end
    for name, content in files:
        table += b"\x01" + name.encode("latin-1").ljust(65, b"\0") + struct.pack("<II", pos, len(content))
        data += content
        pos += len(content)
    return struct.pack("<II", len(files), table_end) + table + data


def pilot_names():
    return ["MIL_DA", "MIL_AA", "PIR_SF", "PIR_DA", "CON_DP", "CON_AA", "CON_SA"]


def encounters():
    # (faction, hull, cast slot, squad); slots counted after PLAYER and the JMP names
    return [("MIL", HULLS["MIL"][0], 0, 2), ("MIL", HULLS["MIL"][1], 1, 1), ("PIR", HULLS["PIR"][0], 2, 3),
            ("PIR", HULLS["PIR"][1], 2, 1), ("CON", HULLS["CON"][0], 4, 1), ("CON", HULLS["CON"][1], 5, 1),
            ("CON", HULLS["CON"][2], 6, 4)]


def universe():
    """A made-up map: Home (start, base code 0), seven ordinary systems in a
    ring with chords, Gate with a story jump (OJMP) into Locked, Locked with a
    jump back and a hidden jump (no nav point) to Two, and Named, whose block
    opens with a NAME chunk like Valhalla's."""
    links = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 9), (9, 0), (0, 3), (1, 5), (7, 4), (6, 2)]
    names = ["Home", "One", "Two", "Three", "Four", "Five", "Six", "Gate", "Locked", "Named"]
    specs = [{"name": n, "jumps": [], "pilots": pilot_names()} for n in names]
    for a, b in links:
        specs[a]["jumps"].append(("JUMP", b, True))
        specs[b]["jumps"].append(("JUMP", a, True))
    specs[7]["jumps"].append(("OJMP", 8, True))
    specs[8]["jumps"].append(("JUMP", 7, True))
    specs[8]["jumps"].append(("JUMP", 2, False))
    specs[2]["jumps"].append(("JUMP", 8, False))
    specs[0]["base"] = 0
    specs[9]["opens_with_name"] = True
    for i, s in enumerate(specs):
        if i != 8:
            n = len(s["jumps"]) + 1  # CAST: PLAYER, one JMP name per jump, then the pilots
            s["encounters"] = [(f, h, n + slot, squad) for f, h, slot, squad in encounters()]
    return specs


def make_archive():
    sectors = build_sectors(universe())
    return build_tre([("..\\..\\DATA\\AIDS\\%s.IFF" % p, b"FORM") for p in pilot_names()] +
                     [("..\\..\\DATA\\SECTORS\\SECTORS.IFF", sectors), ("..\\..\\DATA\\OTHER.IFF", b"x" * 33)])


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def links_of(sectors):
    return sorted((j.system, j.dest, j.chunk) for s in sectors.systems for j in s.all_jumps())


def test_archive_walk():
    data = make_archive()
    sectors = rando.Sectors(data)
    names = [s.name for s in sectors.systems]
    assert names == ["Home", "One", "Two", "Three", "Four", "Five", "Six", "Gate", "Locked", "Named"], names
    assert len(sectors.systems[9].jumps) == 2  # the NAME-first block is read like any other
    assert [j.dest for j in sectors.systems[7].ojumps] == [8]
    hidden = [j for j in sectors.systems[2].jumps if j.nav is None]
    assert len(hidden) == 1 and hidden[0].dest == 8
    for system in sectors.systems:
        for jump in system.all_jumps():
            if jump.nav is not None:
                assert jump.nav.target == jump.dest
    assert rando.check_jump_map(sectors, 0) == []
    assert rando.find_start_system(sectors, 0) == 0
    assert "MIL_DA" in sectors.aids_names()
    # broken archives are refused with ArchiveError, never another exception
    for broken in (data[:5], data[:300], b"\0" * 64, data[:len(data) - 40]):
        try:
            rando.Sectors(broken)
        except rando.ArchiveError:
            pass
        else:
            raise AssertionError("a broken archive was accepted")
    damaged = bytearray(data)
    pos = bytes(damaged).find(b"JUMPTYPEJUMP")
    damaged[pos] = ord("X")
    try:
        rando.Sectors(bytes(damaged))
    except rando.ArchiveError:
        pass
    else:
        raise AssertionError("a damaged jump record was accepted")


def check_map(links, degrees, forbidden=()):
    count = {}
    seen = set()
    for a, b in links:
        assert a != b, "self link"
        assert frozenset((a, b)) not in seen, "double link"
        assert frozenset((a, b)) not in forbidden, "forbidden link"
        seen.add(frozenset((a, b)))
        count[a] = count.get(a, 0) + 1
        count[b] = count.get(b, 0) + 1
    assert count == dict((n, d) for n, d in degrees.items() if d), "slot counts changed"
    nodes = list(count)
    reached = set([nodes[0]])
    todo = [nodes[0]]
    while todo:
        n = todo.pop()
        for a, b in links:
            for x, y in ((a, b), (b, a)):
                if x == n and y not in reached:
                    reached.add(y)
                    todo.append(y)
    assert reached == set(nodes), "map not connected"


def test_connected_map():
    maker = random.Random(1234)
    for seed in range(1000):
        n = maker.randint(3, 40)
        degrees = dict((i, min(n - 1, maker.choice([1, 1, 2, 2, 3, 4, 6]))) for i in range(n))
        while sum(degrees.values()) % 2 or sum(degrees.values()) < 2 * (n - 1) \
                or not rando.is_graphical(list(degrees.values())):
            node = maker.randrange(n)
            if degrees[node] < n - 1:
                degrees[node] += 1
        links = rando.random_connected_map(degrees, rando.feature_rng("S%d" % seed, "jumps"))
        check_map(links, degrees)
        again = rando.random_connected_map(degrees, rando.feature_rng("S%d" % seed, "jumps"))
        assert links == again, "not the same result for the same seed"
    # impossible slot counts are refused, never answered with a broken map
    for degrees in ({0: 1, 1: 1, 2: 1, 3: 1}, {0: 3, 1: 1}, {0: 2}):
        try:
            rando.random_connected_map(degrees, random.Random(1))
        except ValueError:
            pass
        else:
            raise AssertionError("impossible slot counts were accepted: %r" % degrees)


def test_jump_plan():
    data = make_archive()
    before = rando.Sectors(data)
    pinned, partner = rando.find_pinned_jumps(before)
    pinned_systems = sorted(set(rando.jump_by_key(before, k).system for k in pinned))
    assert pinned_systems == [2, 7, 8], pinned_systems
    results = set()
    for seed in range(1000):
        new_dest = rando.plan_jumps(before, rando.feature_rng("SEED%d" % seed, "jumps"))
        assert not set(new_dest) & set(pinned), "a pinned jump was planned"
        writes = rando.jump_writes(before, new_dest)
        result = rando.apply_writes(data, writes)
        after = rando.Sectors(bytes(result))
        assert rando.check_result(data, result, before, writes) == []
        assert rando.check_jump_map(after, 0) == [], rando.check_jump_map(after, 0)
        for key in pinned:
            j = rando.jump_by_key(before, key)
            assert result[j.offset:j.offset + 46] == data[j.offset:j.offset + 46]
        for old, new in zip(before.systems, after.systems):
            assert len(old.jumps) == len(new.jumps) and len(old.ojumps) == len(new.ojumps)
        assert rando.reachable(before, 0, story_open=False) <= rando.reachable(after, 0, story_open=False)
        assert 8 not in [j.dest for s in after.systems for j in s.jumps if j.nav is not None and s.index != 7]
        results.add(tuple(links_of(after)))
    assert len(results) > 100, "the shuffle hardly varies"


def test_spawn_plan():
    data = make_archive()
    before = rando.Sectors(data)
    for seed in range(200):
        writes = rando.plan_spawns(before, rando.feature_rng("SEED%d" % seed, "spawns"))
        result = rando.apply_writes(data, writes)
        after = rando.Sectors(bytes(result))
        assert rando.check_result(data, result, before, writes) == []
        for old, new in zip(before.systems, after.systems):
            capital_before = sum(1 for r in old.wand if r.hull_type() in rando.CAPITAL_HULLS)
            capital_after = sum(1 for r in new.wand if r.hull_type() in rando.CAPITAL_HULLS)
            assert capital_before == capital_after
            for a, b in zip(old.wand, new.wand):
                assert a.squad == b.squad and a.cast_slot == b.cast_slot
                assert rando.faction_of(old.cast[a.cast_slot]) == rando.faction_of(new.cast[b.cast_slot])
                assert b.hull in HULLS[rando.faction_of(new.cast[b.cast_slot])]
            for name in new.cast[1 + len(new.all_jumps()):]:
                assert name.upper() in before.aids_names(), name
            assert new.cast[:1 + len(new.all_jumps())] == old.cast[:1 + len(old.all_jumps())]


def test_seeds():
    a = rando.feature_rng("ABC123", "jumps")
    b = rando.feature_rng("ABC123", "jumps")
    c = rando.feature_rng("ABC123", "spawns")
    first = [a.randrange(1000000) for _ in range(5)]
    assert first == [b.randrange(1000000) for _ in range(5)]
    assert first != [c.randrange(1000000) for _ in range(5)]
    # The derivation is fixed: SHA-256("ABC123/jumps"), first 16 bytes, big-endian,
    # into random.Random. These numbers must never change between versions.
    assert first == [601786, 363183, 163052, 630135, 258450], first
    seed = rando.make_seed()
    assert len(seed) == 12 and seed.isalnum() and seed.upper() == seed


def parse_spoiler_jumps(lines):
    jumps = {}
    inside = False
    for line in lines:
        if line.startswith("Jump List"):
            inside = True
            continue
        if line.startswith("Spawn Changes"):
            break
        if inside and ": " in line and not line.startswith("("):
            name, rest = line.split(": ", 1)
            jumps[name] = sorted(part.split(" (")[0] for part in rest.split(", "))
    return jumps


def test_whole_run():
    data = make_archive()
    fingerprint = rando.data_fingerprint(rando.Sectors(data))
    rando.KNOWN_ARCHIVES[fingerprint] = ("Test game", 0, "Home Base")
    quiet = lambda message: None
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "TEST.TRE")
        with open(path, "wb") as handle:
            handle.write(data)

        spoiler = rando.randomize(path, "SEED1", True, False, say=quiet)
        jumps_only = rando.read_file(path)
        assert rando.read_file(os.path.join(folder, "TEST.ori")) == data
        assert len(jumps_only) == len(data) and jumps_only != data

        rando.randomize(path, "SEED1", True, True, say=quiet)
        both = rando.read_file(path)
        jump_bytes = lambda raw: links_of(rando.Sectors(raw))
        assert jump_bytes(both) == jump_bytes(jumps_only), "turning spawns on changed the jumps"

        # the spoiler is read back from the archive on disk
        with open(spoiler) as handle:
            lines = handle.read().splitlines()
        after = rando.Sectors(both)
        expected = dict((s.name, sorted(rando.system_name(after, j.dest) for j in s.all_jumps()))
                        for s in after.systems if s.all_jumps())
        assert parse_spoiler_jumps(lines) == expected, (parse_spoiler_jumps(lines), expected)
        assert "Game Seed: SEED1" in lines
        assert "Original SHA-256: %s" % rando.sha256_hex(data) in lines

        # same seed, same result
        rando.randomize(path, "SEED1", True, True, say=quiet)
        assert rando.read_file(path) == both

        # both answers NO puts the original back
        rando.randomize(path, "SEED1", False, False, say=quiet)
        assert rando.read_file(path) == data

        # an archive that was changed and has no backup is refused
        os.replace(os.path.join(folder, "TEST.ori"), os.path.join(folder, "kept.bin"))
        with open(path, "wb") as handle:
            handle.write(both)
        try:
            rando.randomize(path, "SEED2", True, False, say=quiet)
        except rando.ArchiveError:
            pass
        else:
            raise AssertionError("a randomized archive without a backup was accepted")
        assert rando.read_file(path) == both
        assert not os.path.exists(path + ".tmp")
    del rando.KNOWN_ARCHIVES[fingerprint]


def test_python_38_syntax():
    with open(SCRIPT, encoding="utf-8") as handle:
        source = handle.read()
    ast.parse(source, feature_version=(3, 8))
    assert chr(0x2014) not in source and chr(0x2013) not in source  # no long dashes


def main():
    tests = [test_archive_walk, test_connected_map, test_jump_plan, test_spawn_plan, test_seeds,
             test_whole_run, test_python_38_syntax]
    for test in tests:
        test()
        print("ok   %s" % test.__name__)
    print("All %d self-tests passed." % len(tests))

if __name__ == "__main__":
    main()
