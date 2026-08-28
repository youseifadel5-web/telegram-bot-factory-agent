from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

URL_RE = re.compile(r"https?://[^\s\"'<>\\]+", re.I)
ROUTE_RE = re.compile(r"(?<![A-Za-z0-9])/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+(?:\?[A-Za-z0-9_=&.{}$:-]+)?")
RETROFIT_RE = re.compile(r'@(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s*\(\s*["\']([^"\']+)["\']\)')
JSON_KEYS_RE = re.compile(r"[\"']([A-Za-z_][A-Za-z0-9_-]{1,80})[\"']\\s*:")
SIGNAL_TERMS = ("iron", "hmac", "sha256", "sha-256", "nonce", "x-sign", "signature", "certificate", "pinning", "okhttp", "retrofit")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def strings_from_bytes(data: bytes) -> list[str]:
    out = []
    for m in re.finditer(rb"[ -~]{4,}", data):
        try:
            out.append(m.group().decode("utf-8", "ignore"))
        except Exception:
            pass
    return out


def evidence(kind: str, value: str, source: str, confidence: str = "observed") -> dict:
    return {"kind": kind, "value": value, "source": source, "confidence": confidence}


def parse_json_body(text: str):
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        try:
            return json.loads(base64.b64decode(text).decode("utf-8"))
        except Exception:
            return None


def schema(value, path="$", depth=0):
    if depth > 8:
        return {"type": "truncated"}
    if isinstance(value, dict):
        return {"type": "object", "properties": {str(k): schema(v, f"{path}.{k}", depth + 1) for k, v in value.items()}}
    if isinstance(value, list):
        return {"type": "array", "items": schema(value[0], f"{path}[]", depth + 1) if value else {"type": "unknown"}}
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    return {"type": "string"}


def analyze_har(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("log", {}).get("entries", [])
    routes = defaultdict(lambda: {"methods": set(), "requests": 0, "status_codes": Counter(), "query": set(), "headers": set(), "response_schemas": [], "response_samples": []})
    bases, urls, observations = set(), set(), []
    for entry in entries:
        req = entry.get("request", {})
        res = entry.get("response", {})
        url = req.get("url", "")
        if not url:
            continue
        p = urlsplit(url)
        route = p.path or "/"
        key = f"{req.get('method', 'GET').upper()} {route}"
        item = routes[key]
        item["methods"].add(req.get("method", "GET").upper())
        item["requests"] += 1
        item["status_codes"][str(res.get("status", ""))] += 1
        item["query"].update(k for k, _ in parse_qsl(p.query, keep_blank_values=True))
        item["headers"].update(h.get("name", "") for h in req.get("headers", []) if h.get("name"))
        bases.add(f"{p.scheme}://{p.netloc}")
        urls.add(url)
        body = (res.get("content") or {}).get("text", "")
        parsed = parse_json_body(body)
        if parsed is not None:
            item["response_schemas"].append(schema(parsed))
            if len(item["response_samples"]) < 3:
                item["response_samples"].append(parsed)
    normalized = {}
    for key, item in routes.items():
        normalized[key] = {"methods": sorted(item["methods"]), "requests": item["requests"], "status_codes": dict(item["status_codes"]), "query_parameters": sorted(item["query"]), "request_headers": sorted(item["headers"]), "response_schemas": item["response_schemas"], "response_samples": item["response_samples"]}
    return {"source": str(path), "entry_count": len(entries), "base_urls": sorted(bases), "observed_urls": sorted(urls), "routes": normalized, "evidence": [evidence("har_route", k, str(path)) for k in normalized]}


def analyze_apk(path: Path) -> dict:
    files, url_values, route_values, native = [], set(), set(), []
    manifest = None
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            files.append(name)
            data = z.read(name)
            text = "\n".join(strings_from_bytes(data))
            for url in URL_RE.findall(text):
                url_values.add(url.rstrip(".,);"))
            for route in ROUTE_RE.findall(text):
                if "/" in route and not route.startswith("//"):
                    route_values.add(route)
            if name == "AndroidManifest.xml":
                manifest = {"present": True, "size": len(data), "note": "Binary AXML retained; use apktool/aapt externally for decoded manifest."}
            if name.startswith("lib/") and name.endswith(".so"):
                hits = sorted({s for s in strings_from_bytes(data) if any(t in s.lower() for t in SIGNAL_TERMS)})
                native.append({"path": name, "size": len(data), "signal_strings": hits[:300]})
    retrofit = []
    for name in files:
        if name.endswith(('.dex', '.jar', '.class', '.smali')):
            with zipfile.ZipFile(path) as z:
                text = "\n".join(strings_from_bytes(z.read(name)))
            for m in RETROFIT_RE.finditer(text):
                retrofit.append({"method": m.group(1), "route": m.group(2), "source": name, "confidence": "static_annotation"})
    return {"source": str(path), "sha256": sha256(path), "file_count": len(files), "manifest": manifest, "base_url_candidates": sorted(url_values), "route_candidates": sorted(route_values), "retrofit_annotations": retrofit, "native_libraries": native, "evidence": [evidence("apk_route_candidate", r, str(path), "candidate") for r in sorted(route_values)]}


def merge(apk, har):
    observed = set((har or {}).get("routes", {}))
    candidates = set((apk or {}).get("route_candidates", []))
    return {"observed_routes": sorted(observed), "apk_only_candidates": sorted(candidates - {x.split(' ', 1)[-1] for x in observed}), "confidence_rule": "HAR observations are confirmed; APK strings/annotations remain candidates until observed in traffic."}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Local deterministic APK/HAR API analyzer")
    ap.add_argument("--owned", action="store_true", help="confirm you own or are authorized to analyze the supplied artifacts")
    ap.add_argument("--apk", type=Path)
    ap.add_argument("--har", type=Path)
    ap.add_argument("--out", type=Path, default=Path("analysis-report.json"))
    args = ap.parse_args(argv)
    if not args.owned:
        ap.error("deep analysis requires --owned confirmation")
    if not args.apk and not args.har:
        ap.error("provide --apk and/or --har")
    result = {"tool": "local-apk-api-analyzer", "version": 1, "apk": analyze_apk(args.apk) if args.apk else None, "har": analyze_har(args.har) if args.har else None}
    result["reconciliation"] = merge(result["apk"], result["har"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.out), "apk": bool(args.apk), "har": bool(args.har)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
