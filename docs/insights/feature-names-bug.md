# `get_feature_names_out()` ka bug — Hinglish me, apne dataset ke saath

_Ye wahi bug hai jo `FunctionTransformer(np.log1p)` ki wajah se aa raha tha._

## Pehle problem samjho: naam kho jaate hain

Tumhara DataFrame andar jaata hai — **13 columns, naam ke saath**:

```
Age | Gender | Country | Academic_Level | Most_Used_Platform | ... | Stress_Level
```

Lekin model sirf **numbers** samajhta hai, text nahi. Toh `ColumnTransformer`
sab kuch numbers me badal deta hai. Bahar aata hai — **39 columns, bilkul bina
naam ke**:

```
[[ 0.42, -1.13, 0.0, 1.0, 0.0, 0.0, ... ]]      <- 39 numbers, koi naam nahi
```

13 kaise 39 ban gaye? Kyunki `Country` ke 11 alag columns ban gaye (India, USA,
UK...), `Most_Used_Platform` ke 12 ban gaye, waghera. Ye One-Hot Encoding karta
hai.

**Problem:** model ke paas ab sirf position hai — column 0, column 1, column 38.
Naam gayab.

## `get_feature_names_out()` kya karta hai

Ye wahi naam **wapas** deta hai. Tumhare pipeline pe chala ke ye mila:

```
column 0  -> Study_Hours
column 1  -> Age
column 2  -> Avg_Daily_Usage_Hours
...
column 36 -> Country_USA
column 38 -> Country_infrequent_sklearn
```

## Iski zarurat kab padegi?

RandomForest tumhe `feature_importances_` deta hai — matlab **39 numbers**, jo
batate hain kaunsa feature sabse important tha:

```
[0.21, 0.04, 0.31, 0.02, ... ]
```

Ab bina naam ke tum sirf itna keh sakte ho: *"column 2 sabse important hai."*
Kisi ko kya samjhaoge? 🤷

Naam ke saath tum keh sakte ho: *"`Avg_Daily_Usage_Hours` sabse important hai —
jitna zyada social media, utna kam mental health score."* **Yahi cheez kaam ki
hai** — interview me, report me, aur debugging me.

## Ab bug: crash kyun hua

Jab humne naam maange, ye error aaya:

```
AttributeError: Estimator log_transform does not provide get_feature_names_out
```

Matlab: *"`log_transform` step ko pata hi nahi ki uske output columns ka naam
kya hoga."*

## Kyun nahi pata? (yahi asli baat hai)

`FunctionTransformer` me tum **koi bhi** Python function daal sakte ho. sklearn
tumhare function ke andar dekh ke ye guess nahi kar sakta ki kitne columns bahar
aayenge. Apne dataset se examples:

| Function | Andar | Bahar | Naam kya hona chahiye |
|---|---|---|---|
| `np.log1p` | `Study_Hours` (1) | 1 column | `Study_Hours` (wahi naam) |
| `Study_Hours + Physical_Activity_Hours` jodne wala | 2 columns | 1 column | naya naam, jaise `total_hours` |
| square + cube banane wala | `Age` (1) | 3 columns | `Age`, `Age^2`, `Age^3` |

Dekho — teeno case me **naam ki ginti alag** hai. sklearn ko kaise pata chalega
tumne kaunsa likha hai? Nahi chalega. Toh wo **guess karne se mana kar deta
hai** aur error de deta hai.

**Aur ye achhi baat hai.** Socho agar sklearn chupchaap wahi purane naam laga
deta — toh 2 columns jod ke 1 banane wale case me naam **galat** ho jaate. Phir
tum feature importance ka chart dekh ke galat conclusion nikaalte, aur mahino
tak pata bhi nahi chalta. **Turant crash hona, chupchaap galat hone se behtar
hai.** (Yahi soch ADR 0002 me thi — imputer wale decision me.)

## Fix (agar kabhi `FunctionTransformer` use karo)

```python
FunctionTransformer(np.log1p, feature_names_out="one-to-one")
```

`"one-to-one"` ka matlab: *"sklearn, mera function jitne columns andar leta hai
utne hi bahar deta hai, usi order me — purane naam hi use kar lo."* `log1p` ke
liye ye sach hai, kyunki wo har value ko alag-alag badalta hai (1 value andar,
1 value bahar).

## Humne kya kiya

Humne `log1p` hi **hata diya** (dekho [ADR 0003](../decisions/0003-remove-log-transform.md)),
kyunki uska koi faayda hi nahi tha. `FunctionTransformer` gaya → **bug bhi khud
hi chala gaya**. Do problem, ek delete. 😄

## Ek aur cheez jo bug se sikhi: latent bug

Ye bug `fit()` ya `predict()` ko **kabhi nahi todta tha.** Training chalti,
tests pass hote, model ship ho jaata.

Ye sirf tab phatta jab tum pipeline se **uske baare me poochho** — feature names,
importance chart, ya `/model-info` endpoint. Yaani wo **mahine baad** phatta, us
code me jo tumne sabse last me likha.

> Jo code path tumne kabhi chalaya nahi, wo "kaam kar raha hai" nahi hai —
> wo **untested** hai.

## Bada MLOps principle

> Data jab pipeline me ghus jaata hai, uska **insaani matlab kho jaata hai** —
> jab tak tum jaan-boojh ke usse bacha ke na rakho.

Har production ML system ko ye map chahiye: *model ka input number 17 → asli
matlab kya hai*. Isi wajah se model metadata me **"feature schema version"**
rakhte hain. Ye chhota bug usi badi cheez ka chhota version hai.

