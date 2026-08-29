# `models/train.py` — meri galtiyaan, fix, aur kya ye ab bulletproof hai?

_Ye file likhte waqt 15 galtiyaan hui. Sabhi asli hain, sabhi maine ki. Har ek ke
saath: **kya hua → kyun galat tha → fix → aur kya naya tarika pakka hai ya
usme bhi tradeoff hai.**_

Teen hisse me divide hai, aur ye division hi sabse badi seekh hai:

| Kism | Kitni | Pakdi kab gayi |
|---|---|---|
| **Crash karne wali** | 6 | 10 second me — chalaya, phat gaya |
| **Chupchaap jhoot bolne wali** | 4 | sirf tab jab koi dhyaan se dekhe |
| **Design / hygiene** | 5 | crash nahi karti, par kal dard degi |

Crash wali galtiyaan **achhi** hoti hain. Jhoot bolne wali khatarnaak.

---

# Hissa 1 — Crash karne wali galtiyaan

## 1.1 `stratify=y` — regression me lagaya

**Maine likha:**

```python
train_test_split(X, y, test_size=0.30, stratify=y, random_state=42)
```

**Kya hua:**

```
ValueError: The least populated class in y has only 1 member,
which is too few. The minimum number of groups for any class cannot be less than 2.
```

**Kyun galat tha:** `stratify` **classification** ka tool hai. Uska kaam hai —
"har class train aur test dono me barabar ratio me jaaye". Jaise 100 email me 10
spam hain, toh train me bhi ~10% spam ho aur test me bhi ~10%.

Mera `y` = `Mental_Health_Score` — 0 se 10 tak ka **continuous** number. Usme
"class" hi nahi hoti. sklearn ne har unique value ko ek class samajh liya —
mere data me **59 unique values** hain aur `9.4` **sirf 1 row** me hai. Ek member
wali class ko 70/30 me kaise baate? Nahi baat sakta → raise.

**Fix:** `stratify=y` poora hata diya.

## 1.2 `Pipeline` ko list nahi di

**Maine likha:**

```python
pipeline = Pipeline(
    ("prep", build_preprocessor()),          # do alag argument
    ("model", RandomForestRegressor())
)
```

**Kya hua:** `TypeError: Pipeline.__init__() takes 2 positional arguments but 3 were given`

**Kyun galat tha:** `Pipeline` **ek hi** cheez maangta hai — steps ki ek **list**.
Maine do tuple do alag argument banake bhej diye.

Soch ke dekho — `Pipeline` ko kaise pata chalega ki tumne 2 step diye hain ya 7?
Isliye wo bolta hai "sab steps ek list me daal ke ek hi cheez ki tarah do".

**Fix:** tuples ko `[ ]` me lapet do:

```python
pipeline = Pipeline([
    ("prep", build_preprocessor()),
    ("model", RandomForestRegressor(random_state=42))
])
```

`preprocessing.py` me `ColumnTransformer` ke saath maine yahi sahi kiya tha —
`transformers=[...]`. Yahan bracket bhool gaya.

## 1.3 `logger.INFO(...)` — CAPS me method bulaya

**Maine likha:** `logger.INFO("pipeline Model found")`

**Kya hua:** `AttributeError: 'Logger' object has no attribute 'INFO'`

**Kyun galat tha:** `logging` me `INFO` **do jagah** aata hai aur wo **do bilkul
alag cheezein** hain:

| Kya | Ye hai | Kahan lagta hai |
|---|---|---|
| `logging.INFO` (CAPS) | ek **number** — 20 | `basicConfig(level=logging.INFO)` — volume knob |
| `logger.info()` (small) | ek **method** — message bhejta hai | jab kuch likhna ho |

CAPS wala **level ka naam** hai, method nahi. Ek yaad rakhne ka tarika: CAPS =
constant (badalta nahi), small = kaam karne wala function.

**Fix:** teeno jagah `logger.INFO` → `logger.info`.

---

# Hissa 2 — Chupchaap jhoot bolne wali galtiyaan

**Ye hissa sabse important hai.** In galtiyon me se ek bhi crash nahi karti.
Training chalti hai, "sab theek hai" lagta hai, aur galat number screen pe aa
jaata hai.

## 2.1 `%d` — saare metrics `0` ban gaye

**Maine likha:**

```python
logger.info("MAE:%d RMSE:%d r2:%d", mae, rmse, r2)
```

**Kya hua — chalake dekha:**

```
%d   ke saath -> r2:0       mae:0       rmse:0
%.4f ke saath -> r2:0.9821  mae:0.1212  rmse:0.4391
```

**Kyun galat tha:** `%d` ka matlab hai *"ise **integer** banake dikhao"*.
Mere saare metrics 0 aur 1 ke beech ke decimal hain. `0.9821` ko integer banao
toh decimal wala hissa kat jaata hai → `0` bachta hai. **Har metric `0`.**

Ab socho agar ye pakda na jaata. Main training chalata, screen pe `r2:0` dikhta,
main sochta model tut gaya — aur ghante barbaad karta ek aise bug ko dhoondhne
me **jo model me hi nahi hai**, sirf print statement me hai.

Usse bhi bura: main `r2:0` dekh ke maan leta ki score sach me 0 hai.

**Fix:** `%d` → `%.4f` (float, 4 decimal tak).

> Yahi baat `feature-names-bug.md` me likhi hai —
> *"Turant crash hona, chupchaap galat hone se behtar hai."*
> `logger.INFO` wali galti 10 second me pakdi gayi. `%d` wali galti mahino
> chal sakti thi.

## 2.2 `{mae, rmse, r2}` — dict samajh ke **set** bana diya

**Maine likha:**

```python
train_metrics = {MAE, RMSE, r2}          # colon nahi lagaya
```

**Kya hua — return value print kiya:**

```
train -> {0.12122106918239002, 0.9821017127293109, 0.1682019742182951}
type  -> <class 'set'>
```

**Kyun galat tha:** Python me `{ }` ke andar **`key: value`** likho toh dict
banta hai. Sirf values likho toh **set** ban jaata hai. Colon chhoot gaya, set
ban gaya.

Teen problem, badhti hui khatarnaki me:

**(a) Naam gayab.** Insert kiya tha `mae, rmse, r2` = `0.121, 0.168, 0.982`.
Print hua `0.121, 0.982, 0.168` — **order badal gaya**, kyunki set order rakhta
hi nahi (hash pe chalta hai). Ab `metrics["r2"]` kaam nahi karta, aur position se
bhi nahi nikal sakte.

**(b) Do barabar value ho toh ek gayab.** Set duplicate hata deta hai. Kisi din
`mae` aur `rmse` dono `0.44` aa gaye → set me **do** element bachenge, teen nahi.
Koi error nahi. Ek metric chupchaap gayab.

**(c) Part 2 ka gate tootega.** `if metrics["test"]["r2"] < 0.85: reject` — set
pe `["r2"]` chalta hi nahi.

**Fix:** colon lagao — `{"mae": mae, "rmse": rmse, "r2": r2}`.

## 2.3 `Path(__name__)` — galat variable, aur "mere machine pe chalta hai"

**Maine likha:**

```python
path = Path(__name__).parent / "data" / "raw" / "...csv"
```

**Kya hua:** kuch nahi. **Chal gaya.** Aur yahi problem hai.

**Kyun galat tha:** `__name__` module ka **naam** hai (ek string) — is file me
chalane pe uski value literally `"__main__"` hai. File ka **rasta**
`__file__` me hota hai. Maine naam ko path samajh liya.

Chalake dekha:

```
Path('__main__')         -> WindowsPath('__main__')
Path('__main__').parent  -> WindowsPath('.')        <- yaani "abhi jahan khade ho"
joined                   -> data\raw\x.csv          <- RELATIVE path
```

Toh path relative ban gaya. Aaj chal gaya **sirf isliye** ki main repo root se
command chala raha tha. Kal jab CI se chalega, ya Docker ke andar, ya kisi
doosre folder se → `FileNotFoundError`.

Ye classic **"mere laptop pe toh chalta hai"** bug hai. Test pass, local run
pass, deploy pe fail.

**Fix:** `__file__` use karo aur gino kitne level upar jaana hai:

```
<repo>/src/mental_health/models/train.py
   ^        ^         ^          ^
   [3]     [2]       [1]        [0]     <- Path(__file__).parents[...]
```

```python
path = Path(__file__).parents[3] / "data" / "raw" / "...csv"
```

## 2.4 `errors='ignore'` — problem ko chhupa diya

**Maine likha:** `prepared_df.drop(columns=['Mental_Health_Score'], errors='ignore')`

**Kyun galat tha:** `errors='ignore'` ka matlab hai *"agar ye column na mile toh
chupchaap kuch na karo"*. Par target column na milna **sabse bada problem** hai
jo ho sakta hai — us case me training ka koi matlab hi nahi.

Ye soch mere `ADR 0002` ke ulta hai, jahan maine likha tha "loudly fail karo,
guess mat karo".

**Fix:** `errors` hata diya. Column na mile toh `KeyError` — turant, saaf.

---

# Hissa 3 — Design aur hygiene galtiyaan

Ye crash nahi karti, par kal ya parso dard deti hain.

## 3.1 Sirf test metrics naape, train ke nahi

Pehle sirf `y_pred = pipeline.predict(X_test)` tha.

**Kyun galat:** sirf test score se **overfit dikhta hi nahi**. Mere numbers:

| | train | test | gap |
|---|---|---|---|
| R² | 0.9821 | 0.8902 | **0.09** |

Ye 0.09 ka gap ek information hai — default RandomForest har tree ko poori depth
tak badhne deta hai, toh wo training data lagbhag yaad kar leta hai. Sirf test
dekhta toh mujhe ye pata hi na chalta.

**Fix:** dono pe naapo. `predict(X_train)` bhi karo.

## 3.2 Metrics nikaale, phir phenk diye

Pehle `mae`, `rmse`, `r2` calculate hote the aur function khatam — koi `return`
nahi, koi log nahi. Chalane pe screen pe **kuch nahi dikhta tha**.

**Fix:** `return pipeline, metrics`.

## 3.3 Wahi code do baar likha

Train aur test ke metrics ka block **exactly same** tha, bas `y_train` ki jagah
`y_test`. Aur maine `mae/rmse/r2` variable dobara use kar liye.

**Kyun galat:** ek line copy-paste me bhool jao — jaise `y_test` ki jagah
`y_train` reh jaye — toh train ka number test ki jagah chala jayega aur
**kabhi pata nahi chalega**. Score sahi dikhega, bas jhootha hoga.

**Fix:** ek chhota helper — `_compute_metrics(y_true, y_pred)` jo teen-key wala
dict de. Dono jagah ek line. 12 line → 2 line, aur galti ki gunjaish khatam.

(`_` prefix ka matlab: *"ye sirf is file ka andar ka kaam hai, bahar se import
mat karo"*.)

## 3.4 `pipeline` aur `metrics` ek hi dict me

**Maine likha:**

```python
return {"pipeline": pipeline, "train": ..., "test": ...}
```

**Kyun galat:** kal Part 2 me main yahi metrics `json.dump` karunga metadata file
me. Par usi dict me `pipeline` baitha hai — ek sklearn object, jo JSON me convert
**nahi** ho sakta:

```
TypeError: Object of type Pipeline is not JSON serializable
```

**Rule:** jo cheez file me likhne wali hai, usko kisi non-serializable object ke
saath mat baandho.

**Fix:** `return pipeline, metrics` — do alag cheezein, do alag return values.
`metrics` apne aap me pura JSON-safe.

## 3.5 `RSME` — spelling ulti (teen baar!)

**R**oot **M**ean **S**quared **E**rror → `RMSE`. Maine `RSME` likha, aur wo dict
ki **key** thi.

**Kyun ye chhoti baat nahi:** ye key kal metadata JSON me likhi jaayegi, aur wo
file model ke saath disk pe **permanently** rahegi. Gate bhi isi naam se padhega.
Baad me theek karo toh purane metadata files ka naam naye code se match nahi
karega.

Saath hi keys ka case mix tha — `"MAE"` caps me, `"r2"` small me. **Sab lowercase**
kar diya (`mae`, `rmse`, `r2`) — JSON me lowercase standard hai.

## 3.6 Ek log message me `\n` — 4 line ban gayi

**Maine likha:**

```python
logger.info("Training Metrics :\nMAE:%.4f\nRMSE:%.4f\nr2:%.4f", ...)
```

**Kyun galat:** ek `logger.info()` = **ek log record**. Par andar 3 newline daal
diye, toh log file me 4 line bahar aayengi — aur prefix
(`INFO:mental_health.models.train:`) **sirf pehli** line pe lagega. Baaki 3 line
anaath.

Ye tab dikhta hai jab log file me jaate hain. `grep "r2"` karo toh jo line
milegi uspe na time hoga, na kis run ka hai wo pata chalega.

**Fix:** ek metric set = ek line, `key=value` style:

```
INFO:__main__:train | r2=0.9821 mae=0.1212 rmse=0.1682
INFO:__main__:test  | r2=0.8902 mae=0.3258 rmse=0.4391
```

Do line, dono grep-able, dono pe apna timestamp. `r2` pehle — kyunki wahi sabse
pehle dekhne wala number hai.

## 3.7 `logger.info("pipeline Model found")` — bekaar log

Ye kuch nahi batata. "Model found" — kahan se found? Training abhi hui hai,
dhoondha nahi gaya. Aur next line hi metrics print kar rahi hai, jo khud iska
proof hai.

**Rule:** log ki har line kisi **sawaal ka jawab** honi chahiye. Ye kisi ka jawab
nahi de rahi thi.

**Fix:** usko kaam ka banao — `logger.info("training started | data=%s", path)`.
Ye ek asli sawaal ka jawab deta hai: *"kaunsi file pe train hua tha?"* — jo debug
karte waqt sabse pehla sawaal hota hai.

## 3.8 "training started" log **training ke baad**

```python
pipeline, metrics = train(path)                     # training YAHAN hui
logger.info("training started | data=%s", path)     # "started" ke BAAD?
```

Output me khud dikha — pehle validation ke log aaye, **phir** "training started".

**Fix:** log ko `train()` ke **andar**, pehli line pe rakho. Kyun? `train()` kal
kisi test se ya gate script se bhi bulaya jayega — tab bhi ye log chahiye. Guard
me rakha toh sirf `-m` se chalane pe milega.

Yahi rule `cleaning.py` me already hai: log wahin hota hai **jahan kaam ho raha
hai**, caller me nahi.

## 3.9 `path: str` — jhootha type hint

Hint `str` kehta tha, par main `Path` object pass kar raha tha.

**Kyun galat:** type hint ka pura maksad hai ki padhne wale ko **sach** pata
chale. **Jhootha hint bina hint se bura hai** — usme bharosa kar ke koi
`path.upper()` likh dega aur crash ho jayega.

## 3.10 Import guard ke andar / khali `__main__`

`from pathlib import Path` `if __name__` block ke andar tha, aur pehle to guard
me sirf `pass` tha (matlab ek command se training chalti hi nahi thi).

**Fix:** imports top pe (PEP 8 — koi bhi file kholte hi 5 second me dikhna
chahiye ki wo kis cheez pe depend karti hai), aur guard me asli kaam.

---

# Hissa 4 — Naya tarika bulletproof hai ya usme bhi tradeoff hai?

Ye sabse imaandaar sawaal hai. Sach ye hai: **15 me se sirf 9 fix poore
bulletproof hain.** Baaki 6 me tradeoff hai, aur wo jaanna zaroori hai.

## Jo poore bulletproof hain (koi tradeoff nahi)

| Fix | Kyun pakka |
|---|---|
| `Pipeline([...])` list me | API ka niyam hai, iska koi doosra tarika nahi |
| `logger.info` (small) | method ka naam hai, bas |
| dict me colon (`"mae": mae`) | keys se access karna hi sahi hai |
| `RMSE` spelling + lowercase keys | naam sahi hai ya galat, beech me kuch nahi |
| `errors='ignore'` hataya | fail loudly — ADR 0002 wali hi soch |
| helper function | duplicate code kam = galti ki jagah kam |
| `pipeline` aur `metrics` alag | serializable cheez ko object se alag rakhna |
| imports top pe | PEP 8 standard |
| sach wala type hint | jhootha hint bina hint se bura |

## Jo bulletproof NAHI hain — inme tradeoff hai

### 4.1 `stratify` hatana — sahi, par ek behtar option bhi hai

Regression me `stratify=y` galat hai, ye pakka. Par **random split ka apna
problem** hai: sirf ittefaq se train aur test me target ki distribution alag ho
sakti hai. 4998 rows pe risk kam hai, 200 rows pe bahut zyada hota.

**Industry me jo karte hain (advanced):** target ko **bins** me baanto, phir un
bins pe stratify karo:

```python
y_bins = pd.qcut(y, q=10, labels=False)      # 10 barabar hisse
train_test_split(X, y, stratify=y_bins, ...)
```

Isse dono side me har score-range ke students aate hain.

**Maine kyun nahi kiya:** 4998 rows kaafi hain, `random_state=42` se result
reproducible hai, aur notebook se comparison bhi barabar rehta hai. Ek extra
step ka faayda measure kiye bina add karna = ADR 0003 wali hi galti dohrana.

### 4.2 `Path(__file__).parents[3]` — chalta hai, par **nazuk** hai

`__name__` se behtar hai, par bulletproof **nahi**. Wo `3` hardcoded hai —
`train.py` ko ek folder gehra sarka do, toh `parents[3]` chupchaap **galat**
folder pe point karega. Koi error nahi, bas galat jagah.

Yaani ek silent bug ko doosre (kam khatarnaak) silent bug se badla hai.

**Industry me kya karte hain — badhte kram me:**

| Tarika | Faayda | Nuksan |
|---|---|---|
| `parents[3]` (abhi) | zero setup | file sarki toh chupchaap toot jaayega |
| CLI argument (`--data path`) | koi guess nahi, jahan se chalao chalega | ek argument parser chahiye |
| env var / config file | Docker aur CI me natural | ek aur cheez set karni padti hai |

**Sahi jawab Part 2 me aayega:** data path ek **argument/config** hona chahiye,
file ke andar guess nahi. Docker me data usi jagah nahi hoga jahan laptop pe hai.
Filhaal `parents[3]` chal raha hai — par ye **jaanbujh ke liya gaya udhaar** hai,
jeet nahi.

### 4.3 Ek 70/30 split — sabse bada weak point

Mera `test r2 = 0.8902`. Par ye **ek** particular split ka number hai. `random_state`
badal do, number badal jayega — 0.88 bhi aa sakta, 0.90 bhi.

**Industry standard:** cross-validation — data ko 5 hisso me baanto, 5 baar train
karo (har baar ek alag hissa test), phir **average ± spread** batao. Tab kehne
layak hota hai *"0.89, ±0.01"* — ek number nahi, ek range.

| | ek split (abhi) | 5-fold CV |
|---|---|---|
| Speed | 1x — ~10 second | 5x |
| Bharosa | ek number, variance chhupa hua | average + spread dikhta hai |
| Setup | already hai | `cross_val_score` — 2 line |

**Maine kyun nahi kiya:** 2 din me ship karna hai, aur 4998 rows pe ek 70/30
split ka number kaafi stable hota hai. Par ye **jaanbujh ke chhoda hai, bhoola
nahi** — aur isi liye ye line yahan likhi hai.

### 4.4 `%.4f` — behtar hai, par `None` pe crash karega

`%.4f` readable hai (`r2=0.8902`), par agar kabhi koi metric `None` aa gaya toh
`TypeError: must be real number, not NoneType`.

`%s` kabhi crash nahi karta, par bahut lambi value print karta hai
(`0.890199835426194`).

**Tradeoff:** metrics ke liye `%.4f` sahi choice hai — wo hamesha float hi hain,
aur padhne me saaf. Par yaad rakho: **`%s` safe hai, `%.4f` sundar hai.** Jahan
value None ho sakti ho, wahan `%s`.

### 4.5 Text log — theek hai, par production me structured log chalta hai

`train | r2=0.9821 mae=0.1212` — grep karne layak hai, ye achha hai. Par ye ab
bhi **text** hai. Bade systems me log **JSON** me nikaalte hain, taaki tool
seedha `r2` field pe query kar sake, string parse na kare.

**Abhi kyun nahi:** ek 2-din ke project me `structlog` ya JSON formatter add
karna pure overhead hai. Text log 4998-row project ke liye bilkul kaafi hai.
Ye "aage ka rasta" hai, "aaj ki galti" nahi.

### 4.6 `return pipeline, metrics` — 2 pe theek, 4 pe kharab

Do cheez return karna saaf hai. Par kal Part 2 me agar `feature_names`,
`version`, `dataset_info` bhi chahiye — toh `return a, b, c, d, e` ho jayega, aur
caller ko **order yaad rakhna** padega. Ek jagah order ulta ho gaya → silent bug.

**Us waqt ka fix:** ek `NamedTuple` ya `dataclass` (jaise `TrainResult`), jisme
har cheez ka **naam** ho. Filhaal 2 hai, toh tuple theek hai. Teesri cheez add
karne ke waqt hi badalna.

---

# Hissa 5 — Jo ab bhi kamzor hai (jaanbujh ke)

Saare fix ke baad bhi `train.py` me ye cheezein missing hain. Ye list isliye hai
ki koi ye na soche "file done hai, sab perfect hai":

| Kami | Kitna serious | Kab theek hoga |
|---|---|---|
| `train.py` ka **koi test nahi** | 🔴 sabse bada | ek smoke test — chhote fixture pe train chal jaaye |
| Model save + version + metadata nahi | 🔴 | Part 2 |
| Acceptance gate nahi (kharab model bhi pass) | 🔴 | Part 2 |
| Data path file me hardcoded | 🟡 | Part 2 — argument/config banega |
| Ek split, CV nahi | 🟡 | jaanbujh ke chhoda (4.3) |
| 39 feature count check nahi | 🟡 | schema chupchaap badla toh pata nahi chalega |
| Text log, structured nahi | 🟢 | zarurat nahi is size pe |

Sabse bada wala dobara: **`train.py` ka ek bhi test nahi hai.** Jo 3 test pass ho
rahe hain, wo `cleaning` aur `preparation` ke hain. Training code ke liye ek bhi
nahi. Aur yahi wo file hai jo sabse zyada badalti rahegi.

---

# Ek line ka lesson

> **Jo galti crash karti hai, wo tumhari dost hai. Jo galti chalti rehti hai aur
> galat number deti hai, wo dushman hai.**

Is file me `logger.INFO` (crash) 10 second me pakdi gayi. `%d` (silent) sirf
isliye pakdi gayi ki koi output ko dhyaan se dekh raha tha — warna `r2:0` dekh ke
main model debug karta rehta, jabki model bilkul theek tha (0.89).

Isi liye pattern banao: **naya code likho → chalao → output ko sach me padho.**
"Error nahi aaya" ka matlab "sahi hai" nahi hota.

## Related docs

- [`sklearn-pipeline-hygiene.md`](../insights/sklearn-pipeline-hygiene.md) — builder
  khali dabba deta hai, fit sirf train pe
- [`feature-names-bug.md`](../insights/feature-names-bug.md) — "turant crash hona,
  chupchaap galat hone se behtar hai" wala poora explanation
- [`logging.md`](../insights/logging.md) — levels, `%s` vs f-string,
  `basicConfig` sirf entry point pe
- [`ADR 0002`](../decisions/0002-no-imputers-in-pipeline.md) — loudly fail karo,
  guess mat karo (2.4 ka source)
- [`ADR 0003`](../decisions/0003-remove-log-transform.md) — measure kiye bina step
  add mat karo (4.1 ka source)
