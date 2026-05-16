const TEAM_LOGOS = {
  "Arizona Diamondbacks":   { abbr: "ARI", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/ari.png" },
  "Atlanta Braves":         { abbr: "ATL", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/atl.png" },
  "Baltimore Orioles":      { abbr: "BAL", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/bal.png" },
  "Boston Red Sox":         { abbr: "BOS", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/bos.png" },
  "Chicago Cubs":           { abbr: "CHC", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/chc.png" },
  "Chicago White Sox":      { abbr: "CWS", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/chw.png" },
  "Cincinnati Reds":        { abbr: "CIN", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/cin.png" },
  "Cleveland Guardians":    { abbr: "CLE", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/cle.png" },
  "Colorado Rockies":       { abbr: "COL", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/col.png" },
  "Detroit Tigers":         { abbr: "DET", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/det.png" },
  "Houston Astros":         { abbr: "HOU", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/hou.png" },
  "Kansas City Royals":     { abbr: "KC",  logo: "https://a.espncdn.com/i/teamlogos/mlb/500/kc.png" },
  "Los Angeles Angels":     { abbr: "LAA", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/laa.png" },
  "Los Angeles Dodgers":    { abbr: "LAD", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/lad.png" },
  "Miami Marlins":          { abbr: "MIA", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/mia.png" },
  "Milwaukee Brewers":      { abbr: "MIL", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/mil.png" },
  "Minnesota Twins":        { abbr: "MIN", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/min.png" },
  "New York Mets":          { abbr: "NYM", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/nym.png" },
  "New York Yankees":       { abbr: "NYY", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/nyy.png" },
  "Athletics":              { abbr: "ATH", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/oak.png" },
  "Oakland Athletics":      { abbr: "ATH", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/oak.png" },
  "Philadelphia Phillies":  { abbr: "PHI", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/phi.png" },
  "Pittsburgh Pirates":     { abbr: "PIT", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/pit.png" },
  "San Diego Padres":       { abbr: "SD",  logo: "https://a.espncdn.com/i/teamlogos/mlb/500/sd.png" },
  "San Francisco Giants":   { abbr: "SF",  logo: "https://a.espncdn.com/i/teamlogos/mlb/500/sf.png" },
  "Seattle Mariners":       { abbr: "SEA", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/sea.png" },
  "St. Louis Cardinals":    { abbr: "STL", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/stl.png" },
  "Tampa Bay Rays":         { abbr: "TB",  logo: "https://a.espncdn.com/i/teamlogos/mlb/500/tb.png" },
  "Texas Rangers":          { abbr: "TEX", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/tex.png" },
  "Toronto Blue Jays":      { abbr: "TOR", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/tor.png" },
  "Washington Nationals":   { abbr: "WSH", logo: "https://a.espncdn.com/i/teamlogos/mlb/500/wsh.png" },

  "Atlanta Hawks":          { abbr: "ATL", logo: "https://a.espncdn.com/i/teamlogos/nba/500/atl.png" },
  "Boston Celtics":         { abbr: "BOS", logo: "https://a.espncdn.com/i/teamlogos/nba/500/bos.png" },
  "Brooklyn Nets":          { abbr: "BKN", logo: "https://a.espncdn.com/i/teamlogos/nba/500/bkn.png" },
  "Charlotte Hornets":      { abbr: "CHA", logo: "https://a.espncdn.com/i/teamlogos/nba/500/cha.png" },
  "Chicago Bulls":          { abbr: "CHI", logo: "https://a.espncdn.com/i/teamlogos/nba/500/chi.png" },
  "Cleveland Cavaliers":    { abbr: "CLE", logo: "https://a.espncdn.com/i/teamlogos/nba/500/cle.png" },
  "Dallas Mavericks":       { abbr: "DAL", logo: "https://a.espncdn.com/i/teamlogos/nba/500/dal.png" },
  "Denver Nuggets":         { abbr: "DEN", logo: "https://a.espncdn.com/i/teamlogos/nba/500/den.png" },
  "Detroit Pistons":        { abbr: "DET", logo: "https://a.espncdn.com/i/teamlogos/nba/500/det.png" },
  "Golden State Warriors":  { abbr: "GSW", logo: "https://a.espncdn.com/i/teamlogos/nba/500/gs.png" },
  "Houston Rockets":        { abbr: "HOU", logo: "https://a.espncdn.com/i/teamlogos/nba/500/hou.png" },
  "Indiana Pacers":         { abbr: "IND", logo: "https://a.espncdn.com/i/teamlogos/nba/500/ind.png" },
  "LA Clippers":            { abbr: "LAC", logo: "https://a.espncdn.com/i/teamlogos/nba/500/lac.png" },
  "Los Angeles Clippers":   { abbr: "LAC", logo: "https://a.espncdn.com/i/teamlogos/nba/500/lac.png" },
  "Los Angeles Lakers":     { abbr: "LAL", logo: "https://a.espncdn.com/i/teamlogos/nba/500/lal.png" },
  "Memphis Grizzlies":      { abbr: "MEM", logo: "https://a.espncdn.com/i/teamlogos/nba/500/mem.png" },
  "Miami Heat":             { abbr: "MIA", logo: "https://a.espncdn.com/i/teamlogos/nba/500/mia.png" },
  "Milwaukee Bucks":        { abbr: "MIL", logo: "https://a.espncdn.com/i/teamlogos/nba/500/mil.png" },
  "Minnesota Timberwolves": { abbr: "MIN", logo: "https://a.espncdn.com/i/teamlogos/nba/500/min.png" },
  "New Orleans Pelicans":   { abbr: "NOP", logo: "https://a.espncdn.com/i/teamlogos/nba/500/no.png" },
  "New York Knicks":        { abbr: "NYK", logo: "https://a.espncdn.com/i/teamlogos/nba/500/ny.png" },
  "Oklahoma City Thunder":  { abbr: "OKC", logo: "https://a.espncdn.com/i/teamlogos/nba/500/okc.png" },
  "Orlando Magic":          { abbr: "ORL", logo: "https://a.espncdn.com/i/teamlogos/nba/500/orl.png" },
  "Philadelphia 76ers":     { abbr: "PHI", logo: "https://a.espncdn.com/i/teamlogos/nba/500/phi.png" },
  "Phoenix Suns":           { abbr: "PHX", logo: "https://a.espncdn.com/i/teamlogos/nba/500/phx.png" },
  "Portland Trail Blazers": { abbr: "POR", logo: "https://a.espncdn.com/i/teamlogos/nba/500/por.png" },
  "Sacramento Kings":       { abbr: "SAC", logo: "https://a.espncdn.com/i/teamlogos/nba/500/sac.png" },
  "San Antonio Spurs":      { abbr: "SAS", logo: "https://a.espncdn.com/i/teamlogos/nba/500/sa.png" },
  "Toronto Raptors":        { abbr: "TOR", logo: "https://a.espncdn.com/i/teamlogos/nba/500/tor.png" },
  "Utah Jazz":              { abbr: "UTA", logo: "https://a.espncdn.com/i/teamlogos/nba/500/utah.png" },
  "Washington Wizards":     { abbr: "WAS", logo: "https://a.espncdn.com/i/teamlogos/nba/500/wsh.png" }
};

function getTeamInfo(name) {
  if (TEAM_LOGOS[name]) return TEAM_LOGOS[name];
  const lower = name.toLowerCase();
  for (const key in TEAM_LOGOS) {
    if (key.toLowerCase() === lower) return TEAM_LOGOS[key];
  }
  for (const key in TEAM_LOGOS) {
    const keyLast = key.toLowerCase().split(' ').slice(-1)[0];
    const nameLast = lower.split(' ').slice(-1)[0];
    if (keyLast === nameLast) return TEAM_LOGOS[key];
  }
  return { abbr: name.substring(0, 3).toUpperCase(), logo: null };
}