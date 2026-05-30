export interface CollectionMeta {
  key: string;
  label: string;
  color: string;
}

export const COLLECTIONS: CollectionMeta[] = [
  { key: "bible",          label: "📖 Bible",         color: "#4caf50" },
  { key: "catechism",      label: "⛪ Catechism",      color: "#4a6fa5" },
  { key: "church-fathers", label: "✝ Church Fathers", color: "#7c6fa5" },
  { key: "encyclicals",    label: "📜 Encyclicals",    color: "#b5892a" },
  { key: "canon-law",      label: "⚖️ Canon Law",      color: "#9e4a4a" },
  { key: "saints",         label: "👼 Saints",         color: "#4a9a8a" },
];

export const ALL_COLLECTION_KEYS: string[] = COLLECTIONS.map((c) => c.key);

export function getCollectionMeta(key: string): CollectionMeta | undefined {
  return COLLECTIONS.find((c) => c.key === key);
}
