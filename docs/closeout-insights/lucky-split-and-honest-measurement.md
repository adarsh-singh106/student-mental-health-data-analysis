# "Lucky split" aur imaandaar measurement — Hinglish me

_Ye Phase 1 ki poori kahani hai: humne `train.py`, `gate.py` aur
`preprocessing.py` me measurement ke defects theek kiye (CLOSEOUT 1.1–1.4).
Decision + why `docs/decisions/0005` me hai; ye rahi seekh, basics se._

## Ek line me problem

Humara model "pass" ho raha tha — par wo pass **ek lucky split** ki wajah se tha,
model ki asli acchai ki wajah se nahi. Number achha dikh raha tha kyunki **naapne
ka tareeka kamzor tha**, isliye nahi ki model utna achha tha.

Ye samajhne ke liye zero se chalte hain.

## Basic 1 — split hota kya hai, aur "lucky" ka matlab kya

Model ko test karne ke liye data do hisson me katte hain:

- **train** — ye dikha ke model ko sikhate hain.
- **test** — ye chhupa ke rakhte hain, phir poochte hain "ye bata" — kyunki jo
  cheez dikhi hi nahi, uspe accuracy hi asli accuracy hai.

Purana code ek hi baar 70/30 kaat raha tha (`random_state=42`). Us **ek** 30% me
jo rows chali gayi, agar wo **sanyog se aasaan** thi, to test score high aayega —
par wo model ki nahi, us **ek lucky cut ki** taareef hai.

Socho ek student ko sirf **ek** mock test do. Agar us paper me sanyog se wahi
sawaal aa gaye jo usne ratte the → 90%. Iska matlab wo topper hai? Nahi. Ek paper
kuch prove nahi karta.

## Basic 2 — 1.1: pehle vault banao (train / val / test)

Sabse pehli galti: hum **jis test set pe select/tune karte the, ussi pe final
score bhi bolte the.** Jab tum test dekh ke faisle lete ho ("ye number achha nahi,
kuch aur try karo"), to test ab "anjaan" nahi raha — tumne usse seekh liya. Uska
score ab jhootha (optimistic) hai.

Fix (1.1) — data **teen** hisson me:

```text
train 60%  -> model isi pe seekhta hai
val   20%  -> ispe select/gate karte hain (bar-bar dekh sakte ho)
test  20%  -> VAULT: ek hi baar, sabse aakhri me, sirf report karne ko
```

`train_test_split` ek baar me sirf do tukde karta hai, isliye do step me:

```python
# step 1: 20% test alag (vault me band)
X_temp, X_test, y_temp, y_test = train_test_split(X, y, test_size=0.20, random_state=42)
# step 2: bache 80% ko train(60) + val(20) me
X_train, X_val, y_train, y_val = train_test_split(X_temp, y_temp, test_size=0.25, random_state=42)
```

(25% of 80% = 20% of total — isliye `0.25`.)

**Vault ka rule:** test ko **sirf ek baar** chhuo, ekdum aakhir me, aur uspe kabhi
koi faisla mat lo. Wo tumhara "aakhri imaandaar number" hai. Isiliye code me wo
`test_final` naam se alag rakha hai aur gate use **nahi** karta.

## Basic 3 — 1.2: ek split ki jagah paanch (cross-validation)

Ek mock test lucky ho sakta hai. Ilaaj? **Paanch** mock test lo, average dekho —
aur ye bhi dekho ki score **kitna upar-neeche** hota hai.

Yahi cross-validation hai. 80% (train+val) ko 5 barabar tukdon me baanto. Phir 5
baar train karo: har baar 4 tukde pe seekho, bache 1 tukde pe test lo. Result: 5
number.

```python
cv = cross_validate(pipeline, X_temp, y_temp, cv=5,
                    scoring=("neg_mean_absolute_error", "r2"))
```

In 5 numbers se do cheezein nikaalte hain:

- **mean** — asli, tikaao performance (ek lucky cut nahi, 5 ka average)
- **std** (standard deviation) — model **kitna wobble** karta hai fold-dar-fold

Ek chhota gotcha: sklearn MAE ko **negative** karke deta hai (uska rule: bada =
behtar). Isliye sign wapas palatna padta hai — `-cv["test_neg_mean_absolute_error"]`.

### Yahan asli sच saamne aaya

Single split ne kaha `test r2 = 0.890`, MAE 0.35 ke neeche → pass.
Par 5-fold CV ne kaha:

```text
CV MAE = 0.3568 +/- 0.0114
worst-case (mean + 1 std) ~= 0.368
```

Purani limit 0.35 thi. **0.368 > 0.35.** Matlab jo model "pass" ho raha tha, wo
imaandaar naap pe **fail** kar raha tha. 0.35 kabhi asli bar thi hi nahi — wo us
ek lucky split pe fit ki gayi thi.

## Basic 4 — 1.2 gate: mean akela kaafi nahi, std bhi jodo

Gate ab CV pe judge karta hai, aur **worst-case** pe:

```python
mae_upper = cv_stats["mae_mean"] + cv_stats["mae_std"]
if mae_upper < MAX_CV_MAE:   # 0.40
    return True
```

std kyun jodte hain? Do model socho, dono ka average MAE same:

- Model A: har fold pe ~0.357 (steady) → bharosa hai.
- Model B: kabhi 0.25, kabhi 0.46 (jhoolta) → ye kabhi bhi bigad sakta hai.

Sirf mean dekho to dono barabar. **mean + std** dekhte hi Model B fail — kyunki
uska worst case kharaab hai. Ek wobbly model trustworthy nahi hota; std wahi
"kitna bharosemand" wala sawaal naap leta hai.

### Bar 0.35 → 0.40 kyun (chupke nahi, evidence ke saath)

Model sach me 0.35 clear nahi karta (worst-case ~0.368). Do imaandaar raaste the:
(A) bar ko ek defensible 0.40 pe le jao **aur kyun bolo**, ya (B) model itna
sudharo ki 0.35 clear kare. Deadline me humne **A** chuna — Phase 1 ka maksad
imaandaar naap hai, aakhri 2% accuracy nichodna nahi. Chupke se bar hilana beimaani
hoti; **CV evidence ke saath, ADR ke saath hilana** hi Phase 1 ka point hai.

## Basic 5 — 1.3: ek check jo kuch naapta hi nahi tha, hataya

Purana gate ye bhi check karta tha:

```python
abs(train_r2 - test_r2) < 0.15   # "overfit gap"
```

Idea tha: "train pe bahut achha, test pe kharaab = ratta maar liya (overfit)."
Aam taur pe theek, **par Random Forest ke liye bekaar.** RF ka kaam hi hai training
data ko lagbhag yaad kar lena — uska train r2 hamesha bahut high hoga **by design.**
Toh bada train-test gap yahan normal hai, bimari nahi. Ye check kuch trustworthy
naap hi nahi raha tha — aur pass bhi sirf 0.03 margin se hua tha (shor).

Isko hataya. Ab wobble ka poora sawaal **CV std** sambhaalta hai — ek check jo
sach me kuch naapta hai.

## Basic 6 — 1.4: Country ka "do kachra-dabba" wala bug

Ye measurement nahi, **encoding** ka defect tha, par kahani wahi — chhupi hui
gadbad. `Country` me ~111 alag value hain. Sabko one-hot karna bewakoofi (110+
khaali column). Toh sirf frequent countries rakho, baaki sabko ek "misc" me daalo.

Problem: **do** misc dabbe ban rahe the —

- `Country_Other` — CSV me pehle se ek literal `"Other"` category thi (1880 rows,
  sabse badi!) → apna column.
- `Country_infrequent_sklearn` — encoder ka apna rare-bucket.

Do kachra-dabbe = "misc" ka signal do jagah bat gaya, bekaar me. Aur mazaa ye:
**sirf encoder settings se ye theek nahi hota** — literal `"Other"` **frequent**
hai (1880 rows), toh `min_frequency`/`max_categories` usse "rare" maan hi nahi
sakte, infrequent bucket me daalenge hi nahi.

Fix: encoder se **pehle** ek chhota map lagao —

```python
KNOWN_COUNTRIES = ["Australia","Canada","France","Germany","India",
                   "Ireland","Mexico","Spain","Turkey","UK","USA"]

country_pipeline = Pipeline([
    ("collapse", FunctionTransformer(_collapse_country, feature_names_out="one-to-one")),
    ("encode",   OneHotEncoder(handle_unknown="ignore")),
])
```

`_collapse_country`: jo `KNOWN_COUNTRIES` me nahi (rare + literal `"Other"` +
serve-time pe koi anjaan desh) — sabko ek `"Other"` bana do. Natija: 12 saaf
column (11 known + ek Other), koi `infrequent_sklearn` nahi.

### Yahan ek leakage-trap tha (bacha liya)

Lalach hoti hai: `KNOWN_COUNTRIES` ko fit ke waqt `value_counts()` se compute kar
lo. **Mat karo — wo leakage hai.** Kaunse desh "count" karenge, ye faisla us fit
ke data se shaped ho jaata, aur serve pe pipeline us data-derived list ko dobara
bana hi nahi sakta (usne store hi nahi ki). Isliye humne list ko ek **frozen
constant** rakha — ek baar ki human decision (jaise `Stress_Level` ka Low/Medium/
High order). Transform ab train/test/serve teeno pe **bilkul same**.

**Trade-off (maan liya):** naya desh frequent ho gaya to list **haath se** update
karni padegi + retrain. Ye leak na karne ki keemat hai. ADR 0005 me likha hai
taaki surprise na ho.

## Poore Phase 1 ka ek dhaaga

Chaaro cheez ek hi harkat hain:

| # | Kya dikh raha tha | Asli sach | Fix |
|---|-------------------|-----------|-----|
| 1.1 | test pe select + report dono | test "anjaan" nahi raha | val alag, test vault |
| 1.2 | ek split: r2 0.890, pass | CV MAE 0.368 > 0.35, fail | CV gate, bar 0.40 (evidence sath) |
| 1.3 | "overfit gap" pass | RF ke liye ye kuch naapta hi nahi | hataya, CV std ne jagah li |
| 1.4 | Country 12 column, theek dikh raha | 2 misc dabbe, signal bata | ek "Other" bucket, no leak |

Har jagah number ya code "theek dikh raha tha" — aur har jagah dikhawa ek kamzor
measurement ki wajah se tha. [[reproducibility-and-dirty-git]] wali kahani ka hi
cousin: wahan artifact chupke se jhooth bol raha tha, yahan measurement.

## Ek line me pura matlab

> Ek split lucky ho sakta hai. Isliye **paanch** lo (CV), **mean + std** dono pe
> gate karo, jo check kuch naapta na ho use **hatao**, encoding me ek hi
> kachra-dabba rakho — aur jo bhi human-decided list ho use **data se compute mat
> karo** (leakage), **freeze** kar do. Number sudhaarne se pehle **naapna**
> sudhaaro.
