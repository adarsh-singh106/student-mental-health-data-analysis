# Data provenance

Record of where this project's dataset came from, how to verify it, and what is
*not* known about it. "Origin undocumented" is written down here as a real finding,
not hidden.

## The dataset

| | |
|---|---|
| File | `data/raw/Student Social Media And Mental Health Impact.csv` |
| Rows | 4998 |
| Size | 398,996 bytes (~390 KB) |
| Target column | `Mental_Health_Score` (0–10, continuous) |
| sha256 | `32b542a497c39389735710fb4e2f43bdf444af5d9bacde6289801d201b6bebd3` |

## Where I got it

Downloaded from a public GitHub repository:

- Repo: https://github.com/tanishq-latent/Mental-Health-Score
- File: https://github.com/tanishq-latent/Mental-Health-Score/blob/main/Student%20Social%20Media%20And%20Mental%20Health%20Impact.csv
- Downloaded: on or around **2026-08-15** (taken from the local file's modification
  time; the exact download date was not recorded at the time).

## Honest caveat — the *original* origin is undocumented

The repo above is a **secondary source**, not an official dataset publisher. As of
this writing it has:

- **no LICENSE file** — reuse terms are undefined (not "free to use");
- **no description**; and
- a README containing only a heading ("Mental-Health-Score" / "Mansik-Santulan-Score")
  with **no statement of where that repo itself obtained the data.**

So I can document where *I* got the file, but **not where the data was originally
produced or collected.** The upstream publisher (Kaggle or elsewhere) is unknown.

## Licensing

No license was found on the source repo, so reuse terms are undefined. This copy is
used **only for an educational / portfolio project and is not redistributed.**
Because the license is unclear, this project does **not** auto-download the CSV — see
the README for the manual placement step.

## Integrity check

The sha256 above is the value stored in the trained model's `metadata.json`. On
**2026-09-05** the CSV on disk was re-hashed and it **matches** that recorded value —
i.e. the file here is byte-identical to the one the shipped model was fingerprinted
against.

Verify it yourself:

```bash
python -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path('data/raw/Student Social Media And Mental Health Impact.csv').read_bytes()).hexdigest())"
```

Expected output:

```
32b542a497c39389735710fb4e2f43bdf444af5d9bacde6289801d201b6bebd3
```

## A note on the data itself

This dataset shows signs of being **generated rather than measured** (very few
distinct ages, exactly two genders, and whole-number target values over-represented
against their neighbours). Details are in `audit/REPORT_model.md` (§1, "Raw data
forensics"). Combined with the undocumented origin above, treat any accuracy number
as "how well the model recovered a data-generating formula", not a real-world claim.
