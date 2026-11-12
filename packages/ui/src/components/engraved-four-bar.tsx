import { useId } from "react";

/**
 * Plate figure: a crank-and-rocker four-bar engraved in the manner of *507 Mechanical Movements*,
 * with its coupler missing. The ghost coupler is the proposed part (ectoplasm, the only colour
 * reserved for candidates), the faint curve is the path its coupler point would trace, and the
 * stitched rings mark the two joints the ghost implies but the drawing does not show.
 *
 * Geometry is a real solution, drawn to scale: ground 300, crank 90, coupler 230, rocker 200
 * (Grashof crank-rocker), crank at 64 degrees, coupler point 55% along BC and 80 off it.
 */
export function EngravedFourBar({ className }: { className?: string }) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const hatch = `hatch-${uid}`;
  const cross = `cross-${uid}`;
  const ground = `ground-${uid}`;
  const glow = `glow-${uid}`;
  const arrow = `arrow-${uid}`;

  return (
    <svg viewBox="0 0 640 560" className={className} role="img" aria-labelledby={`title-${uid}`}>
      <title id={`title-${uid}`}>
        Engraving of a crank and rocker linkage with its connecting link missing. A pale ghost of
        the missing link is drawn where the engine would propose it, with the curve it would trace.
      </title>
      <defs>
        <pattern
          id={hatch}
          width="5"
          height="5"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <line
            x1="0"
            y1="0"
            x2="0"
            y2="5"
            stroke="var(--color-bone)"
            strokeWidth="0.8"
            strokeOpacity="0.7"
          />
        </pattern>
        <pattern
          id={cross}
          width="4"
          height="4"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(-30)"
        >
          <path
            d="M0 0V4M0 0H4"
            stroke="var(--color-bone)"
            strokeWidth="0.6"
            strokeOpacity="0.55"
          />
        </pattern>
        <pattern
          id={ground}
          width="7"
          height="7"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(-45)"
        >
          <line x1="0" y1="0" x2="0" y2="7" stroke="var(--color-parchment)" strokeWidth="1" />
        </pattern>
        <filter id={glow} x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="7" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <marker
          id={arrow}
          viewBox="0 0 10 10"
          refX="10"
          refY="5"
          markerWidth="9"
          markerHeight="9"
          orient="auto-start-reverse"
        >
          <path
            d="M0 1.5L10 5L0 8.5"
            fill="none"
            stroke="var(--color-parchment)"
            strokeWidth="1.2"
          />
        </marker>
      </defs>

      {/* Plate border: a heavy rule with a hairline inside, as on an engraved plate. */}
      <rect
        x="6"
        y="6"
        width="628"
        height="548"
        fill="none"
        stroke="var(--color-bone)"
        strokeOpacity="0.55"
        strokeWidth="2"
      />
      <rect
        x="14"
        y="14"
        width="612"
        height="532"
        fill="none"
        stroke="var(--color-bone)"
        strokeOpacity="0.3"
        strokeWidth="0.75"
      />

      {/* Motion path of the coupler point, faint, as the ghost's trail. */}
      <path
        d="M270.1 250.7 L272.3 247.7 L274.4 244.8 L276.4 241.9 L278.4 239.0 L280.2 236.3 L282.0 233.5 L283.6 230.9 L285.1 228.3 L286.5 225.7 L287.8 223.3 L289.0 220.9 L290.0 218.6 L290.8 216.3 L291.6 214.1 L292.2 212.0 L292.6 210.0 L293.0 208.0 L293.1 206.1 L293.2 204.3 L293.1 202.6 L292.9 201.0 L292.5 199.4 L292.0 197.9 L291.4 196.5 L290.6 195.2 L289.7 193.9 L288.7 192.8 L287.6 191.7 L286.4 190.7 L285.1 189.8 L283.6 189.0 L282.1 188.2 L280.5 187.6 L278.8 187.1 L277.0 186.6 L275.1 186.2 L273.1 185.9 L271.1 185.8 L269.0 185.7 L266.9 185.7 L264.7 185.8 L262.4 185.9 L260.1 186.2 L257.8 186.6 L255.4 187.1 L253.0 187.6 L250.5 188.3 L248.1 189.0 L245.6 189.9 L243.1 190.8 L240.5 191.8 L238.0 192.9 L235.5 194.1 L233.0 195.4 L230.4 196.8 L227.9 198.2 L225.4 199.8 L223.0 201.4 L220.5 203.1 L218.0 204.8 L215.6 206.7 L213.2 208.6 L210.9 210.5 L208.6 212.6 L206.3 214.7 L204.0 216.8 L201.8 219.0 L199.6 221.3 L197.5 223.6 L195.4 226.0 L193.4 228.4 L191.4 230.8 L189.5 233.3 L187.6 235.8 L185.8 238.3 L184.0 240.9 L182.3 243.4 L180.7 246.0 L179.1 248.6 L177.5 251.2 L176.0 253.8 L174.6 256.4 L173.2 259.0 L171.8 261.6 L170.6 264.2 L169.3 266.7 L168.2 269.3 L167.0 271.8 L166.0 274.3 L164.9 276.8 L164.0 279.2 L163.1 281.6 L162.2 284.0 L161.4 286.3 L160.6 288.7 L159.9 290.9 L159.2 293.2 L158.6 295.4 L158.1 297.5 L157.6 299.6 L157.1 301.7 L156.7 303.7 L156.3 305.7 L156.0 307.7 L155.8 309.6 L155.6 311.4 L155.5 313.2 L155.4 315.0 L155.3 316.7 L155.4 318.4 L155.4 320.0 L155.6 321.6 L155.7 323.1 L156.0 324.5 L156.3 325.9 L156.6 327.3 L157.0 328.6 L157.5 329.8 L158.0 331.0 L158.6 332.1 L159.2 333.1 L159.9 334.1 L160.7 335.0 L161.5 335.9 L162.3 336.7 L163.2 337.4 L164.2 338.0 L165.2 338.6 L166.2 339.1 L167.3 339.5 L168.5 339.9 L169.7 340.1 L171.0 340.3 L172.3 340.4 L173.6 340.4 L175.0 340.3 L176.5 340.1 L178.0 339.8 L179.5 339.5 L181.1 339.0 L182.7 338.5 L184.4 337.8 L186.1 337.1 L187.8 336.3 L189.6 335.3 L191.4 334.3 L193.3 333.1 L195.2 331.9 L197.2 330.6 L199.1 329.1 L201.2 327.6 L203.2 325.9 L205.3 324.2 L207.4 322.3 L209.6 320.4 L211.8 318.3 L214.0 316.2 L216.3 314.0 L218.6 311.7 L220.9 309.3 L223.3 306.8 L225.7 304.2 L228.1 301.6 L230.6 298.9 L233.0 296.1 L235.5 293.2 L238.0 290.3 L240.5 287.4 L243.1 284.4 L245.6 281.4 L248.1 278.3 L250.7 275.2 L253.2 272.2 L255.7 269.1 L258.2 266.0 L260.7 262.9 L263.1 259.8 L265.5 256.7 L267.8 253.7 Z"
        className="ghost-trail"
        fill="none"
        stroke="var(--color-ectoplasm)"
        strokeWidth="1"
        strokeDasharray="2 5"
        strokeOpacity="0.45"
      />

      {/* Ground pivots with hatched earth, A and D. */}
      {[170, 470].map((x) => (
        <g key={x}>
          <path
            d={`M${x - 22} 438 L${x} 400 L${x + 22} 438 Z`}
            fill="var(--color-lampblack)"
            stroke="var(--color-bone)"
            strokeWidth="1.2"
          />
          <rect x={x - 34} y="438" width="68" height="12" fill={`url(#${ground})`} />
          <line
            x1={x - 34}
            y1="438"
            x2={x + 34}
            y2="438"
            stroke="var(--color-bone)"
            strokeWidth="1.4"
          />
        </g>
      ))}

      {/* Rocker CD, engraved solid: hatched bar. */}
      <g transform="translate(470 400) rotate(-107.03)">
        <rect
          x="-15"
          y="-15"
          width="230"
          height="30"
          rx="15"
          fill={`url(#${hatch})`}
          stroke="var(--color-bone)"
          strokeWidth="1.3"
        />
      </g>
      {/* Crank AB with its boss. */}
      <g transform="translate(170 400) rotate(-64)">
        <rect
          x="-17"
          y="-13"
          width="124"
          height="26"
          rx="13"
          fill={`url(#${cross})`}
          stroke="var(--color-bone)"
          strokeWidth="1.3"
        />
      </g>
      <circle
        cx="170"
        cy="400"
        r="24"
        fill={`url(#${cross})`}
        stroke="var(--color-bone)"
        strokeWidth="1.3"
      />

      {/* The missing coupler: a ghost plate B–C–P in ectoplasm. */}
      <g className="ghost-part" filter={`url(#${glow})`}>
        <path
          d="M209.5 319.1 L411.3 208.8 L282.1 188.2 Z"
          fill="var(--color-ectoplasm)"
          fillOpacity="0.1"
          stroke="var(--color-ectoplasm)"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
        <circle cx="282.1" cy="188.2" r="4" fill="var(--color-ectoplasm)" />
      </g>

      {/* Pivots. Solid rings are observed joints; stitched rings (sutures) are inferred ones. */}
      {(
        [
          [170, 400],
          [470, 400],
        ] as const
      ).map(([x, y]) => (
        <g key={`p${x}`}>
          <circle
            cx={x}
            cy={y}
            r="9"
            fill="var(--color-lampblack)"
            stroke="var(--color-bone)"
            strokeWidth="1.4"
          />
          <circle cx={x} cy={y} r="2.5" fill="var(--color-bone)" />
        </g>
      ))}
      {(
        [
          [209.5, 319.1],
          [411.3, 208.8],
        ] as const
      ).map(([x, y]) => (
        <g key={`s${x}`}>
          <circle
            cx={x}
            cy={y}
            r="9"
            fill="var(--color-lampblack)"
            stroke="var(--color-bone)"
            strokeWidth="1.2"
          />
          <circle
            cx={x}
            cy={y}
            r="14"
            fill="none"
            stroke="var(--color-bone)"
            strokeWidth="1"
            strokeDasharray="3 3.3"
          />
          {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
            <line
              key={a}
              x1={x + 11 * Math.cos((a * Math.PI) / 180)}
              y1={y + 11 * Math.sin((a * Math.PI) / 180)}
              x2={x + 17 * Math.cos((a * Math.PI) / 180)}
              y2={y + 17 * Math.sin((a * Math.PI) / 180)}
              stroke="var(--color-bone)"
              strokeWidth="0.9"
            />
          ))}
        </g>
      ))}

      {/* Crank angle callout. */}
      <path
        d="M232 400 A62 62 0 0 0 197.2 344.3"
        fill="none"
        stroke="var(--color-parchment)"
        strokeWidth="0.9"
        markerEnd={`url(#${arrow})`}
      />
      <text x="240" y="372" className="font-instrument" fontSize="12" fill="var(--color-parchment)">
        θ = 64.0°
      </text>

      {/* Ground dimension with extension lines and engraved arrows. */}
      <line
        x1="170"
        y1="458"
        x2="170"
        y2="496"
        stroke="var(--color-parchment)"
        strokeWidth="0.75"
      />
      <line
        x1="470"
        y1="458"
        x2="470"
        y2="496"
        stroke="var(--color-parchment)"
        strokeWidth="0.75"
      />
      <line
        x1="176"
        y1="488"
        x2="464"
        y2="488"
        stroke="var(--color-parchment)"
        strokeWidth="0.9"
        markerStart={`url(#${arrow})`}
        markerEnd={`url(#${arrow})`}
      />
      <rect x="280" y="478" width="80" height="18" fill="var(--color-lampblack)" />
      <text
        x="320"
        y="491"
        textAnchor="middle"
        className="font-instrument"
        fontSize="12"
        fill="var(--color-parchment)"
      >
        300.0 mm
      </text>

      {/* Specimen tags, tied to their joints with thread. */}
      {(
        [
          ["A", 170, 400, 92, 352],
          ["B", 209.5, 319.1, 120, 268],
          ["C", 411.3, 208.8, 470, 150],
          ["D", 470, 400, 540, 344],
        ] as const
      ).map(([label, jx, jy, tx, ty]) => (
        <g key={label}>
          <path
            d={`M${jx} ${jy} Q${(jx + tx) / 2} ${Math.max(jy, ty) + 18} ${tx + 13} ${ty + 4}`}
            fill="none"
            stroke="var(--color-parchment)"
            strokeWidth="0.7"
            strokeOpacity="0.8"
          />
          <g
            transform={`translate(${tx} ${ty}) rotate(${label === "A" || label === "C" ? -8 : 7})`}
          >
            <path d="M0 6 L8 0 H36 V30 H8 L0 24 Z" fill="var(--color-parchment)" />
            <circle cx="9" cy="15" r="2.4" fill="var(--color-lampblack)" />
            <text
              x="24"
              y="21"
              textAnchor="middle"
              className="font-display"
              fontSize="17"
              fill="var(--color-lampblack)"
            >
              {label}
            </text>
          </g>
        </g>
      ))}

      {/* Plate heading and caption in the period manner. */}
      <text
        x="320"
        y="52"
        textAnchor="middle"
        className="font-display-sc"
        fontSize="15"
        letterSpacing="3"
        fill="var(--color-bone)"
      >
        Fig. 1. Crank and Rocker
      </text>
      <text
        x="320"
        y="526"
        textAnchor="middle"
        className="font-display"
        fontStyle="italic"
        fontSize="14"
        fill="var(--color-parchment)"
      >
        The coupler B C is wanting. Its ghost is proposed from the motion of A B and C D.
      </text>
    </svg>
  );
}
