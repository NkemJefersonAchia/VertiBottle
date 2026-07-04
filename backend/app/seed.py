"""Demo seed data: 4 crop profiles, 5 pilot sites (3 school + 2 community,
matching the SRS pilot layout in Maroua/Mokolo), one sensor node per site,
and one login per user class.

Idempotent: running it against an already-seeded database does nothing.
Default credentials are documented in README.md.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Channel,
    CropProfile,
    Role,
    SensorNode,
    Site,
    SiteType,
    User,
)
from .security import hash_password

# Target bands per crop. pH/EC lettuce values match the SRS examples
# (lettuce pH 5.5-6.5, EC 800-1200 µS/cm); the rest are standard leafy-green
# hydroponic ranges. water_level is cm of depth in the reservoir.
CROPS = {
    "lettuce":  dict(ph=(5.5, 6.5), ec=(800, 1200),  water_temp=(18, 26), air_temp=(15, 28),
                     humidity=(50, 80), water_level=(10, 30), light=(10000, 40000)),
    "spinach":  dict(ph=(6.0, 7.0), ec=(1200, 1800), water_temp=(18, 25), air_temp=(16, 27),
                     humidity=(45, 75), water_level=(10, 30), light=(12000, 40000)),
    "amaranth": dict(ph=(6.0, 6.8), ec=(1000, 1600), water_temp=(20, 28), air_temp=(20, 32),
                     humidity=(40, 75), water_level=(10, 30), light=(15000, 50000)),
    "basil":    dict(ph=(5.5, 6.5), ec=(1000, 1600), water_temp=(20, 27), air_temp=(18, 30),
                     humidity=(45, 75), water_level=(10, 30), light=(12000, 45000)),
}

SITES = [
    # (name, type, location, crop, connectivity)
    ("GSS Maroua Bottle Farm", SiteType.school, "Maroua", "lettuce", "wifi"),
    ("Lycée de Mokolo Farm", SiteType.school, "Mokolo", "spinach", "wifi"),
    ("EP Salak School Garden", SiteType.school, "Salak", "basil", "wifi"),
    ("Femmes de Makabay Cooperative", SiteType.community, "Makabay", "amaranth", "gsm"),
    ("Jeunesse Mokolo Youth Farm", SiteType.community, "Mokolo", "lettuce", "gsm"),
]

# (username, password, name, role, site index or None, phone, email, language, channel)
USERS = [
    ("school_op", "demo1234", "Aissatou Bello (teacher)", Role.school_operator, 0,
     "+237650000001", "aissatou@school.example", "en", Channel.email),
    ("cb_op", "demo1234", "Falmata Oumarou (CB volunteer)", Role.cb_operator, 3,
     "+237650000002", None, "fr", Channel.ussd),
    ("coordinator", "demo1234", "Jean-Paul Nganou (NGO coordinator)", Role.coordinator, None,
     "+237650000003", "coordinator@ngo.example", "en", Channel.dashboard),
    ("agronomist", "demo1234", "Dr. Sarah Mbarga (agronomist)", Role.agronomist, None,
     None, "sarah@research.example", "en", Channel.email),
    ("admin", "demo1234", "System Administrator", Role.admin, None,
     "+237650000005", "admin@vertibottle.example", "en", Channel.dashboard),
    # Extra operators so every site has someone to notify (business rule:
    # at least one operator per site).
    ("op_mokolo", "demo1234", "Ibrahim Adamou (teacher)", Role.school_operator, 1,
     "+237650000006", "ibrahim@school.example", "fr", Channel.email),
    ("op_salak", "demo1234", "Marie Douala (lab tech)", Role.school_operator, 2,
     "+237650000007", "marie@school.example", "en", Channel.email),
    ("op_jeunesse", "demo1234", "Oumar Sali (youth leader)", Role.cb_operator, 4,
     "+237650000008", None, "fr", Channel.ussd),
]


def seed(db: Session) -> bool:
    """Returns True if data was inserted, False if already seeded."""
    if db.scalar(select(Site).limit(1)) is not None:
        return False

    crops: dict[str, CropProfile] = {}
    for name, bands in CROPS.items():
        crop = CropProfile(
            crop_name=name,
            ph_min=bands["ph"][0], ph_max=bands["ph"][1],
            ec_min=bands["ec"][0], ec_max=bands["ec"][1],
            water_temp_min=bands["water_temp"][0], water_temp_max=bands["water_temp"][1],
            air_temp_min=bands["air_temp"][0], air_temp_max=bands["air_temp"][1],
            humidity_min=bands["humidity"][0], humidity_max=bands["humidity"][1],
            water_level_min=bands["water_level"][0], water_level_max=bands["water_level"][1],
            light_min=bands["light"][0], light_max=bands["light"][1],
        )
        db.add(crop)
        crops[name] = crop

    sites: list[Site] = []
    for name, site_type, location, crop_name, connectivity in SITES:
        site = Site(name=name, site_type=site_type, location=location,
                    crop_profile=crops[crop_name], verified=True)
        db.add(site)
        db.add(SensorNode(site=site, connectivity=connectivity))
        sites.append(site)

    for username, password, name, role, site_idx, phone, email, lang, channel in USERS:
        db.add(User(
            username=username,
            password_hash=hash_password(password),
            name=name,
            role=role,
            site=sites[site_idx] if site_idx is not None else None,
            phone=phone,
            email=email,
            language=lang,
            preferred_channel=channel,
        ))

    db.commit()
    return True
