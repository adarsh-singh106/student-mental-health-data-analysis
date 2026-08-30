# `models/gate.py` + `models/save.py` — Part 2 ki galtiyaan, decisions, aur reasoning

_Ye Part 2 hai: model ko **gate** karo, phir **versioned save** karo metadata ke
saath. `train-py.md` ki tarah — har galti ke saath **kya hua → kyun galat →
fix**, aur end me **kya abhi bhi kamzor hai (jaanbujh ke)**._

Sabse pehli aur sabse badi seekh — **order**:

> **gate → save → metadata. Kabhi ulta nahi.**
> Agar pehle save kiya aur baad me check kiya, toh ek kharab model `artifacts/`
> me pada reh jayega — aur kisi din koi usko deploy kar dega. Isliye check
> pehle, disk baad me.

---

# Hissa 1 — `gate.py` ki galtiyaan

Poori file sirf ~20 line ki hai. Kaam: metrics ka dict andar → **pass ya raise**.
Na data, na file, na model. Isi liye iska test milliseconds me chalega (fake dict
do, raise expected).

## 1.1 Undefined naam — function kabhi chala hi nahi 🔴 CRASH

**Maine likha:**

```python
if (test_stats['r2'] > R2_SCORE) and (test_stats['mae'] < MAE) and (test_stats['rmse'] < RMSE):
```

**Kya hua:** upar constants ka naam `MIN_TEST_R2`, `MAX_TEST_MAE`, `MAX_TEST_RMSE`
tha — par comparison me `R2_SCORE`, `MAE`, `RMSE` likh diya. Ye teen naam **kahin
bane hi nahi**. Jaise hi model theek hota aur andar wale `if` tak baat pahunchti →
`NameError: name 'R2_SCORE' is not defined`.

**Kyun ye khatarnaak lag ke bhi achha hai:** jo case sabse important hai (model
sahi, pass hona chahiye) — usi pe crash. Par crash **achhi baat** hai — `train-py.md`
wala hi rule: *turant crash, chupchaap galat se behtar.* Ye 10 second me pakda gaya.

**Fix:** teeno naam constants se match kiye.

## 1.2 Overfit gate `< 0.3` — bahut dheela

**Maine likha:** `if abs(train_stats['r2'] - test_stats['r2']) < 0.3:`

**Kyun galat:** mera asli gap = `0.9821 − 0.8902 = 0.0919`. `0.3` rakha toh ek
model jiska gap `0.29` hai (yaani train pe rata hua, test pe bekaar) bhi aaram se
pass ho jaata. Gate ka matlab hi nahi bacha.

**Fix:** `< 0.15`. Mere `0.0919` ko accha headroom, aur asli overfit pakda bhi
jayega.

## 1.3 Bare `Exception` — pehchan nahi ban rahi

**Maine likha:** `raise Exception("Model is Overfitting")`

**Kyun galat:** kal test ya CI `except Exception` likhega — toh "gate ne model
reject kiya" aur "code me koi random bug" (jaise upar wala `NameError`) — **dono
ek jaise dikhenge**. Farak hi nahi chalega.

**Fix:** apna naam wala exception —

```python
class GateFailedError(Exception):
    pass
```

Ab test me `pytest.raises(GateFailedError)` likh sakta hoon, aur CI me saaf pata
chalega *"gate ne roka"* vs *"code phat gaya"*.

## gate.py ke decisions (galti nahi, soch)

| Decision | Kyun |
|---|---|
| `raise` karo, `return False` nahi | fail pe CI ka exit code non-zero ho — pipeline ruk jaye |
| threshold module-level constant | ek jagah, aur metadata bhi isi ko padh sakta hai |
| gate me na data na model, sirf dict | test milliseconds me — 4998 rows train karne ki zarurat nahi |

---

# Hissa 2 — `save.py` ki galtiyaan

Kaam: `artifacts/<UTC-timestamp>/model.joblib` + `metadata.json` + `latest.txt`.
Ye file tukdo me bani, aur har tukde pe ek chhoti galti hui — sab asli.

## 2.1 `artifact_pipeline: joblib` — jhootha type hint

**Maine likha:** `def save_artifact(artifact_pipeline: joblib):`

**Kyun galat:** `joblib` ek **library** hai (jisse save karte hain), **type** nahi.
Andar aa raha object sklearn ka `Pipeline` hai. Ye bilkul `train-py.md §3.9` wala
*jhootha hint bina hint se bura* — koi bharosa karke galat cheez maan lega.

**Fix:** `from sklearn.pipeline import Pipeline` → `artifact_pipeline: Pipeline`.

## 2.2 `joblib.dump` — dono argument ulte 🔴 CRASH

**Maine likha:** `joblib.dump(pipeline, folder / artifact_pipeline)`

**Do galti ek saath:**
1. `pipeline` naam is function me hai hi nahi — model to `artifact_pipeline` naam
   se aaya → `NameError`.
2. `folder / artifact_pipeline` — path ke saath **model object** jodne ki koshish.
   Path ke saath to **file ka naam** (`"model.joblib"`) jodna tha.

`dump` ka niyam: `dump(kya_save_karna_hai, kahan_path)`. Dono cheez apni jagah se
hil gayi thi.

**Fix:** `joblib.dump(artifact_pipeline, folder / "model.joblib")`.

## 2.3 `{dataset}` — dict ko set me lapet diya (do baar!) 🔴 CRASH

**Maine likha:** `"dataset": {dataset},` — aur ek baar toh
`"dataset": { {"file":..., "rows":4998, "sha256":"..."} }`.

**Kyun galat:** `dataset` khud pura dict hai (train.py se banke aayega). Usko `{ }`
me lapetne ka matlab Python usko **set** samjhega — aur set ke andar dict aa hi
nahi sakta (`unhashable type: dict`) → crash. Ye wahi `%d`/set wali soch hai
`train-py.md §2.2` se — `{ }` dekh ke dimag "dict" bolta hai, par bina colon wo
set hai.

Doosri galti: `rows: 4998` aur `sha256: "..."` **hardcode** kiye — ye asli value
train.py se aane chahiye, warna metadata jhooth bolega.

**Fix:** `"dataset": dataset,` — jaise `metrics` kiya tha, seedha pass.

## 2.4 `get_feature_names_out()` — numpy array, JSON me nahi jaata

**Trap (pehle se pata tha, isliye bacha):**

```python
names = artifact_pipeline.named_steps["prep"].get_feature_names_out().tolist()
```

`get_feature_names_out()` ek **numpy array** deta hai, normal list nahi. JSON
numpy samajhta hi nahi → `TypeError: Object of type ndarray is not JSON serializable`.
`.tolist()` usko normal list bana deta hai. (Chalane pe `count` = **39** aana
chahiye — na aaye toh preprocessor galat jud raha hai.)

## 2.5 Comment code me chali gayi → SyntaxError

Samjhane wali line `"latest release yehi hai":` galti se file me paste ho gayi.
Bare string with colon = `SyntaxError`. **Fix:** hata di. (Ulta, hatate waqt
`latest.txt` wali do asli line bhi kat gayi thi — wo wapas daali. Seekh: delete
karte waqt sirf utna kaato jitna bekaar hai.)

## save.py ke decisions (soch, galti nahi)

| Decision | Kyun |
|---|---|
| Versioned folder, koi overwrite path **code me hai hi nahi** | rollback ki jaan purane artifacts hain — overwrite = wo maar dena |
| `mkdir(parents=True)` bina `exist_ok=True` | folder pehle se ho toh khud `FileExistsError` → "no overwrite" safety **free** |
| UTC timestamp **bina colon** (`20260830T142530Z`) | Windows filename me `:` allowed nahi; aur ye string apne aap chronological sort hota hai |
| `latest.txt` — **text**, symlink nahi | Windows pe symlink permission maangta hai |
| `now` ek baar nikaala | folder-naam aur `created_at` ek hi pal ke ho |
| `"passed": True` hardcode | save tabhi bulaya jaata hai jab gate pehle pass ho chuka — warna `GateFailedError` raise hoke baat yahan tak aati hi nahi |
| `metrics`/`dataset` bahar se aaye, yahan dobara load nahi | jiske paas cheez hai (train.py) wahi de — data dobara padhna = extra kaam + risk |
| sha256 fingerprint | data ka unique code; ek byte badla toh code badla — proof ki model **isi** data pe bana |
| `n_jobs=1` artifact me bake | serving pe threadpool ke saath core-fight na ho (ye train.py me RF banate waqt) |

---

# Hissa 3 — Jo abhi bhi kamzor hai (jaanbujh ke)

Sab fix ke baad bhi ye cheezein reh gayi hain. List isliye taaki koi ye na soche
"Part 2 perfect ho gaya":

| Kami | Kitna serious | Baat |
|---|---|---|
| `gate.py` / `save.py` ka **koi test nahi** | 🔴 | gate ka test to milliseconds ka hai (fake dict → `pytest.raises`) — likhna hi hai |
| `"passed": True` hardcode | 🟡 | agar koi `save_artifact` ko **gate ke bina** seedha bula de, toh metadata jhooth bolega. Abhi safe kyunki train.py order maanta hai — par ye "bharose" pe tika hai, "code" pe nahi |
| `MAX_TEST_MAE = 0.35` vs measured `0.3258` | 🟡 | sirf ~7% headroom. Ye **ek** 70/30 split ka number hai (`train-py.md §4.3`) — split hila toh ek theek model bhi reject ho sakta hai. Single-split pe calibrated hai, ye maan ke chalo |
| `Path(__file__).parents[3]` | 🟡 | file ek folder sarki toh chupchaap galat jagah. `train-py.md §4.2` wali hi naazuki |
| git commit `subprocess` se | 🟢 | maan raha hai git installed hai aur repo ke andar chal rahe hain — CI/Docker me sach, par assumption hai |
| exception message me number nahi | 🟢 | `"Model is Overfitting"` — kitne se? Kabhi `gap=0.29 > 0.15` likhna behtar hoga |

---

# Ek pending decision (ADR banega)

**70%-fit model ship karein, ya 100% data pe refit karke?**

- **Ship 70% (mera vote):** jo model gate se pass hua aur jiske metrics metadata me
  likhe hain — **wahi** disk pe jaaye. Metrics artifact ko sach me describe karte hain.
- **Refit 100%:** thoda behtar model milega, par ab metadata ke metrics ek **alag**
  model ke hain jo humne kabhi test hi nahi kiya. Metadata jhooth bolega.

Portfolio project ke liye **traceability > thoda extra accuracy**. Isliye ship-70%.
Ye ADR me likhna hai.

---

# Ek line ka lesson

> **Order hi asli safety hai. gate pehle isliye taaki kharab model disk tak
> pahunche hi na. Baaki sab (versioning, metadata, fingerprint) us ek decision
> ko traceable banate hain — usko replace nahi karte.**

## Related docs

- [`train-py.md`](train-py.md) — Part 1 ki galtiyaan; "crash dost, silent dushman"
- [`sklearn-pipeline-hygiene.md`](../insights/sklearn-pipeline-hygiene.md) — builder khali dabba, fit sirf train pe
- [`ADR 0002`](../decisions/0002-no-imputers-in-pipeline.md) — loudly fail karo (2.3 hardcode-hatane wali soch)
- [`GUIDE.md`](../../GUIDE.md) §17 — gate → save → metadata ka order aur kyun
