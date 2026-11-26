#!/bin/sh
# Download the ChEMBL records behind matched.csv into DIR (default: ./chembl-raw).
# Needs curl and python3. Network access only to www.ebi.ac.uk. Then run:
#   python3 research/studies/kpc-oxa/build_input.py DIR research/studies/kpc-oxa/matched.csv
set -eu
DIR=${1:-chembl-raw}
API=https://www.ebi.ac.uk
mkdir -p "$DIR/assays" "$DIR/activities" "$DIR/documents"

next() { python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))['page_meta']['next'] or '')" "$1"; }

fetch_pages() {  # fetch_pages PREFIX URL
    prefix=$1; url=$2; page=0
    while [ -n "$url" ]; do
        page=$((page + 1))
        curl -sS --fail -A "research-client/1.0" "$API$url" -o "${prefix}_$page.json"
        url=$(next "${prefix}_$page.json")
    done
}

curl -sS --fail -A "research-client/1.0" "$API/chembl/api/data/status.json" -o "$DIR/status.json"

# Binding assays whose description names either enzyme family.
for term in OXA-48 KPC; do
    fetch_pages "$DIR/assays/$term" "/chembl/api/data/assay.json?description__icontains=$term&assay_type=B&limit=1000"
done

# IC50 and Ki activities in those assays, 40 assays per request.
python3 -I - "$DIR" <<'EOF'
import glob, json, sys
d = sys.argv[1]
ids = sorted({a["assay_chembl_id"] for f in glob.glob(d + "/assays/*.json")
              for a in json.load(open(f))["assays"]})
with open(d + "/assay_batches.txt", "w") as out:
    for i in range(0, len(ids), 40):
        out.write(",".join(ids[i:i + 40]) + "\n")
EOF
n=0
while read -r ids; do
    n=$((n + 1))
    fetch_pages "$DIR/activities/batch$n" "/chembl/api/data/activity.json?assay_chembl_id__in=$ids&standard_type__in=IC50,Ki&limit=1000"
done < "$DIR/assay_batches.txt"

# Metadata for every document with an activity.
python3 -I - "$DIR" <<'EOF'
import glob, json, sys
d = sys.argv[1]
ids = sorted({r["document_chembl_id"] for f in glob.glob(d + "/activities/*.json")
              for r in json.load(open(f))["activities"]})
with open(d + "/document_batches.txt", "w") as out:
    for i in range(0, len(ids), 40):
        out.write(",".join(ids[i:i + 40]) + "\n")
EOF
n=0
while read -r ids; do
    n=$((n + 1))
    fetch_pages "$DIR/documents/batch$n" "/chembl/api/data/document.json?document_chembl_id__in=$ids&limit=1000"
done < "$DIR/document_batches.txt"
echo "Downloaded ChEMBL records into $DIR"
