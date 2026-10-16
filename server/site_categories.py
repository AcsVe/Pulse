"""Best-effort website categorization for the Browse tab's "category" column.

This is a static, maintained-by-hand mapping, not a live lookup against any
outside classification service (no such request should ever leave the
server just to label a history row) and not a content filter — it only
labels what's already being recorded, the same way the dashboard already
labels an app by its package name. A domain that matches nothing falls back
to 'other' rather than being left blank, so the column is always populated
and sortable/filterable like the rest of the table.

Matching is substring-based against the registrable domain (after stripping
a leading "www.") against an ordered list of (category, keywords) — order
matters where one domain could plausibly match more than one bucket (e.g.
"mail.google.com" should read as email, not search, so email is checked
before search).
"""

CATEGORIES = [
    ('email', (
        'gmail', 'outlook', 'live.com', 'hotmail', 'yahoo.com/mail', 'mail.yahoo',
        'protonmail', 'proton.me', 'icloud.com/mail', 'zoho.com/mail', 'mail.ru',
        'mail.google',
    )),
    ('social', (
        'facebook', 'instagram', 'tiktok', 'twitter', 'x.com', 'snapchat',
        'pinterest', 'linkedin', 'reddit', 'whatsapp', 'telegram', 'discord',
        'tumblr', 'threads.net', 'mastodon',
    )),
    ('video', (
        'youtube', 'netflix', 'hulu', 'disneyplus', 'primevideo', 'twitch',
        'vimeo', 'dailymotion', 'shahid.', 'osn.com',
    )),
    ('gaming', (
        'steampowered', 'epicgames', 'roblox', 'minecraft', 'ea.com',
        'playstation', 'xbox', 'ubisoft', 'ea.com', 'ign.com',
    )),
    ('shopping', (
        'amazon', 'ebay', 'aliexpress', 'noon.com', 'shein', 'walmart',
        'etsy', 'souq.', 'jumia', 'alibaba',
    )),
    ('news', (
        'cnn.com', 'bbc.', 'aljazeera', 'nytimes', 'reuters', 'skynewsarabia',
        'alarabiya', 'alhadath', 'bloomberg', 'theguardian',
    )),
    ('education', (
        'wikipedia', 'coursera', 'udemy', 'khanacademy', 'moodle',
        'classroom.google', 'edmodo', 'blackboard', 'duolingo',
        'scholar.google',
    )),
    ('productivity', (
        'office.com', 'office365', 'microsoft365', 'drive.google',
        'docs.google', 'dropbox', 'github', 'slack.com', 'zoom.us',
        'teams.microsoft', 'notion.so', 'trello.com', 'asana.com',
    )),
    ('search', (
        'google.', 'bing.com', 'duckduckgo', 'yahoo.com', 'baidu',
        'yandex',
    )),
    ('finance', (
        'paypal', 'visa.com', 'mastercard', 'stripe.com', 'bank',
    )),
]

_TLD_FALLBACK = {
    '.edu': 'education',
    '.gov': 'government',
}


def categorize_domain(domain):
    """Returns one of the category keys above, or 'other' when nothing
    matches. `domain` may be empty/None (e.g. a row that only has a URL) —
    returns 'other' rather than raising."""
    d = (domain or '').strip().lower()
    if d.startswith('www.'):
        d = d[4:]
    if not d:
        return 'other'
    for cat, keywords in CATEGORIES:
        if any(k in d for k in keywords):
            return cat
    for suffix, cat in _TLD_FALLBACK.items():
        if d.endswith(suffix):
            return cat
    return 'other'
