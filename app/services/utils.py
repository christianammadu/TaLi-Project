import re

# A bare amount with an optional single k/h multiplier suffix: "5k", "2h", "5000", "5.5k".
_SHORTHAND_RE = re.compile(r'^(\d+(?:\.\d+)?)\s*([kh])?$')


def parse_shorthand(text):
    """Parse a numeric shorthand amount ('5k'->5000, '2h'->200, '5000'->5000).

    Returns 0 when the text isn't a clean numeric shorthand — callers gate on ``> 0``.
    Anchored on a real pattern so arbitrary text containing 'k'/'h' (e.g. "5 cash")
    is no longer mis-parsed to 0 by stripping the letter.
    """
    m = _SHORTHAND_RE.match(text.lower().strip())
    if not m:
        return 0
    num = float(m.group(1))
    suffix = m.group(2)
    if suffix == 'k':
        num *= 1000
    elif suffix == 'h':
        num *= 100
    return int(num)
