# sklearn pipelines: builders return *unfitted* objects

_A short engineering rule, learned while writing `features/preprocessing.py`._

## The rule

A function that builds a preprocessor should **create everything fresh inside
itself** and return it **unfitted**. It should not touch data at all.

```python
def build_preprocessor():
    numeric_pipeline = Pipeline(...)     # created INSIDE
    ...
    return ColumnTransformer(...)        # unfitted
```

Not this:

```python
numeric_pipeline = Pipeline(...)         # created once at import, shared forever

def build_preprocessor():
    return ColumnTransformer([... numeric_pipeline ...])
```

## Why — reason 1: shared state

Objects created at module level are made **once**, when the file is first
imported. Every call to `build_preprocessor()` then hands out a
`ColumnTransformer` pointing at the *same* underlying pipeline objects.

sklearn happens to `clone()` transformers when it fits them, so fitted state
does not usually leak between them — this is why the mistake often goes
unnoticed. But if anything ever *mutates* one of those shared objects (e.g.
`numeric_pipeline.set_params(...)`), the change silently affects every
preprocessor in the whole process. A builder that builds fresh objects cannot
have this problem at all.

Column name lists are fine at module level — they are configuration, and you
read them rather than fit them.

## Why — reason 2: fitting belongs elsewhere

The builder must not call `.fit()`, and must not accept a DataFrame. Fitting
happens later, in the training script, **on the training split only**. If the
builder ever fit anything, it would see data it should not see, and that is
data leakage.

So the split of responsibility is:

| File | Job |
|------|-----|
| `features/preprocessing.py` | *build* the unfitted preprocessor |
| `models/train.py` | split the data, then *fit* it on train only |

## Bonus gotcha: `FunctionTransformer` and feature names

`FunctionTransformer(np.log1p)` does not know what to name its output column, so
asking the pipeline for feature names blows up:

```
AttributeError: Estimator log_transform does not provide get_feature_names_out
```

Fix: `FunctionTransformer(np.log1p, feature_names_out="one-to-one")` —
"one-to-one" means the output columns keep the input names. Worth setting always,
because you *will* want feature names later for importance plots and debugging.

## One-line summary

Builders construct fresh, unfitted objects and never see data; training fits
them on the training split only.
