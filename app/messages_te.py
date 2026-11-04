"""All resident-facing Telugu text, kept in one place for review with OPDs and native speakers.

English gloss is in the comment beside each string. Category/sub-category labels live in
data/taxonomy.json. "Persons with disabilities" is rendered as దివ్యాంగులు, the term used by the
Andhra Pradesh government. WhatsApp limits (checked by tests/test_units.py): button title ≤ 20,
list button ≤ 20, row title ≤ 24, row description ≤ 72, interactive body ≤ 1024.

Screen readers (TalkBack, VoiceOver) read every emoji by name, say "bullet" and often "em dash"
aloud, so resident-facing text uses none of them: plain words, numbered lists that match the
button order, and colons instead of dashes. Strings marked NEW need native-speaker review.
"""

# Hello! This is the PI4C citizen complaint service. You can report: accessibility problems
# (footpath, ramp, toilet...), general civic issues (drinking water, drainage, garbage),
# disaster/climate related issues (floods, cyclone, heat). What would you like to report?
# NEW: Tap an option, or type its number.
WELCOME = (
    "నమస్కారం! ఇది PI4C పౌర ఫిర్యాదుల సేవ.\n\n"
    "మీరు వీటిని ఫిర్యాదు చేయవచ్చు:\n"
    "1. అందుబాటు సమస్య: ఫుట్‌పాత్, ర్యాంప్, మరుగుదొడ్డి వంటివి\n"
    "2. సాధారణ పౌర సమస్య: తాగునీరు, డ్రైనేజీ, చెత్త\n"
    "3. విపత్తు / వాతావరణ సంబంధిత సమస్య: వరదలు, తుఫాను, వేడి\n\n"
    "మీరు దేని గురించి ఫిర్యాదు చేయాలనుకుంటున్నారు? ఒక ఎంపికను నొక్కండి, లేదా దాని సంఖ్యను టైప్ చేయండి."
)

# Choose the correct category.
CHOOSE_CATEGORY = "సరైన వర్గాన్ని ఎంచుకోండి."

# NEW: Please tap one of the options after this message, or type its number.
CHOOSE_FROM_BUTTONS = "దయచేసి ఈ సందేశం తర్వాత ఉన్న ఎంపికలలో ఒకదాన్ని నొక్కండి, లేదా దాని సంఖ్యను టైప్ చేయండి."

# What kind of problem is it?
CHOOSE_SUBCATEGORY = "ఇది ఏ రకమైన సమస్య?"

# Choose
LIST_BUTTON = "ఎంచుకోండి"

# NEW: Type a short description of the problem and send it. Telugu or English, either is fine.
DESCRIBE = "సమస్యను క్లుప్తంగా టైప్ చేసి పంపండి. తెలుగు లేదా ఇంగ్లీష్, ఏదైనా సరే."

# NEW: Please type the problem and send it as a message. Voice messages can't be used.
DESCRIBE_RETRY = "దయచేసి సమస్యను టైప్ చేసి సందేశంగా పంపండి. వాయిస్ సందేశాలు ఉపయోగించలేము."

# NEW: Photo received. Now please type a short description of the problem.
PHOTO_SAVED_DESCRIBE = "ఫోటో అందింది. ఇప్పుడు సమస్యను క్లుప్తంగా టైప్ చేసి పంపండి."

# Where is the problem? NEW: Three buttons are shown in place of your keyboard:
# 1. Live location: sends where you are right now  2. Choose a location: pick the place on the map
# 3. NEW: Type the place name: a landmark, road or area. NEW: You can also type the place name now.
LOCATION = (
    "సమస్య ఎక్కడ ఉంది?\n\n"
    "మీ కీబోర్డ్ స్థానంలో మూడు బటన్‌లు కనిపిస్తాయి:\n"
    "1. లైవ్ లొకేషన్: మీరు ఇప్పుడు ఉన్న ప్రదేశాన్ని పంపుతుంది\n"
    "2. ప్రదేశాన్ని ఎంచుకోండి: మ్యాప్‌లో ప్రదేశాన్ని గుర్తించవచ్చు\n"
    "3. ప్రదేశం పేరు టైప్ చేయండి: ఏదైనా గుర్తు, దుకాణం, రోడ్డు లేదా ప్రాంతం\n\n"
    "ప్రదేశం పేరును ఇప్పుడే టైప్ చేసి కూడా పంపవచ్చు."
)

# NEW: Location not received. Please tap one of the three buttons shown in place of your
# keyboard, or type the place name.
LOCATION_RETRY = (
    "లొకేషన్ అందలేదు. మీ కీబోర్డ్ స్థానంలో ఉన్న మూడు బటన్‌లలో ఒకదాన్ని నొక్కండి, "
    "లేదా ప్రదేశం పేరు టైప్ చేయండి."
)

# To choose the place on the map: 1. NEW: tap the Attach button, the paperclip next to the message box
# 2. tap "Location" 3. NEW: search for the place by name, or move the map so the pin is on the problem
# 4. tap "Send selected location"
CHOOSE_ON_MAP = (
    "మ్యాప్‌లో ప్రదేశాన్ని ఎంచుకోవడానికి:\n"
    "1. సందేశం పెట్టె పక్కన ఉన్న అటాచ్ (Attach) బటన్‌ను, అంటే పేపర్‌క్లిప్‌ను నొక్కండి\n"
    "2. \"లొకేషన్\" (Location) ను నొక్కండి\n"
    "3. ప్రదేశం పేరుతో వెతకండి, లేదా సమస్య ఉన్న చోట పిన్ వచ్చేలా మ్యాప్‌ను జరపండి\n"
    "4. \"ఎంచుకున్న లొకేషన్‌ను పంపండి\" ను నొక్కండి"
)

# Telegram keyboard buttons (WhatsApp draws its own location button)
BTN_SEND_LOCATION = "లైవ్ లొకేషన్"  # Live location
BTN_CHOOSE_LOCATION = "ప్రదేశాన్ని ఎంచుకోండి"  # Choose a location
BTN_TYPE_PLACE = "ప్రదేశం పేరు టైప్ చేయండి"  # NEW: Type the place name

# Location received.
LOCATION_RECEIVED = "లొకేషన్ అందింది."

# NEW: Type the name of the place in Visakhapatnam: a landmark, shop, road or area.
# For example: Jagadamba Junction.
TYPE_PLACE = (
    "విశాఖపట్నంలోని ప్రదేశం పేరు టైప్ చేయండి: ఏదైనా గుర్తు, దుకాణం, రోడ్డు లేదా ప్రాంతం. "
    "ఉదాహరణకు: జగదాంబ జంక్షన్."
)

# NEW: Which of these is the place? Tap it, or type its number.
CHOOSE_PLACE = "వీటిలో ఏది ఆ ప్రదేశం? దాన్ని నొక్కండి, లేదా దాని సంఖ్యను టైప్ చేయండి."
PLACE_SECTION = "ప్రదేశాలు"  # NEW: Places
PLACE_NONE = "వీటిలో ఏదీ కాదు"  # NEW: None of these

# NEW: Place search is not working right now. Please tap "Live location" or "Choose a location".
PLACE_SEARCH_FAILED = (
    "ప్రదేశం వెతకడం ఇప్పుడు పనిచేయడం లేదు. దయచేసి \"లైవ్ లొకేషన్\" లేదా \"ప్రదేశాన్ని ఎంచుకోండి\" నొక్కండి."
)


def place_not_found(query: str) -> str:
    """NEW: No place called "QUERY" was found in Visakhapatnam. Try a nearby landmark or the
    area name, or use the buttons."""
    return (
        f"విశాఖపట్నంలో \"{query}\" అనే ప్రదేశం కనబడలేదు. "
        "దగ్గరలోని ఏదైనా గుర్తు లేదా ప్రాంతం పేరుతో ప్రయత్నించండి, లేదా బటన్‌లను ఉపయోగించండి."
    )


def location_saved(name: str) -> str:
    """NEW: Location saved: NAME."""
    return f"ప్రదేశం నమోదైంది: {name}."

# If you have a photo of the problem, send it. This is optional.
PHOTO = "సమస్య ఫోటో ఉంటే పంపండి. ఇది ఐచ్ఛికం."

# Please send a photo, or press "No photo".
PHOTO_RETRY = "ఫోటో పంపండి, లేదా \"ఫోటో లేదు\" నొక్కండి."

BTN_NO_PHOTO = "ఫోటో లేదు"  # No photo

# Who is this complaint for?
#  1. I am a person with disability: it affects me
#  2. As a caregiver: for a person with disability
#  3. General problem: not disability-related
AFFECTED = (
    "ఈ ఫిర్యాదు ఎవరి కోసం చేస్తున్నారు?\n\n"
    "1. దివ్యాంగ వ్యక్తిని: నాకే ఇబ్బంది\n"
    "2. సంరక్షకులుగా: ఒక దివ్యాంగ వ్యక్తి కోసం\n"
    "3. సాధారణ సమస్య: దివ్యాంగతకు సంబంధించినది కాదు"
)

AFFECTED_OPTIONS: list[tuple[str, str]] = [
    ("self", "దివ్యాంగ వ్యక్తిని"),  # I am a person with disability
    ("caregiver", "సంరక్షకులుగా"),  # As a caregiver
    ("none", "సాధారణ సమస్య"),  # General problem
]

BTN_CONFIRM = "సరే, పంపండి"  # OK, send
BTN_EDIT = "మార్చండి"  # Edit
BTN_CANCEL = "రద్దు చేయండి"  # Cancel

# What would you like to edit?
EDIT = "దేనిని మార్చాలి?"
EDIT_SECTION = "మార్పు"  # Edit
EDIT_OPTIONS: list[tuple[str, str]] = [
    ("category", "వర్గం"),  # Category
    ("description", "వివరణ"),  # Description
    ("location", "ప్రదేశం"),  # Location
    ("photo", "ఫోటో"),  # Photo
    ("affected", "ఎవరి కోసం"),  # Reported for whom
]

# Complaint cancelled. Send "menu" to start again.
CANCELLED = "ఫిర్యాదు రద్దు చేయబడింది. మళ్లీ ప్రారంభించడానికి \"మెనూ\" అని పంపండి."

# The previous complaint was stopped because there was no reply for a long time. Let's start again.
EXPIRED = "చాలా సేపు జవాబు లేనందున మునుపటి ఫిర్యాదు ఆపివేయబడింది. మళ్లీ ప్రారంభిద్దాం."


def readback(category: str, subcategory: str, description: str, location: str, photos: int, affected: str) -> str:
    """Please check your complaint: Category / Details / Place / Photo / For whom. Is everything correct?"""
    photo_line = f"{photos} జత చేయబడింది" if photos else "లేదు"  # "N attached" / "none"
    return (
        "మీ ఫిర్యాదును తనిఖీ చేయండి:\n\n"
        f"వర్గం: {category}, {subcategory}.\n"
        f"వివరణ: {description}\n"
        f"ప్రదేశం: {location}.\n"
        f"ఫోటో: {photo_line}.\n"
        f"ఎవరి కోసం: {affected}.\n\n"
        "అన్నీ సరిగ్గా ఉన్నాయా?"
    )


def submitted(ref: str) -> str:
    """Thank you! Your complaint is registered. Complaint number: REF. Send "menu" anytime for a new one."""
    return (
        "ధన్యవాదాలు! మీ ఫిర్యాదు నమోదు చేయబడింది.\n"
        f"ఫిర్యాదు సంఖ్య: {ref}\n\n"
        "కొత్త ఫిర్యాదు చేయడానికి ఎప్పుడైనా \"మెనూ\" అని పంపండి."
    )


# --- Telegram bot profile (published with `python -m app.telegram_cli set-profile`) ---------

# PI4C lets you report problems in your area in Telugu or English. You can report: accessibility
# problems (broken footpath, no ramp, unusable toilets); general civic issues (drinking water,
# drainage, garbage, streetlights); disaster/climate related issues (floods, cyclone damage, heat).
# Share the place, describe the problem in writing, attach a photo, get a complaint
# number. Press Start to begin.
BOT_DESCRIPTION = (
    "PI4C ద్వారా మీ ప్రాంతంలోని సమస్యలను తెలుగు లేదా ఇంగ్లీష్‌లో ఫిర్యాదు చేయవచ్చు.\n\n"
    "ఫిర్యాదు చేయవచ్చు:\n"
    "1. అందుబాటు సమస్య: పాడైన ఫుట్‌పాత్, ర్యాంప్ లేకపోవడం, ఉపయోగించలేని మరుగుదొడ్లు\n"
    "2. సాధారణ పౌర సమస్య: తాగునీరు, డ్రైనేజీ, చెత్త, వీధి దీపాలు\n"
    "3. విపత్తు / వాతావరణ సంబంధిత సమస్య: వరదలు, తుఫాను నష్టం, వేడి\n\n"
    "ప్రదేశాన్ని పంచుకోండి, సమస్యను అక్షరాల్లో వివరించండి, ఫోటో జత చేయండి, "
    "ఫిర్యాదు సంఖ్య పొందండి.\n\n"
    "ప్రారంభించడానికి Start నొక్కండి."
)

# Report accessibility, civic, disaster/climate problems in Telugu or English.
BOT_SHORT_DESCRIPTION = "అందుబాటు, పౌర, విపత్తు / వాతావరణ సమస్యలను తెలుగు లేదా ఇంగ్లీష్‌లో ఫిర్యాదు చేయండి."

BOT_COMMANDS: list[tuple[str, str]] = [
    ("start", "కొత్త ఫిర్యాదు"),  # New complaint
    ("language", "భాష మార్చండి"),  # Change language
    ("cancel", "ఫిర్యాదు రద్దు చేయండి"),  # Cancel the complaint
]
