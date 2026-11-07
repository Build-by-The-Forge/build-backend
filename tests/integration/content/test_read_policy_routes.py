"""No /content route can skip the read policy (M3-D ruling B).

Every route under /content in the running app must take a ``Caller`` from
``app.api.content.reading.reading``, or be listed below with the reason it
never lists, returns or streams a document or its job. A new route that does
neither fails here, the way the drift gate fails a route the contract lacks.
"""

from fastapi.routing import iter_route_contexts

from app.main import app

EXEMPT = {
    ("POST", "/content/ingestion/callbacks"): "AI-service's signed callback: a system context, no reader",
    ("POST", "/content/sources/{source_id}/assets"): "retired, answers 410 without reading anything",
    ("POST", "/content/assets/{asset_id}/version"): "retired, answers 410 without reading anything",
    ("POST", "/content/sources"): "a source, not a document",
    ("GET", "/content/sources"): "sources, not documents",
    ("GET", "/content/sources/{source_id}"): "a source, not a document",
    ("PATCH", "/content/sources/{source_id}"): "a source, not a document",
    ("POST", "/content/sources/{source_id}/deprecate"): "a source, not a document",
    ("POST", "/content/sources/{source_id}/revoke"): "a source, not a document",
    ("POST", "/content/sources/{source_id}/activate"): "a source, not a document",
}


def _calls(dependant) -> list:
    found = []
    for dependency in dependant.dependencies:
        found.append(dependency.call)
        found += _calls(dependency)
    return found


def _content_routes() -> dict:
    # Included routers are nested in this FastAPI; iter_route_contexts gives
    # every effective route with its full path and dependencies.
    routes = {}
    for route in iter_route_contexts(app.routes):
        path = route.path or ""
        if path.startswith("/content") and hasattr(route, "dependant"):
            for method in route.methods or ():
                routes[(method, path)] = route
    return routes


def test_every_content_route_goes_through_the_read_policy_or_states_why_not():
    routes = _content_routes()
    assert routes, "no /content routes found"
    skipping = sorted(
        key
        for key, route in routes.items()
        if key not in EXEMPT and not any(getattr(call, "__read_policy__", False) for call in _calls(route.dependant))
    )
    assert skipping == [], f"routes that skip the read policy: {skipping}"


def test_every_exemption_names_a_route_that_exists_and_takes_no_reader():
    routes = _content_routes()
    stale = sorted(key for key in EXEMPT if key not in routes)
    assert stale == [], f"exemptions for routes that no longer exist: {stale}"
    reading = sorted(
        key for key in EXEMPT if any(getattr(call, "__read_policy__", False) for call in _calls(routes[key].dependant))
    )
    assert reading == [], f"exempt routes that do take a reader, so shouldn't be exempt: {reading}"
