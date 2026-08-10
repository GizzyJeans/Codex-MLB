from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import exp, lgamma, log


ALPHA = 0.12  # Gamma-Poisson overdispersion: Var(R) = mu + alpha * mu^2.
MAX_RUNS = 35


@dataclass(frozen=True)
class Game:
    away: str
    home: str
    away_mu: float
    home_mu: float
    total_line: tuple
    total_hk: float
    away_run_line: float
    rl_away_hk: float
    rl_home_hk: float


GAMES = [
    # NYY batting order was official at the last check; the away ATL order was not.
    Game("ATL", "NYY", 4.05, 3.25, (7, "minus", .80), .94, -1.5, 1.28, .70),
    Game("ATH", "BOS", 3.25, 5.60, (9, "minus", .10), .94, +1.5, 1.14, .79),
    Game("LAA", "MIA", 3.55, 3.90, (7, "minus", .60), .94, +1.5, .64, 1.42),
    Game("TOR", "PHI", 4.50, 5.75, (9.5, "half", 0), .94, +1.5, .71, 1.26),
    Game("NYM", "PIT", 3.65, 5.20, (9, "plus", .20), .94, +1.5, .55, 1.63),
    Game("CIN", "WSH", 4.90, 4.20, (8.5, "half", 0), .94, -1.5, 1.18, .77),
    Game("CHC", "KC", 5.55, 3.75, (9, "minus", .70), .94, -1.5, .95, .95),
    Game("MIN", "MIL", 3.55, 4.55, (8, "minus", .30), .94, +1.5, .64, 1.41),
    Game("COL", "STL", 3.60, 4.80, (8.5, "half", 0), .94, +1.5, .64, 1.40),
    Game("CLE", "CWS", 3.90, 3.30, (7, "minus", .70), .94, -1.5, 1.41, .64),
    Game("BAL", "TEX", 3.35, 4.05, (7, "minus", .70), .94, +1.5, .60, 1.50),
    Game("DET", "SF", 4.15, 3.75, (8, "flat", 0), .94, -1.5, 1.46, .559),
    Game("HOU", "SD", 4.05, 3.95, (8, "plus", .40), .94, +1.5, .50, 1.65),
    Game("LAD", "ARI", 5.05, 3.25, (8, "minus", .90), .94, -1.5, .926, .885),
    Game("TB", "SEA", 3.70, 3.65, (7, "flat", 0), .94, +1.5, .476, 1.77),
]

# Best observed current full-game total from the cross-book snapshot.  These are
# standard totals; several differ from the user's Taiwan split/tail line above.
PUBLIC_TOTALS = {
    "ATL@NYY": (7.5, -100, -115, "FanDuel", "BetMGM/bet365/Caesars"),
    "ATH@BOS": (9.0, -113, +102, "DraftKings", "BetRivers"),
    "LAA@MIA": (7.5, +102, -117, "BetRivers", "DraftKings"),
    "TOR@PHI": (9.5, -106.38, -106.38, "User", "User"),
    "NYM@PIT": (9.0, -106, -110, "DraftKings", "BetRivers/bet365"),
    "CIN@WSH": (8.5, -106.38, +100, "User", "BetRivers"),
    "CHC@KC": (9.5, +100, -117, "Multiple", "BetRivers"),
    "MIN@MIL": (8.0, -105, -108, "bet365", "FanDuel"),
    "COL@STL": (8.5, -106.38, -105, "User", "Multiple"),
    "CLE@CWS": (7.5, +102, -120, "BetRivers", "Multiple"),
    "BAL@TEX": (7.5, +100, -110, "bet365", "BetMGM"),
    "DET@SF": (8.0, -106.38, -105, "User", "Multiple"),
    "HOU@SD": (8.0, -105, -114, "Multiple", "BetRivers"),
    "LAD@ARI": (8.5, -105, -108, "Multiple", "BetRivers"),
    "TB@SEA": (7.0, -105, -106.38, "bet365", "User"),
}

# Consensus de-vig reference and best observed price for the same standard RL.
# American odds; "User" is the confirmed-access screenshot book.
PUBLIC_RL = {
    "ATL@NYY": (-1.5, +124, -149, +128, "User", -140, "bet365"),
    "ATH@BOS": (+1.5, +108, -131, +118, "Caesars", -125, "DraftKings"),
    "LAA@MIA": (+1.5, -160, +135, -153, "DraftKings", +142, "User"),
    "TOR@PHI": (+1.5, -145, +120, -140, "bet365/Caesars", +126, "User"),
    "NYM@PIT": (+1.5, -190, +156, -181.82, "User", +164, "FanDuel"),
    "CIN@WSH": (-1.5, +114, -136, +118, "User", -129.87, "User"),
    "CHC@KC": (-1.5, -109, -111, -102, "FanDuel", -105, "bet365"),
    "MIN@MIL": (+1.5, -171, +141, -156.25, "User", +150, "FanDuel"),
    "COL@STL": (+1.5, -160, +135, -156.25, "User", +140, "User"),
    "CLE@CWS": (-1.5, +131, -158, +141, "User", -150, "bet365"),
    "BAL@TEX": (+1.5, -176, +145, -166.67, "User", +150, "User/BetMGM"),
    "DET@SF": (-1.5, +142, -173, +145, "BetMGM", -164, "FanDuel"),
    "HOU@SD": (+1.5, -200, +165, -195, "Caesars", +167, "DraftKings"),
    "LAD@ARI": (-1.5, -110, -110, -104, "FanDuel", -105, "bet365"),
    # The consensus feed crosses the favorite on this near-pick'em game; use
    # bet365's internally coherent TB +1.5 / SEA -1.5 pair for de-vigging.
    "TB@SEA": (+1.5, -210, +175, -210, "bet365", +188, "FanDuel"),
}


def nb_pmf(mu: float, max_runs: int = MAX_RUNS) -> list[float]:
    """Negative-binomial PMF with a mean/dispersion parameterization."""
    r = 1.0 / ALPHA
    p = r / (r + mu)
    out = []
    for k in range(max_runs + 1):
        logp = lgamma(k + r) - lgamma(r) - lgamma(k + 1)
        logp += r * log(p) + k * log(1 - p)
        out.append(exp(logp))
    # Negligible tail is folded into the final bucket.
    out[-1] += 1.0 - sum(out)
    return out


def final_score_dist(away_mu: float, home_mu: float):
    """Joint score distribution; tied regulation games receive a simple extras model."""
    pa = nb_pmf(away_mu)
    ph = nb_pmf(home_mu)
    dist = defaultdict(float)
    extra_patterns = [((1, 0), .64), ((2, 0), .18), ((2, 1), .12), ((3, 1), .04), ((3, 2), .02)]
    for a, p_a in enumerate(pa):
        for h, p_h in enumerate(ph):
            mass = p_a * p_h
            if a != h:
                dist[(a, h)] += mass
                continue
            for (w, l), p_extra in extra_patterns:
                # Home wins an extra-inning tie slightly more often.
                dist[(a + l, h + w)] += mass * p_extra * .54
                dist[(a + w, h + l)] += mass * p_extra * .46
    return dist


def devig_pair(h1: float, h2: float) -> tuple[float, float]:
    q1, q2 = 1 / (1 + h1), 1 / (1 + h2)
    return q1 / (q1 + q2), q2 / (q1 + q2)


def american_to_hk(price: float) -> float:
    return price / 100 if price > 0 else 100 / abs(price)


def binary_metrics(prob: float, hk: float, market_prob: float):
    ev = prob * hk - (1 - prob)
    fair_hk = (1 - prob) / prob
    min_hk = (1.04 - prob) / prob
    full_kelly = max(0.0, (prob * hk - (1 - prob)) / hk)
    return {
        "p": prob,
        "fair_hk": fair_hk,
        "ev": ev,
        "gap": prob - market_prob,
        "min_hk": min_hk,
        "qk_stake": min(1000, 100000 * .25 * full_kelly),
    }


def total_wln(dist, line: tuple, side: str):
    n, kind, x = line
    w = l = neutral = 0.0
    for (a, h), mass in dist.items():
        t = a + h
        if t > n:
            outcome = "over"
        elif t < n:
            outcome = "under"
        else:
            outcome = "equal"

        if kind == "half":
            is_win = (side == "over" and t > n) or (side == "under" and t < n)
            if is_win:
                w += mass
            else:
                l += mass
        elif kind == "flat":
            if outcome == "equal":
                neutral += mass
            elif outcome == side:
                w += mass
            else:
                l += mass
        elif kind == "minus":
            if outcome == "equal":
                # N-x: Over loses x; Under wins x; the balance pushes.
                if side == "over":
                    l += x * mass
                else:
                    w += x * mass
                neutral += (1 - x) * mass
            elif outcome == side:
                w += mass
            else:
                l += mass
        elif kind == "plus":
            if outcome == "equal":
                # N+x: Over wins x; Under loses x; the balance pushes.
                if side == "over":
                    w += x * mass
                else:
                    l += x * mass
                neutral += (1 - x) * mass
            elif outcome == side:
                w += mass
            else:
                l += mass
        else:
            raise ValueError(kind)
    return w, l, neutral


def total_metrics(dist, line: tuple, side: str, hk: float):
    w, l, neutral = total_wln(dist, line, side)
    effective_p = w / (w + l)
    ev = hk * w - l
    fair_hk = l / w
    min_hk = (l + .04) / w
    return {
        "p_eff": effective_p,
        "win_mass": w,
        "loss_mass": l,
        "neutral": neutral,
        "fair_hk": fair_hk,
        "ev": ev,
        "gap": effective_p - .50,
        "min_hk": min_hk,
    }


def pct(x):
    return f"{100*x:6.2f}%"


def fmt(m):
    return (
        f"P={pct(m.get('p', m.get('p_eff')))} fairHK={m['fair_hk']:.3f} "
        f"EV={pct(m['ev'])} gap={100*m['gap']:+.2f}pp minHK={m['min_hk']:.3f}"
    )


for g in GAMES:
    dist = final_score_dist(g.away_mu, g.home_mu)
    if g.away_run_line == -1.5:
        away_cover = sum(p for (a, h), p in dist.items() if a - h >= 2)
    else:
        away_cover = sum(p for (a, h), p in dist.items() if a - h >= -1)
    home_cover = 1 - away_cover
    mkt_away, mkt_home = devig_pair(g.rl_away_hk, g.rl_home_hk)
    a_metrics = binary_metrics(away_cover, g.rl_away_hk, mkt_away)
    h_metrics = binary_metrics(home_cover, g.rl_home_hk, mkt_home)
    o_metrics = total_metrics(dist, g.total_line, "over", g.total_hk)
    u_metrics = total_metrics(dist, g.total_line, "under", g.total_hk)
    print(f"\n{g.away}@{g.home} mu={g.away_mu:.2f}-{g.home_mu:.2f} line={g.total_line}")
    print(f"  away {g.away_run_line:+.1f}", fmt(a_metrics), f"mkt={pct(mkt_away)}")
    print(f"  home {-g.away_run_line:+.1f}", fmt(h_metrics), f"mkt={pct(mkt_home)}")
    print("  over      ", fmt(o_metrics))
    print("  under     ", fmt(u_metrics))
    pub_line, over_us, under_us, over_book, under_book = PUBLIC_TOTALS[f"{g.away}@{g.home}"]
    public_spec = (pub_line, "half" if pub_line % 1 else "flat", 0)
    po = total_metrics(dist, public_spec, "over", american_to_hk(over_us))
    pu = total_metrics(dist, public_spec, "under", american_to_hk(under_us))
    print(f"  public O{pub_line:g} {over_us:+g} {over_book:<12}", fmt(po))
    print(f"  public U{pub_line:g} {under_us:+g} {under_book:<12}", fmt(pu))
    _, cons_a_us, cons_h_us, best_a_us, best_a_book, best_h_us, best_h_book = PUBLIC_RL[f"{g.away}@{g.home}"]
    cons_a_hk, cons_h_hk = american_to_hk(cons_a_us), american_to_hk(cons_h_us)
    cons_a_p, cons_h_p = devig_pair(cons_a_hk, cons_h_hk)
    best_a = binary_metrics(away_cover, american_to_hk(best_a_us), cons_a_p)
    best_h = binary_metrics(home_cover, american_to_hk(best_h_us), cons_h_p)
    print(f"  best awayRL {best_a_us:+g} {best_a_book:<12}", fmt(best_a), f"cons={pct(cons_a_p)}")
    print(f"  best homeRL {best_h_us:+g} {best_h_book:<12}", fmt(best_h), f"cons={pct(cons_h_p)}")
