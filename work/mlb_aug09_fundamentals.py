from math import sqrt

LG_R = 4.45
LG_OPS = .715

# team: (R/G, OPS, vsL OPS, vsR OPS, bullpen adjusted true-talent RA9, OAA)
T = {
    'CIN':(4.15,.709,.744,.698,4.59,7),'WSH':(5.34,.766,.782,.759,5.05,-15),
    'ATH':(4.32,.716,.709,.719,5.96,-30),'BOS':(4.48,.724,.773,.706,3.06,13),
    'NYM':(4.14,.689,.714,.680,3.87,-20),'PIT':(5.05,.748,.690,.773,4.21,-15),
    'TOR':(3.92,.681,.631,.699,4.27,6),'PHI':(4.42,.708,.692,.715,4.93,-10),
    'ATL':(4.91,.735,.713,.747,3.68,10),'NYY':(4.53,.722,.725,.721,3.09,5),
    'LAA':(4.11,.690,.705,.685,4.82,-22),'MIA':(4.34,.728,.707,.736,3.79,7),
    'CHC':(5.12,.752,.806,.733,3.98,58),'KC':(4.15,.711,.706,.712,5.65,7),
    'CLE':(3.98,.683,.659,.693,4.12,12),'CWS':(4.76,.720,.710,.724,4.24,8),
    'MIN':(4.66,.724,.682,.741,5.03,-18),'MIL':(4.97,.733,.686,.751,3.45,6),
    'COL':(4.82,.746,.713,.760,5.24,-7),'STL':(4.34,.694,.692,.695,4.30,27),
    'BAL':(4.43,.709,.706,.710,4.01,-17),'TEX':(4.14,.717,.746,.708,4.16,10),
    'DET':(4.58,.732,.706,.742,3.71,-23),'SF':(4.14,.717,.673,.734,4.76,-11),
    'LAD':(5.03,.768,.753,.774,4.38,23),'ARI':(4.52,.709,.781,.683,4.38,30),
    'TB':(4.44,.730,.681,.753,4.47,-9),'SEA':(3.91,.684,.652,.698,4.00,-39),
    'HOU':(4.64,.739,.710,.748,3.88,0),'SD':(4.21,.695,.668,.704,3.68,8),
}

# lineup weighted OPS where official; omitted means projected/uncertain.
LINEUP = {
    'CIN':.711,'WSH':.707,'ATH':.650,'BOS':.746,'TOR':.646,'PHI':.753,
    'ATL':.760,'NYY':.795,'LAA':.714,'MIA':.748,'KC':.735,'CWS':.708,
    'MIN':.710,'COL':.798,'STL':.712,
}

# game: away, home, starter xERA/IP for away and home, park/weather run factor.
G = [
    ('CIN','WSH',4.95,5.2,4.24,3.5,1.03),
    ('ATH','BOS',3.95,5.2,3.23,1.0,1.07),
    ('NYM','PIT',4.63,5.0,3.32,5.0,.98),
    ('TOR','PHI',7.43,4.5,2.95,5.9,1.05),
    ('ATL','NYY',4.70,4.9,2.95,5.8,1.05),
    ('LAA','MIA',7.20,4.6,4.42,4.0,.97),
    ('CHC','KC',4.57,5.6,4.86,5.0,1.04),
    ('CLE','CWS',3.98,5.0,4.60,5.5,.99),
    ('MIN','MIL',4.04,5.2,1.91,6.0,.95),
    ('COL','STL',5.84,4.5,5.62,5.5,1.05),
    ('BAL','TEX',4.70,5.0,4.45,5.1,.98),
    ('DET','SF',3.11,6.0,3.81,6.2,.93),
    ('LAD','ARI',4.51,6.1,4.86,5.9,.98),
    ('TB','SEA',3.47,5.0,4.09,5.5,.92),
]


def offense(team, opp_hand):
    rpg, ops, vsl, vsr, _, _ = T[team]
    split = vsl if opp_hand == 'L' else vsr
    out = rpg * (split / ops) ** 1.15
    if team in LINEUP:
        out *= (LINEUP[team] / ops) ** .65
    return out


def pitching(sp_xera, sp_ip, bp):
    return (sp_xera * sp_ip + bp * (9 - sp_ip)) / 9


HAND = {
    'Singer':'R','Lord':'R','Ginn':'R','Miller':'L','Manaea':'L','Jones':'R',
    'Bieber':'R','Luzardo':'L','Holmes':'R','Schlittler':'R','Rodriguez':'R',
    'Gusto':'R','Boyd':'L','Dobnak':'R','Cantillo':'L','Martin':'R',
    'Prielipp':'L','Misiorowski':'R','Lorenzen':'R','McGreevy':'R','Povich':'L',
    'Rocker':'R','Melton':'R','Webb':'R','Wrobleski':'L','ERod':'L',
    'Seymour':'L','Hancock':'R'
}
NAMES = [
    ('Singer','Lord'),('Ginn','Miller'),('Manaea','Jones'),('Bieber','Luzardo'),
    ('Holmes','Schlittler'),('Rodriguez','Gusto'),('Boyd','Dobnak'),
    ('Cantillo','Martin'),('Prielipp','Misiorowski'),('Lorenzen','McGreevy'),
    ('Povich','Rocker'),('Melton','Webb'),('Wrobleski','ERod'),('Seymour','Hancock')
]

for row, (an, hn) in zip(G, NAMES):
    a, h, ax, ai, hx, hi, park = row
    ao = offense(a, HAND[hn])
    ho = offense(h, HAND[an])
    ap = pitching(ax, ai, T[a][4])  # runs allowed by away pitching
    hp = pitching(hx, hi, T[h][4])  # runs allowed by home pitching
    amu = sqrt(ao * hp) * park - T[h][5] / 260 - .03
    hmu = sqrt(ho * ap) * park - T[a][5] / 260 + .08
    print(f'{a}@{h}: off={ao:.2f}/{ho:.2f} pit={hp:.2f}/{ap:.2f} mu={amu:.2f}-{hmu:.2f} total={amu+hmu:.2f}')
