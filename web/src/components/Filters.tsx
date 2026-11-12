import type { Filter } from "../types.ts";

interface Props {
  value: Filter;
  onChange: (f: Filter) => void;
}

const OPTIONS: { f: Filter; label: string }[] = [
  { f: "all", label: "전체" },
  { f: "person", label: "사람" },
  { f: "bicycle", label: "자전거" },
  // labeler 의 conf_threshold 와 같은 기준
  { f: "low", label: "신뢰도 0.7 미만" },
];

export default function Filters({ value, onChange }: Props) {
  return (
    <div className="chips">
      {OPTIONS.map((o) => (
        <button
          key={o.f}
          type="button"
          className="chip"
          aria-pressed={value === o.f}
          onClick={() => onChange(o.f)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
