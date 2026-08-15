from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import exp, lgamma, log


ALPHA = 0.12  # Gamma-Poisson overdispersion: Var(R) = mu + alpha * mu^2.
MAX_RUNS = 35

# Selection policy calibrated after the 2026-08-10 postmortem. A quoted EV is
# not enough on its own: totals must survive a modest error in the projected
# scoring environment, while sides must also stay reasonably close to the
# de-vigged public consensus.
TOTAL_FORMAL_MIN_EV = 0.06
TOTAL_MEAN_STRESS_RUNS = 0.30
TOTAL_WORST_CASE_MIN_EV = 0.00
SIDE_FORMAL_MIN_EV = 0.04
SIDE_MEAN_STRESS_RUNS = 0.40
SIDE_WORST_CASE_MIN_EV = 0.00
SIDE_MAX_MARKET_GAP = 0.04


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


def move_total_mean(away_mu: float, home_mu: float, delta: float) -> tuple[float, float]:
    """Move the game total mean while preserving the teams' scoring ratio."""
    total_mu = away_mu + home_mu
    if total_mu <= 0:
        raise ValueError("run means must sum to a positive value")
    stressed_total = max(0.10, total_mu + delta)
    scale = stressed_total / total_mu
    return away_mu * scale, home_mu * scale


def stressed_total_metrics(
    away_mu: float,
    home_mu: float,
    line: tuple,
    side: str,
    hk: float,
    stress_runs: float = TOTAL_MEAN_STRESS_RUNS,
):
    """Reprice a total after an adverse scoring-mean move.

    Overs are stressed by lowering the combined mean; unders are stressed by
    raising it. This catches small nominal edges that disappear when the run
    projection is wrong by only a few tenths.
    """
    if side not in {"over", "under"}:
        raise ValueError(f"unsupported total side: {side}")
    delta = -stress_runs if side == "over" else stress_runs
    stressed_away, stressed_home = move_total_mean(away_mu, home_mu, delta)
    metrics = total_metrics(final_score_dist(stressed_away, stressed_home), line, side, hk)
    return {
        **metrics,
        "away_mu": stressed_away,
        "home_mu": stressed_home,
        "stress_runs": stress_runs,
    }


def classify_total_pick(base_metrics: dict, stress_metrics: dict) -> str:
    """Return FORMAL only for totals with both sufficient and robust EV."""
    if (
        base_metrics["ev"] >= TOTAL_FORMAL_MIN_EV
        and stress_metrics["ev"] >= TOTAL_WORST_CASE_MIN_EV
    ):
        return "FORMAL"
    if base_metrics["ev"] > 0:
        return "WATCH"
    return "PASS"


def away_cover_probability(dist, away_run_line: float) -> float:
    """Probability that the away team covers a standard half-run spread."""
    return sum(
        mass
        for (away_runs, home_runs), mass in dist.items()
        if away_runs + away_run_line > home_runs
    )


def stressed_side_metrics(
    game: Game,
    back_away: bool,
    hk: float,
    market_prob: float,
    stress_runs: float = SIDE_MEAN_STRESS_RUNS,
):
    """Reprice a side after reducing the backed team's run mean."""
    away_mu, home_mu = game.away_mu, game.home_mu
    if back_away:
        away_mu = max(0.10, away_mu - stress_runs)
    else:
        home_mu = max(0.10, home_mu - stress_runs)
    away_cover = away_cover_probability(final_score_dist(away_mu, home_mu), game.away_run_line)
    prob = away_cover if back_away else 1 - away_cover
    metrics = binary_metrics(prob, hk, market_prob)
    return {
        **metrics,
        "away_mu": away_mu,
        "home_mu": home_mu,
        "stress_runs": stress_runs,
    }


def classify_side_pick(base_metrics: dict, stress_metrics: dict) -> str:
    """Classify a side using EV, robustness and public-market agreement."""
    if base_metrics["ev"] <= 0:
        return "PASS"
    if abs(base_metrics["gap"]) > SIDE_MAX_MARKET_GAP:
        return "CONFLICT"
    if (
        base_metrics["ev"] >= SIDE_FORMAL_MIN_EV
        and stress_metrics["ev"] >= SIDE_WORST_CASE_MIN_EV
    ):
        return "FORMAL"
    if base_metrics["ev"] >= SIDE_FORMAL_MIN_EV:
        return "CONDITIONAL"
    return "WATCH"


def pct(x):
    return f"{100*x:6.2f}%"


def fmt(m):
    return (
        f"P={pct(m.get('p', m.get('p_eff')))} fairHK={m['fair_hk']:.3f} "
        f"EV={pct(m['ev'])} gap={100*m['gap']:+.2f}pp minHK={m['min_hk']:.3f}"
    )


def analyze_game(g: Game):
    dist = final_score_dist(g.away_mu, g.home_mu)
    away_cover = away_cover_probability(dist, g.away_run_line)
    home_cover = 1 - away_cover
    mkt_away, mkt_home = devig_pair(g.rl_away_hk, g.rl_home_hk)
    a_metrics = binary_metrics(away_cover, g.rl_away_hk, mkt_away)
    h_metrics = binary_metrics(home_cover, g.rl_home_hk, mkt_home)
    o_metrics = total_metrics(dist, g.total_line, "over", g.total_hk)
    u_metrics = total_metrics(dist, g.total_line, "under", g.total_hk)
    o_stress = stressed_total_metrics(
        g.away_mu, g.home_mu, g.total_line, "over", g.total_hk
    )
    u_stress = stressed_total_metrics(
        g.away_mu, g.home_mu, g.total_line, "under", g.total_hk
    )
    print(f"\n{g.away}@{g.home} mu={g.away_mu:.2f}-{g.home_mu:.2f} line={g.total_line}")
    print(f"  away {g.away_run_line:+.1f}", fmt(a_metrics), f"mkt={pct(mkt_away)}")
    print(f"  home {-g.away_run_line:+.1f}", fmt(h_metrics), f"mkt={pct(mkt_home)}")
    print(
        "  over      ",
        fmt(o_metrics),
        f"stressEV={pct(o_stress['ev'])} {classify_total_pick(o_metrics, o_stress)}",
    )
    print(
        "  under     ",
        fmt(u_metrics),
        f"stressEV={pct(u_stress['ev'])} {classify_total_pick(u_metrics, u_stress)}",
    )
    pub_line, over_us, under_us, over_book, under_book = PUBLIC_TOTALS[f"{g.away}@{g.home}"]
    public_spec = (pub_line, "half" if pub_line % 1 else "flat", 0)
    po = total_metrics(dist, public_spec, "over", american_to_hk(over_us))
    pu = total_metrics(dist, public_spec, "under", american_to_hk(under_us))
    po_stress = stressed_total_metrics(
        g.away_mu, g.home_mu, public_spec, "over", american_to_hk(over_us)
    )
    pu_stress = stressed_total_metrics(
        g.away_mu, g.home_mu, public_spec, "under", american_to_hk(under_us)
    )
    print(
        f"  public O{pub_line:g} {over_us:+g} {over_book:<12}",
        fmt(po),
        f"stressEV={pct(po_stress['ev'])} {classify_total_pick(po, po_stress)}",
    )
    print(
        f"  public U{pub_line:g} {under_us:+g} {under_book:<12}",
        fmt(pu),
        f"stressEV={pct(pu_stress['ev'])} {classify_total_pick(pu, pu_stress)}",
    )
    _, cons_a_us, cons_h_us, best_a_us, best_a_book, best_h_us, best_h_book = PUBLIC_RL[f"{g.away}@{g.home}"]
    cons_a_hk, cons_h_hk = american_to_hk(cons_a_us), american_to_hk(cons_h_us)
    cons_a_p, cons_h_p = devig_pair(cons_a_hk, cons_h_hk)
    best_a = binary_metrics(away_cover, american_to_hk(best_a_us), cons_a_p)
    best_h = binary_metrics(home_cover, american_to_hk(best_h_us), cons_h_p)
    best_a_stress = stressed_side_metrics(
        g, True, american_to_hk(best_a_us), cons_a_p
    )
    best_h_stress = stressed_side_metrics(
        g, False, american_to_hk(best_h_us), cons_h_p
    )
    print(
        f"  best awayRL {best_a_us:+g} {best_a_book:<12}",
        fmt(best_a),
        f"cons={pct(cons_a_p)} stressEV={pct(best_a_stress['ev'])}",
        classify_side_pick(best_a, best_a_stress),
    )
    print(
        f"  best homeRL {best_h_us:+g} {best_h_book:<12}",
        fmt(best_h),
        f"cons={pct(cons_h_p)} stressEV={pct(best_h_stress['ev'])}",
        classify_side_pick(best_h, best_h_stress),
    )


def main():
    print(
        "Selection policy: "
        f"totals EV>={pct(TOTAL_FORMAL_MIN_EV)} and adverse {TOTAL_MEAN_STRESS_RUNS:.1f}-run "
        f"stress EV>={pct(TOTAL_WORST_CASE_MIN_EV)}; "
        f"sides EV>={pct(SIDE_FORMAL_MIN_EV)}, adverse {SIDE_MEAN_STRESS_RUNS:.1f}-run "
        f"stress EV>={pct(SIDE_WORST_CASE_MIN_EV)}, "
        f"market gap<={100 * SIDE_MAX_MARKET_GAP:.1f}pp."
    )
    for game in GAMES:
        analyze_game(game)


if __name__ == "__main__":
    main()
