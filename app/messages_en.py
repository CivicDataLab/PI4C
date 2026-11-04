"""English resident-facing text. Must define the same names as messages_te.py (tests check this).

WhatsApp limits apply here too: button title ≤ 20, row title ≤ 24, row description ≤ 72.

Screen readers (TalkBack, VoiceOver) read every emoji by name ("round pushpin Live location"),
say "bullet" and often "em dash" aloud, so resident-facing text uses none of them: plain words,
numbered lists that match the button order, and colons instead of dashes.
"""

WELCOME = (
    "Hello! This is the PI4C citizen complaint service.\n\n"
    "You can report:\n"
    "1. Accessibility issue: footpath, ramp, toilet and similar\n"
    "2. General Civic Issue: drinking water, drainage, garbage\n"
    "3. Disaster/Climate related Issue: flood, storm, heat\n\n"
    "What would you like to report? Tap an option, or type its number."
)

CHOOSE_CATEGORY = "Choose the correct category."

CHOOSE_FROM_BUTTONS = "Please tap one of the options after this message, or type its number."

CHOOSE_SUBCATEGORY = "What kind of problem is it?"

LIST_BUTTON = "Choose"

DESCRIBE = "Briefly describe the problem in a text message, in Telugu or English."

DESCRIBE_RETRY = "Please type the problem as a text message. Voice messages can't be used."

PHOTO_SAVED_DESCRIBE = "Photo received. Now please type a short description of the problem."

LOCATION = (
    "Where is the problem?\n\n"
    "Three buttons are shown in place of your keyboard:\n"
    "1. Live location: sends where you are right now\n"
    "2. Choose a location: pick the place on the map\n"
    "3. Type the place name: a landmark, shop, road or area\n\n"
    "You can also type the place name now."
)

LOCATION_RETRY = (
    "Location not received. Please tap one of the three buttons shown in place of your keyboard, "
    "or type the place name."
)

CHOOSE_ON_MAP = (
    "To choose the place on the map:\n"
    "1. Tap the Attach button, the paperclip next to the message box\n"
    "2. Tap \"Location\"\n"
    "3. Search for the place by name, or move the map so the pin is on the problem\n"
    "4. Tap \"Send selected location\""
)

BTN_SEND_LOCATION = "Live location"
BTN_CHOOSE_LOCATION = "Choose a location"
BTN_TYPE_PLACE = "Type the place name"

LOCATION_RECEIVED = "Location received."

TYPE_PLACE = (
    "Type the name of the place in Visakhapatnam: a landmark, shop, road or area. "
    "For example: Jagadamba Junction."
)

CHOOSE_PLACE = "Which of these is the place? Tap it, or type its number."
PLACE_SECTION = "Places"
PLACE_NONE = "None of these"

PLACE_SEARCH_FAILED = (
    "Place search is not working right now. Please tap \"Live location\" or \"Choose a location\"."
)


def place_not_found(query: str) -> str:
    return (
        f"No place called \"{query}\" was found in Visakhapatnam. "
        "Try a nearby landmark or the area name, or use the buttons."
    )


def location_saved(name: str) -> str:
    return f"Location saved: {name}."

PHOTO = "If you have a photo of the problem, send it. This is optional."

PHOTO_RETRY = "Send a photo, or tap \"No photo\"."

BTN_NO_PHOTO = "No photo"

AFFECTED = (
    "Who are you reporting this for?\n\n"
    "1. I have a disability: it affects me\n"
    "2. Caregiver: for a person with disability\n"
    "3. General problem: not disability-related"
)

AFFECTED_OPTIONS: list[tuple[str, str]] = [
    ("self", "I have a disability"),
    ("caregiver", "Caregiver"),
    ("none", "General problem"),
]

BTN_CONFIRM = "Yes, submit"
BTN_EDIT = "Edit"
BTN_CANCEL = "Cancel"

EDIT = "What would you like to edit?"
EDIT_SECTION = "Edit"
EDIT_OPTIONS: list[tuple[str, str]] = [
    ("category", "Category"),
    ("description", "Description"),
    ("location", "Location"),
    ("photo", "Photo"),
    ("affected", "Reported for"),
]

CANCELLED = "Complaint cancelled. Send \"menu\" to start again."

EXPIRED = "The previous complaint was stopped because there was no reply for a long time. Let's start again."


def readback(category: str, subcategory: str, description: str, location: str, photos: int, affected: str) -> str:
    photo_line = f"{photos} attached" if photos else "none"
    return (
        "Please check your complaint:\n\n"
        f"Type: {category}, {subcategory}.\n"
        f"Details: {description}\n"
        f"Location: {location}.\n"
        f"Photo: {photo_line}.\n"
        f"For: {affected}.\n\n"
        "Is everything correct?"
    )


def submitted(ref: str) -> str:
    return (
        "Thank you! Your complaint has been registered.\n"
        f"Complaint number: {ref}\n\n"
        "Send \"menu\" any time to make a new complaint."
    )


# --- Telegram bot profile (published with `python -m app.telegram_cli set-profile`) ---------

BOT_DESCRIPTION = (
    "PI4C helps residents report problems in their area, in Telugu or English.\n\n"
    "You can report:\n"
    "1. Accessibility issues: broken footpaths, missing ramps, inaccessible toilets\n"
    "2. General civic issues: water, drainage, garbage, streetlights\n"
    "3. Disaster/climate related issues: flooding, storm damage, heat\n\n"
    "Share the location, describe the problem in a message, add a photo, and get a complaint number.\n\n"
    "Tap Start to begin."
)

BOT_SHORT_DESCRIPTION = (
    "Report accessibility, civic and disaster/climate issues in Telugu or English, and get a complaint number."
)

BOT_COMMANDS: list[tuple[str, str]] = [
    ("start", "Start a new report"),
    ("language", "Change language"),
    ("cancel", "Cancel the current report"),
]
