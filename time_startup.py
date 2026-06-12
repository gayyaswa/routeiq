"""Measures wall-clock time for every startup import and query pipeline step."""
import time, os
from dotenv import load_dotenv
load_dotenv()

def t(label, fn):
    start = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - start
    print(f"{elapsed:6.2f}s  {label}")
    return result

# ── imports ───────────────────────────────────────────────────────────────────
print("\n── imports ──────────────────────────────────────────────")
t("osmnx",                      lambda: __import__("osmnx"))
t("networkx",                   lambda: __import__("networkx"))
t("chromadb",                   lambda: __import__("chromadb"))
t("langchain_anthropic",        lambda: __import__("langchain_anthropic"))
t("langchain_core",             lambda: __import__("langchain_core"))
t("langgraph",                  lambda: __import__("langgraph"))
t("streamlit",                  lambda: __import__("streamlit"))
t("folium / streamlit_folium",  lambda: __import__("streamlit_folium"))
t("shapely",                    lambda: __import__("shapely"))
t("geopandas",                  lambda: __import__("geopandas"))
t("routeiq.graph",              lambda: __import__("routeiq.graph",   fromlist=["GraphLoader"]))
t("routeiq.ui",                 lambda: __import__("routeiq.ui",      fromlist=["MapBuilder"]))
t("routeiq.rag",                lambda: __import__("routeiq.rag",     fromlist=["POIIndexer"]))
t("routeiq.facade",             lambda: __import__("routeiq.facade",  fromlist=["RouteIQFacade"]))
t("eval.evaluator (seed pois)", lambda: __import__("eval.evaluator",  fromlist=["_BAY_AREA_SEED_POIS"]))

# ── object init ───────────────────────────────────────────────────────────────
print("\n── object initialization ────────────────────────────────")
import chromadb, osmnx as ox
from routeiq.graph import GraphLoader
from routeiq.ui import MapBuilder
from routeiq.facade import RouteIQFacade
from routeiq.rag import POIIndexer, VectorBaseline
from langchain_anthropic import ChatAnthropic
from eval.evaluator import _BAY_AREA_SEED_POIS

t("GraphLoader()",                  lambda: GraphLoader())
t("MapBuilder()",                   lambda: MapBuilder())
t("chromadb.PersistentClient",      lambda: chromadb.PersistentClient(path="./cache/chroma"))

chroma = chromadb.PersistentClient(path="./cache/chroma")
t("POIIndexer(client)",             lambda: POIIndexer(client=chroma))
t("POIIndexer(vector_baseline)",    lambda: POIIndexer(client=chroma, collection_name="routeiq_vector_baseline"))

api_key = os.environ.get("ANTHROPIC_API_KEY", "")
if not api_key:
    print("  SKIP   ChatAnthropic() — no ANTHROPIC_API_KEY")
    print("  SKIP   RouteIQFacade()")
    print("  SKIP   pipeline steps — no API key\n")
    raise SystemExit(0)

llm = t("ChatAnthropic()",          lambda: ChatAnthropic(model="claude-sonnet-4-6", api_key=api_key))
t("RouteIQFacade(llm)",             lambda: RouteIQFacade(llm, chroma_client=chroma))

# ── pipeline steps (cached graph + cached pois) ───────────────────────────────
print("\n── pipeline steps (SF → Monterey, all caches warm) ─────")
facade = RouteIQFacade(llm, chroma_client=chroma)

steps = {}
def on_progress(step, subtask):
    if step not in steps:
        steps[step] = time.perf_counter()

total = time.perf_counter()
result = facade.run(
    "Drive from San Francisco to Monterey, show coastal history and natural landmarks",
    on_progress=on_progress,
)
total_elapsed = time.perf_counter() - total

ordered = sorted(steps.items(), key=lambda x: x[1])
prev = total
for i, (step, ts) in enumerate(ordered):
    nxt = ordered[i+1][1] if i+1 < len(ordered) else total + total_elapsed
    print(f"{nxt-ts:6.2f}s  [{step}] node")

print(f"{total_elapsed:6.2f}s  TOTAL")
if result.get("error"):
    print(f"         ⚠ pipeline error: {result['error']} — {result.get('fallback_reason','')[:80]}")
else:
    print(f"         {len(result.get('top_pois') or [])} stops returned")
print()
