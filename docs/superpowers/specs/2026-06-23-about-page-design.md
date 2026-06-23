# About Page Design

**Date:** 2026-06-23
**Status:** Approved

---

## Overview

Add a static `/about` page inside the authenticated app shell. The page serves two purposes: (1) surface the mission statement for users who signed up without seeing the landing page, and (2) explain each document collection so users understand what they're searching before they start.

Accessible via a new sidebar button positioned between "Saved Passages" and "Settings".

---

## Route & Files

| Action | Path |
|---|---|
| Create | `apps/web/src/app/about/page.tsx` |
| Create | `apps/web/src/components/about/AboutPage.tsx` |
| Modify | `apps/web/src/components/layout/Sidebar.tsx` |

---

## Sidebar Button

- Location: between "Saved Passages" (`/bookmarks`) and "Settings" (`/settings`) in the bottom nav
- Icon: `Info` from `lucide-react` (size 12, matching existing nav icons)
- Label: `About`
- Active state: `text-brand-accent` when `pathname === "/about"` (same pattern as existing links)
- Inactive/hover state: `text-brand-muted hover:text-brand-primary` (identical to other nav links)

---

## Page Structure

Outer shell matches SourcesPage exactly:
- Wrapped in `AppShell` + `ErrorBoundary` at the route level
- `div.flex.flex-col.h-full.overflow-y-auto` → `div.px-6.py-6.max-w-3xl.w-full.mx-auto`

### Section 1 — Header

```
h1: "About"                          (text-2xl font-semibold text-brand-primary)
p:  "What Body of Christ is and what's in the corpus."   (text-brand-muted text-sm mb-6)
```

### Section 2 — Our Mission

Labeled subsection headed `"Our Mission"` using a small uppercase tracking label (same style as the "Recent" label in the sidebar: `text-brand-muted text-[10px] uppercase tracking-widest`), followed by a top border divider.

Content: the two mission statement paragraphs verbatim from `apps/web/src/app/page.tsx`:

> At the Body of Christ, we believe that while AI and LLMs are incredibly useful tools, fields centered around truth, meaning, morality, theology, and the human condition are better served to be studied through the wisdom of real people. The goal of this project is to make the accumulated knowledge of the Church more accessible to everyone.

> For over two thousand years, Christians have wrestled with questions surrounding suffering, virtue, justice, grace, salvation, human nature, and God Himself. Those conversations have occurred over Scripture, catechisms, encyclicals, writings of the early church fathers, the lives of the saints, and more. The Body of Christ brings their wisdom together into one place, allowing you to explore the Catholic tradition through the people who built, defended, and passed down the fullness of the faith.

Typography: `text-brand-primary text-sm leading-relaxed space-y-4`

### Section 3 — Collections

One card per collection, ordered exactly as `COLLECTIONS` array in `apps/web/src/lib/collections.ts`. Each card:

- Colored pill badge (same `text-xs font-semibold px-2.5 py-0.5 rounded-full border` style as SourcesPage, using `meta.color` for color and border)
- Collection name as heading (`text-brand-primary text-sm font-medium`)
- Short paragraph (`text-brand-muted text-xs leading-relaxed mt-1`)

Card container: `rounded bg-brand-surface px-3 py-3` — no hover state (static, not clickable).

#### Collection Descriptions

**Bible**
The Sacred Scriptures of the Catholic Church, comprising 73 books of the Old and New Testaments. Composed by many human authors over roughly 1,500 years under divine inspiration, as understood by the Church. The Bible is the foundation of Christian faith and the starting point for virtually every theological question — anyone exploring Catholic teaching, prayer, or doctrine will find Scripture woven throughout.

**Catechism**
The Catechism of the Catholic Church (CCC), promulgated by Pope John Paul II in 1992. A comprehensive, authoritative summary of Catholic belief and practice, organized into four pillars: the Creed, the Sacraments, the Commandments, and Prayer. Written for anyone who wants to understand what the Church actually teaches — whether a new Catholic, a lifelong believer, or a curious outsider.

**Summa Theologica**
The masterwork of St. Thomas Aquinas, written between 1265 and 1274. A systematic theological and philosophical synthesis of Christian doctrine, structured as a series of questions, objections, and reasoned replies. Aquinas draws on Scripture, the Church Fathers, and Aristotelian philosophy to address everything from the existence of God to the nature of virtue. Invaluable for anyone interested in the intellectual tradition of the Church, moral theology, or classical philosophy.

**Encyclicals**
Formal letters issued by popes to the universal Church, addressing matters of doctrine, morality, and social teaching. Encyclicals carry significant teaching authority and have shaped Catholic thought on topics ranging from labor rights (Rerum Novarum) to marriage (Humanae Vitae) to the nature of faith (Fides et Ratio). Useful for understanding how Catholic teaching has developed and been applied to the questions of each era.

**Councils**
The proceedings and documents of the ecumenical councils — formal gatherings of the world's bishops that define doctrine and address Church affairs. The corpus includes councils from Nicaea (325 AD) through the Second Vatican Council (1962–1965). Council documents are among the most authoritative sources in Catholic theology, defining core beliefs such as the Trinity, the Incarnation, and the nature of the Church.

**Church Fathers**
Writings of the early Christian theologians and bishops from roughly the 1st through 8th centuries — figures such as Ignatius of Antioch, Justin Martyr, Origen, Athanasius, Augustine, and John Chrysostom. The Fathers interpreted Scripture, defended the faith against heresies, and laid the theological foundations the Church still stands on. Essential for understanding how Christian doctrine developed in its earliest centuries.

**Medieval**
Theological and philosophical works from the medieval period (roughly 9th–15th centuries), including scholastic theologians, mystics, and canonists beyond Aquinas. Figures such as Anselm of Canterbury, Bonaventure, Hildegard of Bingen, and Duns Scotus. A rich tradition of rigorous intellectual inquiry paired with deep spiritual reflection — valuable for those interested in how the Church thought through faith and reason across the Middle Ages.

**Canon Law**
The Code of Canon Law (1983), the body of laws governing the Latin Church. Enacted by Pope John Paul II, it codifies the rights and obligations of the faithful, the structure of Church governance, the sacraments, and ecclesiastical procedures. Useful for understanding how the Church operates as an institution and the legal framework underlying pastoral practice.

**Apostolic Exhortations**
Post-synodal documents in which popes synthesize the work of a bishops' synod and offer pastoral guidance to the Church. Notable examples include Evangelii Gaudium (Francis, 2013) on the joy of the Gospel, and Familiaris Consortio (John Paul II, 1981) on marriage and family. More pastoral in tone than encyclicals, these documents often address how Catholic teaching should be lived in contemporary life.

**Papal Documents**
A broader category of official papal writings — including apostolic constitutions, apostolic letters, motu proprios, and bulls — that don't fall neatly into the categories above. These documents address a wide range of matters: defining dogmas (such as the Immaculate Conception), reforming Church structures, and issuing pastoral directives. Helpful for tracing specific decisions and pronouncements across pontificates.

---

## Component Design

```
AboutPage.tsx (client component)
├── header section (h1 + subhead)
├── MissionSection
│   └── two static paragraphs
└── CollectionsSection
    └── collection cards mapped from COLLECTIONS array
        ├── color badge (from meta.color)
        └── description paragraph (static string map keyed by collection key)
```

The description strings live in a `COLLECTION_DESCRIPTIONS` record inside `AboutPage.tsx` keyed by collection key (e.g., `"bible"`, `"catechism"`, etc.). No API calls. Fully static.

---

## Non-Goals

- No linking from collection cards to the Sources page or search filters
- No animations or expand/collapse on cards
- No internationalization
- Page content is hardcoded — not fetched from CMS or API
