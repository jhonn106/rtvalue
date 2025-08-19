def is_market_open_jkt(dt):
    hhmm = dt.strftime("%H%M")
    return "0855" <= hhmm <= "1600"
