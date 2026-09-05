# Model reproducibility aur "dirty git" — Hinglish me, apne artifact ke saath

_Ye wahi cheez hai jo humne `models/save.py` me theek ki (CLOSEOUT 0.5)._

## Problem: humari artifact chupke se jhooth bol rahi thi

Jab model train hota hai, wo do file me save hota hai:

- `model.joblib` — seekha hua model (bas numbers)
- `metadata.json` — uski **kundli** (kaunsa data, kaunsa code, kab bana, kaunsi library)

Humari `metadata.json` me git ke baare me ye likha tha:

```json
"git": { "commit": "b6c188a5...", "dirty": true }
```

Ye `dirty: true` hi problem hai. Kyun problem hai — ye samajhne ke liye ekdum
zero se chalte hain, ek line ke baad dusri.

## Basic 1 — model banta kaise hai?

1. `model.joblib` sirf **seekhe hue numbers** hain. Wo ye nahi batati ki wo bana kaise.
2. Model banta hai do cheezon se: **(a) data + (b) code** jo data ko train karta hai.
3. Same data + same code = **same model**. Inme se ek bhi badla = **alag model**.
4. Toh agar kabhi yehi model dobara banana ho, do cheezein chahiye: **exact data**
   aur **exact code**.
5. Data ka record humare paas hai — metadata me CSV ka `sha256` likha hai. ✓
6. Code ka record kaise rakhein? → **git commit hash**.

## Basic 2 — git commit hash kya hota hai?

Ek commit hash (jaise `b6c188a`) tumhare **saare code ka ek pal ka photo** hai.
Us pal file me jo bhi tha, wo us hash me pakka ho gaya.

Toh metadata me `"commit": "b6c188a"` likhne ka matlab hai:

> _"Ye model IS code-photo se bana."_

Idea achha hai — ek din koi (ya khud tum) us commit pe jaake bilkul yahi model
dobara bana sakta hai. **Yahi reproducibility hai.**

## dirty: true ka matlab — recipe wali kahani

Yahan crack hai: **commit hash sirf _committed_ code ka photo leta hai.** Jo change
tumne abhi commit nahi ki (uncommitted ya untracked), wo us photo me aati hi nahi.

Socho tum ek pakwaan (model) banate ho aur jar pe label (metadata) chipka dete ho:

> _"Ye recipe #b6c188a se bana hai."_

Par `dirty: true` ka matlab: _"banate waqt maine recipe to #b6c188a use ki, **par
saath me kuch extra masala bhi daala jo kisi recipe me likha hi nahi tha.**"_

Ab koi us recipe #b6c188a ko padh ke dobara banaye — **bilkul same nahi banega**,
kyunki wo extra masala (uncommitted code) kahin likha hi nahi tha, wo gum ho gaya.

**Matlab:** `dirty: true` ek imaandar confession hai ki _"is pal kuch uncommitted
tha, isliye ye commit hash akela poora code nahi batata."_ Jis code ne asli me model
banaya, wo aadha kho gaya. Label galat commit pe ungli utha raha hai.

### Ye hua kyun?

Kyunki model **dirty tree pe train hua** — code likha, commit nahi kiya, aur ussi
waqt `train.py` chala diya (jo `save_artifact` bulata hai). Galti save.py ki nahi
thi — usne imaandari se `dirty: true` likh diya. Galti **workflow** ki thi:
_pehle train, baad me commit._

## Tumhara asli sawaal: "model to save hai, phir git ka kya kaam?"

Ye sabse important hissa hai. Do **alag** zaroorat hain, inhe alag rakho:

### Zaroorat A — Rollback (purane model pe wapas jaana)

`latest.txt` ko purane folder ka naam de do. `model.joblib` wahin pada hai, use lo.
**Git ki, commit ki, dirty ki — koi zaroorat nahi.** Yahan tum bilkul sahi ho —
dirty flag ka rollback se **koi lena-dena nahi.**

### Zaroorat B — Reproduce (model ko scratch se dobara banana)

Ye tab chahiye jab `.joblib` file kaam ki nahi rahi:

- File **corrupt / delete** ho gayi, ya kisi ne `artifacts/` saaf kar diya.
- **sklearn version badal gaya** — 1.7.2 pe bana `.joblib` kabhi 1.8 pe load hi na ho.
  Tab bachta hai sirf: code se dobara banao.
- Ek **chhota change** karna hai ("same model par `n_jobs=4`") — iske liye exact base
  code chahiye, guess nahi.
- Koi poochhe **"proof do ye model isi code se bana"** — commit checkout karke dobara
  banake dikha do. `dirty: true` = proof nahi de sakte.

**Yaad rakhne ka tarika:**

> `.joblib` = tumhara **backup** (cheez ready hai).
> commit = tumhara **blueprint** (dobara banane ka naksha).

Do alag insurance. Backup tha, par blueprint ka record jhootha reh gaya tha.

## "Provenance" kya hai (ye word)

Provenance = kisi cheez ki **kundli** — kahan se aayi, kisne banayi, kab, kaise.
Museum me painting ke saath uski provenance hoti hai (proof ki asli hai, kisne
banayi, kab). Model ki provenance = _kaunsa data + kaunsa code + kaunsa commit +
kab + kaunsi library_ ne isko banaya. Humari `metadata.json` **hi** wo kundli hai.
`dirty: true` us kundli me ek **chhed** tha.

## Fix — 3 line (aur ek bug jo review me pakda)

Rule: **dirty tree pe artifact save hone hi mat do.** `save_artifact` ke shuru me
(folder banane se pehle, taaki koi khaali folder na bache):

```python
class DirtyTreeError(Exception):
    """Model training is only allowed when the working tree is clean."""

def save_artifact(...):
    if artifacts_root is None:
        artifacts_root = Path(__file__).parents[3] / "artifacts"

    if _git_dirty():                       # <- ye line
        raise DirtyTreeError("Train on a clean tree")
    ...
```

**Bug jo pehli baar hua:** maine likha tha `if _git_dirty:` — bina `()`. Ye
**function ko point kar raha tha, use call nahi kar raha.** Aur Python me function
object hamesha truthy hota hai, toh ye `if` **hamesha** True — clean ho ya dirty,
har baar raise. Proof:

```python
def f(): return False
bool(f)     # True   <- function object (hamesha True)
bool(f())   # False  <- asli call
```

`()` lagate hi theek ho gaya.

## Bonus lesson — test chupke se asli git se bandha tha

Jaise hi save "dirty pe raise" karne laga, `test_save.py` **aur**
`test_artifacts.py` fail hone lage. Kyun? Wo test asli `save_artifact` ko bulate
hain, jo andar **asli git** se poochta hai. Aur dev ke waqt tree lagbhag hamesha
dirty hota hai (README untracked, code uncommitted) → raise → test fail.

**Chhupi hui problem:** ye test chupke se _tumhare repo ke git-state_ se bandhe the
— tree clean to pass, dirty to fail. Test ka result code pe nahi, "abhi commit kiya
ki nahi" pe depend kar raha tha. **Galat** — unit test repo ki halat se azaad hona
chahiye.

Fix: test me git ko nakli bana do —

```python
monkeypatch.setattr("mental_health.models.save._git_dirty", lambda: False)
```

Ab test bolta hai "maan lo tree clean hai" aur sirf save-logic test karta hai.

## Ek line me pura matlab

> `.joblib` backup hai, commit blueprint hai. Dirty tree pe blueprint ka record
> jhootha ban jaata hai, isliye save ab **dirty tree pe mana kar deta hai** — aur
> test ko asli git se **azaad** rakho, warna wo repo ki halat pe depend kar jaata hai.
