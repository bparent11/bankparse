// One stable hue per category name, readable in light and dark (used through the .category-chip CSS class).
const PALETTE = [
  "#2f9e5b",
  "#1d9bb0",
  "#3d6fd6",
  "#e0822b",
  "#c2489a",
  "#8a5cd6",
  "#c99a12",
  "#d1495b",
  "#5b8c3a",
  "#6b7f99",
  "#0f8f74",
  "#b5651d",
];

export function categoryColor(name: string): string {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
