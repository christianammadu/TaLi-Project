def parse_shorthand(text):
    text = text.lower().strip()
    if 'k' in text:
        try: return int(float(text.replace('k', '')) * 1000)
        except: return 0
    elif 'h' in text:
        try: return int(float(text.replace('h', '')) * 100)
        except: return 0
    try: return int(text)
    except: return 0
