"""Interior kit and layout markers. Blender axes: x east, y north, z up; glTF turns them into x, z up, -y."""
import bpy
import bmesh
import math

from lib import box, collection

T = 0.25
DOOR_H = 2.7


def quad(name, corners, mat, coll):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bm.faces.new([bm.verts.new(c) for c in corners])
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    mesh.materials.append(mat)
    collection(coll).objects.link(obj)
    return obj


def plane(name, rect, z, mat, coll, holes=()):
    """Flat floor at z over rect, leaving out each hole rect; one face per uncovered cell."""
    x0, y0, x1, y1 = rect
    xs = sorted({x0, x1, *[c for h in holes for c in (h[0], h[2]) if x0 < c < x1]})
    ys = sorted({y0, y1, *[c for h in holes for c in (h[1], h[3]) if y0 < c < y1]})
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    verts = {}

    def vert(x, y):
        if (x, y) not in verts:
            verts[(x, y)] = bm.verts.new((x, y, z))
        return verts[(x, y)]

    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
            if any(h[0] <= cx <= h[2] and h[1] <= cy <= h[3] for h in holes):
                continue
            bm.faces.new((vert(xs[i], ys[j]), vert(xs[i + 1], ys[j]), vert(xs[i + 1], ys[j + 1]), vert(xs[i], ys[j + 1])))
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    mesh.materials.append(mat)
    collection(coll).objects.link(obj)
    return obj


def side_frame(rect, side):
    """origin, along, outward normal, length of one outer side, along running left to right seen from outside."""
    x0, y0, x1, y1 = rect
    if side == "S":
        return (x0, y0), (1, 0), (0, -1), x1 - x0
    if side == "N":
        return (x1, y1), (-1, 0), (0, 1), x1 - x0
    if side == "E":
        return (x1, y0), (0, 1), (1, 0), y1 - y0
    return (x0, y1), (0, -1), (-1, 0), y1 - y0


def face_box(name, frame, u0, u1, z0, z1, d0, d1, mat, coll):
    (ox, oy), (ax, ay), (nx, ny), _ = frame
    xs = [ox + ax * u + nx * d for u in (u0, u1) for d in (d0, d1)]
    ys = [oy + ay * u + ny * d for u in (u0, u1) for d in (d0, d1)]
    return box(name, min(xs), min(ys), z0, max(xs), max(ys), z1, mat, coll)


def walls(name, rect, height, mat, coll, openings=None):
    """Outer walls T thick inside rect. openings: {side: [(u0, u1, top)]}, u along the side seen from outside.
    The wall over an opening is one block up to the full height."""
    openings = openings or {}
    for side in "NSEW":
        frame = side_frame(rect, side)
        length = frame[3]
        trim0 = T if side in "EW" else 0.0
        trim1 = T if side in "EW" else 0.0
        cursor = trim0
        for index, opening in enumerate(sorted(openings.get(side, []))):
            u0, u1, top = opening[:3]
            bottom = opening[3] if len(opening) > 3 else 0.0
            if u0 - cursor > 1e-3:
                face_box(f"{name} wall {side}{index}", frame, cursor, u0, 0.0, height, -T, 0.0, mat, coll)
            if bottom > 1e-3:
                face_box(f"{name} wall {side}{index} under", frame, u0, u1, 0.0, bottom, -T, 0.0, mat, coll)
            face_box(f"{name} wall {side}{index} over", frame, u0, u1, top, height, -T, 0.0, mat, coll)
            cursor = u1
        if length - trim1 - cursor > 1e-3:
            face_box(f"{name} wall {side} end", frame, cursor, length - trim1, 0.0, height, -T, 0.0, mat, coll)


def to_u(rect, side, a):
    """World coordinate along a side (x for N/S, y for E/W) to that side's u."""
    x0, y0, x1, y1 = rect
    return {"S": a - x0, "N": x1 - a, "E": a - y0, "W": y1 - a}[side]


def parapet(name, rect, z0, z1, mat, coll, gaps=None):
    """Low wall on the roof edge, T thick, inside rect; gaps: {side: [(u0, u1)]} left open."""
    gaps = gaps or {}
    for side in "NSEW":
        frame = side_frame(rect, side)
        length = frame[3]
        start = T if side in "EW" else 0.0
        end = length - (T if side in "EW" else 0.0)
        cursor = start
        for index, (u0, u1) in enumerate(sorted(gaps.get(side, []))):
            u0, u1 = max(u0, start), min(u1, end)
            if u0 - cursor > 1e-3:
                face_box(f"{name} parapet {side}{index}", frame, cursor, u0, z0, z1, -T, 0.0, mat, coll)
            cursor = max(cursor, u1)
        if end - cursor > 1e-3:
            face_box(f"{name} parapet {side} end", frame, cursor, end, z0, z1, -T, 0.0, mat, coll)


def roof_gaps(name, rect, top, walkable, landings):
    """Parapet gaps for a walkable roof: edges shared with another walkable roof at the same height,
    plus landings [(x, y) point on the edge, half width]."""
    gaps = {"N": [], "S": [], "E": [], "W": []}
    x0, y0, x1, y1 = rect
    for other_name, (a0, b0, a1, b1), other_top in walkable:
        if other_name == name or abs(other_top - top) > 1e-3:
            continue
        if abs(b0 - y1) < 1e-3 or abs(b1 - y0) < 1e-3:
            lo, hi = max(a0, x0), min(a1, x1)
            if hi - lo > 0.1:
                side = "N" if abs(b0 - y1) < 1e-3 else "S"
                u = sorted((to_u(rect, side, lo), to_u(rect, side, hi)))
                gaps[side].append((u[0] - T, u[1] + T))
        if abs(a0 - x1) < 1e-3 or abs(a1 - x0) < 1e-3:
            lo, hi = max(b0, y0), min(b1, y1)
            if hi - lo > 0.1:
                side = "E" if abs(a0 - x1) < 1e-3 else "W"
                u = sorted((to_u(rect, side, lo), to_u(rect, side, hi)))
                gaps[side].append((u[0] - T, u[1] + T))
    for (px, py), half in landings:
        for side, on_edge, along in (("N", abs(py - y1) < 0.05, px), ("S", abs(py - y0) < 0.05, px),
                                     ("E", abs(px - x1) < 0.05, py), ("W", abs(px - x0) < 0.05, py)):
            if on_edge and ((side in "NS" and x0 <= px <= x1) or (side in "EW" and y0 <= py <= y1)):
                u = to_u(rect, side, along)
                gaps[side].append((u - half, u + half))
    return gaps


TREAD = 0.4
MAX_RISE = 0.235
# Residents check the ground 0.4 m to each side of every step; 1.6 m always leaves a line whose sides stay on the treads.
STAIR_WIDTH = 1.6


def stair_run(rise):
    """Length a stair needs: 0.4 m treads (one per grid sample) and risers no taller than the 0.25 m step residents take."""
    return math.ceil(rise / MAX_RISE) * TREAD


def step_box(name, x0, y0, z0, x1, y1, z1, mat, coll):
    """Box without a bottom face: a step's underside would otherwise read as a floor under the first tread."""
    obj = box(name, x0, y0, z0, x1, y1, z1, mat, coll)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bottom = [f for f in bm.faces if f.normal.z < -0.5]
    bmesh.ops.delete(bm, geom=bottom, context="FACES_ONLY")
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def stair(name, x0, y0, x1, y1, z0, z1, rising, mat, coll, base=None):
    """Solid stair inside the rect, climbing from z0 to z1 toward `rising` (N, S, E or W); every step reaches down to base (z0 by default).
    One riser per 0.4 m tread, so the rect's run decides the step count."""
    base = z0 if base is None else base
    run = (y1 - y0) if rising in "NS" else (x1 - x0)
    width = (x1 - x0) if rising in "NS" else (y1 - y0)
    assert width >= STAIR_WIDTH - 1e-6, f"{name}: {width:.2f} m is narrower than {STAIR_WIDTH} m"
    count = max(1, round(run / TREAD))
    assert (z1 - z0) / count <= 0.25 + 1e-6, f"{name}: {run:.2f} m run is too short for {z1 - z0:.2f} m"
    for k in range(count):
        t0, t1 = k / count, (k + 1) / count
        top = z0 + (z1 - z0) * (k + 1) / count
        if rising == "N":
            step_box(f"{name} {k + 1}", x0, y0 + (y1 - y0) * t0, base, x1, y0 + (y1 - y0) * t1, top, mat, coll)
        elif rising == "S":
            step_box(f"{name} {k + 1}", x0, y1 - (y1 - y0) * t1, base, x1, y1 - (y1 - y0) * t0, top, mat, coll)
        elif rising == "E":
            step_box(f"{name} {k + 1}", x0 + (x1 - x0) * t0, y0, base, x0 + (x1 - x0) * t1, y1, top, mat, coll)
        else:
            step_box(f"{name} {k + 1}", x1 - (x1 - x0) * t1, y0, base, x1 - (x1 - x0) * t0, y1, top, mat, coll)


def sawtooth_roof(name, rect, z, mat, coll, pitch=1.6, rise=1.1):
    """Row of steep ridges over rect along x; every face is steeper than 45 degrees, so none of it can be walked on."""
    x0, y0, x1, y1 = rect
    count = max(1, round((y1 - y0) / pitch))
    span = (y1 - y0) / count
    for k in range(count):
        a, b = y0 + k * span, y0 + (k + 1) * span
        m = (a + b) / 2
        quad(f"{name} ridge {k} S", [(x0, a, z), (x1, a, z), (x1, m, z + rise), (x0, m, z + rise)], mat, coll)
        quad(f"{name} ridge {k} N", [(x1, b, z), (x0, b, z), (x0, m, z + rise), (x1, m, z + rise)], mat, coll)
        quad(f"{name} ridge {k} W", [(x0, a, z), (x0, m, z + rise), (x0, b, z)], mat, coll)
        quad(f"{name} ridge {k} E", [(x1, b, z), (x1, m, z + rise), (x1, a, z)], mat, coll)


MARKERS = "Markers"


def empty(name, location, vera, parent=None, rotation_z=0.0):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.4
    collection(MARKERS).objects.link(obj)
    if parent is not None:
        obj.parent = parent
        px, py, pz = parent.location
        obj.location = (location[0] - px, location[1] - py, location[2] - pz)
    else:
        obj.location = location
    obj.rotation_euler = (0.0, 0.0, rotation_z)
    obj["vera"] = vera
    return obj


def floor_marker(fid, name, min_y, max_y):
    return empty(f"Floor.{fid}", (0.0, 0.0, 0.0), {"type": "floor", "id": fid, "name": name, "minY": min_y, "maxY": max_y})


def zone(zid, name, description, floor, rect, z, entry, height=3.6, parent=None, private=False, secret=False, access=None):
    """Zone over rect at floor height z; outline is in the zone's local glTF x and z (z = -y)."""
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    outline = [[x0 - cx, -(y0 - cy)], [x1 - cx, -(y0 - cy)], [x1 - cx, -(y1 - cy)], [x0 - cx, -(y1 - cy)]]
    vera = {"type": "zone", "id": zid, "name": name, "description": description, "floor": floor,
            "outline": outline, "minY": -0.6, "maxY": height}
    if parent:
        vera["parent"] = parent
    if private:
        vera["private"] = True
    if secret:
        vera["secret"] = True
    if access:
        vera["access"] = list(access)
    node = empty(f"Zone.{zid}", (cx, cy, z), vera)
    empty(f"Zone.{zid}.Entry", (entry[0], entry[1], z), {"type": "entry"}, parent=node)
    return node


def facing_rotation(facing_deg):
    """Empty rotation whose glTF facing (local +Z, Blender local -Y) points at facing_deg, counted from +x toward +y."""
    return math.radians(facing_deg + 90.0)


ACTIVITY_POSES = {
    "grab": ["buy-a-drink", "buy-snacks", "buy-a-cold-drink", "buy-a-book", "buy-parts", "buy-flowers", "buy-paper", "take-a-paper", "buy-tokens",
             "buy-a-tape", "buy-clothes", "buy-spray-paint", "buy-a-ticket", "take-key", "pick-clothes", "pick-materials", "restock", "drop-coin",
             "post-a-letter", "post", "pin-a-note", "search-letters", "search-logs", "pawn", "buy-something", "make-change", "tend-plants", "open-drawer",
             "pick-up-the-photo", "put-on-a-record", "order"],
    "thinking": ["browse", "read-the-board", "read-menu", "read-timetable", "inspect", "study-sketches", "look-at-hardware", "listen-daemon", "check-the-mirror",
                 "monitor", "wish", "look-down", "look-out", "sketch", "tend-clock", "maintain", "listen-to-a-tape", "watch-alley"],
    "use_phone": ["make-a-call", "answer-the-phone", "dial", "run-board"],
    "drink": ["drink", "drink-standing", "drink-coffee"],
    "talk": ["gossip", "talk", "haggle"],
    "swishing": ["headbang"],
    "peace": ["take-photos"],
    "annoyed": ["guard"],
}
POSE_FOR_ACTIVITY = {aid: pose for pose, aids in ACTIVITY_POSES.items() for aid in aids}
POURED = ("bar", "espresso", "scoop", "noodle", "taqueria", "kitchen")


def with_pose(oid, activity):
    """Gives an activity the pose its doer plays, unless it already names one."""
    a = dict(activity)
    if "pose" not in a:
        pose = POSE_FOR_ACTIVITY.get(a["id"])
        if a["id"] in ("serve", "brew", "cook") and any(word in oid for word in POURED):
            pose = "mix_drink"
        if pose:
            a["pose"] = pose
    return a


def thing(oid, name, description, location, spots=()):
    """Object marker with spots: (spot id, (x, y, z), facing degrees, activities[, capacity])."""
    node = empty(f"Object.{oid}", location, {"type": "object", "id": oid, "name": name, "description": description})
    for spot in spots:
        sid, position, facing, activities = spot[:4]
        vera = {"type": "spot", "id": sid, "activities": [with_pose(oid, a) for a in activities]}
        if len(spot) > 4:
            vera["capacity"] = spot[4]
        empty(f"Spot.{sid}", position, vera, parent=node, rotation_z=facing_rotation(facing))
    return node


SIT = {"id": "sit", "name": "Sit", "posture": "sitting"}
STAND = {"id": "stand", "name": "Stand"}
LIE = {"id": "sleep", "name": "Sleep", "posture": "lying"}


def act(aid, name, posture=None):
    a = {"id": aid, "name": name}
    if posture:
        a["posture"] = posture
    return a


def passage(pid, name, location, facing_deg, radius=None):
    """Passage marker; arrivals step out one metre along facing_deg."""
    vera = {"type": "passage", "id": pid, "name": name}
    if radius is not None:
        vera["radius"] = radius
    return empty(f"Passage.{pid}", location, vera, rotation_z=facing_rotation(facing_deg))
