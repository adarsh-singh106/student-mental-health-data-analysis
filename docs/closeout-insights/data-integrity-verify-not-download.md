# Data ko "verify karo, download mat karo" — aur expected hash alag kyun rakhte hain

_Ye wahi cheez hai jo humne `scripts/fetch_data.py` me banayi (CLOSEOUT 0.4)._

## Problem: cloner ke paas data pahुंchega kaise?

Humara pura project ek CSV pe khada hai (`data/raw/…Impact.csv`). Par wo CSV
**git me commit nahi hoti** — `.gitignore` me `/data/raw/` blocked hai. Matlab
koi banda repo clone kare, to uske paas code to aayega par **data nahi**. Bina
data ke na train hoga, na kuch.

Toh sawaal: _stranger ko working `data/raw/` tak ka raasta kaise dein?_

CLOSEOUT 0.4 do option deta hai:

1. Ek script jo CSV **download** kare, ya
2. license unclear ho to **manual step** document karo.

## Pehle decide: download karna theek hai bhi ya nahi?

Yahan license aड़ta hai. `data/PROVENANCE.md` me humne pehle hi likh diya tha:
source GitHub repo pe **koi LICENSE file nahi** hai. Aur no-license ka matlab
"free to use" **nahi** hota — ulta, reuse terms **undefined** hote hain.

Toh agar main script me `requests.get(url)` likh ke CSV auto-download karta, to
main bina-license data ko programmatically fetch aur redistribute kar raha hota —
theek wahi cheez jo PROVENANCE.md ne mana ki thi. Script apne hi project ke likhe
rule ko contradict kar deti.

**Faisla:** download nahi. Par sirf README me ek paragraph likh dena bhi kaafi
imaandaar nahi — wo verify nahi karता ki cloner ne **sahi file sahi jagah** rakhi.
Isliye beech ka raasta: script **download nahi karti, verify-and-guide karti hai.**

## verify-and-guide kya karta hai

Teen halat, teen jawab (aur har ek ka apna exit code, taaki CI/automation samajh sake):

| halat | script kya karti hai | exit |
|---|---|---|
| file hai + hash match | `OK` bolti hai | 0 |
| file hai par hash galat | `FAIL` — ye wo file nahi | 1 |
| file hai hi nahi | source URL + exact naam + kahan rakhni hai, print | 2 |

Cloner ke liye raasta ab **checkable** hai: script chalao → ya to OK, ya bilkul
saaf instructions. Guess-work zero.

## Asli lesson: expected hash **alag** source se aana chahiye

Ye is task ka dil hai. Script me ek line hai:

```python
EXPECTED_SHA256 = "32b542a497c39389735710fb4e2f43bdf444af5d9bacde6289801d201b6bebd3"
```

Ye hardcoded hai. Pehli nazar me galat lagta hai — "single source of truth" ka
rule to kehta hai value ek hi jagah rakho, do jagah copy mat karo. Toh main isko
artifact ki `metadata.json` se ya PROVENANCE.md se padh ke kyun nahi laya?

Kyunki **integrity check ka pura point yahi hai ki expected value us cheez se
alag ho jise tum check kar rahe ho.**

Socho — agar main expected hash ussi file se nikaalun jise verify kar raha hoon:

1. File corrupt/tampered ho jaati hai.
2. Main uska hash nikaalta hoon → wo naya (galat) hash aata hai.
3. Main use "expected" maan leta hoon (kyunki wahi file se aaya).
4. Compare: naya hash == naya hash → **match! OK!**

Verification ne kuch pakda hi nahi. Tampered file apna hi hash saath le aayi, aur
check use pass kar diya. Ye **circular** hai — apne aap ko apne against verify
karna hamesha pass hota hai.

Isliye expected hash ko **bahar, fixed** rakhte hain — ek "known-good" value jo
tumne tab record ki thi jab file sahi thi. Wahi industry pattern hai:

- `sha256sum -c SHA256SUMS` — hashes ek alag file me pehle se likhe hote hain.
- Debian/apt packages — expected hash repo metadata me, package se alag.
- `package-lock.json` / `uv.lock` — har dependency ka hash lock file me pinned.

Sab me expected value **source se alag** rehti hai. Humara hardcoded constant wahi
role nibha raha hai.

## Toh "single source of truth" ka kya? Do jagah to ho gaya (yahan + PROVENANCE)

Haan, aur ye ek asli trade-off hai — jhooth nahi bolenge. Hash ab do jagah hai:
`fetch_data.py` aur `PROVENANCE.md`. Risk: ek badla, dusra nahi → **drift**.

Isko manage karne ka tarika: constant ke upar comment me saaf likha hai —

```python
# If you ever change the dataset, update BOTH this constant and
# data/PROVENANCE.md together so they never drift apart.
```

Ye "duplication" jaan-boojh ke hai. Circular check (jo chup-chaap fail ho) se
behtar hai ek honest duplication (jo comment se guard kiya ho). Security check me
**alag-hona** > **DRY**. Dono compete karein to alag-hona jeetता hai.

## Ek line me pura matlab

> Bina-license data auto-download mat karo — verify karo aur cloner ko guide karo.
> Aur jis file ko verify kar rahe ho, uska expected hash **usi se mat lo** (warna
> check circular ho jaata hai) — known-good value ko alag, fixed rakho, chahe wo
> thodi duplication kyun na ho.
