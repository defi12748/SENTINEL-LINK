/* Project mark: the "satellite" glyph from Tabler Icons (MIT licence,
   public/brand/LICENSE-tabler-icons.txt) on a round badge. */
export function Mark({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" role="img" aria-label="Sentinel Link">
      <circle cx="24" cy="24" r="23" fill="#0b3d91" />
      <ellipse cx="24" cy="25" rx="21" ry="7.5" transform="rotate(-24 24 25)" fill="none" stroke="#f64137" strokeWidth="2.4" />
      <g transform="translate(9.6 9.6) scale(1.2)" fill="none" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3.707 6.293l2.586 -2.586a1 1 0 0 1 1.414 0l5.586 5.586a1 1 0 0 1 0 1.414l-2.586 2.586a1 1 0 0 1 -1.414 0l-5.586 -5.586a1 1 0 0 1 0 -1.414z" />
        <path d="M6 10l-3 3l3 3l3 -3" />
        <path d="M10 6l3 -3l3 3l-3 3" />
        <path d="M12 12l1.5 1.5" />
        <path d="M14.5 17a2.5 2.5 0 0 0 2.5 -2.5" />
        <path d="M15 21a6 6 0 0 0 6 -6" />
      </g>
    </svg>
  );
}
