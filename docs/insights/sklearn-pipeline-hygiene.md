# sklearn pipeline ki safai — Hinglish me, apne code ke saath

_Ye wahi cheez hai jo humne `features/preprocessing.py` me theek ki._

## Sabse pehle: "fitted" aur "unfitted" ka matlab

Ye samajh liya toh baaki sab aasan hai.

`StandardScaler()` ka kaam hai numbers ko normal karna. Par uske liye usko
**mean aur standard deviation pata hona chahiye** — aur wo usse data se
**seekhna** padta hai.

**Unfitted (khali dabba)** — abhi bana hai, kuch nahi jaanta:

```python
scaler = StandardScaler()      # isko kuch nahi pata
```

**Fitted (bhara dabba)** — train data dekh liya, ab numbers yaad hain:

```python
scaler.fit(X_train)
# ab andar ye store ho gaya (tumhare hi dataset se):
#   Avg_Daily_Usage_Hours -> mean 5.078, std 1.654
#   Study_Hours           -> mean 3.008, std 1.637
```

Aur `transform` inhi yaad kiye numbers ka istemaal karta hai.

Bas yahi farak hai. **Unfitted = khali recipe. Fitted = jisme asli numbers bhar
gaye.**

Isi tarah tumhara `OneHotEncoder(max_categories=11)` bhi fit hone par
**seekhta** hai ki top 10 countries kaunse hain (India, USA, UK, Canada...) aur
baaki sab `infrequent` bucket me jaayenge. Wo list uske andar store ho jaati hai.

## Rule 1 — builder har baar naye objects banaye

Tumhara `build_preprocessor()` **unfitted** preprocessor return karta hai. Uske
andar ke chhote pipelines bhi **function ke andar** bane hone chahiye.

**Galat tarika (jo pehle tha):**

```python
numeric_pipeline = Pipeline(...)      # file ke top pe, function ke BAHAR

def build_preprocessor():
    return ColumnTransformer([("numeric_pipeline", numeric_pipeline, ...)])
```

**Sahi tarika (jo ab hai):**

```python
def build_preprocessor():
    numeric_pipeline = Pipeline(...)   # function ke ANDAR, har baar naya
    ...
    return ColumnTransformer([...])
```

### Kyun? — tiffin box wali baat

File ke top pe likha object **sirf ek baar** banta hai — jab file pehli baar
import hoti hai. Uske baad tum `build_preprocessor()` **10 baar** bulao, sabko
**wahi ek** `numeric_pipeline` milta hai. Ek hi tiffin box sabko baant diya.

Ab agar kisi ne us box me kuch badal diya — jaise:

```python
numeric_pipeline.set_params(scale__with_mean=False)
```

toh wo badlav **poore program** me sab jagah lag jaayega. Tumhare test me bhi,
training me bhi. Aur dhoondhna bahut mushkil hota hai, kyunki code ki us line me
kuch galat nahi dikhta.

**Sach:** sklearn `fit` karte waqt `clone()` karta hai (copy banata hai), toh
fitted numbers usually leak nahi hote. Isi wajah se ye galti pakdi nahi jaati.
Par **function ke andar banao toh ye problem ho hi nahi sakti.** Free me safety.

Column ke naam wali lists (`numeric_bucket`, `country_bucket`) top pe rakhna
**theek hai** — wo configuration hain, unko fit nahi karte, sirf padhte hain.

## Rule 2 — builder data ko chhue hi na

`build_preprocessor()` me:
- koi `df` nahi
- koi `.fit()` nahi
- koi argument nahi

Wo sirf **khali dabba banata hai aur return karta hai.** Bas.

`fit` kahan hoga? `models/train.py` me — aur **sirf train data pe**:

```python
X_train, X_test, ... = train_test_split(...)     # pehle split
pipeline.fit(X_train, y_train)                   # PHIR fit, sirf train pe
```

### Kyun? — leakage

Socho agar scaler ne **poore** data ka mean seekh liya (test wale rows bhi
milake). Toh model ne indirectly test data ke baare me jaan liya. Phir test score
**jhoot** bolega — asli duniya me model itna achha nahi hoga.

Isliye order hamesha yahi: **split pehle, fit baad me.**

## Kaam ka batwara

| File | Kaam |
|------|------|
| `features/preprocessing.py` | khali (unfitted) preprocessor **banata** hai |
| `models/train.py` | data split karta hai, phir usse **train pe fit** karta hai |

## Ek aur gotcha

`FunctionTransformer` wala bug — uska pura Hinglish explanation alag doc me hai:
[feature-names-bug.md](feature-names-bug.md)

## Ek line me pura matlab

> Builder **khali** dabba banata hai aur data ko chhuta bhi nahi.
> Training us dabbe ko **sirf train data** pe bharti hai.
