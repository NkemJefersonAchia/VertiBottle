"""USSD interface (FR 6), served to the phone-shaped simulator page.

Emulates an Africa's Talking-style webhook: the frontend posts the phone
number and the '*'-joined string of keypresses for the session; we return
the next screen and whether the session ends. No real USSD gateway exists
here, so the simulator page plays the role of the aggregator.

Constraints honoured from the SRS:
  - menu tree: 1 Today's reading, 2 Current alerts, 3 Acknowledge alert,
    4 Change language, 0 Exit
  - every screen <= 182 characters (MNO session policy, SRS 2.5)
  - any useful action within <= 3 keypresses (NFR 4.2) — acknowledging is
    dial, '3', then the alert number.
  - sessions are tied to the SIM's phone number; the number must belong to
    a registered operator (business rule).
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..database import get_db
from ..models import Alert, AlertState, Site, User
from ..notifier import PARAM_LABELS, PARAM_UNITS
from ..rule_engine import OPEN_STATES
from ..schemas import UssdRequest, UssdResponse
from ..state_machine import IllegalTransition, transition

router = APIRouter(prefix="/api/v1/ussd", tags=["ussd"])

MENU = {
    "en": ("VertiBottle\n1. Today's reading\n2. Current alerts\n"
           "3. Acknowledge alert\n4. Change language\n0. Exit"),
    "fr": ("VertiBottle\n1. Releve du jour\n2. Alertes en cours\n"
           "3. Confirmer une alerte\n4. Changer de langue\n0. Quitter"),
}

T = {
    "no_operator": {
        "en": "This number is not registered with VertiBottle. Contact your administrator.",
        "fr": "Ce numero n'est pas enregistre aupres de VertiBottle. Contactez votre administrateur.",
    },
    "no_site": {
        "en": "No farm is assigned to your account yet.",
        "fr": "Aucune ferme n'est encore associee a votre compte.",
    },
    "no_alerts": {"en": "No active alerts. All parameters in range.",
                  "fr": "Aucune alerte active. Tous les parametres sont dans la plage."},
    "ack_which": {"en": "Reply with alert number to acknowledge:",
                  "fr": "Repondez avec le numero de l'alerte a confirmer:"},
    "ack_done": {"en": "Alert acknowledged. Thank you.",
                 "fr": "Alerte confirmee. Merci."},
    "ack_fail": {"en": "Could not acknowledge that alert.",
                 "fr": "Impossible de confirmer cette alerte."},
    "lang_menu": {"en": "Choose language:\n1. English\n2. Francais",
                  "fr": "Choisissez la langue:\n1. English\n2. Francais"},
    "lang_set": {"en": "Language set to English.", "fr": "Langue definie sur le francais."},
    "bye": {"en": "Goodbye.", "fr": "Au revoir."},
    "bad_input": {"en": "Invalid choice.", "fr": "Choix invalide."},
}


def _clip(msg: str) -> str:
    # Hard MNO limit from the SRS; if a screen ever overflows we truncate
    # rather than let the aggregator reject the whole response.
    return msg if len(msg) <= 182 else msg[:179] + "..."


def _fmt_value(param: str, value: float) -> str:
    return f"{value:g}{PARAM_UNITS[param]}"


def _ackable_alerts(db: Session, site_id: str) -> list[Alert]:
    # Only Notification Sent alerts can be acknowledged (state machine).
    return db.scalars(
        select(Alert)
        .where(Alert.site_id == site_id, Alert.state == AlertState.notification_sent)
        .order_by(Alert.created_at)
    ).all()


def _latest_readings_text(db: Session, site: Site, lang: str) -> str:
    # Latest value per parameter, compact enough for one USSD screen.
    from ..models import Parameter, Reading  # local import to avoid cycle noise

    lines = [site.name[:28]]
    for param in Parameter:
        r = db.scalar(
            select(Reading)
            .where(Reading.site_id == site.id, Reading.parameter == param)
            .order_by(Reading.ts.desc())
            .limit(1)
        )
        if r is None:
            continue
        lo, hi = site.crop_profile.band(param)
        flag = "" if lo <= r.value <= hi else " !"
        label = PARAM_LABELS[param.value][lang]
        lines.append(f"{label}: {_fmt_value(param.value, r.value)}{flag}")
    return "\n".join(lines)


def _active_alerts_text(db: Session, site: Site, lang: str) -> str:
    alerts = db.scalars(
        select(Alert)
        .where(Alert.site_id == site.id, Alert.state.in_(OPEN_STATES))
        .order_by(Alert.created_at)
    ).all()
    if not alerts:
        return T["no_alerts"][lang]
    lines = []
    for i, a in enumerate(alerts[:4], 1):
        label = PARAM_LABELS[a.parameter.value][lang]
        lines.append(f"{i}. {label} {_fmt_value(a.parameter.value, a.trigger_value)} "
                     f"({a.band_min:g}-{a.band_max:g})")
    return "\n".join(lines)


@router.post("", response_model=UssdResponse)
def ussd(body: UssdRequest, db: Session = Depends(get_db)):
    """Stateless per-request handler: the aggregator (here: the simulator
    page) resends the full keypress history each time, so no server-side
    session store is needed."""
    operator = db.scalar(select(User).where(User.phone == body.phone, User.active.is_(True)))
    if operator is None:
        return UssdResponse(message=_clip(T["no_operator"]["en"]), end=True)
    lang = operator.language or "en"

    keys = [k for k in body.text.split("*") if k != ""]

    if not keys:  # first screen after dialing the shortcode
        return UssdResponse(message=_clip(MENU[lang]), end=False)

    site = db.get(Site, operator.site_id) if operator.site_id else None
    choice = keys[0]

    if choice == "0":
        return UssdResponse(message=_clip(T["bye"][lang]), end=True)

    if choice == "1":
        if site is None:
            return UssdResponse(message=_clip(T["no_site"][lang]), end=True)
        audit.log(db, operator.username, "ussd_view_readings", site.name, site.id)
        db.commit()
        return UssdResponse(message=_clip(_latest_readings_text(db, site, lang)), end=True)

    if choice == "2":
        if site is None:
            return UssdResponse(message=_clip(T["no_site"][lang]), end=True)
        audit.log(db, operator.username, "ussd_view_alerts", site.name, site.id)
        db.commit()
        return UssdResponse(message=_clip(_active_alerts_text(db, site, lang)), end=True)

    if choice == "3":
        if site is None:
            return UssdResponse(message=_clip(T["no_site"][lang]), end=True)
        alerts = _ackable_alerts(db, site.id)
        if not alerts:
            return UssdResponse(message=_clip(T["no_alerts"][lang]), end=True)
        if len(keys) == 1:
            lines = [T["ack_which"][lang]]
            for i, a in enumerate(alerts[:4], 1):
                label = PARAM_LABELS[a.parameter.value][lang]
                lines.append(f"{i}. {label} {_fmt_value(a.parameter.value, a.trigger_value)}")
            return UssdResponse(message=_clip("\n".join(lines)), end=False)
        # Third keypress: the alert index. This is the <= 3 presses path.
        try:
            alert = alerts[int(keys[1]) - 1]
            transition(alert, AlertState.acknowledged)
            alert.acknowledged_by = operator.id
            audit.log(db, operator.username, "alert_acknowledged",
                      f"{alert.parameter.value} alert via USSD", site.id)
            db.commit()
            return UssdResponse(message=_clip(T["ack_done"][lang]), end=True)
        except (ValueError, IndexError, IllegalTransition):
            return UssdResponse(message=_clip(T["ack_fail"][lang]), end=True)

    if choice == "4":
        if len(keys) == 1:
            return UssdResponse(message=_clip(T["lang_menu"][lang]), end=False)
        new_lang = "en" if keys[1] == "1" else "fr" if keys[1] == "2" else None
        if new_lang is None:
            return UssdResponse(message=_clip(T["bad_input"][lang]), end=True)
        operator.language = new_lang
        audit.log(db, operator.username, "language_changed", f"to {new_lang}")
        db.commit()
        return UssdResponse(message=_clip(T["lang_set"][new_lang]), end=True)

    return UssdResponse(message=_clip(T["bad_input"][lang]), end=True)
