"""Renders a single POI stop as a Bootstrap-style HTML card string."""
from __future__ import annotations

from routeiq.routing.scored_poi import ScoredPOI
from routeiq.ui import CATEGORY_COLORS

_PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80'%3E%3Crect width='80' height='80' fill='%23ecf0f1'/%3E%3C/svg%3E"


def render_stop_card(sp: ScoredPOI, rank: int) -> str:
    """Return a self-contained HTML string for one stop card."""
    p = sp.poi
    color = CATEGORY_COLORS.get(p.category, "#7f8c8d")
    category_label = p.category.capitalize()
    detour_label = f"+{sp.detour_min:.0f} min detour"
    description = (p.description or "")[:160]
    img_src = p.image_url or _PLACEHOLDER
    img_tag = (
        f'<img src="{img_src}" '
        f'style="width:80px;height:80px;object-fit:cover;border-radius:6px;flex-shrink:0;" '
        f'onerror="this.src=\'{_PLACEHOLDER}\'" />'
    )

    return f"""
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
">
    {img_tag}
    <div style="flex: 1; min-width: 0;">
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
            <span style="
                background:{color};
                color:#fff;
                font-size:10px;
                font-weight:600;
                padding:2px 8px;
                border-radius:12px;
                text-transform:uppercase;
                letter-spacing:0.5px;
            ">{category_label}</span>
            <span style="color:#7f8c8d; font-size:12px;">{detour_label}</span>
        </div>
        <div style="font-size:15px; font-weight:600; color:#2c3e50; margin-bottom:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{rank}. {p.name}</div>
        <div style="font-size:12px; color:#555; line-height:1.4; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">{description}</div>
    </div>
</div>
"""
