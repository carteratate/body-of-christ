export interface CollectionMeta {
  key: string;
  label: string;
  color: string;
  hex: string;
}

export const COLLECTIONS: CollectionMeta[] = [
  { key: "bible",          label: "Bible",            color: "var(--color-collection-bible)",          hex: "#d4885a" },
  { key: "catechism",      label: "Catechism",        color: "var(--color-collection-catechism)",      hex: "#5b9bd4" },
  { key: "summa",          label: "Summa Theologica", color: "var(--color-collection-summa)",          hex: "#55cc88" },
  { key: "encyclicals",    label: "Encyclicals",      color: "var(--color-collection-encyclicals)",    hex: "#e8c040" },
  { key: "councils",       label: "Councils",         color: "var(--color-collection-councils)",       hex: "#60d4c8" },
  { key: "church-fathers", label: "Church Fathers",   color: "var(--color-collection-church-fathers)", hex: "#b070d4" },
  { key: "medieval",       label: "Medieval",         color: "var(--color-collection-medieval)",       hex: "#90a0a8" },
  { key: "canon-law",               label: "Canon Law",             color: "var(--color-collection-canon-law)",               hex: "#e84040" },
  { key: "apostolic-exhortations", label: "Apostolic Exhortations", color: "var(--color-collection-apostolic-exhortations)", hex: "#c87840" },
  { key: "papal-documents",        label: "Papal Documents",        color: "var(--color-collection-papal-documents)",        hex: "#6070c8" },
];

export const ALL_COLLECTION_KEYS: string[] = COLLECTIONS.map((c) => c.key);

export function getCollectionMeta(key: string): CollectionMeta | undefined {
  return COLLECTIONS.find((c) => c.key === key);
}

export function hexToRgb(hex: string): string {
  if (!hex.startsWith("#") || hex.length < 7) return "196,151,42";
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r},${g},${b}`;
}
