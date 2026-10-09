import type React from 'react';

interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  stroke?: string;
}

/** Hand-rolled SVG polyline sparkline — zero deps. */
export const Sparkline: React.FC<SparklineProps> = ({
  values,
  width = 96,
  height = 24,
  stroke = '#2dd4bf',
}) => {
  if (values.length < 2) {
    return (
      <svg width={width} height={height} className="opacity-40">
        <line
          x1={2}
          y1={height / 2}
          x2={width - 2}
          y2={height / 2}
          stroke="#475569"
          strokeWidth={1.5}
          strokeDasharray="3 3"
        />
      </svg>
    );
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 2;
  const step = (width - pad * 2) / (values.length - 1);
  const points = values
    .map((v, i) => {
      const x = pad + i * step;
      const y = height - pad - ((v - min) / span) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const lastY = (
    height -
    pad -
    ((values[values.length - 1] - min) / span) * (height - pad * 2)
  ).toFixed(1);

  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={width - pad} cy={Number(lastY)} r={2} fill={stroke} />
    </svg>
  );
};
