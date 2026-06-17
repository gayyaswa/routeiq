"""Renders POI stop cards as Bootstrap-style HTML strings."""
from __future__ import annotations

from routeiq.routing.scored_poi import ScoredPOI
from routeiq.ui import CATEGORY_COLORS

_PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80'%3E%3Crect width='80' height='80' fill='%23ecf0f1'/%3E%3C/svg%3E"

# Append once to any cards container. Provides a full-iframe lightbox triggered by
# riShow(url) — called from clickable card images.
IMAGE_MODAL_HTML = """
<div id="ri-modal" onclick="this.style.display='none'"
     style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;
            background:rgba(0,0,0,0.88);z-index:9999;cursor:pointer;
            align-items:center;justify-content:center;flex-direction:column;gap:10px;">
  <img id="ri-img" style="max-width:92%;max-height:86%;border-radius:10px;
                           box-shadow:0 8px 40px rgba(0,0,0,0.7);" />
  <span style="color:rgba(255,255,255,0.55);font-size:11px;font-family:-apple-system,sans-serif;">
    Click anywhere or press Esc to close
  </span>
</div>
<script>
function riShow(src){
  document.getElementById('ri-img').src=src;
  document.getElementById('ri-modal').style.display='flex';
}
document.addEventListener('keydown',function(e){
  if(e.key==='Escape')document.getElementById('ri-modal').style.display='none';
});
</script>
"""

_CARD_WRAP = """
<div style="
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    border: 1px solid #e8ecef;
    border-radius: 10px;
    padding: 12px;
    margin-bottom: 10px;
    background: #ffffff;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    display: flex;
    gap: 12px;
    align-items: flex-start;
">{img}{body}</div>
"""


def _img_tag(src: str, zoom_src: str | None = None) -> str:
    """Image tag. zoom_src enables click-to-enlarge via the riShow() lightbox."""
    cursor = "cursor:zoom-in;" if zoom_src else ""
    click = (
        f' onclick="riShow(\'{zoom_src}\')"'
        f' onerror="this.src=\'{_PLACEHOLDER}\';this.style.cursor=\'default\';this.onclick=null"'
        if zoom_src
        else f' onerror="this.src=\'{_PLACEHOLDER}\'"'
    )
    return (
        f'<img src="{src}" '
        f'style="width:80px;height:80px;object-fit:cover;border-radius:6px;flex-shrink:0;{cursor}"'
        f'{click} />'
    )


def _card_body(rank: int, name: str, color: str, badge: str, description: str) -> str:
    return (
        f'<div style="flex:1;min-width:0;">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
        f'<span style="background:{color};color:#fff;font-size:10px;font-weight:600;'
        f'padding:2px 8px;border-radius:12px;text-transform:uppercase;letter-spacing:0.5px;">'
        f'{name.split()[0].capitalize() if not badge else ""}</span>'
        f'<span style="color:#7f8c8d;font-size:12px;">{badge}</span>'
        f'</div>'
        f'<div style="font-size:15px;font-weight:600;color:#2c3e50;margin-bottom:4px;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{rank}. {name}</div>'
        f'<div style="font-size:12px;color:#555;line-height:1.4;display:-webkit-box;'
        f'-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">{description}</div>'
        f'</div>'
    )


def render_stop_card(sp: ScoredPOI, rank: int) -> str:
    """Return a self-contained HTML string for one GraphRAG stop card."""
    p = sp.poi
    color = CATEGORY_COLORS.get(p.category, "#7f8c8d")
    category_label = p.category.capitalize()
    img = _img_tag(p.image_url or _PLACEHOLDER, zoom_src=p.image_url or None)
    body = (
        f'<div style="flex:1;min-width:0;">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
        f'<span style="background:{color};color:#fff;font-size:10px;font-weight:600;'
        f'padding:2px 8px;border-radius:12px;text-transform:uppercase;letter-spacing:0.5px;">'
        f'{category_label}</span>'
        f'<span style="color:#7f8c8d;font-size:12px;">+{sp.detour_min:.0f} min detour</span>'
        f'</div>'
        f'<div style="font-size:15px;font-weight:600;color:#2c3e50;margin-bottom:4px;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{rank}. {p.name}</div>'
        f'<div style="font-size:12px;color:#555;line-height:1.4;display:-webkit-box;'
        f'-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">'
        f'{(p.description or "")[:160]}</div>'
        f'</div>'
    )
    return _CARD_WRAP.format(img=img, body=body)


def render_dt_card(stop: dict, rank: int) -> str:
    """Return a self-contained HTML string for one Day Trip Planner stop card."""
    category = (stop.get("category") or "").lower()
    color = CATEGORY_COLORS.get(category, "#7f8c8d")
    category_label = category.capitalize() or "Stop"

    photo_urls = stop.get("photo_urls") or []
    img_src = (photo_urls[0] if photo_urls else None) or stop.get("image_url") or _PLACEHOLDER
    zoom_src = img_src if img_src != _PLACEHOLDER else None
    img = _img_tag(img_src, zoom_src=zoom_src)

    arrival = stop.get("arrival_time") or ""
    departure = stop.get("departure_time") or ""
    time_slot = f"{arrival} – {departure}" if arrival and departure else arrival or departure

    rating = stop.get("rating")
    review_count = stop.get("review_count")
    review_source = stop.get("review_source") or ""
    rating_html = ""
    if rating is not None:
        count_str = f" ({review_count:,})" if review_count else ""
        source_str = f" · {review_source}" if review_source else ""
        rating_html = (
            f'<div style="font-size:12px;color:#b7791f;margin-bottom:4px;">'
            f'⭐ {rating:.1f}{count_str}'
            f'<span style="color:#7f8c8d;">{source_str}</span></div>'
        )

    why_visit = (stop.get("why_visit") or "")[:200]
    why_html = (
        f'<div style="font-size:12px;color:#555;line-height:1.4;margin-bottom:4px;'
        f'display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">'
        f'{why_visit}</div>'
    ) if why_visit else ""

    visitor_quote = stop.get("visitor_quote") or ""
    quote_html = (
        f'<div style="font-size:11px;color:#4f46e5;border-left:3px solid #6366f1;'
        f'padding-left:7px;margin-bottom:5px;font-style:italic;line-height:1.4;">'
        f'"{visitor_quote[:140]}"</div>'
    ) if visitor_quote else ""

    activities = (stop.get("activities") or [])[:3]
    badges_html = ""
    if activities:
        badges = "".join(
            f'<span style="background:#f1f5f9;color:#475569;font-size:10px;'
            f'padding:2px 7px;border-radius:10px;">{a}</span>'
            for a in activities
        )
        badges_html = f'<div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:4px;">{badges}</div>'

    hours = stop.get("hours") or ""
    hours_html = (
        f'<div style="font-size:11px;color:#7f8c8d;">🕐 {hours}</div>'
    ) if hours else ""

    body = (
        f'<div style="flex:1;min-width:0;">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
        f'<span style="background:{color};color:#fff;font-size:10px;font-weight:600;'
        f'padding:2px 8px;border-radius:12px;text-transform:uppercase;letter-spacing:0.5px;">'
        f'{category_label}</span>'
        f'<span style="color:#7f8c8d;font-size:12px;">{time_slot}</span>'
        f'</div>'
        f'<div style="font-size:15px;font-weight:600;color:#2c3e50;margin-bottom:4px;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{rank}. {stop.get("name","")}</div>'
        f'{rating_html}{why_html}{quote_html}{badges_html}{hours_html}'
        f'</div>'
    )
    return _CARD_WRAP.format(img=img, body=body)


def render_vector_card(result: dict, rank: int) -> str:
    """Return a self-contained HTML string for one Vector Baseline result card."""
    color = CATEGORY_COLORS.get(result.get("category", ""), "#7f8c8d")
    category_label = result.get("category", "").capitalize()
    score_label = f"similarity {result.get('similarity_score', 0):.3f}"
    img_url = result.get("image_url") or None
    img = _img_tag(img_url or _PLACEHOLDER, zoom_src=img_url)
    body = (
        f'<div style="flex:1;min-width:0;">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
        f'<span style="background:{color};color:#fff;font-size:10px;font-weight:600;'
        f'padding:2px 8px;border-radius:12px;text-transform:uppercase;letter-spacing:0.5px;">'
        f'{category_label}</span>'
        f'<span style="color:#7f8c8d;font-size:12px;">{score_label}</span>'
        f'</div>'
        f'<div style="font-size:15px;font-weight:600;color:#2c3e50;margin-bottom:4px;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{rank}. {result.get("name", "")}</div>'
        f'<div style="font-size:12px;color:#555;line-height:1.4;display:-webkit-box;'
        f'-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">'
        f'{(result.get("description") or "")[:160]}</div>'
        f'</div>'
    )
    return _CARD_WRAP.format(img=img, body=body)
