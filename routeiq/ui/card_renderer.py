"""Renders POI stop cards as Bootstrap-style HTML strings."""
from __future__ import annotations

from routeiq.routing.scored_poi import ScoredPOI
from routeiq.ui import CATEGORY_COLORS

_PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80'%3E%3Crect width='80' height='80' fill='%23ecf0f1'/%3E%3C/svg%3E"

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


def _img_tag(src: str) -> str:
    return (
        f'<img src="{src}" '
        f'style="width:80px;height:80px;object-fit:cover;border-radius:6px;flex-shrink:0;" '
        f'onerror="this.src=\'{_PLACEHOLDER}\'" />'
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
    img = _img_tag(p.image_url or _PLACEHOLDER)
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


def render_vector_card(result: dict, rank: int) -> str:
    """Return a self-contained HTML string for one Vector Baseline result card."""
    color = CATEGORY_COLORS.get(result.get("category", ""), "#7f8c8d")
    category_label = result.get("category", "").capitalize()
    score_label = f"similarity {result.get('similarity_score', 0):.3f}"
    img = _img_tag(_PLACEHOLDER)
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
