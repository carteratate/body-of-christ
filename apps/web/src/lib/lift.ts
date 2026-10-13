// The raised hover shared by clickable cards and rows (Search History, Continue Reading,
// Library rows, document sections): on hover and keyboard focus, a darker surface plus
// shadow-lift's soft shadow and hairline edge. outline-hidden keeps a focus outline in
// forced-colors mode. Use with a bg-brand-surface (or similar) resting background.
export const LIFT =
  "transition-[background-color,box-shadow] duration-200 hover:bg-brand-surface-hover hover:shadow-lift focus-visible:bg-brand-surface-hover focus-visible:shadow-lift focus-visible:outline-hidden";
