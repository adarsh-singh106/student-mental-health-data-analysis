# ADR 0003 — `Study_Hours` par log transform hataya

**Status:** Accepted
**Date:** 2026-08-28
**Area:** feature engineering / preprocessing

## Context

Notebook me `Study_Hours` ke liye ek alag "skewed" pipeline tha:

```python
skew_pipeline = Pipeline([
    ('log_transform', FunctionTransformer(np.log1p)),
    ('scale', StandardScaler())
])
```

Ye tutorial se aaya tha — kisi ne check nahi kiya ki iska **faayda** ho raha hai
ya nahi. Isliye humne measure kiya.

## Data (jo humne actually naapa)

```
Study_Hours skew  :  0.436     ->  log1p ke baad  -0.134

RandomForest   log ke SAATH -> R2 0.89037   MAE 0.32569
RandomForest   log ke BINA  -> R2 0.89020   MAE 0.32580

LinearRegression  log ke SAATH -> R2 0.74468   MAE 0.53643
LinearRegression  log ke BINA  -> R2 0.74474   MAE 0.53583
```

## Teen reason (kyun hata rahe hain)

**1. Skew hi kaafi nahi tha.** Industry rule of thumb: `|skew| > 0.5` par socho,
`|skew| > 1.0` par pakka transform karo. Yahan skew **0.436** hai — threshold se
neeche. Column pehle se hi theek tha.

**2. RandomForest ko skew se matlab hi nahi.** Tree model sirf order dekhta hai
("value 3 se badi hai ya chhoti"), actual number nahi. `log` order badalta nahi
(monotonic hai), toh RF ke splits waise hi rehte hain. Aur hum RF hi ship kar
rahe hain.

**3. Faayda literally zero.** R2 ka farak 0.00017 — pura noise. LinearRegression
par log wala version thoda **kharab** nikla.

## Decision

Log transform **hata diya**. `Study_Hours` ko `numeric_bucket` me daal diya
(baaki numeric columns ke saath — sirf scaling).

`ColumnTransformer` 5 branch se **4 branch** ka ho gaya.

## Consequences

- Ek pura pipeline branch aur ek `FunctionTransformer` delete — kam code,
  kam test, kam cheezein tootne ke liye.
- **Bonus:** `FunctionTransformer` ki wajah se ek real bug tha —
  `get_feature_names_out()` crash ho raha tha. Transform hatane se wo bug
  **automatically khatam** ho gaya. (Us bug ka explanation:
  [feature-names-bug.md](../insights/feature-names-bug.md))
- Model performance par koi asar nahi (numbers upar hain).
- Agar future me koi column genuinely heavily skewed aaya (`|skew| > 1`), tab
  transform wapas add karenge — measure karke, blindly nahi.

## Asli lesson (generalizable)

> Pipeline ka **har step** maintain karna padta hai, test karna padta hai, aur
> toot sakta hai. Jo step apni jagah **kama nahi raha**, wo delete hona chahiye.

Yahan proof bhi mil gaya: ek bekaar step ne **zero faayda** diya aur ek **bug
free me** de diya. Yahi overengineering ki definition hai.

Standard practice: **skew naapo → threshold check karo → tabhi transform lagao.**
Tutorial me tha isliye nahi.

Related: [ADR 0002](0002-no-imputers-in-pipeline.md) — wahi soch, "safety net"
sirf tab jab wo asli problem solve kare.

