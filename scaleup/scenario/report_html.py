"""Professional, self-contained HTML T&E report for a scenario run.

Design: a single committed dark 'ops-console' theme (a deliberate tactical
look, not a themed toggle). Colours are the data-viz skill's validated default
palette: blue+orange for the two tracks (best-separated CVD-safe pair), status
colours reserved for severity and always paired with a text label. Hand-built
static SVG -- no JS, no CDN, no external assets (renders anywhere, CSP-safe).

to_html(result, scenario) -> str
"""
import html as _html
from . import geo, standards

# --- validated palette (dark steps + chrome) --------------------------------
PLANE   = "#0d0d0d"
SURFACE = "#15151a"
PANEL   = "#1a1a19"
INK     = "#ffffff"
INK2    = "#c3c2b7"
MUTED   = "#898781"
GRID    = "#2c2c2a"
AXIS    = "#383835"
RING    = "rgba(255,255,255,0.10)"
BELIEVED = "#3987e5"   # slot 1 blue  -- what the autopilot believes (the clean reference)
TRUE     = "#d95926"   # slot 2 orange-- where the hull actually goes (the divergence)
CONTACT  = "#d55181"   # slot 5 magenta-- other vessel
STATUS = {"critical": "#d03b3b", "high": "#ec835a", "medium": "#fab219",
          "low": "#898781", "none": "#0ca30c"}
NOGO_COL = "#d03b3b"    # status-critical red  -- danger region
SHOAL_COL = "#fab219"   # status-warning amber -- navigational hazard
SEV_LABEL = {"none": "NO IMPACT", "low": "LOW", "medium": "MEDIUM",
             "high": "HIGH", "critical": "CRITICAL"}

MAP_W, MAP_H, PAD = 860, 500, 54
CH_W, CH_H = 860, 240


def _esc(s):
    return _html.escape(str(s))


def _nice_scale_m(span_m):
    """A round distance (m) ~1/4 of the span for the scale bar."""
    target = span_m / 4.0
    for v in (10, 20, 25, 50, 100, 150, 200, 250, 500, 1000, 2000):
        if v >= target:
            return v
    return 5000


def _projection(latlon_pts):
    ref_lat, ref_lon = latlon_pts[0]
    mlon = geo.m_per_deg_lon(ref_lat)

    def ne(lat, lon):
        return ((lat - ref_lat) * geo.M_PER_DEG_LAT, (lon - ref_lon) * mlon)

    nes = [ne(la, lo) for la, lo in latlon_pts]
    ns = [p[0] for p in nes]; es = [p[1] for p in nes]
    nmin, nmax, emin, emax = min(ns), max(ns), min(es), max(es)
    nrange = (nmax - nmin) or 1.0
    erange = (emax - emin) or 1.0
    scale = min((MAP_W - 2 * PAD) / erange, (MAP_H - 2 * PAD) / nrange)
    ox = PAD + ((MAP_W - 2 * PAD) - erange * scale) / 2.0
    oy = PAD + ((MAP_H - 2 * PAD) - nrange * scale) / 2.0

    def project(lat, lon):
        n, e = ne(lat, lon)
        return (ox + (e - emin) * scale, MAP_H - (oy + (n - nmin) * scale))

    return project, scale, max(nrange, erange)


def _poly(points):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def _sample_at(telemetry, t):
    return min(telemetry, key=lambda s: abs(s["t"] - telemetry[0]["t"] - t))


def _map_svg(result, scenario):
    tel = result.telemetry
    if not tel:
        return "<p>No telemetry.</p>"
    dur = tel[-1]["t"] - tel[0]["t"]

    # gather every point so the projection frames all geometry
    pts = [tuple(scenario.mission["start"]), tuple(scenario.mission["goal"])]
    pts += [(s["true_lat"], s["true_lon"]) for s in tel]
    pts += [(s["believed_lat"], s["believed_lon"]) for s in tel]
    for h in scenario.hazards:
        if h.type == "nogo_zone":
            pts += [(v[0], v[1]) for v in h.polygon]
        elif h.type == "shoal" and h.point:
            for dn in (-h.radius_m, h.radius_m):
                for de in (-h.radius_m, h.radius_m):
                    pts.append(geo.offset_m(h.point[0], h.point[1], dn, de))
    for c in scenario.contacts:
        pts.append(tuple(c.start))
        pts.append(geo.offset_m(c.start[0], c.start[1],
                                c.velocity_ne_mps[0] * dur, c.velocity_ne_mps[1] * dur))
    project, scale, span_m = _projection(pts)

    el = []
    el.append(f'<rect x="0" y="0" width="{MAP_W}" height="{MAP_H}" rx="6" fill="{SURFACE}" stroke="{RING}"/>')

    # faint grid
    for gx in range(PAD, MAP_W - PAD + 1, 72):
        el.append(f'<line x1="{gx}" y1="{PAD}" x2="{gx}" y2="{MAP_H-PAD}" stroke="{GRID}" stroke-width="1"/>')
    for gy in range(PAD, MAP_H - PAD + 1, 72):
        el.append(f'<line x1="{PAD}" y1="{gy}" x2="{MAP_W-PAD}" y2="{gy}" stroke="{GRID}" stroke-width="1"/>')

    # hazards
    for h in scenario.hazards:
        if h.type == "nogo_zone":
            poly = _poly([project(v[0], v[1]) for v in h.polygon])
            el.append(f'<polygon points="{poly}" fill="{NOGO_COL}" fill-opacity="0.10" '
                      f'stroke="{NOGO_COL}" stroke-opacity="0.65" stroke-width="1.5" stroke-dasharray="6 4"/>')
            vx, vy = project(h.polygon[0][0], h.polygon[0][1])
            el.append(f'<text x="{vx+6:.0f}" y="{vy+16:.0f}" fill="{NOGO_COL}" '
                      f'font-size="11" font-weight="600" opacity="0.9">NO-GO: {_esc(h.name)}</text>')
        elif h.type == "shoal" and h.point:
            cx, cy = project(h.point[0], h.point[1])
            r = max(h.radius_m * scale, 3)
            el.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{SHOAL_COL}" '
                      f'fill-opacity="0.12" stroke="{SHOAL_COL}" stroke-opacity="0.7" '
                      f'stroke-width="1.5" stroke-dasharray="3 3"/>')
            el.append(f'<path d="M{cx-4:.1f},{cy-4:.1f} l8,8 M{cx+4:.1f},{cy-4:.1f} l-8,8" '
                      f'stroke="{SHOAL_COL}" stroke-width="1.6"/>')
            el.append(f'<text x="{cx:.0f}" y="{cy-r-6:.0f}" fill="{SHOAL_COL}" font-size="11" '
                      f'font-weight="600" text-anchor="middle">SHOAL: {_esc(h.name)}</text>')

    # contact track
    for c in scenario.contacts:
        a = project(*c.start)
        blat, blon = geo.offset_m(c.start[0], c.start[1],
                                  c.velocity_ne_mps[0] * dur, c.velocity_ne_mps[1] * dur)
        b = project(blat, blon)
        el.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                  f'stroke="{CONTACT}" stroke-width="1.6" stroke-dasharray="2 5" opacity="0.85"/>')
        el.append(f'<text x="{b[0]+6:.0f}" y="{b[1]:.0f}" fill="{CONTACT}" font-size="11">contact: {_esc(c.name)}</text>')

    # believed (reference) then true (divergence) on top
    el.append(f'<polyline points="{_poly([project(s["believed_lat"], s["believed_lon"]) for s in tel])}" '
              f'fill="none" stroke="{BELIEVED}" stroke-width="2" opacity="0.95"/>')
    el.append(f'<polyline points="{_poly([project(s["true_lat"], s["true_lon"]) for s in tel])}" '
              f'fill="none" stroke="{TRUE}" stroke-width="2.6"/>')

    # start / goal
    sx, sy = project(*scenario.mission["start"])
    gx, gy = project(*scenario.mission["goal"])
    el.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="5" fill="{BELIEVED}"/>')
    el.append(f'<text x="{sx+8:.0f}" y="{sy+4:.0f}" fill="{INK2}" font-size="11" font-weight="600">START</text>')
    el.append(f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="5" fill="none" stroke="{BELIEVED}" stroke-width="2"/>')
    el.append(f'<text x="{gx+8:.0f}" y="{gy+4:.0f}" fill="{INK2}" font-size="11" font-weight="600">GOAL</text>')

    # annotate each TRIGGERED consequence at the TRUE position when it fired
    for r in result.results:
        if not r.triggered or r.at_s < 0:
            continue
        s = _sample_at(tel, r.at_s)
        x, y = project(s["true_lat"], s["true_lon"])
        col = STATUS.get(r.severity, MUTED)
        label = {"grounding": "GROUNDING", "nogo_breach": "NO-GO BREACH",
                 "cpa_violation": f"CPA {r.metric:.0f} m", "position_divergence": ""}.get(r.type, r.type)
        el.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="{col}" stroke="{PLANE}" stroke-width="1.5"/>')
        if label:
            anchor = "end" if x > MAP_W / 2 else "start"
            dx = -9 if anchor == "end" else 9
            el.append(f'<text x="{x+dx:.0f}" y="{y-8:.0f}" fill="{col}" font-size="11" '
                      f'font-weight="700" text-anchor="{anchor}">{_esc(label)}</text>')

    # scale bar + north arrow
    sb = _nice_scale_m(span_m)
    sbpx = sb * scale
    bx, by = PAD, MAP_H - 24
    el.append(f'<line x1="{bx}" y1="{by}" x2="{bx+sbpx:.1f}" y2="{by}" stroke="{INK2}" stroke-width="2"/>')
    el.append(f'<line x1="{bx}" y1="{by-4}" x2="{bx}" y2="{by+4}" stroke="{INK2}" stroke-width="2"/>')
    el.append(f'<line x1="{bx+sbpx:.1f}" y1="{by-4}" x2="{bx+sbpx:.1f}" y2="{by+4}" stroke="{INK2}" stroke-width="2"/>')
    el.append(f'<text x="{bx+sbpx/2:.0f}" y="{by-8:.0f}" fill="{MUTED}" font-size="11" text-anchor="middle">{sb} m</text>')
    nx, ny = MAP_W - PAD - 6, PAD + 6
    el.append(f'<path d="M{nx},{ny+26} L{nx},{ny}" stroke="{INK2}" stroke-width="1.5"/>')
    el.append(f'<path d="M{nx-4},{ny+6} L{nx},{ny} L{nx+4},{ny+6} Z" fill="{INK2}"/>')
    el.append(f'<text x="{nx}" y="{ny+40}" fill="{MUTED}" font-size="11" text-anchor="middle">N</text>')

    return f'<svg viewBox="0 0 {MAP_W} {MAP_H}" width="100%" role="img" ' \
           f'aria-label="Tactical map: true vs believed track">{"".join(el)}</svg>'


def _divergence_svg(result, scenario):
    tel = result.telemetry
    if not tel:
        return ""
    t0 = tel[0]["t"]
    series = [(s["t"] - t0, geo.horiz_m(s["true_lat"], s["true_lon"], s["believed_lat"], s["believed_lon"]))
              for s in tel]
    dur = series[-1][0] or 1.0
    thresh = next((c.threshold_m for c in scenario.consequences if c.type == "position_divergence"), 0)
    ymax = max(max(v for _, v in series), thresh) * 1.15 or 1.0
    L, R, T, B = 56, 20, 18, 34
    pw, ph = CH_W - L - R, CH_H - T - B

    def px(t): return L + (t / dur) * pw
    def py(v): return T + ph - (v / ymax) * ph

    el = [f'<rect x="0" y="0" width="{CH_W}" height="{CH_H}" rx="6" fill="{SURFACE}" stroke="{RING}"/>']
    # y gridlines + ticks
    for i in range(5):
        v = ymax * i / 4
        y = py(v)
        el.append(f'<line x1="{L}" y1="{y:.1f}" x2="{CH_W-R}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        el.append(f'<text x="{L-8}" y="{y+4:.1f}" fill="{MUTED}" font-size="11" text-anchor="end" '
                  f'font-variant-numeric="tabular-nums">{v:.0f}</text>')
    # x ticks
    for i in range(5):
        t = dur * i / 4
        x = px(t)
        el.append(f'<text x="{x:.1f}" y="{CH_H-12}" fill="{MUTED}" font-size="11" text-anchor="middle" '
                  f'font-variant-numeric="tabular-nums">{t:.0f}</text>')
    el.append(f'<text x="{L-40}" y="{T+10}" fill="{MUTED}" font-size="11">metres</text>')
    el.append(f'<text x="{CH_W-R}" y="{CH_H-12}" fill="{MUTED}" font-size="11" text-anchor="end">seconds</text>')

    # tolerance threshold line
    if thresh:
        yt = py(thresh)
        el.append(f'<line x1="{L}" y1="{yt:.1f}" x2="{CH_W-R}" y2="{yt:.1f}" stroke="{MUTED}" '
                  f'stroke-width="1.3" stroke-dasharray="5 4"/>')
        el.append(f'<text x="{CH_W-R-4}" y="{yt-6:.1f}" fill="{MUTED}" font-size="11" text-anchor="end">'
                  f'tolerance {thresh:.0f} m</text>')
    # divergence line
    el.append(f'<polyline points="{" ".join(f"{px(t):.1f},{py(v):.1f}" for t, v in series)}" '
              f'fill="none" stroke="{BELIEVED}" stroke-width="2.2"/>')
    # trigger markers
    for r in result.results:
        if r.triggered and r.at_s >= 0:
            v = next((vv for tt, vv in series if tt >= r.at_s), series[-1][1])
            x, y = px(r.at_s), py(v)
            col = STATUS.get(r.severity, MUTED)
            el.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{col}" stroke="{PLANE}" stroke-width="1.3"/>')

    return f'<svg viewBox="0 0 {CH_W} {CH_H}" width="100%" role="img" ' \
           f'aria-label="True-vs-believed divergence over time">{"".join(el)}</svg>'


def _legend():
    items = [(BELIEVED, "Believed track (what the autopilot reports)"),
             (TRUE, "True track (actual hull position)"),
             (CONTACT, "Other vessel")]
    sw = "".join(
        f'<span class="lg"><span class="sw" style="background:{c}"></span>{_esc(t)}</span>' for c, t in items)
    return f'<div class="legend">{sw}</div>'


def to_html(result, scenario):
    sev = result.overall_severity
    badge = STATUS.get(sev, MUTED)
    ts = result.telemetry_summary
    rows = []
    for r in result.results:
        col = STATUS.get(r.severity, MUTED)
        state = "TRIGGERED" if r.triggered else "clear"
        metric = f"{r.metric:g}" if r.metric >= 0 else "—"
        at = f"{r.at_s:g}" if r.at_s >= 0 else "—"
        rows.append(
            f'<tr><td>{_esc(r.type)}</td>'
            f'<td><span class="dot" style="background:{col if r.triggered else MUTED}"></span>'
            f'<span style="color:{col if r.triggered else INK2}">{state}</span></td>'
            f'<td class="num">{metric}</td><td class="num">{at}</td>'
            f'<td><span class="chip" style="color:{col};border-color:{col}">{_esc(r.severity.upper())}</span></td></tr>')

    findings = []
    for r in result.results:
        if not r.triggered:
            continue
        col = STATUS.get(r.severity, MUTED)
        ctrls = "".join(f'<li><code>{_esc(s)}</code> — {_esc(c)}</li>' for s, c in standards.controls_for(r.type))
        findings.append(
            f'<div class="finding"><div class="fh"><span class="chip" style="color:{col};border-color:{col}">'
            f'{_esc(r.severity.upper())}</span><strong>{_esc(r.type)}</strong></div>'
            f'<p>{_esc(r.detail)}</p><ul>{ctrls}</ul></div>')

    attacks = "".join(
        f'<li>t+{a["at_s"]:.0f}s · <code>{_esc(a["action"])}</code> '
        f'<span class="mut">{_esc(a["params"]) if a["params"] else ""}</span></li>'
        for a in result.attacks_run)

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(result.scenario_name)} — Scenario T&amp;E report</title>
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;background:{PLANE};color:{INK};
 font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px;line-height:1.5}}
.wrap{{max-width:920px;margin:0 auto;padding:28px 20px 56px}}
.kicker{{color:{MUTED};font-size:12px;letter-spacing:.14em;text-transform:uppercase}}
h1{{font-size:22px;margin:4px 0 2px;font-weight:650}}
h2{{font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:{INK2};
 margin:30px 0 12px;font-weight:650;border-bottom:1px solid {GRID};padding-bottom:7px}}
.desc{{color:{INK2};margin:10px 0 18px;max-width:72ch}}
.meta{{display:flex;flex-wrap:wrap;gap:8px 22px;color:{MUTED};font-size:12.5px;margin-bottom:18px}}
.meta b{{color:{INK2};font-weight:600}}
.verdict{{display:inline-flex;align-items:center;gap:10px;border:1px solid {badge};
 border-radius:7px;padding:9px 15px;background:rgba(255,255,255,.02)}}
.verdict .lab{{color:{MUTED};font-size:11px;letter-spacing:.12em;text-transform:uppercase}}
.verdict .val{{color:{badge};font-weight:750;font-size:17px;letter-spacing:.03em}}
.verdict .dotbig{{width:9px;height:9px;border-radius:50%;background:{badge}}}
figure{{margin:0}}
figcaption{{color:{MUTED};font-size:12px;margin-top:8px}}
.legend{{display:flex;flex-wrap:wrap;gap:6px 18px;margin:12px 0 2px;color:{INK2};font-size:12.5px}}
.lg{{display:inline-flex;align-items:center;gap:7px}}
.sw{{width:16px;height:3px;border-radius:2px;display:inline-block}}
table{{width:100%;border-collapse:collapse;margin-top:4px}}
th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid {GRID};font-size:13px}}
th{{color:{MUTED};font-weight:600;font-size:11px;letter-spacing:.08em;text-transform:uppercase}}
td.num{{text-align:right;font-variant-numeric:tabular-nums;color:{INK2}}}
.dot{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;vertical-align:middle}}
.chip{{display:inline-block;border:1px solid;border-radius:4px;padding:1px 7px;font-size:11px;font-weight:650;letter-spacing:.04em}}
.finding{{border:1px solid {GRID};border-left-width:3px;border-radius:6px;padding:12px 15px;margin:10px 0;background:{PANEL}}}
.fh{{display:flex;align-items:center;gap:10px;margin-bottom:4px}}
.finding p{{margin:6px 0 8px;color:{INK2}}}
.finding ul{{margin:0;padding-left:18px;color:{INK2}}}
.finding code,.att code{{background:rgba(255,255,255,.06);padding:1px 6px;border-radius:4px;font-size:12px}}
.att{{list-style:none;padding:0;margin:0;color:{INK2}}}
.att li{{padding:5px 0;border-bottom:1px solid {GRID}}}
.mut{{color:{MUTED}}}
footer{{margin-top:34px;color:{MUTED};font-size:11.5px;border-top:1px solid {GRID};padding-top:14px}}
</style></head><body><div class="wrap">
<div class="kicker">Maritime Cyber Range · Scenario Test &amp; Evaluation</div>
<h1>{_esc(result.scenario_name)}</h1>
<p class="desc">{_esc(result.description)}</p>
<div class="meta"><span><b>Target</b> {_esc(result.target)}</span>
<span><b>Domain</b> {_esc(result.domain)}</span>
<span><b>Executor</b> {_esc(result.executor)}</span>
<span><b>Run</b> {ts.get('samples',0)} samples / {ts.get('duration_s',0)} s</span>
<span><b>Peak divergence</b> {ts.get('peak_divergence_m',0)} m</span></div>
<div class="verdict"><span class="dotbig"></span><span class="lab">Mission impact</span>
<span class="val">{_esc(SEV_LABEL.get(sev, sev.upper()))}</span></div>

<h2>Tactical picture</h2>
<figure>{_map_svg(result, scenario)}
{_legend()}
<figcaption>Believed track holds the planned route; the forged offset walks the TRUE hull
track into the charted hazards. Markers show where each consequence first occurred.</figcaption></figure>

<h2>True-vs-believed divergence</h2>
<figure>{_divergence_svg(result, scenario)}
<figcaption>Separation between the hull's actual position and what the autopilot believes,
over the run. Dashed line is the declared tolerance; dots mark consequence triggers.</figcaption></figure>

<h2>Consequences</h2>
<table><thead><tr><th>Consequence</th><th>Result</th><th class="num">Metric (m)</th>
<th class="num">At (s)</th><th>Severity</th></tr></thead><tbody>{''.join(rows)}</tbody></table>

<h2>Findings &amp; standards mapping</h2>
{''.join(findings) or '<p class="mut">No consequences triggered.</p>'}

<h2>Attacks exercised</h2>
<ul class="att">{attacks}</ul>

<footer>Generated by the Maritime Cyber Range scenario engine (scale-up prototype).
Standards references name the controlling documents (IACS UR E26/E27, IMO MSC.428(98));
clause-level mapping is a Phase-II refinement with the controlling authority.</footer>
</div></body></html>"""
