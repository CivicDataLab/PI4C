"""Fill the database with demo reports around Visakhapatnam (GVMC) for trying out the dashboard.

    uv run python scripts/seed_demo.py               # add 100 demo reports
    uv run python scripts/seed_demo.py --count 50
    uv run python scripts/seed_demo.py --add-photos  # give photos to demo reports that have none
    uv run python scripts/seed_demo.py --clear       # remove every demo report (real reports are untouched)

Demo reports have channel "demo", so they are easy to find and remove. They look like what the
bot produces with the rules classifier: no confidence score, no AI summary, no translation.
About four in five get a photo from data/demo_photos/ (one or two per issue type, reused;
see data/demo_photos/CREDITS.md).
"""

import argparse
import hashlib
import math
import random
import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Cluster, Media, MediaFile, Report, utcnow  # noqa: E402
from app import taxonomy  # noqa: E402

DEMO_CHANNEL = "demo"
PHOTO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo_photos"
PHOTO_RATE = 0.8  # share of demo reports that get a photo

# Localities across GVMC with approximate centres (lat, lon).
LOCALITIES = [
    ("RK Beach", 17.7146, 83.3237), ("Jagadamba Junction", 17.7114, 83.3015),
    ("Dwaraka Nagar", 17.7290, 83.3080), ("MVP Colony", 17.7425, 83.3360),
    ("Gajuwaka", 17.6868, 83.2100), ("Madhurawada", 17.8055, 83.3570),
    ("Seethammadhara", 17.7400, 83.3100), ("Akkayyapalem", 17.7310, 83.2940),
    ("Maddilapalem", 17.7380, 83.3220), ("Simhachalam", 17.7666, 83.2500),
    ("Pendurthi", 17.8110, 83.2050), ("Kancharapalem", 17.7280, 83.2770),
    ("NAD Junction", 17.7480, 83.2380), ("Gopalapatnam", 17.7500, 83.2250),
    ("Rushikonda", 17.7820, 83.3850), ("Yendada", 17.7720, 83.3640),
    ("Arilova", 17.7600, 83.3200), ("Ukkunagaram", 17.6280, 83.1650),
    ("Anakapalle", 17.6913, 83.0037), ("Bheemunipatnam", 17.8900, 83.4500),
    ("One Town", 17.6960, 83.2960), ("Asilmetta", 17.7220, 83.3080),
    ("Siripuram", 17.7220, 83.3170), ("Lawsons Bay Colony", 17.7330, 83.3330),
    ("Kurmannapalem", 17.6890, 83.1690), ("Sheela Nagar", 17.7110, 83.2210),
    ("Marripalem", 17.7440, 83.2630), ("Isukathota", 17.7500, 83.3300),
    ("PM Palem", 17.7960, 83.3530), ("Kailasagiri", 17.7480, 83.3420),
]

# (English, Telugu) descriptions a resident might type, per sub-category.
DESCRIPTIONS = {
    ("accessibility", "footpath"): [
        ("Footpath is broken and full of holes, wheelchair cannot pass", "ఫుట్‌పాత్ పగిలిపోయి గుంతలతో ఉంది, వీల్‌చైర్ వెళ్ళలేదు"),
        ("Shops have encroached the footpath, we have to walk on the road", "దుకాణాలు ఫుట్‌పాత్‌ను ఆక్రమించాయి, రోడ్డు మీద నడవాల్సి వస్తోంది"),
    ],
    ("accessibility", "ramp"): [
        ("No ramp at the ward office entrance", "వార్డు కార్యాలయం ప్రవేశం వద్ద ర్యాంప్ లేదు"),
        ("Ramp is too steep and has no railing", "ర్యాంప్ చాలా ఏటవాలుగా ఉంది, పట్టుకోవడానికి రెయిలింగ్ లేదు"),
    ],
    ("accessibility", "kerb"): [
        ("Kerb is very high, no lowered kerb to get down", "అంచు చాలా ఎత్తుగా ఉంది, దిగడానికి దారి లేదు"),
    ],
    ("accessibility", "crossing"): [
        ("No zebra crossing or signal near the school", "స్కూల్ దగ్గర జీబ్రా క్రాసింగ్ గానీ సిగ్నల్ గానీ లేదు"),
        ("Signal time is too short for elderly people to cross", "వృద్ధులు దాటడానికి సిగ్నల్ సమయం సరిపోవడం లేదు"),
    ],
    ("accessibility", "toilet"): [
        ("Public toilet has no accessible cubicle", "పబ్లిక్ టాయిలెట్‌లో వికలాంగులకు అనువైన గది లేదు"),
        ("Accessible toilet is locked all the time", "అందుబాటు టాయిలెట్ ఎప్పుడూ తాళం వేసి ఉంటుంది"),
    ],
    ("accessibility", "transport"): [
        ("Bus shelter has a high step, cannot board with wheelchair", "బస్ షెల్టర్ వద్ద ఎత్తైన మెట్టు ఉంది, వీల్‌చైర్‌తో ఎక్కలేము"),
    ],
    ("accessibility", "building"): [
        ("Only stairs at the hospital entrance, no lift or ramp", "ఆసుపత్రి ప్రవేశం వద్ద మెట్లు మాత్రమే ఉన్నాయి, లిఫ్ట్ లేదా ర్యాంప్ లేదు"),
    ],
    ("accessibility", "other"): [
        ("Tactile paving on the footpath is damaged", "ఫుట్‌పాత్ మీద దృష్టిలోపం ఉన్నవారి కోసం వేసిన టైల్స్ పాడయ్యాయి"),
    ],
    ("civic", "water"): [
        ("No drinking water supply for three days", "మూడు రోజులుగా తాగునీటి సరఫరా లేదు"),
        ("Pipe leaking on the main road, water wasted", "మెయిన్ రోడ్డు మీద పైప్ లీక్ అవుతోంది, నీళ్ళు వృథా అవుతున్నాయి"),
        ("Tap water is muddy and smells bad", "కుళాయి నీళ్ళు బురదగా ఉన్నాయి, దుర్వాసన వస్తోంది"),
    ],
    ("civic", "drainage"): [
        ("Drain is blocked and sewage is overflowing on the road", "డ్రైనేజీ మూసుకుపోయి మురుగునీరు రోడ్డు మీద పొంగుతోంది"),
        ("Open drain without cover, dangerous for children", "మూత లేని డ్రైనేజీ, పిల్లలకు ప్రమాదకరం"),
    ],
    ("civic", "garbage"): [
        ("Garbage not collected for a week", "వారం రోజులుగా చెత్త తీయడం లేదు"),
        ("Garbage dumped next to the bus stop", "బస్ స్టాప్ పక్కన చెత్త పోస్తున్నారు"),
    ],
    ("civic", "streetlight"): [
        ("Streetlights not working, very dark at night", "వీధి దీపాలు పని చేయడం లేదు, రాత్రి చాలా చీకటిగా ఉంది"),
        ("Streetlight pole is leaning and wires are hanging", "వీధి దీపం స్తంభం వంగిపోయింది, వైర్లు వేలాడుతున్నాయి"),
    ],
    ("civic", "road"): [
        ("Big pothole in the middle of the road", "రోడ్డు మధ్యలో పెద్ద గుంత ఉంది"),
        ("Road dug up for pipeline work and never repaired", "పైప్‌లైన్ పని కోసం రోడ్డు తవ్వి మళ్ళీ వేయలేదు"),
    ],
    ("civic", "other"): [
        ("Stray dogs attacking people in the colony", "కాలనీలో వీధి కుక్కలు జనాల మీద దాడి చేస్తున్నాయి"),
    ],
    ("disaster", "flooding"): [
        ("Water logging after rain, houses flooded", "వర్షం తర్వాత నీరు నిలిచిపోయింది, ఇళ్ళలోకి నీళ్ళు వచ్చాయి"),
        ("Underpass is flooded, vehicles stuck", "అండర్‌పాస్ నీటితో నిండిపోయింది, వాహనాలు ఇరుక్కుపోయాయి"),
    ],
    ("disaster", "storm"): [
        ("Tree fell on the road after the storm", "తుఫాను తర్వాత చెట్టు రోడ్డు మీద పడిపోయింది"),
        ("Roof sheets blown away, family has no shelter", "గాలికి రేకులు ఎగిరిపోయాయి, కుటుంబానికి నీడ లేదు"),
    ],
    ("disaster", "heat"): [
        ("No drinking water point at the bus stand in this heat", "ఈ ఎండలో బస్ స్టాండ్ వద్ద తాగునీటి సౌకర్యం లేదు"),
    ],
    ("disaster", "shelter"): [
        ("Relief camp has no ramp or accessible toilet", "సహాయ శిబిరంలో ర్యాంప్ గానీ అందుబాటు టాయిలెట్ గానీ లేదు"),
    ],
    ("disaster", "other"): [
        ("Electric wire fell in the water after the storm", "తుఫాను తర్వాత కరెంటు వైరు నీళ్ళలో పడింది"),
    ],
}

CATEGORY_WEIGHTS = {"civic": 50, "accessibility": 35, "disaster": 15}

# Typical severity mix per category: low, medium, high, critical
SEVERITY_WEIGHTS = {
    "accessibility": [20, 50, 25, 5],
    "civic": [20, 45, 28, 7],
    "disaster": [5, 25, 45, 25],
}

STATUS_NOTES = {
    "acknowledged": ["Forwarded to the {dept} section.", "Received; site inspection scheduled."],
    "in_progress": ["Work order issued; team visited the site.", "Repair work started."],
    "resolved": ["Work completed and verified on site.", "Fixed by the {dept} team."],
    "rejected": ["Duplicate of an earlier report.", "Not under GVMC jurisdiction; forwarded to the right agency."],
}


def jitter(lat: float, lon: float, metres: float, rng: random.Random) -> tuple[float, float]:
    """A random point within `metres` of (lat, lon)."""
    r = metres * math.sqrt(rng.random())
    theta = rng.random() * 2 * math.pi
    dlat = (r * math.cos(theta)) / 111_320
    dlon = (r * math.sin(theta)) / (111_320 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lon + dlon, 6)


def pick_status(age_days: float, rng: random.Random) -> str:
    statuses = ["new", "acknowledged", "in_progress", "resolved", "rejected"]
    if age_days > 45:
        weights = [10, 12, 15, 55, 8]
    elif age_days > 14:
        weights = [15, 25, 30, 25, 5]
    else:
        weights = [55, 25, 15, 5, 0]
    return rng.choices(statuses, weights)[0]


def load_photos() -> dict[str, list[bytes]]:
    """Photos keyed by "<category>-<subcategory>"; "civic-road-2.jpg" is a second photo for civic-road."""
    photos: dict[str, list[bytes]] = {}
    for path in sorted(PHOTO_DIR.glob("*.jpg")):
        key = path.stem[:-2] if path.stem[-2:] in {f"-{n}" for n in range(2, 10)} else path.stem
        photos.setdefault(key, []).append(path.read_bytes())
    return photos


def attach_photo(report: Report, photos: dict[str, list[bytes]], rng: random.Random) -> bool:
    options = photos.get(f"{report.category}-{report.subcategory}")
    if not options:
        return False
    media = Media(kind="image", mime_type="image/jpeg", created_at=report.created_at)
    media.file = MediaFile.from_bytes(rng.choice(options))
    report.media.append(media)
    return True


def add_photos(db, rng: random.Random) -> int:
    photos = load_photos()
    added = 0
    for report in db.scalars(select(Report).where(Report.channel == DEMO_CHANNEL).order_by(Report.id)):
        if not report.media and rng.random() < PHOTO_RATE:
            added += attach_photo(report, photos, rng)
    db.commit()
    return added


def clear_demo(db) -> int:
    report_ids = db.scalars(select(Report.id).where(Report.channel == DEMO_CHANNEL)).all()
    for report in db.scalars(select(Report).where(Report.id.in_(report_ids))):
        db.delete(report)  # media rows go with it (cascade)
    db.flush()
    # Clusters left with no reports were demo-only
    used = select(Report.cluster_id).where(Report.cluster_id.is_not(None))
    db.execute(delete(Cluster).where(Cluster.id.not_in(used)))
    db.commit()
    return len(report_ids)


def seed(db, count: int, rng: random.Random) -> int:
    default_dept = {
        (c["id"], s["id"]): s["default_department"] for c in taxonomy.categories() for s in c["subcategories"]
    }
    dept_names = {d["id"]: d["name_en"] for d in taxonomy.departments()}
    photos = load_photos()
    subcats = {cat: [s for (c, s) in DESCRIPTIONS if c == cat] for cat in CATEGORY_WEIGHTS}

    now = utcnow()
    specs = []
    cyclone_age = 39  # a cyclone about five weeks ago brings a burst of disaster reports
    for i in range(count):
        if i < count // 8:
            category, subcategory = "disaster", rng.choice(["flooding", "storm", "storm", "flooding", "other"])
            age = cyclone_age + rng.uniform(-1.5, 1.5)
        else:
            category = rng.choices(list(CATEGORY_WEIGHTS), list(CATEGORY_WEIGHTS.values()))[0]
            subcategory = rng.choice(subcats[category])
            age = 90 * rng.random() ** 1.6  # more recent reports than old ones
        created = now - timedelta(days=age)
        # Keep times between 07:00 and 22:00 IST (01:30–16:30 UTC)
        created = created.replace(hour=rng.randint(2, 16), minute=rng.randint(0, 59), second=rng.randint(0, 59))
        if created > now:
            created -= timedelta(days=1)
        specs.append((created, category, subcategory))
    specs.sort()

    open_clusters: list[tuple[Cluster, str, str]] = []
    cluster_reports: dict[int, list[Report]] = {}
    for n, (created, category, subcategory) in enumerate(specs):
        age_days = (now - created).total_seconds() / 86400
        en, te = rng.choice(DESCRIPTIONS[(category, subcategory)])
        language = rng.choices(["te", "en"], [60, 40])[0]
        affected = rng.choices(["self", "caregiver", "none"], [25, 15, 60] if category != "accessibility" else [55, 30, 15])[0]
        place, base_lat, base_lon = rng.choice(LOCALITIES)

        # About one report in six is someone else reporting a problem already on the map
        same = [c for c, cat, sub in open_clusters if cat == category and sub == subcategory]
        cluster = None
        if same and rng.random() < 0.18:
            cluster = rng.choice(same)
            strict = rng.random() < 0.7
            lat, lon = jitter(cluster.latitude, cluster.longitude, 25 if strict else 70, rng)
            cluster_match = "strict" if strict else "possible"
            place = cluster_reports[cluster.id][0].location_name or place
        else:
            lat, lon = jitter(base_lat, base_lon, 600, rng)
            cluster_match = "new"

        status = pick_status(age_days, rng)
        dept = default_dept[(category, subcategory)]
        needs_review = rng.random() < 0.1
        if needs_review and rng.random() < 0.5:
            dept = "general"
        note = None
        if status != "new" and rng.random() < 0.75:
            note = rng.choice(STATUS_NOTES[status]).format(dept=dept_names.get(dept, dept))
        updated = created if status == "new" else min(now, created + timedelta(hours=rng.uniform(2, 24 * min(age_days, 20))))
        route = rng.choices(["shared_location", "place_search"], [60, 40])[0]
        edits = rng.choices([0, 1, 2], [85, 12, 3])[0]

        report = Report(
            interaction_id=str(uuid.uuid4()),
            created_at=created,
            updated_at=updated,
            channel=DEMO_CHANNEL,
            language=language,
            category=category,
            subcategory=subcategory,
            barrier_type=subcategory,
            municipal_subject=None,
            department_id=dept,
            severity=rng.choices(["low", "medium", "high", "critical"], SEVERITY_WEIGHTS[category])[0],
            classifier="rules",
            needs_review=needs_review,
            pwd_marker=affected in ("self", "caregiver") or category == "accessibility",
            affected=affected,
            description_raw=te if language == "te" else en,
            description_type="text",
            latitude=lat,
            longitude=lon,
            location_name=place if route == "place_search" else None,
            location_address=f"{place}, Visakhapatnam, Andhra Pradesh" if route == "place_search" else None,
            location_route=route,
            cluster_match=cluster_match,
            readback_outcome="edited" if edits else "confirmed",
            edit_count=edits,
            status=status,
            status_note=note,
            reporter_hash=hashlib.sha256(f"demo-reporter-{rng.randint(1, 70)}".encode()).hexdigest(),
        )

        if cluster is None:
            cluster = Cluster(
                category=category, subcategory=subcategory, latitude=lat, longitude=lon,
                report_count=0, first_seen=created, last_seen=created,
            )
            db.add(cluster)
            db.flush()
            open_clusters.append((cluster, category, subcategory))
            cluster_reports[cluster.id] = []
        cluster.report_count += 1
        cluster.last_seen = created
        report.cluster = cluster
        cluster_reports[cluster.id].append(report)
        if rng.random() < PHOTO_RATE:
            attach_photo(report, photos, rng)
        db.add(report)

        if n % 25 == 0:
            db.flush()

    # A cluster is resolved once every report in it is closed
    for cluster_id, reports in cluster_reports.items():
        if all(r.status in ("resolved", "rejected") for r in reports):
            db.get(Cluster, cluster_id).status = "resolved"

    db.commit()
    return len(specs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--clear", action="store_true", help="remove all demo reports and stop")
    parser.add_argument("--add-photos", action="store_true", help="give photos to existing demo reports that have none, and stop")
    parser.add_argument("--seed", type=int, default=2026, help="random seed, for repeatable data")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as db:
        if args.clear:
            print(f"removed {clear_demo(db)} demo reports")
            return
        if args.add_photos:
            print(f"added photos to {add_photos(db, random.Random(args.seed))} demo reports")
            return
        added = seed(db, args.count, random.Random(args.seed))
        total = db.scalar(select(func.count()).select_from(Report))
        print(f"added {added} demo reports ({total} reports in the database now)")


if __name__ == "__main__":
    main()
