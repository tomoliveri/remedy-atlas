"""Build matched.csv from ChEMBL records downloaded by fetch_chembl.sh.

A measurement is kept when its assay description names exactly one of KPC or OXA-48,
it is an IC50 or Ki in nM with relation '=' or '>', and ChEMBL has not flagged its
validity. Only (document, compound, endpoint) groups measured against both enzyme
families are written, so every row has a partner from the same publication.
"""

import argparse
import csv
import glob
import json
from pathlib import Path
import re

KPC = re.compile(r"KPC-?(\d+)?")
OXA48 = re.compile(r"OXA-?48", re.IGNORECASE)
# Review articles that compile values measured in other laboratories. Their pairs
# are not matched assays, so the study analyses them only as a sensitivity check.
COMPILED_REVIEWS = {
    "CHEMBL5247575": "Strategic approaches to overcome resistance (perspective)",
    "CHEMBL5331045": "Recent advances in beta-lactamase inhibitor chemotypes (review)",
}
FIELDS = ["document_chembl_id", "doi", "year", "compiled_review", "molecule_chembl_id",
          "molecule_name", "endpoint", "family", "enzyme", "assay_chembl_id", "activity_id",
          "relation", "value_nm"]


def records(directory, kind):
    for path in sorted(glob.glob(str(directory / kind / "*.json"))):
        with open(path) as source:
            yield from json.load(source)[kind]


def enzyme(description):
    kpc, oxa = KPC.search(description), OXA48.search(description)
    if bool(kpc) == bool(oxa):
        return None
    if oxa:
        return "OXA-48", "OXA-48"
    return "KPC", "KPC-" + kpc.group(1) if kpc.group(1) else "KPC"


def build(directory):
    assays = {a["assay_chembl_id"]: a for a in records(directory, "assays")}
    documents = {d["document_chembl_id"]: d for d in records(directory, "documents")}
    kept, seen = [], set()
    for row in records(directory, "activities"):
        if row["activity_id"] in seen:
            continue
        seen.add(row["activity_id"])
        named = enzyme(assays[row["assay_chembl_id"]]["description"])
        if (named is None or row["standard_units"] != "nM" or not row["standard_value"]
                or row["standard_relation"] not in ("=", ">") or row["data_validity_comment"]
                or float(row["standard_value"]) <= 0):
            continue
        doc = documents[row["document_chembl_id"]]
        kept.append({
            "document_chembl_id": row["document_chembl_id"], "doi": doc["doi"] or "",
            "year": doc["year"] or "", "compiled_review": int(row["document_chembl_id"] in COMPILED_REVIEWS),
            # Salts and parents (e.g. avibactam sodium, avibactam) share a parent ID.
            "molecule_chembl_id": row["parent_molecule_chembl_id"] or row["molecule_chembl_id"],
            "molecule_name": row["molecule_pref_name"] or "", "endpoint": row["standard_type"],
            "family": named[0], "enzyme": named[1], "assay_chembl_id": row["assay_chembl_id"],
            "activity_id": row["activity_id"], "relation": row["standard_relation"],
            "value_nm": row["standard_value"],
        })
    families = {}
    for row in kept:
        key = (row["document_chembl_id"], row["molecule_chembl_id"], row["endpoint"])
        families.setdefault(key, set()).add(row["family"])
    matched = [row for row in kept if len(families[(row["document_chembl_id"],
                                                    row["molecule_chembl_id"], row["endpoint"])]) == 2]
    return sorted(matched, key=lambda r: (r["document_chembl_id"], r["molecule_chembl_id"],
                                          r["endpoint"], r["family"], r["activity_id"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows = build(args.directory)
    with args.output.open("w", newline="") as out:
        writer = csv.DictWriter(out, FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} matched measurements written to {args.output}")


if __name__ == "__main__":
    main()
