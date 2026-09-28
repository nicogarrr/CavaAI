#!/usr/bin/env python3
"""Sincroniza SEC -> mirror HuggingFace (resiliencia ante el ban de IPs).

Para cada ticker vigilado (scripts/sec_mirror_tickers.txt) descarga de la
SEC el companyfacts, el submissions y sus ficheros historicos, y sube al
dataset HF solo lo que cambio (comparando bytes). El dataset es PUBLICO:
la ingesta lo lee sin credenciales; solo el sync necesita HF_TOKEN (write).

Uso: HF_TOKEN=... HF_DATASET=usuario/cavaai-sec-mirror python data-engine/scripts/sec_hf_mirror_sync.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import httpx

SEC_UA = "CavaAI Research research@cavaai.example"
TICKERS_FILE = Path(__file__).with_name("sec_mirror_tickers.txt")
RPS_DELAY = 0.15  # ~6-7 req/s, bajo el limite de la SEC (10/s)


def sec_get(client: httpx.Client, url: str) -> dict:
    for attempt in range(5):
        response = client.get(url)
        if response.status_code == 429:
            time.sleep(float(response.headers.get("retry-after", 2)) * (attempt + 1))
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"SEC rate-limited tras reintentos: {url}")


def main() -> int:
    token = os.environ.get("HF_TOKEN")
    dataset = os.environ.get("HF_DATASET")
    if not token or not dataset:
        print("Faltan HF_TOKEN o HF_DATASET", file=sys.stderr)
        return 2
    from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download

    tickers = [t.strip().upper() for t in TICKERS_FILE.read_text().splitlines()
               if t.strip() and not t.startswith("#")]
    api = HfApi(token=token)
    api.create_repo(dataset, repo_type="dataset", exist_ok=True, private=False)

    uploads: dict[str, bytes] = {}
    with httpx.Client(
        headers={"User-Agent": SEC_UA, "Accept-Encoding": "gzip, deflate"},
        timeout=60, follow_redirects=True,
    ) as client:
        mapping = sec_get(client, "https://www.sec.gov/files/company_tickers.json")
        uploads["company_tickers.json"] = json.dumps(mapping).encode()
        cik_by_ticker = {v["ticker"].upper(): v["cik_str"] for v in mapping.values()}
        manifest = {}
        for ticker in tickers:
            cik = cik_by_ticker.get(ticker)
            if not cik:
                print(f"{ticker}: sin CIK, se omite")
                continue
            padded = f"{cik:010d}"
            manifest[ticker] = padded
            facts = sec_get(client, f"https://data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json")
            uploads[f"companyfacts/CIK{padded}.json"] = json.dumps(facts).encode()
            time.sleep(RPS_DELAY)
            subs = sec_get(client, f"https://data.sec.gov/submissions/CIK{padded}.json")
            uploads[f"submissions/CIK{padded}.json"] = json.dumps(subs).encode()
            time.sleep(RPS_DELAY)
            for extra in subs.get("filings", {}).get("files", []) or []:
                name = extra.get("name")
                if not name:
                    continue
                payload = sec_get(client, f"https://data.sec.gov/submissions/{name}")
                uploads[f"submissions/{name}"] = json.dumps(payload).encode()
                time.sleep(RPS_DELAY)
            print(f"{ticker}: {len(uploads)} ficheros acumulados")
        uploads["manifest.json"] = json.dumps({
            "tickers": manifest,
            "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "SEC EDGAR (companyfacts/submissions oficiales)",
            # Proveniencia por archivo: sha1 del contenido oficial servido.
            "files": {p: hashlib.sha1(c).hexdigest() for p, c in uploads.items()},
        }).encode()

    # Publicacion atomica: un unico commit con todos los ficheros cambiados
    # y el manifest. Un sync a mitad NUNCA deja un manifest fresco declarando
    # contenidos que aun no se subieron (el lector verifica sha1 por archivo).
    # Delta contra los sha1 declarados en el manifest remoto anterior.
    old_files: dict = {}
    try:
        old_manifest = hf_hub_download(
            dataset, "manifest.json", repo_type="dataset", token=token)
        old_files = json.loads(Path(old_manifest).read_text()).get("files", {})
    except Exception:
        old_files = {}
    operations = []
    for path, content in sorted(uploads.items()):
        digest = hashlib.sha1(content).hexdigest()
        if path != "manifest.json" and old_files.get(path) == digest:
            continue
        operations.append(CommitOperationAdd(
            path_in_repo=path, path_or_fileobj=content))
    if operations:
        api.create_commit(
            repo_id=dataset, repo_type="dataset", operations=operations,
            commit_message=(
                f"sync SEC {time.strftime('%Y-%m-%d %H:%M')} UTC "
                f"({len(operations)} ficheros)"))
    print(f"Sincronizados {len(operations)}/{len(uploads)} ficheros en "
          f"{dataset} (1 commit atomico)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
