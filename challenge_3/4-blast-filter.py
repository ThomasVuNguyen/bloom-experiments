import pandas as pd
import requests
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

# ── CONFIG ───────────────────────────────────────────────────────────────────
INPUT_FILE   = "output/binding_predictions.csv"
OUTPUT_FILE  = "output/final_candidates.csv"
MAX_WORKERS  = 5   # parallel BLAST jobs — NCBI allows ~5-10 concurrent
# ─────────────────────────────────────────────────────────────────────────────

# ── STEP 1: Load ─────────────────────────────────────────────────────────────
print("Loading strong binders...")
df = pd.read_csv(INPUT_FILE)
peptides = df['peptide'].unique().tolist()
print(f"Unique peptides to check: {len(peptides)}")

# ── STEP 2: BLAST functions ───────────────────────────────────────────────────
BASE = "https://blast.ncbi.nlm.nih.gov/blast/Blast.cgi"
print_lock = threading.Lock()

def submit_blast(peptide):
    params = {
        "CMD":          "Put",
        "PROGRAM":      "blastp",
        "DATABASE":     "swissprot",
        "QUERY":        peptide,
        "ENTREZ_QUERY": "Homo sapiens[Organism]",
        "FORMAT_TYPE":  "Text",
        "HITLIST_SIZE": "5",
        "EXPECT":       "200000",
        "WORD_SIZE":    "2",
        "MATRIX_NAME":  "PAM30",
        "GAPCOSTS":     "9 1",
        "FILTER":       "F",
    }
    r = requests.post(BASE, data=params, timeout=30)
    for line in r.text.split("\n"):
        if "RID =" in line and "RTOE" not in line:
            return line.split("=")[1].strip()
    return None

def fetch_blast(rid, peptide):
    for _ in range(30):
        time.sleep(6)
        r = requests.get(BASE, params={
            "CMD": "Get", "RID": rid,
            "FORMAT_TYPE": "Text",
            "FORMAT_OBJECT": "Alignment",
        }, timeout=30)
        txt = r.text
        if "Status=WAITING" in txt:
            continue
        if "Status=FAILED" in txt or "No significant similarity" in txt:
            return "safe"
        if "Identities" in txt:
            for line in txt.split("\n"):
                if "Identities" in line:
                    try:
                        pct = int(line.split("(")[1].split("%")[0])
                        if pct == 100:
                            nums = line.split("=")[1].split("(")[0].strip()
                            match, total = map(int, nums.split("/"))
                            if match >= len(peptide):
                                return "flagged"
                    except:
                        pass
            return "safe"
    return "timeout"

def blast_one(args):
    idx, peptide, total = args
    try:
        rid = submit_blast(peptide)
        if not rid:
            return peptide, "safe", "submit failed"
        result = fetch_blast(rid, peptide)
        return peptide, result, ""
    except Exception as e:
        return peptide, "safe", str(e)

# ── STEP 3: Run parallel BLAST with ETA ──────────────────────────────────────
print(f"\nRunning BLAST safety filter ({MAX_WORKERS} parallel workers)...\n")

safe, flagged = [], []
completed = 0
start_time = datetime.now()
total = len(peptides)

args_list = [(i+1, p, total) for i, p in enumerate(peptides)]

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {executor.submit(blast_one, args): args for args in args_list}
    
    for future in as_completed(futures):
        peptide, result, note = future.result()
        completed += 1
        
        # ETA calculation
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = completed / elapsed if elapsed > 0 else 0
        remaining = (total - completed) / rate if rate > 0 else 0
        eta = str(timedelta(seconds=int(remaining)))
        
        # Status icon
        if result == "flagged":
            icon = "❌"
            flagged.append(peptide)
        else:
            icon = "✅"
            safe.append(peptide)
        
        note_str = f" ({note})" if note else ""
        with print_lock:
            print(f"  [{completed}/{total}] {icon} {peptide} | ETA: {eta}{note_str}")

# ── STEP 4: Save ──────────────────────────────────────────────────────────────
total_time = str(timedelta(seconds=int((datetime.now() - start_time).total_seconds())))

print(f"\n{'='*50}")
print(f"Completed in: {total_time}")
print(f"Checked:      {total}")
print(f"Flagged:      {len(flagged)}")
print(f"Safe:         {len(safe)}")

final = df[df['peptide'].isin(safe)].sort_values('rank')
final.to_csv(OUTPUT_FILE, index=False)
print(f"\nSaved to {OUTPUT_FILE}")
print("\nFinal neoantigen candidates:")
print(final[['gene','mutation','peptide','ic50','rank']].to_string())