# Docker, Makefile aur CI — bilkul zero se, Hinglish me

_Ye wahi cheez hai jo humne CLOSEOUT 0.6 (Dockerfile + Makefile) aur 0.7 (CI)
me banaya. Main Docker ka beginner tha, isliye ye doc kisi cheez ko "pata hoga"
maan ke nahi chalta — har term zero se._

Related: [[reproducibility-and-dirty-git]] (0.5) — kyunki aakhir me "train host pe,
serve container me" ka faisla usi git-provenance wali baat se nikla.

---

## Problem: "mere laptop pe to chal raha tha"

Ek app tumhare laptop pe chalti hai kyunki tumhare laptop pe **sahi Python version,
sahi libraries, sahi settings** hain. Kisi aur ke laptop pe wo cheezein alag hain ya
missing hain → app phat jaati hai. Ye hi wo purani bimari hai jise sab "works on my
machine" bolte hain.

Docker isko aise theek karta hai: app ko uske **poore environment ke saath ek dabbe
me band** kar do. Ab jo bhi us dabbe ko chalayega, usko **bilkul wahi environment**
milega — chahe uska laptop kaisa bhi ho.

CLOSEOUT ke liye ye ek **reproducibility** sawaal hai (kya ajnabi isko chala paayega?),
ops-theatre nahi. Isiliye ye 0.6 me banaya, aur "do not build" list me nahi hai.

---

## Basic 1 — teen shabd: Image, Container, Dockerfile

| Shabd | Matlab | Analogy |
|---|---|---|
| **Image** | Blueprint — jisme sab define kiya hua hai, sealed | Cake ka **final packed dabba** |
| **Container** | Image ka chalta-firta instance | Us dabbe ko **khol ke actually use karna** |
| **Dockerfile** | Recipe — image kaisi banni chahiye, uske rules | Cake ki **likhi hui recipe** |

Ek Dockerfile se **bahut se** containers ban sakte hain — jaise ek recipe se bahut se
cake. Image ek baar banti hai, container har `run` pe naya.

**Poora flow:**

```
Dockerfile  --(docker build)-->  Image  --(docker run)-->  Container
 (recipe)                       (dabba)                   (chalta app)
```

---

## Basic 2 — humari Dockerfile, line by line

Ye rahi humari poori Dockerfile, aur har line ka matlab:

```dockerfile
FROM python:3.10-slim
```
**"Khaali dabbe ki jagah, ek aisa dabba lo jisme Python 3.10 pehle se pada hai."**
`slim` = chhota version (kam faltu cheezein → image halki). Ye humari **base** hai;
isi ke upar hum apni cheezein rakhenge.

```dockerfile
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
```
`uv` humara package manager hai (libraries install karta hai). Base image me wo nahi
hai. Ye line ek fixed version ka `uv` (`0.11.32`) uठा ke dabbe me rakh deti hai.
**Version fix isliye** taaki 6 mahine baad bhi bilkul yehi uv aaye — koi surprise na ho.

```dockerfile
WORKDIR /app
```
**"Dabbe ke andar `/app` folder banao aur wahin khade ho jao."** Iske baad ke saare
commands isi folder me chalenge.

```dockerfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
```
Sabse dhoshiyaar wali jodi. Pehle sirf **do files** copy ki: `pyproject.toml` +
`uv.lock` (inme likha hai "kaun-kaunsi libraries chahiye, exact kaunse version").
Phir `uv sync` unhe install karta hai.
- `--frozen` = "lock file ko hуб- hu maano, chupke se update mat karo" (repeatable).
- `--no-install-project` = "abhi sirf libraries daalo, mera apna code abhi mat chhuo."
- **Ye alag kyun? → neeche 'layer caching' me.**

```dockerfile
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY README.md ./
```
Ab humara **apna code** dabbe me. `tests/` isliye taaki dabbe ke **andar** test chal
sakein (CI ka docker job yehi karta hai). `README.md` isliye — us par ek poora bug
tha (neeche Bug 2).

```dockerfile
RUN uv sync --frozen
```
Ab poora sync — khud ka project bhi install ho gaya. Dabba ab taiyaar.

```dockerfile
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "mental_health.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
- `PATH` = "jab `python`/`uvicorn` bolun to humare virtual-env wale se chalao."
- `EXPOSE 8000` = "ye dabba apna port 8000 khula rakhega" (API yahin bolegi).
- `CMD` = **default command** — dabba chalao to ye apne aap chalega: API server start.
  (`0.0.0.0` = "dabbe ke bahar se bhi sunno", warna sirf dabbe ke andar se milta.)

---

## Basic 3 — Layer caching: order aisa kyun?

Docker har line ka ek **snapshot (photo)** rakhta hai — isko **layer** kehte hain.
Dobara build karte waqt Docker sochta hai: _"jo upar wali layers same hain, unhe dobara
mat banao — purani photo reuse karo."_

Ab dhyan do:
- Libraries install karna **slow** hai (minutes) aur **kabhi-kabhi** badalti hain.
- Apna code copy karna **fast** hai (seconds) aur **roz** badalta hai.

Isiliye humne **slow + kam-badalne-wali** cheez (libraries) **pehle** rakhi, aur
**fast + roz-badalne-wali** cheez (code) **baad me**. Faayda: code badla to Docker
sirf neeche wali chhoti layers dobara banata hai; bhaari libraries wali layer **photo
se reuse** ho jaati hai → build tez.

Agar order ulta hota (pehle code, phir libraries), to har chhote code change pe saari
libraries **dobara** install hotीं. Bahut slow. **Yahi wo "chalaki" hai jiske liye
COPY do baar likha.**

---

## Basic 4 — `.dockerignore`: dabbe me kya NAHI jaana chahiye

Jab `docker build .` chalate ho, wo `.` (poora current folder) Docker ko bhej diya
jaata hai — isko **build context** kehte hain. Problem: usme bhaari/faltu/private
cheezein bhi hain (data, purane models, `.git` history, virtual env). Wo image me
nahi chahiye.

`.dockerignore` ek list hai: **"ye cheezein context se hata do."** Humari:

```
data/          # dataset — license clear nahi → ship hi nahi karna
artifacts/     # trained models — bhaari, run-time pe mount honge
.git/          # poori git history — image me bekaar + bhaari
.venv/         # local virtual env — image apna banayega
notebooks/ audit/ docs/ *.md   # API chalane ke liye zaroori nahi
!README.md     # EXCEPTION — README ko rehne do
```

`!README.md` ka matlab: "`*.md` ne saari markdown hataayi, par README.md **wapas
rakho**." (Kyun zaroori tha → Bug 2.)

**Halki image = tez build, tez download, kam attack-surface (kam risk).**

---

## Basic 5 — Bake vs Mount: data dabbe me kyun nahi ghusaya (Raasta B)

Do raaste the:

- **Raasta A — bake:** data + models ko image ke andar hi pack kar do.
  Dikkat: (1) dataset ka license clear nahi → usko distribute karna galat;
  (2) image bhaari; (3) naya model banao to poori image dobara banani pade.
- **Raasta B — mount (humne ye chuna):** image me sirf **code**. Data aur models
  **run-time pe bahar se** "dikhaye" jaate hain — isko **volume mount** kehte hain.

Volume mount ko aise socho: dabbe ki deewar me ek **khidki** bana di, jisse bahar
(tumhara laptop) ka ek folder andar dikhta hai. `make serve` me ye line:

```
-v "$(CURDIR)/artifacts:/app/artifacts:ro"
```
Matlab: "mere laptop ka `artifacts/` folder, dabbe ke andar `/app/artifacts` pe dikhao;
`ro` = **read-only** (dabba padh sakta hai, badal nahi sakta)." Model dabbe me
permanently baka nahi — bas chalate waqt khidki se dikhaya. **License-safe + image halki.**

Ye 0.4 (fetch_data verify-not-download) aur PROVENANCE.md wali soch ke saath consistent
hai: unlicensed CSV kabhi ship nahi hota.

---

## Basic 6 — Makefile: chhote naam, lambe commands

Docker ke commands lambe hote hain: `docker run --rm -p 8000:8000 -v "...:...:ro" ...`.
Har baar type karna = galti ka chance + sab yaad rakhna pade.

**Makefile ek chhoti diary hai jisme lambe commands ko chhota naam de dete hain.**
Tum `make serve` bolo, wo andar ka poora lamba `docker run ...` chala deta hai.
Humari diary:

| Command | Kya karta hai | Kahan chalta hai |
|---|---|---|
| `make train` | model train, `./artifacts` me likhta hai | **host** (uv) |
| `make test`  | saare tests | **host** (uv) |
| `make build` | image (dabba) banata hai | Docker |
| `make serve` | dabbe se API, port 8000 pe | Docker |

Ajnabi ko ab Docker ke lambe commands yaad rakhne ki zaroorat nahi — 4 chhote naam kaafi.

_(Chhoti Windows note: is machine pe `make` aur `docker` install nahi the — isiliye
inhe local nahi, **CI pe** verify kiya. Aage dekho.)_

---

## Basic 7 — CI: GitHub ka robot jo har push pe khud check karta hai

**CI = Continuous Integration.**

Socho: tum code GitHub pe push karte ho. **CI ek robot hai jo har push pe apne aap ek
bilkul saaf, naya Linux computer leta hai, tumhara code clone karta hai, aur khud chala
ke dekhta hai — "chalta hai ya phat gaya?"** Result GitHub pe green tick (✓) ya red
cross (✗).

Ye itna zaroori kyun? Kyunki tumhare laptop pe bahut se **chhupe hue jugaad** hote hain
jo sirf tumhare paas hain — koi library jo kabhi install ki thi, koi file jo commit hi
nahi ki, koi setting. Tumhare laptop pe chalta hai, par saaf naye computer pe nahi. **CI
wahi saaf computer hai. Wo tumhare sab jugaad pakad leta hai.**

Humne `.github/workflows/ci.yml` me **do robot (jobs)** likhe:

- **`test` job:** `uv sync` (libraries install) → `uv run --frozen pytest`.
  (Ye CLOSEOUT 0.7 ne literally maanga tha.)
- **`docker` job:** `docker build` (dabba banao) → dabbe ke **andar** `pytest`.
  Ye 0.6 (Docker) ka **asli proof** hai — kyunki is Windows laptop pe Docker
  installed hi nahi, to dabba sach me banta hai ya nahi, ye Linux robot hi bata sakta hai.

Dono job **push aur pull-request** dono pe chalte hain.

---

## Basic 8 — CI ne 3 bug pakde (yahi CI ka asli fayda)

Jaise hi CI pehli baar chala, **teen baar red cross (✗)** aaya. Har cross ne ek asli
bug pakda jo Windows laptop pe **kabhi nahi dikhta.** Ye literally wo cheez hai jo
sabit karti hai ki CI kyun chahiye.

### Bug 1 — README hai hi nahi (dono job fail)

`pyproject.toml` me likha tha `readme = "README.md"` (build ko README padhni hai). Par
README.md kabhi commit hi nahi hui thi — laptop pe 0-byte file padi thi, GitHub pe thi
hi nahi. Saaf naye computer pe clone hua → README missing → `uv sync` (hatchling build)
phat gaya:

```
OSError: Readme file does not exist: README.md
```

**Fix:** ek README stub commit ki.
**Lesson:** _"mere laptop pe file hai" ≠ "GitHub pe committed hai."_ CI ne ye farak pakda.

### Bug 2 — Dockerfile ne README copy hi nahi ki (docker job fail)

README ab committed thi, par Dockerfile me usko dabbe ke andar copy karne wali line nahi
thi. `.dockerignore` ka `!README.md` sirf itna karta hai ki README **build context me
rahe** — usko dabbe ke **andar copy** karna alag baat hai. Wahi `OSError` phir se, is
baar image build ke andar.

**Fix:** `COPY README.md ./` line daali.
**Lesson:** _"context me hai" ≠ "image ke andar hai."_ Do alag steps.

### Bug 3 — dabbe me git hai hi nahi (docker job, pytest-in-image fail)

Humari `save.py` model save karte waqt `git rev-parse HEAD` chalati hai (commit-hash
metadata me likhne ke liye — ye provenance, dekho [[reproducibility-and-dirty-git]]).
Par `python:3.10-slim` dabbe me **git binary hi nahi hota.** Tests ne `_git_dirty` to
mock kiya tha par `_git_commit` nahi → dabbe ke andar test ne git maanga → crash:

```
FileNotFoundError  (git binary nahi mila)
```

**Fix:** dono save tests me `_git_commit` bhi mock kiya
(`monkeypatch.setattr("mental_health.models.save._git_commit", lambda: "test-commit")`).
**Lesson:** test ko bahar ki cheezon (git, network) pe depend nahi karna chahiye —
warna wo alag environment me toot-ta hai. (Yehi 0.5 wala isolation lesson dobara.)

**Teeno fix ke baad → dono job green (✓).** Socho: teeno bug laptop pe **kabhi nahi
dikhte**, kyunki wo cheezein mere paas pehle se thीं. CI ne unhe pakda. **Isiliye CI ko
hi "proof" banaya, apne laptop ke Docker ko nahi.**

---

## Aaj ka faisla — train host pe kyun, container me kyun nahi

Bug 3 se ek badi baat nikli: **dabbe me git nahi hai.** Aur humne `.git/` ko jaan-boojh
ke `.dockerignore` me daala (image = deployable, dev-repo nahi).

Par `make train` ko model save karte waqt git **chahiye** (commit-hash metadata me
likhna hai — provenance). To agar train dabbe ke andar chale → hamesha crash.

Isiliye split:

- **`train` + `test` → host (tumhara laptop) pe**, `uv` se. Train ko git chahiye, aur
  asli git repo sirf host pe hai. Test fast chahiye + wahi git-mock wala reason.
- **`serve` → dabbe se.** Serve ko sirf trained model **padhna** hai, git nahi chahiye —
  aur yehi wo cheez hai jo actually "ship" hoti hai (CLOSEOUT ki soch: request path real hai).

**Imaandaar trade-off (README me likha):** ajnabi ko ab **dono** chahiye — `uv`
(train/test) aur Docker (serve). Chhupaya nahi.

**Ek caveat:** `make train` **abhi** chalao to `DirtyTreeError` dega, kyunki tree dirty
hai (uncommitted changes) — ye **0.5 ka guard, by design.** Clean tree pe hi chalega
(Phase 1 retrain ke waqt). Isiliye train command ka _shape_ sahi hai par is dirty tree
pe end-to-end verify nahi hua — wo Phase 1 me hoga.

---

## Ek line me pura matlab

> Docker code ko ek standard **dabbe** me band karta hai taaki har jagah same chale;
> Makefile lambe commands ko **chhote naam** deta hai; CI ek **robot** hai jo saaf naye
> computer pe sach-much prove karta hai ki chalega — aur usne 3 chhupe bug pakde. Train
> host pe rehta hai kyunki usko git-provenance chahiye, jo dabbe me hai hi nahi.
