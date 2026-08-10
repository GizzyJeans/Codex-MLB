import numpy as np

SEED = 20260809
N = 2_000_000

# Pregame run means. These are independent of the betting market and combine
# handedness-adjusted offense, confirmed-lineup quality where available,
# SP xERA/expected innings, bullpen availability, defense, park and weather.
GAMES = {
    "CIN@WSH": (4.56, 5.11),
    "ATH@BOS": (3.68, 5.13),
    "NYM@PIT": (3.84, 4.51),
    "TOR@PHI": (3.74, 5.54),
    "ATL@NYY": (4.06, 4.78),
    "LAA@MIA": (3.94, 5.20),
    "CHC@KC": (5.24, 4.30),
    "CLE@CWS": (4.15, 4.32),
    "MIN@MIL": (3.16, 4.45),
    "COL@STL": (5.25, 5.30),
    "BAL@TEX": (4.22, 4.42),
    "DET@SF": (4.08, 3.66),
    "LAD@ARI": (4.56, 4.65),
    "TB@SEA": (4.09, 3.62),
}

rng = np.random.default_rng(SEED)

def simulate(mu_a, mu_h):
    # Gamma-Poisson mixture: a shared game environment plus team-specific
    # overdispersion. This is deliberately fatter-tailed than Poisson.
    common = rng.gamma(25.0, 1.0 / 25.0, N)
    fa = rng.gamma(10.0, 1.0 / 10.0, N)
    fh = rng.gamma(10.0, 1.0 / 10.0, N)
    a = rng.poisson(mu_a * common * fa)
    h = rng.poisson(mu_h * common * fh)

    # Resolve 9-inning ties as a conservative extra-inning approximation.
    tie = a == h
    n_tie = int(tie.sum())
    if n_tie:
        away_extra_win = rng.random(n_tie) < (mu_a / (mu_a + mu_h))
        idx = np.flatnonzero(tie)
        a[idx[away_extra_win]] += 1
        h[idx[~away_extra_win]] += 1
    return a, h

def pct(x):
    return 100.0 * float(np.mean(x))

for game, (ma, mh) in GAMES.items():
    a, h = simulate(ma, mh)
    t = a + h
    d = h - a
    vals, counts = np.unique(t, return_counts=True)
    exact = dict(zip(vals.tolist(), (counts / N).tolist()))
    print(f"\n{game} mean={ma:.2f}-{mh:.2f} pred={round(ma)}-{round(mh)}")
    print(f"away+1.5={pct(a+1.5>h):.2f} home-1.5={pct(d>=2):.2f} "
          f"home+1.5={pct(h+1.5>a):.2f} away-1.5={pct(a-h>=2):.2f}")
    for line in (7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.5):
        if line.is_integer():
            win_o = pct(t > line); push = pct(t == line); win_u = pct(t < line)
            print(f"T{line:.1f} O={win_o:.2f} P={push:.2f} U={win_u:.2f}")
        else:
            print(f"T{line:.1f} O={pct(t>line):.2f} U={pct(t<line):.2f}")
